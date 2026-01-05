"""
ATLAS Yönlendirici - Web Arama Aracı (Search Tool)
--------------------------------------------------
Bu araç, Serper.dev API'sini kullanarak Google üzerinde
güncel bilgi araması yapar ve sonuçları sisteme döndürür.

Temel Özellikler:
1. Gerçek Zamanlı Arama: Google serp sonuçlarını anlık olarak çekme.
2. Sonuç Sayısı Kontrolü: Döndürülecek link sayısını belirleme.
3. Asenkron İşleme: Arama sürerken sistemi bloke etmeme.
4. Hata Yönetimi: API anahtarı eksikliği veya servis hatalarında anlaşılır mesajlar.

Kullanım Senaryoları:
- "Dolar kuru ne kadar?" gibi güncel bilgi soruları.
- "X kimdir?" gibi ansiklopedik sorgular.
- Haberler ve teknik dokümantasyon aramaları.
"""
import httpx
import logging
from typing import Any, Dict
from pydantic import BaseModel, Field
from sandbox_router.tools.base import BaseTool
from sandbox_router.config import Config

logger = logging.getLogger(__name__)

# --- GİRDİ ŞEMASI ---
class SerperInput(BaseModel):
    """Arama sorgusunda beklenen parametreleri tanımlar."""
    query: str = Field(..., description="Arama yapılacak kelime veya cümle.")
    num_results: int = Field(default=3, description="Döndürülecek sonuç sayısı.")


# --- ANA ARAÇ SINIFI ---

class SerperTool(BaseTool):
    """
    Serper.dev API kullanarak Google araması yapan tool.
    """
    name = "search_tool"
    description = "Google üzerinde arama yaparak güncel bilgileri getirir. Haberler, teknik dökümanlar veya genel bilgiler için kullanılır."
    input_schema = SerperInput

    async def execute(self, query: str, num_results: int = 3) -> Dict[str, Any]:
        """
        Serper API'sine asenkron istek atar.
        """
        api_key = Config.SERPER_API_KEY
        if not api_key:
            return {"error": "Serper API key bulunamadı. Lütfen config dosyasını kontrol edin."}

        url = "https://google.serper.dev/search"
        payload = {
            "q": query,
            "num": num_results
        }
        # API istek başlıkları (kimlik doğrulama için anahtar gerekli)
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }

        # --- API ÇAĞRISI VE HATA YÖNETİMİ ---
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Serper API hatası: {e.response.status_code} - {e.response.text}")
            return {"error": f"Arama servisi hata döndürdü: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Serper execute hatası: {str(e)}")
            return {"error": f"Beklenmedik bir hata oluştu: {str(e)}"}
