"""
ATLAS Yönlendirici - Akıllı Orkestratör (Orchestrator v2)
-------------------------------------------------------
Bu bileşen, sistemin "Beyni" olarak görev yapar. Kullanıcının niyetini anlar,
gerekiyorsa sorguyu yeniden yazar (query rewriting) ve karmaşık talepleri 
yürütülebilir alt görevlere (DAG) böler.

Temel Sorumluluklar:
1. Niyet Yönetimi: Kullanıcı mesajından niyet (intent) çıkarımı ve kalıtımı.
2. Sorgu İyileştirme: Anlaşılmayan veya bağlam gerektiren sorguların netleştirilmesi.
3. Görev Dağıtımı: Talebi uzman modellere (expert models) veya araçlara (tools) yönlendirme.
4. Bağlam Birleştirme: Hafıza (Neo4j), Kullanıcı Bilgileri ve Zaman bağlamını tek potada eritme.
5. Dayanıklılık (Resilience): Model hatalarında veya kota sınırlarında otomatik yedek modele geçiş.
"""

import logging
import json
import time
import os
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import httpx

from Atlas.config import API_CONFIG, MODEL_GOVERNANCE
from Atlas.memory import MessageBuffer
from Atlas.memory.state import state_manager
from Atlas.time_context import time_context
from Atlas.memory.neo4j_manager import neo4j_manager

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationPlan:
    """Orkestratör tarafından oluşturulan yürütme planı veri yapısı."""
    tasks: List[Dict[str, Any]]        # Yürütülecek alt görevlerin listesi
    active_intent: str                 # Belirlenen ana niyet (coding, creative vb.)
    is_follow_up: bool                 # Mevcut mesaj bir devam sorusu mu?
    context_focus: str                 # Yanıt için odaklanılması gereken bağlam alanı
    rewritten_query: Optional[str] = None # İyileştirilmiş/Yeniden yazılmış kullanıcı sorgusu
    resilience_data: Dict[str, Any] = field(default_factory=dict) # Hata yönetim verileri
    orchestrator_prompt: str = ""      # Karar verilirken kullanılan tam prompt
    orchestrator_model: str = ""       # Karar veren modelin ID'si
    reasoning: str = ""                # Teknik karar mantığı (COT)
    user_thought: str = ""             # Kullanıcıya yönelik iş özeti
    detected_topic: str = "SAME"       # Algılanan konuşma konusu

from Atlas.prompts import ORCHESTRATOR_PROMPT

