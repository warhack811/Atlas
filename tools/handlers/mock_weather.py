"""
ATLAS Yönlendirici - Test Hava Durumu Aracı (Mock Weather)
---------------------------------------------------------
Bu araç, geliştirme ve test amaçlı rastgele hava durumu
verileri üreten sahte (mock) bir servistir.

Temel Özellikler:
1. API Bağımsız: Gerçek bir dış servise ihtiyaç duymaz.
2. Rastgele Veri: Her çağrıda 15-35°C arası rastgele değer döndürür.
3. Hızlı Test: DAG Executor ve araç entegrasyonunu doğrulamak için ideal.

Not: Üretim ortamında gerçek bir hava durumu API'si ile değiştirilmelidir.
"""
import random
from typing import Any
from pydantic import BaseModel, Field
from sandbox_router.tools.base import BaseTool

# --- GİRDİ ŞEMASI ---
class WeatherInput(BaseModel):
    """Hava durumu sorgusunda beklenen parametreleri tanımlar."""
    city: str = Field(..., description="Sıcaklığı merak edilen şehir adı.")


# --- ANA ARAÇ SINIFI ---

class MockWeatherTool(BaseTool):
    name = "mock_weather"
    description = "Belirli bir şehir için güncel hava durumu bilgisini (rastgele) döndürür."
    input_schema = WeatherInput

    async def execute(self, city: str) -> str:
        """Belirtilen şehir için sahte hava durumu verisi üretir."""
        # Rastgele sıcaklık değeri oluştur (15-35°C arası)
        temp = random.randint(15, 35)
        # Kullanıcı dostu formatında sonuç döndür
        return f"{city} şehri için hava durumu: {temp}°C, Güneşli."
