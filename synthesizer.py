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
from .config import API_CONFIG, MODEL_GOVERNANCE, STYLE_TEMPERATURE_MAP
from .key_manager import KeyManager  # EKLENDİ: KeyManager import edildi
from .prompts import SYNTHESIZER_PROMPT

class Synthesizer:
    """Uzman çıktılarını nihai yanıta dönüştüren sentez katmanı."""
    @staticmethod
    async def synthesize(raw_results: List[Dict[str, Any]], session_id: str, intent: str = "general", user_message: str = "", mode: str = "standard") -> tuple[str, str, str, dict]:
        """
        Çoklu uzman sonuçlarını birleştirir ve tekil (blok) bir yanıt oluşturur.
        Dönüş: (yanıt_metni, model_id, prompt, metadata)
        """
        # 1. Ham verileri sentez için hazırla
        formatted_data = ""
        if not raw_results:
            formatted_data = f"[DİKKAT: Uzman raporu bulunamadı. Lütfen kullanıcının şu mesajına nazikçe cevap ver.]\nKullanıcı Mesajı: {user_message}"
        else:
            for res in raw_results:
                # DÜZELTME: Hem 'output' hem 'response' kontrolü (Uyumluluk için)
                content = res.get('output') or res.get('response') or "[Veri Yok]"
                formatted_data += f"--- Uzman ({res.get('model')}): ---\n{content}\n\n"

        print(f"[HATA AYIKLAMA] Sentezleyici {len(raw_results)} uzman sonucunu işliyor")
        
        # 2. Üslup Talimatlarını Getir (Style Injector)
        from .style_injector import get_system_instruction, STYLE_PRESETS
        style_instruction = get_system_instruction(mode)
        
        # 3. Konuşma Geçmişi Bağlamı: Tekrarı önlemek için güncel mesajı geçmişten ayıklar
        from .memory import MessageBuffer
        history = MessageBuffer.get_llm_messages(session_id, limit=6)
        
        # Eğer son mesaj kullanıcının şu anki mesajıyla aynıysa onu geçmişten ayır
        history_to_show = []
        for msg in history:
            if msg["role"] == "user" and msg["content"] == user_message:
                continue
            history_to_show.append(msg)
            
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_to_show])

        messages = [
            {"role": "system", "content": style_instruction},
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
            # DÜZELTME: API Key döngü içinde alınıyor
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
        # DÜZELTME: List comprehension içinde güvenli .get() kullanımı
    @staticmethod
    async def synthesize_stream(raw_results: List[Dict[str, Any]], session_id: str, intent: str = "general", user_message: str = "", mode: str = "standard"):
        """
        Expert sonuçlarını birleştirir ve final yanıtı stream (akış) olarak üretir.
        """
        from .generator import generate_stream
        from .style_injector import get_system_instruction
        
        # 1. Uzman verilerini hazırla
        formatted_data = ""
        if not raw_results:
            formatted_data = f"[DİKKAT: Uzman raporu bulunamadı.]\nKullanıcı: {user_message}"
        else:
            for res in raw_results:
                content = res.get('output') or res.get('response') or "[Veri Yok]"
                formatted_data += f"--- Uzman ({res.get('model')}): ---\n{content}\n\n"

        # 2. Sistem talimatı ve prompt
        style_instruction = get_system_instruction(mode)
        
        from .memory import MessageBuffer
        history = MessageBuffer.get_llm_messages(session_id, limit=6)
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history if m['content'] != user_message])

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
                async for chunk in generate_stream(prompt, model_id, intent, api_key=api_key):
                    yield {"type": "chunk", "content": chunk}
                return # Başarılı akış bitti
            except Exception as e:
                print(f"[HATA] {model_id} için Sentezleyici akışı başarısız oldu: {e}")
                continue

        yield "Maalesef şu an yanıt oluşturulamadı."

    @staticmethod
    def _sanitize_response(text: str) -> str:
        """Metni temizler: CJK karakterlerini ve teknik etiketleri (THOUGHT vb.) siler."""
        import re
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
            
        return sanitized.strip()

synthesizer = Synthesizer()