class Orchestrator:
    """Niyet analizi ve görev planlamasından sorumlu sınıf."""
    @staticmethod
    async def plan(session_id: str, message: str, user_id: str = "admin", use_mock: bool = False, context_builder: Any = None) -> OrchestrationPlan:
        """Kullanıcı mesajına göre bir yürütme planı (DAG) hazırlar."""
        if use_mock:
            return OrchestrationPlan(
                tasks=[{"id": "t1", "type": "generation", "specialist": "logic", "instruction": "cevap ver"}],
                active_intent="general",
                is_follow_up=False,
                context_focus=""
            )

        # 1. Araç Bilgisi: Tool Registry'den mevcut araçları çek
        from Atlas.tools.registry import ToolRegistry
        registry = ToolRegistry()
        # tools_info = registry.list_tools() # İleride dinamik prompt için kullanılabilir

        # 2. Konuşma Geçmişi (History): Son 10 mesajı tampondan çeker
        history = MessageBuffer.get_llm_messages(session_id, limit=10)
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        
        # 3. Durum Bilgisi: Kullanıcının aktif alanı getirilir
        state = state_manager.get_state(session_id)
        
        # FAZ-α Final: State Hydration (Optimized)
        # Sadece konu 'Genel' ise VE daha önce kontrol edilmemişse DB'ye sor.
        if state.current_topic == "Genel" and not state._hydrated:
            try:
                saved_topic = await neo4j_manager.get_session_topic(session_id)
                if saved_topic:
                    state.current_topic = saved_topic
                    logger.info(f"[STATE HYDRATION]: Konu '{saved_topic}' olarak geri yüklendi.")
            except Exception as e:
                logger.error(f"[STATE HYDRATION ERROR]: {e}")
            finally:
                # Başarılı veya başarısız, bir daha sorma (Session boyunca RAM geçerli)
                state._hydrated = True
        
        # FAZ-γ: Identity Cache is now handled by build_chat_context_v1 for sync reliability
        # But we still log its state for debugging consistency
        logger.info(f"[ORCHESTRATOR] Identity cache state: {'Hydrated' if state._identity_hydrated else 'Pending'} ({len(state._identity_cache)} facts)")
        
        time_info = time_context.get_system_prompt_addition(message)
        full_context = time_info
        
        if context_builder and hasattr(context_builder, "_neo4j_context") and context_builder._neo4j_context:
            full_context += "\n\n[GRAFİK BELLEK BAĞLAMI]\n" + context_builder._neo4j_context
        
        logger.debug(f"[HATA AYIKLAMA] Orkestratör Geçmişi: {len(history)} mesaj. Aktif Alan: {state.active_domain}")

        # 4. Beyin (LLM) Çağrısı: Mevcut bilgilerle en uygun planı oluşturması için modele danışılır
        plan_data, used_prompt, used_model = await Orchestrator._call_brain(message, history_text, full_context)
        
        logger.debug(f"[HATA AYIKLAMA] Orkestratör Plan Verisi: {json.dumps(plan_data, ensure_ascii=False)}")
        
        # 4. Plan İşleme ve Niyet Kalıtımı (Intent Inheritance)
        if plan_data.get("is_follow_up") and plan_data.get("intent") == "general":
            plan_data["intent"] = state.active_domain
            
        # FAZ-Y.5: Active Conflict Management
        conflicts = []
        if "status: CONFLICTED" in full_context:
            import re
            # Çelişkili tripletleri bul (Basit regex ile context içinden ayıkla)
            conflict_matches = re.findall(r'(\[GRAF \| Skor:.*?status: CONFLICTED\])', full_context)
            if conflict_matches:
                conflicts = conflict_matches
                conflict_note = "\n\n[DİKKAT]: Hafızada çelişkili (CONFLICTED) bilgiler tespit edildi. Kullanıcıya nazikçe bu durumu sorup netleştir."
                if "user_thought" in plan_data:
                    plan_data["user_thought"] += " (Not: Hafızandaki bir çelişkiyi de netleştireceğim.)"
                
                for task in plan_data.get("tasks", []):
                    if task.get("type") == "generation":
                        task["instruction"] = task.get("instruction", "") + conflict_note

        # Mevcut niyet durumunu güncelle (User State Persistence)
        state.update_domain(plan_data["intent"], 0.9)
        
        # Konu Takibi Güncellemesi
        detected_topic = plan_data.get("detected_topic", "SAME")
        old_topic = state.current_topic
        state.update_topic(detected_topic)
        
        # Eğer konu değiştiyse Neo4j'ye asenkron (fire-and-forget) yaz
        if state.current_topic != old_topic:
            # DÜZELTME: user_id'yi context_builder'dan veya history'den alabiliriz. 
            # Genelde RDR veya context için session_id yeterli ama Neo4j user_id ister.
            # Şimdilik context_builder objesinin user_id'si varsa kullanalım.
            user_id = getattr(context_builder, "user_id", "anonymous")
            asyncio.create_task(neo4j_manager.update_session_topic(user_id, session_id, state.current_topic))
            logger.info(f"[KONU DEĞİŞTİ]: {old_topic} -> {state.current_topic}")
        
        return OrchestrationPlan(
            tasks=plan_data.get("tasks", []),
            active_intent=plan_data.get("intent", "general"),
            is_follow_up=plan_data.get("is_follow_up", False),
            context_focus=plan_data.get("context_focus", ""),
            rewritten_query=plan_data.get("rewritten_query"),
            resilience_data=plan_data.get("_resilience", {}),
            orchestrator_prompt=used_prompt,
            orchestrator_model=used_model,
            reasoning=plan_data.get("reasoning", ""),
            user_thought=plan_data.get("user_thought", ""),
            detected_topic=plan_data.get("detected_topic", "SAME")
        )

    @staticmethod
    async def _call_brain(message: str, history: str, context: str) -> tuple[Dict, str, str]:
        """
        Orkestrasyon kararı için modelli çağrı yapar. 
        Gemini 2.0 Flash birincil tercihtir; başarısızlık durumunda Llama modellerine döner.
        """
        from Atlas.key_manager import KeyManager
        
        models = MODEL_GOVERNANCE.get("orchestrator", [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3-8b-instant"
        ])
        
        prompt = ORCHESTRATOR_PROMPT.format(history=history, message=message, context=context)
        
        attempt_count = 0
        used_models = []
        
        for model in models:
            attempt_count += 1
            used_models.append(model)
            api_key = KeyManager.get_best_key()
            if not api_key:
                break
                
            try:
                logger.debug(f"[HATA AYIKLAMA] Beyin Model Deniyor: {model}")
                
                # --- GEMINI YOLU (Modern Google SDK v1.0) ---
                if "gemini" in model.lower():
                    try:
                        from google import genai
                        from google.genai import types
                        from Atlas.config import get_gemini_api_key
                        
                        gemini_key = get_gemini_api_key()
                        if not gemini_key:
                            logger.error(f"[HATA] {model} için Gemini API Anahtarı eksik")
                            continue

                        client = genai.Client(api_key=gemini_key)
                        
                        # Yeni SDK kullanarak asenkron çağrı (Timeout Korumalı)
                        response = await asyncio.wait_for(
                            client.aio.models.generate_content(
                                model=model,
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    temperature=0.1
                                )
                            ), timeout=15.0
                        )
                        
                        raw_content = response.text
                        data = json.loads(raw_content)
                        logger.info(f"[HATA AYIKLAMA] Beyin Gemini ile Başarılı ({model})")
                        
                        data["_resilience"] = {
                            "attempts": attempt_count,
                            "models": used_models
                        }
                        return data, prompt, model

                    except Exception as ge:
                        logger.error(f"[HATA] Gemini çağrısı başarısız: {ge}")
                        continue 

                # --- GROQ YOLU: Gemini API başarısızsa veya listede Groq modelleri varsa kullanılır ---
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{API_CONFIG['groq_api_base']}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "response_format": {"type": "json_object"}
                        }
                    )
                    
                    if response.status_code == 200:
                        KeyManager.report_success(api_key, model_id=model)
                        raw_content = response.json()["choices"][0]["message"]["content"]
                        try:
                            data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                            logger.info(f"[HATA AYIKLAMA] Beyin {model} ile Başarılı")
                            data["_resilience"] = {
                                "attempts": attempt_count,
                                "models": used_models
                            }
                            return data, prompt, model
                        except Exception as je:
                            logger.error(f"[HATA] {model} için JSON ayrıştırma başarısız: {je}")
                            continue
                    else:
                        KeyManager.report_error(api_key, status_code=response.status_code)
                        logger.error(f"[HATA] Beyin çağrısı {model} için başarısız: HTTP {response.status_code}")
                        continue
            except Exception as e:
                logger.error(f"[HATA] {model} için beyin istisnası: {e}")
                continue
                
        # Tüm modeller başarısız olursa güvenli bir varsayılan plan döner
        return {
            "intent": "general", 
            "is_follow_up": False, 
            "tasks": [{"id": "t1", "type": "generation", "specialist": "logic", "instruction": "Lütfen yardımcı ol."}]
        }, prompt, "fallback-safety"

orchestrator = Orchestrator()
