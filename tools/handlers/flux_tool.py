"""
ATLAS Yönlendirici - Görsel Üretim Aracı (Flux Tool)
----------------------------------------------------
Bu araç, yerel Stable Diffusion (Forge/A1111) API'sini kullanarak
metin tabanlı görsel üretimi gerçekleştirir.

Temel Özellikler:
1. Prompt Tabanlı Üretim: Kullanıcının İngilizce tanımlamasından görsel oluşturma.
2. Boy Oranı Desteği: 1:1, 16:9 veya 9:16 formatlarında görsel üretebilme.
3. Asenkron İşleme: Uzun süren üretim işlemlerini engellemeden yönetme.
4. Hata Yönetimi: Bağlantı problemlerinde anlaşılır hata mesajları döndürme.

Kullanım Senaryoları:
- "Bir uzay gemisi çiz" gibi yaratıcı istekler.
- Teknik diyagramlar ve konsept görseller.
"""
import httpx
import logging
from typing import Any, Dict
from pydantic import BaseModel, Field
from sandbox_router.tools.base import BaseTool
from sandbox_router.config import Config

logger = logging.getLogger(__name__)

# --- GİRDİ ŞEMASI ---
class FluxInput(BaseModel):
    """Araç çağrısında beklenen parametreleri tanımlar."""
    prompt: str = Field(..., description="Üretilecek görselin İngilizce tanımı.")
    aspect_ratio: str = Field(default="16:9", description="Görselin en-boy oranı (Örn: 1:1, 16:9, 9:16).")


# --- ANA ARAÇ SINIFI ---

class FluxTool(BaseTool):
    """
    Yerel Forge veya A1111 API kullanarak görsel üreten tool.
    """
    name = "flux_tool"
    description = "Metinden görsel üretir. Kullanıcının sanatsal veya teknik görsel ihtiyaçları için kullanılır."
    input_schema = FluxInput

    async def execute(self, prompt: str, aspect_ratio: str = "16:9") -> Dict[str, Any]:
        """
        Yerel API'ye asenkron POST isteği atar.
        """
        api_url = Config.FLUX_API_URL
        
        # Basit en-boy oranı hesaplama (Gerçek API bekleyişine göre uyarlanabilir)
        width, height = 1024, 1024
        if aspect_ratio == "16:9":
            width, height = 1344, 768
        elif aspect_ratio == "9:16":
            width, height = 768, 1344

        # API isteği için gönderilecek parametre sözlüğü
        payload = {
            "prompt": prompt,
            "steps": 20,           # Üretim kalitesi (daha yüksek = daha iyi ama yavaş)
            "width": width,
            "height": height,
            "cfg_scale": 7.0       # Prompt'a bağlılık oranı
        }

        # --- API ÇAĞRISI VE HATA YÖNETİMİ ---
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, json=payload)
                response.raise_for_status()
                # Genellikle image verisi 'images' key'i altında base64 olarak döner.
                return response.json()
        except httpx.ConnectError:
            logger.error(f"Flux API bağlantı hatası: {api_url} adresine ulaşılamıyor.")
            return {"error": "Görsel üretim sunucusu şu an kapalı. Lütfen daha sonra tekrar deneyin."}
        except Exception as e:
            logger.error(f"Flux execute hatası: {str(e)}")
            return {"error": f"Görsel üretilirken bir hata oluştu: {str(e)}"}
