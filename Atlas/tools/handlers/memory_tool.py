"""
ATLAS Yönlendirici - Hafıza Erişim Aracı (Memory Tool)
-----------------------------------------------------
Bu araç, Agent'ın (Orchestrator) kendi hafızasında (Neo4j) bilinçli olarak
arama yapmasını sağlar. "Active Memory" konseptinin temelidir.

Kullanım:
- `retrieve_memory(query="...")`: Kullanıcı hakkında spesifik bilgi arar.
"""
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from Atlas.tools.base import BaseTool
from Atlas.memory.neo4j_manager import neo4j_manager

logger = logging.getLogger(__name__)

class MemoryRetrieveInput(BaseModel):
    """Hafıza araması için gerekli parametreler."""
    query: str = Field(..., description="Aranacak bilgi (örn: 'Kullanıcının mesleği ne?', 'Geçen haftaki toplantı notları')")
    limit: int = Field(default=5, description="Getirilecek maksimum kayıt sayısı")

class MemoryTool(BaseTool):
    """
    Agent'ın hafızada (Knowledge Graph) arama yapmasını sağlayan araç.
    """
    name = "retrieve_memory"
    description = "Kullanıcı hakkında geçmiş bilgileri, tercihleri veya önceki konuşmaları hafızadan (veritabanından) sorgulamak için kullanılır."
    input_schema = MemoryRetrieveInput

    async def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Neo4j üzerinde vektör veya keyword tabanlı arama yapar.
        Şimdilik 'Hybrid Retrieval' alt yapısını kullanarak en alakalı sonuçları döner.
        """
        try:
            # Şimdilik basit bir keyword/graph araması simülasyonu
            # İleride `neo4j_manager.search(query)` gibi bir metot eklenebilir.
            # Şu anlık mevcut graph query yapısını kullanıyoruz.

            cypher_query = """
            MATCH (u:User)-[:KNOWS]->(s:Entity)-[r:FACT]->(o:Entity)
            WHERE toLower(r.predicate) CONTAINS toLower($q) OR toLower(o.name) CONTAINS toLower($q)
            RETURN s.name as subject, r.predicate as predicate, o.name as object
            LIMIT $limit
            """
            # Basit bir keyword match denemesi (MVP)
            results = await neo4j_manager.query_graph(cypher_query, {"q": query.split()[0], "limit": limit}) # Çok basit, sadece ilk kelimeyi arıyor şimdilik

            if not results:
                return {"result": "Hafızada bu konuda net bir bilgi bulunamadı."}

            formatted_results = [f"- {r['subject']} {r['predicate']} {r['object']}" for r in results]
            return {
                "source": "memory",
                "query": query,
                "content": "\n".join(formatted_results)
            }

        except Exception as e:
            logger.error(f"Memory tool hatası: {e}")
            return {"error": f"Hafıza erişim hatası: {str(e)}"}
