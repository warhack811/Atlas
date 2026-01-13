"""
Atlas Request Context
---------------------
Request-scoped context container that flows through the entire pipeline.

This module implements the "Request Context Pattern" to solve the identity
propagation problem. Instead of each component creating its own context,
a single AtlasRequestContext is created at the API entry point and passed
through all layers.

Key Responsibilities:
1. Pre-fetch identity facts from Neo4j ONCE at request start
2. Build formatted context strings for LLM consumption
3. Provide consistent access to user identity across all components
4. Track request metadata (timing, tracing, etc.)
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AtlasRequestContext:
    """
    Request-scoped context container.
    
    Created once at API entry, passed through:
    api.py → orchestrator.py → dag_executor.py → generator.py → synthesizer.py
    
    All components access the SAME context instance, ensuring consistency.
    """
    
    # Core identifiers
    request_id: str
    user_id: str
    session_id: str
    
    # User message and intent
    user_message: str
    persona: str = "friendly"
    intent: str = "general"
    
    # Pre-fetched identity (from Neo4j)
    identity_facts: Dict[str, str] = field(default_factory=dict)
    # Example: {"İSİM": "Muhammet", "YAŞI": "32", "MESLEĞİ": "Yazılımcı"}
    
    # Formatted context strings (for LLM injection)
    neo4j_context_str: str = ""
    system_prompt: str = ""
    
    # Conversation history (from MessageBuffer)
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Runtime metadata
    created_at: datetime = field(default_factory=datetime.now)
    trace: Optional[Any] = None
    
    # =========================================================================
    # FACTORY METHOD
    # =========================================================================
    
    @classmethod
    async def create(
        cls,
        request_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        persona: str = "friendly",
        trace: Optional[Any] = None
    ) -> "AtlasRequestContext":
        """
        Factory method that creates a fully hydrated context.
        
        This is the ONLY place where identity facts are fetched from Neo4j.
        All downstream components reuse this pre-fetched data.
        
        Args:
            request_id: Unique request identifier
            user_id: User identifier (normalized to lowercase)
            session_id: Session identifier
            user_message: The user's input message
            persona: Persona name for style injection
            trace: Optional ContextTrace for debugging
            
        Returns:
            Fully initialized AtlasRequestContext with identity facts loaded
        """
        # 1. Normalize user_id
        user_id = user_id.lower()
        
        # 2. Create base context
        ctx = cls(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            persona=persona,
            trace=trace
        )
        
        # 3. Load identity facts from Neo4j
        await ctx._hydrate_identity()
        
        # 4. Build formatted context string for LLM
        await ctx._build_neo4j_context()
        
        # 5. Load system prompt based on persona
        ctx._load_system_prompt()
        
        # 6. Load conversation history from MessageBuffer
        ctx._load_history()
        
        logger.info(f"[REQUEST_CONTEXT] Created for user={user_id}, session={session_id}, identity_facts={len(ctx.identity_facts)}")
        
        return ctx
    
    # =========================================================================
    # INTERNAL HYDRATION METHODS
    # =========================================================================
    
    async def _hydrate_identity(self) -> None:
        """Load identity facts from Neo4j into self.identity_facts."""
        from Atlas.memory.neo4j_manager import neo4j_manager
        from Atlas.memory.identity_resolver import get_user_anchor
        from Atlas.memory.predicate_catalog import get_catalog
        
        user_anchor = get_user_anchor(self.user_id)
        
        # Get identity predicates from catalog
        catalog = get_catalog()
        if catalog:
            identity_preds = catalog.get_predicates_by_category("identity")
        else:
            identity_preds = ['İSİM', 'YAŞI', 'MESLEĞİ', 'YAŞAR_YER', 'LAKABI', 'GELDİĞİ_YER']
        
        query = """
        MATCH (s:Entity {name: $anchor})-[r:FACT {user_id: $uid}]->(o:Entity)
        WHERE (r.status IS NULL OR r.status = 'ACTIVE')
          AND r.predicate IN $predicates
        RETURN r.predicate as predicate, o.name as object
        ORDER BY r.updated_at DESC
        """
        
        try:
            results = await neo4j_manager.query_graph(query, {
                "anchor": user_anchor,
                "uid": self.user_id,
                "predicates": identity_preds
            })
            
            # Store in dict (first occurrence wins due to DESC order)
            for res in results:
                pred = res.get("predicate")
                obj = res.get("object")
                if pred and obj and pred not in self.identity_facts:
                    self.identity_facts[pred] = obj
                    
            logger.info(f"[REQUEST_CONTEXT] Identity hydrated: {self.identity_facts}")
            
        except Exception as e:
            logger.error(f"[REQUEST_CONTEXT] Identity hydration failed: {e}")
    
    async def _build_neo4j_context(self) -> None:
        """Build the formatted neo4j context string for LLM injection."""
        from Atlas.memory.context import build_chat_context_v1
        
        try:
            self.neo4j_context_str = await build_chat_context_v1(
                self.user_id,
                self.session_id,
                self.user_message,
                trace=self.trace
            )
        except Exception as e:
            logger.error(f"[REQUEST_CONTEXT] Context build failed: {e}")
            self.neo4j_context_str = ""
    
    def _load_system_prompt(self) -> None:
        """Load system prompt based on persona."""
        from Atlas.prompts import get_persona_prompt
        self.system_prompt = get_persona_prompt(self.persona)
    
    def _load_history(self, limit: int = 10) -> None:
        """Load conversation history from MessageBuffer."""
        from Atlas.memory.buffer import MessageBuffer
        self.history = MessageBuffer.get_llm_messages(self.session_id, limit=limit)
    
    # =========================================================================
    # PUBLIC ACCESSORS
    # =========================================================================
    
    def get_identity(self, predicate: str, default: str = "") -> str:
        """
        Get a specific identity fact.
        
        Args:
            predicate: The predicate key (e.g., "İSİM", "YAŞI")
            default: Default value if not found
            
        Returns:
            The value associated with the predicate, or default
        """
        return self.identity_facts.get(predicate, default)
    
    def get_user_name(self) -> Optional[str]:
        """Convenience method to get user's name."""
        return self.identity_facts.get("İSİM") or self.identity_facts.get("ISIM")
    
    def get_user_age(self) -> Optional[str]:
        """Convenience method to get user's age."""
        return self.identity_facts.get("YAŞI") or self.identity_facts.get("YASI")
    
    def has_identity(self) -> bool:
        """Check if any identity facts are loaded."""
        return len(self.identity_facts) > 0
    
    def build_llm_messages(self, current_message: str, history_limit: int = 5) -> List[Dict[str, str]]:
        """
        Build the messages array for LLM API call.
        
        This replaces the ContextBuilder.build() pattern.
        
        Args:
            current_message: The current user message
            history_limit: Max history messages to include
            
        Returns:
            List of message dicts ready for LLM API
        """
        messages = []
        
        # 1. System prompt with injected context
        system_content = self.system_prompt
        if self.neo4j_context_str:
            system_content += "\n\n[GRAFİK_BELLEK_BAĞLAMI]\n" + self.neo4j_context_str
        
        messages.append({"role": "system", "content": system_content})
        
        # 2. History (limited)
        history_subset = self.history[-history_limit:] if len(self.history) > history_limit else self.history
        messages.extend(history_subset)
        
        # 3. Current message
        messages.append({"role": "user", "content": current_message})
        
        # 4. Merge consecutive same-role messages
        merged = []
        for msg in messages:
            if not merged or merged[-1]["role"] != msg["role"]:
                merged.append(msg.copy())
            else:
                merged[-1]["content"] += "\n\n" + msg["content"]
        
        return merged
    
    def get_human_memory_instruction(self) -> str:
        """
        Identity facts'i LLM'e görünmez doğal dil talimatı olarak formatla.
        
        Memory Voice System: Teknik format (- İSİM: Muhammet) yerine
        doğal dil kullanarak LLM'in robotik yanıtlar üretmesini önler.
        
        Returns:
            Invisible system instruction for human-like memory usage
            
        Example Output:
            <system_memory type="invisible">
            Konuştuğun kişi: adı Muhammet, 32 yaşında, yazılımcı, İstanbul'da yaşıyor.
            
            KRİTİK TALİMAT:
            - Bu bilgileri "profil", "kayıt", "veri" kelimeleriyle REFERANS ETME
            ...
            </system_memory>
        """
        if not self.identity_facts:
            return ""
        
        # Doğal dil formatına dönüştür
        facts_natural = []
        
        # Türkçe predicate -> doğal dil mapping
        predicate_templates = {
            "İSİM": "adı {}",
            "ISIM": "adı {}",
            "YAŞI": "{} yaşında",
            "YASI": "{} yaşında",
            "MESLEĞİ": "mesleği {}",
            "MESLEGI": "mesleği {}",
            "YAŞAR_YER": "{}'da yaşıyor",
            "YASAR_YER": "{}'da yaşıyor",
            "GELDİĞİ_YER": "{}'dan gelmiş",
            "GELDIGI_YER": "{}'dan gelmiş",
            "LAKABI": "lakabı {}",
        }
        
        for pred, obj in self.identity_facts.items():
            if not obj:
                continue
            template = predicate_templates.get(pred)
            if template:
                facts_natural.append(template.format(obj))
            else:
                # Fallback: predicate'i küçük harfle kullan
                facts_natural.append(f"{pred.lower().replace('_', ' ')}: {obj}")
        
        if not facts_natural:
            return ""
        
        facts_text = ", ".join(facts_natural)
        
        # Kullanıcı adını al (varsa)
        user_name = self.get_user_name() or "bu kişi"
        
        return f"""<system_memory type="invisible">
Konuştuğun kişi hakkında bildiklerin: {facts_text}.

KRİTİK TALİMAT (Hafıza Kullanımı):
1. Bu bilgileri "profil", "kayıt", "veritabanı", "veri" gibi teknik kelimelerle REFERANS ETME
2. "Gördüğüm kadarıyla", "Profiline göre", "Kayıtlarıma göre" gibi meta-referanslar YAPMA
3. Bu bilgileri zaten BİLİYORMUŞ gibi doğal kullan - bir arkadaşın hakkında konuşurken "veritabanımda yazıyor" demezsin
4. İsim sorulursa sadece "{user_name}" de, "Profiline göre {user_name}" DEME
5. Yaş sorulursa "X yaşındasın" de, "Kayıtlarıma göre X yaşındasın" DEME
</system_memory>"""
    
    def get_formatted_identity_block(self) -> str:
        """
        DEPRECATED: Use get_human_memory_instruction() instead.
        
        This method returns technical format that causes robotic LLM responses.
        Kept for backward compatibility only.
        """
        import warnings
        warnings.warn(
            "get_formatted_identity_block() is deprecated. "
            "Use get_human_memory_instruction() for human-like responses.",
            DeprecationWarning,
            stacklevel=2
        )
        # Fallback to new method
        return self.get_human_memory_instruction()
