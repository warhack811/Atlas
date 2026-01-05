"""
ATLAS Yönlendirici - Görsel İşleme Motoru (Vision Engine)
--------------------------------------------------------
Bu bileşen, sisteme yüklenen görsellerin içeriğini analiz etmekten sorumludur.
Google Gemini 2.0 Flash modelini ve en güncel Google GenAI SDK'sını kullanır.

Temel Sorumluluklar:
1. Görsel Analizi: JPEG/PNG formatındaki görsellerin metne dökülmesini sağlar.
2. Kota Yönetimi: 429 (Resource Exhausted) hatalarında üstel geri çekilme (exponential backoff) uygular.
3. Güvenli Geri Dönüş: Analiz başarısız olduğunda kullanıcıya anlamlı hata mesajları üretir.
"""
from google import genai
from google.genai import types
from sandbox_router.config import Config
from .prompts import VISION_SYSTEM_PROMPT
import asyncio
import logging
from google.api_core import exceptions

logger = logging.getLogger(__name__)

async def analyze_image(image_bytes: bytes) -> str:
    """
    Gemini 2.0 Flash modelini kullanarak görseli analiz eder.
    Hata durumlarında otomatik yeniden deneme (retry) mekanizmasına sahiptir.
    """
    max_retries = 3
    retry_delay = 2 # seconds
    
    # Google GenAI SDK istemcisini yapılandır
    client = genai.Client(api_key=Config.GEMINI_API_KEY)
    
    for attempt in range(max_retries):
        try:
            # Görsel verisini SDK'nın beklediği 'Part' formatına dönüştür
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type='image/jpeg'
            )
            
            # Asenkron olarak içerik üretimini (vision analysis) başlat
            response = await client.aio.models.generate_content(
                model='gemini-2.0-flash',
                contents=[VISION_SYSTEM_PROMPT, image_part]
            )
            
            if not response or not response.text:
                return "Görsel analiz edilemedi veya boş yanıt döndü."
                
            return response.text.strip()
            
        except exceptions.ResourceExhausted as e:
            logger.warning(f"Görsel Motoru: 429 (Deneme {attempt+1}/{max_retries}). {retry_delay}s içinde yeniden deneniyor...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2 # Üstel geri çekilme (exponential backoff)
            else:
                return "Görsel analiz edilemedi (Sistem Yoğunluğu/Kota). Lütfen kullanıcıya şu an göremediğini belirt."
        except Exception as e:
            logger.error(f"Görsel Motoru Hatası: {e}")
            return f"Görsel analiz hatası: {str(e)}"
    
    return "Görsel analiz edilemedi (Beklenmeyen Hata)."
