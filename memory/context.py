"""
ATLAS Yönlendirici - Bağlam Oluşturucu (Context Builder)
-------------------------------------------------------
Bu bileşen, LLM'lere (Büyük Dil Modelleri) gönderilecek olan nihai istemi (prompt) 
hazırlar. Statik talimatlar ile dinamik verileri (geçmiş, hafıza, dış bilgiler) 
bir araya getirerek modelin doğru cevap vermesini sağlar.

Temel Sorumluluklar:
1. Bağlam Birleştirme: Sistem talimatları, mesaj geçmişi ve güncel mesajı harmanlama.
2. Hafıza Entegrasyonu: Kullanıcı gerçekleri (facts) ve Graf Bellek (Neo4j) verilerini enjekte etme.
3. Görsel Analiz Desteği: Önceki mesajlardan gelen görsel analiz sonuçlarını bağlama dahil etme.
4. Token Yönetimi: Bağlamın modelin limitlerini aşmaması için akıllı budama (pruning) yapma.
5. Rol Düzenleme: LLM API'lerinin beklediği ardışık rol (user-assistant) sırasını koruma.
"""

from typing import Optional
from .buffer import MessageBuffer


# Yaklaşık token limitleri ve tahminleri
MAX_CONTEXT_TOKENS = 4000
TOKENS_PER_MESSAGE = 100  # Ortalama mesaj başına tahmin edilen token


