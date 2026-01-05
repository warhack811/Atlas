"""
ATLAS Yönlendirici - DAG Yürütücü (DAG Executor)
-----------------------------------------------
Bu bileşen, orkestratör tarafından oluşturulan iş planını (DAG) analiz eder
ve görevleri bağımlılık sırasına göre paralel veya ardışık olarak çalıştırır.

Temel Sorumluluklar:
1. Bağımlılık Yönetimi: Görevlerin birbirine olan bağımlılıklarını (dependencies) çözer.
2. Paralel Yürütme: Bağımsız görevleri (`asyncio.gather`) ile aynı anda çalıştırır.
3. Araç Entegrasyonu: ToolRegistry üzerinden harici araçları (Arama, Görsel Üretme vb.) tetikler.
4. Veri Enjeksiyonu: Bir görevin çıktısını, başka bir görevin girdisine (`{t1.output}`) enjekte eder.
5. Hata Toleransı: Görev bazlı hata yönetimi ve yedek modellerle (fallback) dayanıklılık sağlar.
"""

import asyncio
import os
import sys
import traceback
import logging
from typing import List, Dict, Any, Optional, Union
from .config import MODEL_GOVERNANCE
from .tools.registry import ToolRegistry
from .schemas import OrchestrationPlan, TaskSpec

logger = logging.getLogger(__name__)

