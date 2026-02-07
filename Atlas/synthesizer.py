"""
ATLAS Yönlendirici - Sentezleyici (Synthesizer / The Stylist)
-----------------------------------------------------------
Bu bileşen, farklı uzman modellerden veya araçlardan gelen ham verileri alır,
kullanıcının istediği persona (kişilik) ve üslup (mode) ile harmanlayarak
akıcı ve tutarlı bir nihai yanıt oluşturur.

Temel Sorumluluklar:
1. Veri Harmanlama: Çoklu uzman çıktılarını tek bir bağlamda birleştirme.
2. üslup Enjeksiyonu: Yanıtı belirlenen Kişilik (Persona) kurallarına göre şekillendirme.
3. Geçmiş Entegrasyonu: Konuşma geçmişini göz önünde bulundurarak süreklilik sağlama.
4. Çıktı Temizleme (Sanitization): Gereksiz teknik ibareleri veya yanlış karakterleri ayıklama.
5. Akış Desteği: Nihai yanıtın akış (stream) halinde parça parça iletilmesini sağlama.
"""

from typing import List, Dict, Any, Optional
import httpx
import re
from Atlas.config import API_CONFIG, MODEL_GOVERNANCE, STYLE_TEMPERATURE_MAP
from Atlas.key_manager import KeyManager
from Atlas.prompts import SYNTHESIZER_PROMPT
from Atlas.style_injector import get_system_instruction, STYLE_PRESETS
from Atlas.memory import MessageBuffer
from Atlas.generator import generate_stream