class ContextBuilder:
    """LLM için kapsamlı bağlam (context) hazırlayan sınıf."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._system_prompt: Optional[str] = None
        self._user_facts: dict = {}  # MVP-3'te doldurulacak
        self._semantic_results: list = []  # MVP-4'te doldurulacak
        self._neo4j_context: str = "" # Faz 3
    
    def with_system_prompt(self, prompt: str) -> "ContextBuilder":
        """System prompt ayarla."""
        self._system_prompt = prompt
        return self
    
    def with_user_facts(self, facts: list) -> "ContextBuilder":
        """User facts ekle (MVP-3). List[UserFact] veya dict alır."""
        self._user_facts = facts
        return self
    
    def with_semantic_results(self, results: list) -> "ContextBuilder":
        """Semantic search sonuçları ekle (MVP-4)."""
        self._semantic_results = results
        return self
    
    def with_neo4j_context(self, context: str) -> "ContextBuilder":
        """Neo4j'den gelen grafiksel bağlamı ekle (Faz 3)."""
        self._neo4j_context = context
        return self

    async def get_neo4j_context(self, user_id: str, message: str) -> str:
        """
        Neo4j'den mesajla ilgili bilgileri çeker.
        """
        import re
        from .neo4j_manager import neo4j_manager

        # 1. Basit anahtar kelime çıkarımı (Stop-wordleri atlamıyoruz şimdilik)
        # 3 karakterden büyük kelimeleri al
        keywords = [w.strip() for w in re.split(r'\W+', message) if len(w.strip()) > 3]
        if not keywords:
            return ""

        # 2. Neo4j sorgusu
        # Kullanıcının bildiği entity'ler içinden mesajdaki kelimeleri içerenleri bul
        cypher = """
        MATCH (u:User {id: $uid})-[:KNOWS]->(s:Entity)-[r:FACT]->(o:Entity)
        WHERE any(kw IN $keywords WHERE toLower(s.name) CONTAINS toLower(kw))
        RETURN s.name as subject, r.predicate as predicate, o.name as object
        LIMIT 10
        """
        
        try:
            records = await neo4j_manager.query_graph(cypher, {"uid": user_id, "keywords": keywords})
            if not records:
                return ""
            
            # 3. Formatla
            facts = []
            for rec in records:
                facts.append(f"{rec['subject']} - {rec['predicate']} - {rec['object']}")
            
            return "\n".join(facts)
        except Exception:
            return ""
    def build(self, current_message: str, history_limit: int = 5, signal_only: bool = False) -> list[dict]:
        """
        LLM için messages listesi oluşturur.
        
        Args:
            current_message: Kullanıcının yeni mesajı
            history_limit: Kaç mesaj geçmişi alınacak
            signal_only: Uzmanlar için sadeleştirilmiş bağlam (Persona gürültüsünü azaltır)
        """
        if signal_only:
            # Uzmanlar için son 2-3 mesaj yeterli (Anchor + Current)
            history_limit = min(history_limit, 3) 

        messages = []
        
        # 1. System Prompt Construction with Structural Tagging
        if self._system_prompt:
            system_parts = ["[SİSTEM_TALİMATLARI]", self._system_prompt]
            
            # User facts (Eğer varsa)
            if self._user_facts:
                from .facts import UserFact
                facts_list = []
                if isinstance(self._user_facts, list):
                    for f in self._user_facts:
                        facts_list.append(f"- {f.key}: {f.value}" if isinstance(f, UserFact) else f"- {str(f)}")
                elif isinstance(self._user_facts, dict):
                    for k, v in self._user_facts.items():
                        facts_list.append(f"- {k}: {v}")
                
                if facts_list:
                    system_parts.append("\n[KULLANICI_OLGULARI]")
                    system_parts.append("\n".join(facts_list))
            
            # Semantic Results
            if self._semantic_results:
                system_parts.append("\n[İLGİLİ_GEÇMİŞ_BİLGİLER]")
                system_parts.append("\n".join(f"- {r}" for r in self._semantic_results[:3]))
            
            # Neo4j
            if self._neo4j_context:
                system_parts.append("\n[GRAFİK_BELLEK_BAĞLAMI]")
                system_parts.append(self._neo4j_context)
            
            system_content = "\n".join(system_parts)
            messages.append({"role": "system", "content": system_content})
        
        # 2. History Retrieval
        history = MessageBuffer.get_llm_messages(self.session_id, limit=history_limit)
        
        # 3. Handle Vision Context
        vision_context = ""
        for msg in reversed(history):
            if "[CONTEXT - VISION_ANALYSIS" in msg["content"] or "[SİSTEM ANALİZİ - GÖRSEL" in msg["content"]:
                vision_context = msg["content"]
                break
        
        if vision_context and messages:
             messages[0]["content"] += "\n\n[GÖRSEL_ANALİZ_BAĞLAMI]\n" + vision_context

        # 4. History Integration
        if signal_only and history:
            messages.append({"role": "system", "content": "[GEÇMİŞ_KONUŞMA_BAĞLAMI]"})
            
        messages.extend(history)
        
        # 5. Current Message
        if signal_only:
            messages.append({"role": "user", "content": f"[AKTİF_GÖREV]\n{current_message}"})
        else:
            messages.append({"role": "user", "content": current_message})
        
        # 6. Pooling/Merging - Alternating Roles Enforcement
        merged_messages = []
        for msg in messages:
            if not merged_messages or merged_messages[-1]["role"] != msg["role"]:
                merged_messages.append(msg.copy())
            else:
                # Aynı roldeki peş peşe mesajları birleştir
                merged_messages[-1]["content"] += "\n\n" + msg["content"]
        
        messages = merged_messages

        # Token limit kontrolü (basit)
        estimated_tokens = len(messages) * TOKENS_PER_MESSAGE
        if estimated_tokens > MAX_CONTEXT_TOKENS:
            # Geçmişi kısalt
            while len(messages) > 3 and estimated_tokens > MAX_CONTEXT_TOKENS:
                # System ve current'ı koru, ortadakileri sil
                if len(messages) > 2:
                    messages.pop(1)
                estimated_tokens = len(messages) * TOKENS_PER_MESSAGE
        
        return messages
    
    def get_context_info(self) -> dict:
        """Debug için context bilgisi."""
        history = MessageBuffer.get_llm_messages(self.session_id)
        return {
            "session_id": self.session_id,
            "history_count": len(history),
            "has_system_prompt": bool(self._system_prompt),
            "user_facts_count": len(self._user_facts),
            "semantic_results_count": len(self._semantic_results)
        }


# Future extensions interfaces
class UserFactsStore:
    """MVP-3: PostgreSQL user facts - placeholder."""
    
    @staticmethod
    def get_facts(user_id: str) -> dict:
        # TODO: PostgreSQL'den oku
        return {}
    
    @staticmethod
    def save_fact(user_id: str, key: str, value: str) -> None:
        # TODO: PostgreSQL'e yaz
        pass


class SemanticSearch:
    """MVP-4: pgvector semantic search - placeholder."""
    
    @staticmethod
    def search(query: str, session_id: str, top_k: int = 3) -> list[str]:
        # İleride: pgvector benzerlik araması eklenebilir
        return []