class DAGExecutor:
    """Görev akış diyagramını yürüten ana sınıf."""
    def __init__(self):
        self.tool_registry = ToolRegistry()
        # Kullanılabilir araçları (tools) tanımlardan yükle
        base_dir = os.path.dirname(os.path.abspath(__file__))
        definitions_path = os.path.join(base_dir, "tools", "definitions")
        self.tool_registry.load_tools(definitions_path)

    async def execute_plan(self, plan: Union[OrchestrationPlan, Dict[str, Any]], session_id: str, original_message: str) -> List[Dict[str, Any]]:
        """Gelen planı (plan/dict) analiz eder ve tüm görevleri tamamlar."""
        # 1. Veri Yapısı Uyumluluğu: Dict gelirse model objesine çevirir
        if isinstance(plan, dict):
            plan = OrchestrationPlan(**plan)

        # 2. Görev Normalizasyonu: Tüm görevlerin TaskSpec yapısında olduğundan emin olur
        normalized_tasks = []
        if hasattr(plan, 'tasks'):
            for t in plan.tasks:
                if isinstance(t, dict):
                    normalized_tasks.append(TaskSpec(**t))
                else:
                    normalized_tasks.append(t)
            plan.tasks = normalized_tasks

        try:
            executed_tasks = {} # Tamamlanan görev haritası: task_id -> sonuç
            all_results = []
            
            # Görevleri kopyala
            remaining_tasks = list(plan.tasks)
            
            while remaining_tasks:
                # O anda çalıştırılmaya hazır olan (bağımlılığı olmayan veya çözülen) görevleri belirle
                ready_tasks = [
                    t for t in remaining_tasks 
                    if not t.dependencies or all(dep in executed_tasks for dep in t.dependencies)
                ]
                
                if not ready_tasks:
                    logger.error(f"Döngüsel bağımlılık veya çözülemeyen görev: {[t.id for t in remaining_tasks]}")
                    break
                
                layer_coroutines = []
                import time
                for task_spec in ready_tasks:
                    layer_coroutines.append(self._execute_single_task(task_spec, plan, executed_tasks, session_id, original_message))
                
                layer_results = await asyncio.gather(*layer_coroutines)
                
                # Sonuçları kaydet
                for res in layer_results:
                    executed_tasks[res["task_id"]] = res
                    all_results.append(res)
                
                # Tamamlanan görevleri listeden güvenli bir şekilde çıkar
                ready_ids = set()
                for t in ready_tasks:
                    tid = getattr(t, 'id', None) or (t.get('id') if isinstance(t, dict) else None)
                    if tid: ready_ids.add(tid)
                
                remaining_tasks = [t for t in remaining_tasks if (getattr(t, 'id', None) or (t.get('id') if isinstance(t, dict) else None)) not in ready_ids]

            return all_results

        except Exception as e:
            logger.error(f"DAG Yürütücü başarısız oldu: {e}")
            traceback.print_exc()
            raise e

    async def _execute_single_task(self, task: TaskSpec, plan: OrchestrationPlan, executed_tasks: Dict, session_id: str, original_message: str) -> Dict:
        """Bir görevi tipine göre çalıştırır."""
        
        task_id = task.id
        import time
        start_t = time.time()
        
        if task.type == "tool":
            res = await self._execute_tool(task)
        elif task.type == "generation":
            # Prompt enjeksiyonu yap
            processed_prompt = self._inject_dependencies(task.prompt or "", executed_tasks)
            
            # Eğer prompt boşsa (ve dependency yoksa) ana mesajı kullan
            if not processed_prompt:
                processed_prompt = task.instruction if task.instruction else original_message

            model_id = self._map_specialist_to_model(task.specialist or "logic")
            res = await self._run_generation(
                task_id=task_id,
                role_key=model_id,
                prompt=processed_prompt,
                instruction=task.instruction or "",
                session_id=session_id,
                intent=plan.active_intent, # OrchestrationPlan'dan gelen alan adı active_intent
                signal_only=True # Specialistler için bağlamı sadeleştiriyoruz
            )
        else:
            res = {"task_id": task_id, "error": f"Bilinmeyen görev tipi: {task.type}"}
            
        res["duration_ms"] = int((time.time() - start_t) * 1000)
        return res

    async def _execute_tool(self, task: TaskSpec) -> Dict:
        """Registry üzerinden bir aracı (tool) çalıştırır."""
        tool = self.tool_registry.get_tool(task.tool_name)
        if not tool:
            return {"task_id": task.id, "error": f"Tool bulunamadı: {task.tool_name}", "output": None, "status": "failed"}

        try:
            params = task.params or {}
            result = await tool.execute(**params)
            return {
                "task_id": task.id,
                "type": "tool",
                "tool_name": task.tool_name,
                "output": result,
                "status": "success"
            }
        except Exception as e:
            return {
                "task_id": task.id,
                "type": "tool",
                "tool_name": task.tool_name,
                "error": str(e),
                "output": None,
                "status": "başarısız"
            }

    def _inject_dependencies(self, prompt: str, executed_tasks: Dict) -> str:
        """Prompt içindeki {tX.output} ifadelerini gerçek görev sonuçlarıyla değiştirir."""
        import re
        pattern = r"\{(t\d+)\.output\}"
        def replace_match(match):
            task_id = match.group(1)
            if task_id in executed_tasks:
                res = executed_tasks[task_id]
                if res.get("status") == "failed":
                    return f"[Hata: {task_id} verisi alınamadı]"
                return str(res.get("output", ""))
            return match.group(0)
        return re.sub(pattern, replace_match, prompt)

    async def _run_generation(self, task_id: str, role_key: str, prompt: str, instruction: str, session_id: str, intent: str = "general", signal_only: bool = False) -> Dict:
        """Özel bir uzman model (expert) çağrısı yapar ve hata durumunda yedeklere geçer."""
        from .generator import generate_response, GeneratorResult
        full_message = f"{instruction}\n\nVeri/Mesaj: {prompt}" if instruction else prompt
        
        models = MODEL_GOVERNANCE.get(role_key, MODEL_GOVERNANCE["logic"])
        
        from .key_manager import KeyManager
        total_keys = KeyManager.get_total_key_count() or 4
        
        last_error = None
        for model_id in models:
            # Üst Düzey Hata Yönetimi: Her model için tüm anahtarları (Key Rotation) dener
            for attempt in range(total_keys):
                try:
                    result = await generate_response(
                        message=full_message,
                        model_id=model_id,
                        intent=intent,
                        session_id=session_id,
                        signal_only=signal_only
                    )
                    
                    if isinstance(result, GeneratorResult):
                        if result.ok:
                            return {
                                "task_id": task_id,
                                "type": "generation",
                                "output": result.text,
                                "model": model_id,
                                "prompt": full_message,
                                "status": "success"
                            }
                        
                        # Handle specific error cases
                        if result.error_code == "CAPACITY":
                            # Model based error (503) -> Skip this model and try next model
                            last_error = f"Model {model_id} over capacity."
                            break 
                            
                        if not result.retryable:
                            # Kalıcı hata (örn: geçersiz prompt) -> Bu modeli atla
                            last_error = result.text
                            break
                        
                        # If retryable (429 or Quota), loop will try next key
                        last_error = result.text
                        continue
                    else:
                        # Fallback for non-structured result
                        return {
                            "task_id": task_id,
                            "type": "generation",
                            "output": str(result),
                            "model": model_id,
                            "status": "success"
                        }
                except Exception as e:
                    last_error = e
                    continue
        
        return {
            "task_id": task_id,
            "type": "generation",
            "output": f"Nesil Hatası: {str(last_error)}",
            "error": True,
            "status": "başarısız"
        }

    def _map_specialist_to_model(self, specialist: str) -> str:
        valid_roles = ["coding", "tr_creative", "logic", "search", "chat"]
        return specialist if specialist in valid_roles else "logic"

dag_executor = DAGExecutor()