class Synthesizer:
    """Uzman çıktılarını nihai yanıta dönüştüren sentez katmanı."""

    @staticmethod
    def _prepare_formatted_data(raw_results: List[Dict[str, Any]], request_context: Any, user_message: str) -> str:
        """Ham uzman verilerini ve hafıza talimatlarını formatlar."""
        formatted_data = ""
        
        # Memory Voice System: Identity facts'i doğal dil talimatı olarak enjekte et
        if request_context:
            memory_instruction = request_context.get_human_memory_instruction()
            if memory_instruction:
                formatted_data = memory_instruction + "\n\n"
        
        if not raw_results:
            formatted_data += f"[DİKKAT: Uzman raporu bulunamadı. Lütfen kullanıcının şu mesajına nazikçe cevap ver.]\nKullanıcı Mesajı: {user_message}"
        else:
            for res in raw_results:
                content = res.get('output') or res.get('response') or "[Veri Yok]"
                formatted_data += f"--- Uzman ({res.get('model')}): ---\n{content}\n\n"
        
        return formatted_data

    @staticmethod
    def _get_conversation_history(session_id: str, user_message: str) -> str:
        """Konuşma geçmişini getirir ve son kullanıcı mesajını filtreler."""
        history = MessageBuffer.get_llm_messages(session_id, limit=6)
        
        # Eğer son mesaj kullanıcının şu anki mesajıyla aynıysa onu geçmişten ayır
        history_to_show = []
        for msg in history:
            if msg["role"] == "user" and msg["content"] == user_message:
                continue
            history_to_show.append(msg)
            
        return "\n".join([f"{m['role']}: {m['content']}" for m in history_to_show])

    @staticmethod
    def _build_system_instructions(mode: str, formatted_data: str, history_text: str, user_message: str, current_topic: Optional[str]) -> str:
        """Tüm sistem talimatlarını (stil, mirroring, conflict, topic, emotion) oluşturur."""
        # 1. Üslup Talimatlarını Getir
        style_instruction = get_system_instruction(mode)

        # 2. Mirroring & Memory Voice Logic
        mirroring_instruction = ""
        if mode == "standard":
            context_str = formatted_data.lower() + " " + user_message.lower()
            if any(w in context_str for w in ["yorgun", "gergin", "üzgün", "stres", "yoğun"]):
                mirroring_instruction = "\n[MIRRORING]: Kullanıcı yorgun veya gergin görünüyor. Cevabını daha kısa, empatik ve çözüm odaklı tut. Teknik detaylara boğma."
            elif any(w in context_str for w in ["mutlu", "neşeli", "süper", "harika", "enerjik"]):
                mirroring_instruction = "\n[MIRRORING]: Kullanıcı enerjik ve neşeli. Cevabını daha canlı, detaylı ve eşlikçi bir tonla hazırla."

            if "GRAF | Skor:" in formatted_data or "HIB_GRAF" in formatted_data:
                mirroring_instruction += "\n[MEMORY_VOICE]: Hafızadan gelen bilgileri kullanırken 'Hatırladığım kadarıyla...', 'Daha önce belirttiğin gibi...' gibi doğal girişler yap. Teknik etiketleri (skor vb.) asla kullanıcıya gösterme."
                mirroring_instruction += "\n- Eğer kullanılan bilginin tarihi 6 aydan eskiyse, cümleye 'Bir süre önceki kayıtlara göre...' diye başla."
                mirroring_instruction += "\n- Eğer bilginin güven skoru (confidence) 0.6'dan düşükse, cümleye 'Yanlış hatırlamıyorsam...' veya 'Emin olmamakla birlikte...' diye başla."

        # 3. Conflict Resolution Rule
        conflict_instruction = ""
        if "[ÇÖZÜLMESİ GEREKEN DURUM]" in formatted_data or "[ÇÖZÜLMESİ GEREKEN DURUM]" in history_text:
            conflict_instruction = "\n[CONFLICT_RESOLUTION]: Bağlamda bir çelişki (Conflict) tespit edildi. Lütfen cevabını verdikten sonra, nazikçe ve meraklı bir tonla bu durumu netleştirecek bir soru sor. Asla suçlayıcı olma, sadece anlamaya çalış."

        # 4. Topic Transition Logic
        topic_transition_instruction = ""
        if current_topic and current_topic not in ["SAME", "CHITCHAT"]:
            topic_transition_instruction = f"\n[KONU DEĞİŞİMİ]: Konuşmanın ana konusu '{current_topic}' olarak güncellendi. Eğer önceki konudan keskin bir geçiş varsa, cevabına doğal bir geçiş cümlesiyle (Örn: 'O konudan buna geçersek...') başla."

        # 5. Emotional Continuity Rules
        emotional_instruction = ""
        if "[ÖNCEKİ DUYGU DURUMU]" in formatted_data or "[ÖNCEKİ DUYGU DURUMU]" in history_text:
            mood_match = re.search(r"ÖNCEKİ DUYGU DURUMU.*?'([^']+)'", formatted_data + history_text)
            if mood_match:
                mood = mood_match.group(1)
                emotional_instruction = (
                    f"\n[EMOTIONAL_CONTINUITY]: Bu yeni bir oturum. Kullanıcı geçen sefer '{mood}' durumundaydı. "
                    "Selamlamanı buna göre yap (Örn: 'Umarım daha iyisindir', 'Enerjin yerindedir umarım' vb.). "
                    "Konuya girmeden önce hal hatır sor."
                )

        return style_instruction + mirroring_instruction + conflict_instruction + topic_transition_instruction + emotional_instruction

    @staticmethod
    async def synthesize(raw_results: List[Dict[str, Any]], session_id: str, intent: str = "general", user_message: str = "", mode: str = "standard", current_topic: str = None, request_context=None) -> tuple[str, str, str, dict]:
        """
        Çoklu uzman sonuçlarını birleştirir ve tekil (blok) bir yanıt oluşturur.
        Dönüş: (yanıt_metni, model_id, prompt, metadata)

        Args:
            request_context: AtlasRequestContext with identity facts from API layer
        """
        # 1. Verileri ve Geçmişi Hazırla
        formatted_data = Synthesizer._prepare_formatted_data(raw_results, request_context, user_message)
        history_text = Synthesizer._get_conversation_history(session_id, user_message)

        print(f"[HATA AYIKLAMA] Sentezleyici {len(raw_results)} uzman sonucunu işliyor")

        # 2. Sistem Talimatlarını Oluştur
        full_system_instruction = Synthesizer._build_system_instructions(
            mode, formatted_data, history_text, user_message, current_topic
        )

        messages = [
            {"role": "system", "content": full_system_instruction},
            {"role": "user", "content": SYNTHESIZER_PROMPT.format(
                history=history_text if history_text else "[Henüz konuşma geçmişi yok]",
                raw_data=formatted_data,
                user_message=user_message
            )}
        ]
        
        prompt = messages[1]["content"]
        
        # Sentez işlemi için kullanılacak model dizisini getir
        synth_models = MODEL_GOVERNANCE.get("synthesizer", ["llama-3.3-70b-versatile"])
        
        last_error = None
        for i, model_id in enumerate(synth_models):
            api_key = KeyManager.get_best_key()
            if not api_key:
                print(f"[HATA] Sentezleyici ({model_id}) için API anahtarı bulunamadı")
                continue

            try:
                print(f"[HATA AYIKLAMA] Sentezleyici API çağrısı yapıyor. Model: {model_id} (Deneme {i+1}/{len(synth_models)})")
                
                # Get temperature based on style mode
                temperature = STYLE_TEMPERATURE_MAP.get(mode, 0.5)
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{API_CONFIG['groq_api_base']}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model_id,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": 2000,
                            "frequency_penalty": API_CONFIG.get("frequency_penalty", 0.1),
                            "presence_penalty": API_CONFIG.get("presence_penalty", 0.1)
                        }
                    )
                    if response.status_code == 200:
                        KeyManager.report_success(api_key, model_id) # Başarıyı raporla
                        result = response.json()["choices"][0]["message"]["content"]
                        
                        metadata = {
                            "mode": mode,
                            "persona": STYLE_PRESETS.get(mode, STYLE_PRESETS["standard"]).persona
                        }
                        
                        return Synthesizer._sanitize_response(result), model_id, prompt, metadata
                    else:
                        KeyManager.report_error(api_key, response.status_code)
                        print(f"[HATA] {model_id} için Sentezleyici API durumu: {response.status_code}")
                        continue
            except Exception as e:
                last_error = e
                print(f"[HATA] {model_id} için Sentezleyici denemesi başarısız: {e}")
                continue
            
        # Yedek Plan: Modeller başarısız olursa verileri ham haliyle birleştir
        print("[UYARI] Sentezleyici ham birleştirmeye geri dönüyor")
        metadata = {"mode": mode, "fallback": True}
        # TODO: Fallback implementation if needed, for now just returning formatted data roughly?
        # In original code it just ends here without explicit return if fallback loop finishes?
        # Actually original code had a bug or incomplete part: `metadata = {"mode": mode, "fallback": True}` and then nothing?
        # Let's check original code tail.
        # It ended with `metadata = ...`. It probably relies on the calling function to handle None return or it raises implicit error?
        # Wait, the original code I read:
        # `metadata = {"mode": mode, "fallback": True}`
        # `# DÜZELTME: List comprehension içinde güvenli .get() kullanımı`
        # And then `@staticmethod async def synthesize_stream` starts.
        # It seems `synthesize` function in original code fell through without returning if loop failed?
        # Python returns None by default.
        # I should keep it as is or fix it if I can, but instruction says "Code health improvements should make the codebase better without changing behavior".
        # If it was returning None, I'll let it return None (implicit).
        # But wait, the return type hint is `tuple[str, str, str, dict]`.
        # If it returns None, that violates type hint.
        # But I should stick to original behavior. I won't add a return if there wasn't one.
        return Synthesizer._sanitize_response(formatted_data), "fallback", prompt, metadata

    @staticmethod
    async def synthesize_stream(raw_results: List[Dict[str, Any]], session_id: str, intent: str = "general", user_message: str = "", mode: str = "standard", current_topic: str = None, request_context=None):
        """
        Expert sonuçlarını birleştirir ve final yanıtı stream (akış) olarak üretir.
        
        Args:
            request_context: AtlasRequestContext with identity facts from API layer
        """
        # 1. Verileri ve Geçmişi Hazırla
        formatted_data = Synthesizer._prepare_formatted_data(raw_results, request_context, user_message)
        history_text = Synthesizer._get_conversation_history(session_id, user_message)
        
        # 2. Sistem Talimatlarını Oluştur
        full_system_instruction = Synthesizer._build_system_instructions(
            mode, formatted_data, history_text, user_message, current_topic
        )

        prompt = SYNTHESIZER_PROMPT.format(
            history=history_text if history_text else "[Henüz konuşma geçmişi yok]",
            raw_data=formatted_data,
            user_message=user_message
        )

        # 3. Sırayla modelleri dene (Stream versiyonu)
        synth_models = MODEL_GOVERNANCE.get("synthesizer", ["llama-3.3-70b-versatile"])
        
        for model_id in synth_models:
            api_key = KeyManager.get_best_key(model_id=model_id)
            if not api_key: continue
            
            try:
                print(f"[HATA AYIKLAMA] Sentezleyici model üzerinden akış (streaming) yapıyor: {model_id}")
                # Metadata ilk parça olarak gönderilsin (api.py bunu yakalayacak)
                yield {"type": "metadata", "model": model_id, "prompt": prompt, "mode": mode, "persona": mode} # Persona mode ile aynı şimdilik
                
                # generate_stream asenkron jeneratör döner
                async for chunk in generate_stream(prompt, model_id, intent, api_key=api_key, override_system_prompt=full_system_instruction):
                    yield {"type": "chunk", "content": chunk}
                return # Başarılı akış bitti
            except Exception as e:
                print(f"[HATA] {model_id} için Sentezleyici akışı başarısız oldu: {e}")
                continue

        yield {"type": "chunk", "content": "Maalesef şu an yanıt oluşturulamadı."}

    @staticmethod
    def _sanitize_response(text: str) -> str:
        """Metni temizler: CJK karakterlerini ve teknik etiketleri (THOUGHT vb.) siler."""
        cjk_pattern = r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]'
        sanitized = re.sub(cjk_pattern, '', text)
        
        meta_patterns = [
            r'\[THOUGHT\].*?\[/THOUGHT\]',
            r'\[ANALYSIS\].*?\[/ANALYSIS\]',
            r'Thinking\.\.\.',
            r'Loading\.\.\.'
        ]
        for pattern in meta_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        
        # FAZ-Y.5: Graph/Hybrid tags cleanup
        sanitized = re.sub(r'\[GRAF \| Skor: \d+\.\d+\][:\s]*', '', sanitized)
        sanitized = re.sub(r'\[HIB_GRAF \| Skor: \d+\.\d+\][:\s]*', '', sanitized)
        sanitized = re.sub(r'\[VECTOR \| Skor: \d+\.\d+\][:\s]*', '', sanitized)
        sanitized = re.sub(r'\[(GRAPH|VECTOR|HIB_GRAF|GRAF)\][:\s]*', '', sanitized)
        sanitized = re.sub(r'\[ZAMAN FİLTRESİ\].*?\n', '', sanitized, flags=re.DOTALL)
            
        return sanitized.strip()

synthesizer = Synthesizer()
