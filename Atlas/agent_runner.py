"""
ATLAS Agent Runner - ReAct Döngü Yöneticisi (The Loop)
------------------------------------------------------
Bu bileşen, Atlas'ın "Tek Atımlık" (One-Shot) çalışma mantığını
"Döngüsel" (Iterative) bir yapıya dönüştürür.

Mantık:
1. Düşün (Think): LLM'e mevcut durumu sor.
2. Hareket Et (Act): LLM bir araç çağırmak isterse (Tool Call) onu çalıştır.
3. Gözlemle (Observe): Aracın çıktısını al ve LLM'e geri besle.
4. Tekrarla (Loop): Cevap hazır olana kadar 1. adıma dön.

Bu yapı, Atlas'ın hata yaptığında düzeltebilmesini ve eksik bilgiyi
arayarak bulabilmesini sağlar.
"""

import asyncio
import logging
import json
from typing import List, Dict, Any, AsyncGenerator
from datetime import datetime

from Atlas.orchestrator import orchestrator
from Atlas.dag_executor import dag_executor
from Atlas.schemas import OrchestrationPlan, TaskSpec

logger = logging.getLogger(__name__)

class AgentRunner:
    """ReAct (Reason+Act) döngüsünü yöneten sınıf."""

    MAX_STEPS = 5  # Sonsuz döngü koruması

    async def run_loop(
        self,
        session_id: str,
        user_message: str,
        user_id: str,
        context_builder: Any = None,
        request_context: Any = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Ana ajan döngüsü.

        Yields:
            Dict: {type: 'thought'|'tool_call'|'tool_result'|'final_answer', ...}
        """

        # Hafıza (Short-term memory for the loop)
        loop_history: List[Dict[str, Any]] = []

        step_count = 0
        final_answer = None

        while step_count < self.MAX_STEPS:
            step_count += 1
            logger.info(f"[AgentRunner] Adım {step_count}/{self.MAX_STEPS} başladı.")

            # 1. PLANLAMA (THINK)
            # Orchestrator'a mevcut geçmişi ve loop geçmişini gönder
            # Not: orchestrator.plan metodunu loop_history destekleyecek şekilde güncelleyeceğiz.
            # Şimdilik standart plan metodunu kullanıyoruz ama context'e loop bilgisini enjekte edebiliriz.

            # Loop geçmişini metne dök
            loop_context = ""
            if loop_history:
                loop_context = "\n[ŞU ANA KADAR YAPILANLAR (LOOP HISTORY)]:\n"
                for item in loop_history:
                    if item["type"] == "tool_result":
                        loop_context += f"- Araç ({item['tool']}) Çıktısı: {str(item['output'])[:500]}\n"

            # ContextBuilder'a loop bilgisini ekle (Hacky injection for now)
            if context_builder:
                # Mevcut system prompt'a ekleme yap
                if hasattr(context_builder, "_system_prompt") and context_builder._system_prompt:
                    if "[ŞU ANA KADAR" not in context_builder._system_prompt:
                        context_builder._system_prompt += loop_context

            # Planlama yap
            plan = await orchestrator.plan(
                session_id,
                user_message,
                user_id=user_id,
                context_builder=context_builder
            )

            # Düşünceyi yayınla
            thought_content = plan.user_thought or plan.reasoning or "Bir sonraki adımı planlıyorum..."
            yield {
                "type": "thought",
                "step": {"title": f"Adım {step_count}: Analiz", "content": thought_content}
            }

            # 2. HAREKET (ACT)
            # Plan içindeki görevleri incele
            # Eğer sadece "generation" varsa ve tool yoksa -> DÖNGÜ BİTTİ (Cevap hazır)
            tool_tasks = [t for t in plan.tasks if t.type == "tool"]
            generation_tasks = [t for t in plan.tasks if t.type == "generation"]

            if not tool_tasks:
                # Sadece cevap üretme görevi kaldıysa, bu final cevaptır.
                # Generation görevini çalıştırıp bitireceğiz.
                # Ancak generation görevi de bir 'Task' olduğu için DAG executor ile çalıştırıp sonucu almalıyız.

                # DAG Executor'ı tek seferlik çalıştır
                # (Akış olmadığı için stream yerine execute_plan kullanılabilir ama stream yapısı tutarlı olsun)
                final_results = []
                async for event in dag_executor.execute_plan_stream(plan, session_id, user_message, request_context=request_context):
                    if event["type"] == "task_result":
                        final_results.append(event["result"])
                    yield event # thought/result eventlerini yukarıya (API) ilet

                # Sonuçları döndür (API'deki synthesizer için)
                # Loop bitti sinyali
                yield {"type": "loop_done", "results": final_results, "plan": plan}
                return

            # Tool varsa çalıştır
            # Not: ReAct genelde "tek adımda tek tool" veya "paralel tool" mantığıyla çalışır.
            # Atlas DAG Executor zaten paralelliği yönetiyor.

            results = []
            async for event in dag_executor.execute_plan_stream(plan, session_id, user_message, request_context=request_context):
                yield event # UI için eventleri ilet
                if event["type"] == "task_result":
                    res = event["result"]
                    results.append(res)
                    # Loop hafızasına kaydet
                    if res.get("type") == "tool":
                        loop_history.append({
                            "type": "tool_result",
                            "tool": res.get("tool_name"),
                            "output": res.get("output") or res.get("error")
                        })

            # Eğer tool çalıştıysa, döngü devam etmeli (Observe -> Think again)
            # Context Builder'ı güncellemek gerekebilir (yukarıdaki hacky injection yerine)
            # Şimdilik loop başında context injection ile hallediyoruz.

            # Bir sonraki adım için bekleme (opsiyonel rate limit)
            await asyncio.sleep(0.1)

        # Döngü limiti aşıldı
        logger.warning(f"[AgentRunner] Maksimum adım sayısına ({self.MAX_STEPS}) ulaşıldı. Döngü kırılıyor.")
        yield {
            "type": "error",
            "content": "İşlem çok karmaşık olduğu için maksimum adım sayısına ulaşıldı. Eldeki bilgilerle cevap veriliyor."
        }
        # Eldeki son sonuçlarla bitir
        yield {"type": "loop_done", "results": [], "plan": plan} # Boş result, synthesizer muhtemelen hata veya özür üretecek

agent_runner = AgentRunner()
