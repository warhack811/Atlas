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
from Atlas.config import MODEL_GOVERNANCE
from Atlas.tools.registry import ToolRegistry
from Atlas.schemas import OrchestrationPlan, TaskSpec

logger = logging.getLogger(__name__)

class DAGExecutor:
    """Görev akış diyagramını yürüten ana sınıf."""
    def __init__(self):
        self.tool_registry = ToolRegistry()
        # Kullanılabilir araçları (tools) tanımlardan yükle
        base_dir = os.path.dirname(os.path.abspath(__file__))
        definitions_path = os.path.join(base_dir, "tools", "definitions")
        self.tool_registry.load_tools(definitions_path)

    async def execute_plan(self, plan: Union[OrchestrationPlan, Dict[str, Any]], session_id: str, original_message: str, request_context=None) -> List[Dict[str, Any]]:
        """Geriye dönük uyumluluk için: Tüm sonuçları liste olarak döner."""
        results = []
        async for event in self.execute_plan_stream(plan, session_id, original_message, request_context=request_context):
            if event["type"] == "task_result":
                results.append(event["result"])
        return results

    async def execute_plan_stream(self, plan: Union[OrchestrationPlan, Dict[str, Any]], session_id: str, original_message: str, request_context=None):
        """Görev akışını yürütür ve her adımda thought/result olaylarını yield eder."""
        if isinstance(plan, dict):
            plan = OrchestrationPlan(**plan)

        normalized_tasks = []
        if hasattr(plan, 'tasks'):
            for t in plan.tasks:
                if isinstance(t, dict):
                    normalized_tasks.append(TaskSpec(**t))
                else:
                    normalized_tasks.append(t)
            plan.tasks = normalized_tasks

        try:
            executed_tasks = {} 
            remaining_tasks = list(plan.tasks)
            
            while remaining_tasks:
                ready_tasks = [
                    t for t in remaining_tasks 
                    if not t.dependencies or all(dep in executed_tasks for dep in t.dependencies)
                ]
                
                if not ready_tasks:
                    break
                
                layer_coroutines = []
                for task_spec in ready_tasks:
                    layer_coroutines.append(self._execute_single_task(task_spec, plan, executed_tasks, session_id, original_message, request_context=request_context))
                
                layer_results = await asyncio.gather(*layer_coroutines)
                
                for res in layer_results:
                    task_id = res["task_id"]
                    
                    # Eğer sonuç bir dict ise ve içinde 'thought' varsa ayıkla
                    thought = None
                    if res.get("thought"): # Generation'dan gelen
                        thought = res["thought"]
                    elif isinstance(res.get("output"), dict) and "thought" in res["output"]: # Tool'dan gelen
                        thought = res["output"]["thought"]
                        # Output'u sadeleştir (sadece gerçek sonucu kalsın)
                        res["output"] = res["output"]["output"]
                    
                    executed_tasks[task_id] = res
                    
                    if thought:
                        yield {"type": "thought", "thought": thought, "task_id": task_id}
                    
                    yield {"type": "task_result", "result": res}
                
                ready_ids = {getattr(t, 'id', None) or t.get('id') for t in ready_tasks if isinstance(t, dict) or hasattr(t, 'id')}
                remaining_tasks = [t for t in remaining_tasks if (getattr(t, 'id', None) or t.get('id')) not in ready_ids]

        except Exception as e:
            logger.error(f"DAG Stream Hatası: {e}")
            raise e

    async def _execute_single_task(self, task: TaskSpec, plan: OrchestrationPlan, executed_tasks: Dict, session_id: str, original_message: str, request_context=None) -> Dict:
        """Bir görevi tipine göre çalıştırır."""
        
        task_id = task.id
        import time
        start_t = time.time()
        
        if task.type == "tool":
            res = await self._execute_tool(task)
        elif task.type == "generation" or task.type == "context_clarification":
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
                intent=plan.active_intent,
                signal_only=True,
                request_context=request_context
            )
        elif task.type == "memory_control":
            res = await self._execute_memory_control(task, session_id, request_context=request_context)
        else:
            res = {"task_id": task_id, "error": f"Bilinmeyen görev tipi: {task.type}"}
            
        res["duration_ms"] = int((time.time() - start_t) * 1000)
        return res

    async def _execute_memory_control(self, task: TaskSpec, session_id: str, request_context=None) -> Dict:
        """Hafıza kontrol işlemlerini (silme, unutma) yürütür."""
        from Atlas.memory.neo4j_manager import neo4j_manager
        
        # V4.3 Identity Lock: user_id önceliği
        uid = session_id
        if request_context and hasattr(request_context, "user_id") and request_context.user_id:
            uid = request_context.user_id
        elif isinstance(request_context, dict) and request_context.get("user_id"):
            uid = request_context["user_id"]
            
        action = task.params.get("action")
        try:
            if action == "forget_all":
                success = await neo4j_manager.delete_all_memory(uid)
                output = "Tüm hafıza başarıyla temizlendi." if success else "Hafıza temizleme başarısız oldu."
            elif action == "forget_entity":
                entity = task.params.get("entity", "")
                # hard_delete parametresi (Opsiyonel: Eğer kullanıcı açıkça "tamamen sil" dediyse)
                is_hard = task.params.get("hard_delete", False)
                await neo4j_manager.forget_fact(uid, entity, hard_delete=is_hard)
                output = f"'{entity}' bilgisi hafızamdan {'silindi' if is_hard else 'arşivlendi'}."
            else:
                output = f"Bilinmeyen hafıza aksiyonu: {action}"
            
            return {
                "task_id": task.id,
                "type": "memory_control",
                "output": output,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Hafıza kontrol hatası: {e}")
            return {"task_id": task.id, "error": str(e), "status": "failed"}

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

    async def _run_generation(self, task_id: str, role_key: str, prompt: str, instruction: str, session_id: str, intent: str = "general", signal_only: bool = False, request_context=None) -> Dict:
        """Özel bir uzman model (expert) çağrısı yapar ve hata durumunda yedeklere geçer."""
        from Atlas.generator import generate_response, GeneratorResult
        from Atlas.key_manager import KeyManager
        full_message = f"{instruction}\n\nVeri/Mesaj: {prompt}" if instruction else prompt
        
        models = MODEL_GOVERNANCE.get(role_key, MODEL_GOVERNANCE["logic"])
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
                        signal_only=signal_only,
                        request_context=request_context
                    )
                    
                    if isinstance(result, GeneratorResult):
                        if result.ok:
                            # Thought ayıkla (Örn: <thought>...</thought> formatını arar)
                            import re
                            raw_text = result.text
                            thought_match = re.search(r"<thought>(.*?)</thought>", raw_text, re.DOTALL | re.IGNORECASE)
                            clean_text = re.sub(r"<thought>.*?</thought>", "", raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
                            
                            return {
                                "task_id": task_id,
                                "type": "generation",
                                "output": clean_text,
                                "thought": thought_match.group(1).strip() if thought_match else None,
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