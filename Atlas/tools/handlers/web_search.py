"""
ATLAS Yönlendirici - Web Arama Aracı (WebSearchTool)
---------------------------------------------------
Bu araç, Google (Serper.dev) API kullanarak internet araması yapar.
LLM'in güncel bilgiye erişmesini sağlar.

Kullanım:
1. `Config.SERPER_API_KEY` ayarlanmalıdır.
2. `input_schema` Pydantic modeli ile doğrulanmış girdi alır.
3. `execute(query="...")` metodu asenkron olarak çalışır.
"""
import logging
import httpx
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from Atlas.tools.base import BaseTool
from Atlas.config import Config
from Atlas.tools.summarizer import summarize_tool_output

logger = logging.getLogger(__name__)

class WebSearchInput(BaseModel):
    """Web araması için gerekli parametreler."""
    query: str = Field(..., description="Arama sorgusu (örn: '2024 olimpiyatları nerede?')")
    num_results: int = Field(default=5, description="Getirilecek sonuç sayısı (varsayılan: 5)")

class WebSearchTool(BaseTool):
    """
    Google Serper API Wrapper Aracı.
    """
    name = "web_search"
    description = "İnternette güncel bilgi, haber ve gerçekleri aramak için kullanılır. Bilinmeyen konularda mutlaka kullanılmalıdır."
    input_schema = WebSearchInput

    async def execute(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Serper.dev API üzerinden arama yapar.
        """
        api_key = Config.SERPER_API_KEY
        if not api_key:
            logger.warning("SERPER_API_KEY eksik! Web araması yapılamıyor.")
            return {"error": "API anahtarı yapılandırılmamış."}

        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "num": num_results,
            "gl": "tr",  # Türkiye lokasyonu
            "hl": "tr"   # Türkçe sonuçlar
        })
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, data=payload)
                response.raise_for_status()
                data = response.json()

                # Sonuçları işle ve özetle
                organic_results = data.get("organic", [])
                knowledge_graph = data.get("knowledgeGraph", {})

                # Özetleme mantığı (token tasarrufu için)
                summary = []

                # Knowledge Graph varsa en başa ekle
                if knowledge_graph:
                    title = knowledge_graph.get("title", "")
                    desc = knowledge_graph.get("description", "")
                    attrs = knowledge_graph.get("attributes", {})
                    summary.append(f"**{title}**\n{desc}\nAttributes: {attrs}")

                # Organik sonuçları ekle
                for res in organic_results[:num_results]:
                    title = res.get("title", "Başlıksız")
                    snippet = res.get("snippet", "Açıklama yok")
                    link = res.get("link", "")
                    summary.append(f"- [{title}]({link}): {snippet}")

                final_text = "\n\n".join(summary)

                return {
                    "source": "google_serper",
                    "query": query,
                    "results_count": len(organic_results),
                    "content": final_text
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"Serper API hatası: {e.response.status_code} - {e.response.text}")
            return {"error": f"Arama servisi hatası: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Web arama beklenmeyen hata: {e}")
            return {"error": f"Beklenmeyen hata: {str(e)}"}
