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

import logging
from typing import Optional
from Atlas.memory.buffer import MessageBuffer
from Atlas.memory.neo4j_manager import neo4j_manager  # Modül seviyesi import: test mocking için standardizasyon

logger = logging.getLogger(__name__)


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
        Neo4j'den kullanıcıya özel hibrit bağlamı (context) çeker. (RC-3)
        Transcript + Episodic + Context V3 birleşimi.
        """
        from Atlas.memory.context import build_chat_context_v1
        return await build_chat_context_v1(user_id, self.session_id, message)
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
                from Atlas.memory.facts import UserFact
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


# ==============================================================================
# FAZ 6: Context Packaging V3 - Hard/Soft/Open Questions
# ==============================================================================

async def build_memory_context_v3(
    user_id: str,
    user_message: str,
    policy = None,
    session_id: Optional[str] = None
) -> str:
    """
    FAZ 6: LLM için 3-bölmeli hafıza context'i oluşturur.
    
    Bölümler:
    - Kullanıcı Profili: Identity bilgileri (__USER__ anchor'dan)
    - Sert Gerçekler (Hard Facts): EXCLUSIVE predicates (İSİM, YAŞI, MESLEĞİ vb.)
    - Yumuşak Sinyaller (Soft Signals): ADDITIVE/TEMPORAL predicates (SEVER, ARKADAŞI vb.)
    - Açık Sorular (Open Questions): Eksik EXCLUSIVE bilgiler veya çelişkiler
    
    Args:
        user_id: Kullanıcı kimliği (session_id)
        user_message: Kullanıcının mesajı (relevance için kullanılabilir)
        policy: MemoryPolicy instance (None ise varsayılan STANDARD)
    
    Returns:
        Formatlanmış context string
    
    Kurallar:
    - MemoryPolicy.OFF ise kişisel hafıza retrieval KAPALI
    - Sadece ACTIVE status (SUPERSEDED/RETRACTED hariç)
    - Hard: max 20 satır, Soft: max 20 satır, Open: max 10 satır
    - En son güncellenler önce (updated_at desc)
    """
    # neo4j_manager modül seviyesinde import edilmiş (test mocking için)
    from Atlas.memory.identity_resolver import get_user_anchor
    from Atlas.memory.predicate_catalog import get_catalog
    from Atlas.memory.memory_policy import load_policy_for_user
    
    # Policy kontrolü
    if policy is None:
        # RC-1: Kullanıcı bazlı modu Neo4j'den çek
        from Atlas.memory.neo4j_manager import neo4j_manager
        mode = await neo4j_manager.get_user_memory_mode(user_id)
        from Atlas.memory.memory_policy import get_default_policy
        policy = get_default_policy(mode)
    
    # MemoryPolicy.OFF ise kişisel hafıza kapalı
    if policy.mode == "OFF":
        logger.info(f"Memory: {user_id} için hafıza modu OFF. Retrieval bypass ediliyor.")
        return "[BİLGİ]: Kullanıcı tercihi gereği kişisel hafıza erişimi kapalıdır."
    
    # Catalog yükle
    catalog = get_catalog()
    if not catalog:
        logger.warning("FAZ6: Predicate catalog yüklenemedi, minimal context döndürülüyor")
        return _build_minimal_context()
    
    # Anchor-based identity retrieval
    user_anchor = get_user_anchor(user_id)
    identity_facts = await _retrieve_identity_facts(user_id, user_anchor)
    
    # Hard Facts (EXCLUSIVE predicates)
    hard_facts = await _retrieve_hard_facts(user_id, user_anchor, catalog)
    
    # Soft Signals (ADDITIVE/TEMPORAL predicates)
    soft_signals = await _retrieve_soft_signals(user_id, catalog)
    
    # Open Questions (eksik EXCLUSIVE'ler)
    open_questions = _generate_open_questions(identity_facts, hard_facts, catalog)
    
    # Format oluştur
    return _format_context_v3(identity_facts, hard_facts, soft_signals, open_questions)


def _build_off_mode_context() -> str:
    """
    MemoryPolicy.OFF modunda döndürülecek context.
    Kişisel hafıza retrieval kapalıdır.
    """
    return """### Kullanıcı Profili
(Hafıza modu kapalı - kişisel bilgi yok)

### Sert Gerçekler (Hard Facts)
(Hafıza modu kapalı)

### Yumuşak Sinyaller (Soft Signals)
(Hafıza modu kapalı)

### Açık Sorular (Open Questions)
(Hafıza modu kapalı)"""


def _build_minimal_context() -> str:
    """
    Catalog yüklenemediğinde minimal context.
    """
    return """### Kullanıcı Profili
(Bellek sistemi geçici olarak kullanılamıyor)

### Sert Gerçekler (Hard Facts)
(Bellek sistemi geçici olarak kullanılamıyor)

### Yumuşak Sinyaller (Soft Signals)
(Bellek sistemi geçici olarak kullanılamıyor)

### Açık Sorular (Open Questions)
(Bellek sistemi geçici olarak kullanılamıyor)"""


async def _retrieve_identity_facts(user_id: str, user_anchor: str) -> list:
    """
    __USER__ anchor'dan identity bilgilerini çek.
    
    Args:
        user_id: Kullanıcı ID
        user_anchor: __USER__::<uid> anchor entity
    
    Returns:
        List of {predicate, object} dicts
    """
    # Global neo4j_manager kullanılıyor (test mocking için)
    
    # Sadece identity category predicates
    query = """
    MATCH (s:Entity {name: $anchor})-[r:FACT {user_id: $uid}]->(o:Entity)
    WHERE (r.status IS NULL OR r.status = 'ACTIVE')
      AND r.predicate IN ['İSİM', 'YAŞI', 'MESLEĞİ', 'YAŞAR_YER', 'LAKABI', 'GELDİĞİ_YER']
    RETURN r.predicate as predicate, o.name as object, r.updated_at as updated_at
    ORDER BY r.updated_at DESC
    LIMIT 10
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {"anchor": user_anchor, "uid": user_id})
        return result if result else []
    except Exception as e:
        logger.warning(f"FAZ6 identity retrieval hatası: {e}")
        return []


async def _retrieve_hard_facts(user_id: str, user_anchor: str, catalog) -> list:
    """
    EXCLUSIVE predicates'leri çek (Hard Facts).
    Identity predicates hariç (onlar zaten identity_facts'te).
    
    Args:
        user_id: Kullanıcı ID
        user_anchor: Anchor entity (hard facts için subject olarak kullanılabilir)
        catalog: PredicateCatalog instance
    
    Returns:
        List of {subject, predicate, object} dicts
    """
    # Global neo4j_manager kullanılıyor (test mocking için)
    
    # Catalog'dan EXCLUSIVE predicates al
    exclusive_preds = []
    for key, entry in catalog.by_key.items():
        if entry.get("type") == "EXCLUSIVE" and entry.get("enabled", True):
            canonical = entry.get("canonical", key)
            # Identity predicates'leri hariç tut (zaten identity_facts'te)
            if canonical not in ['İSİM', 'YAŞI', 'MESLEĞİ', 'YAŞAR_YER', 'LAKABI', 'GELDİĞİ_YER']:
                exclusive_preds.append(canonical)
    
    if not exclusive_preds:
        return []
    
    # Neo4j'den çek
    query = """
    MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
    WHERE (r.status IS NULL OR r.status = 'ACTIVE')
      AND r.predicate IN $predicates
    RETURN s.name as subject, r.predicate as predicate, o.name as object, r.updated_at as updated_at
    ORDER BY r.updated_at DESC
    LIMIT 20
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {"uid": user_id, "predicates": exclusive_preds})
        return result if result else []
    except Exception as e:
        logger.warning(f"FAZ6 hard facts retrieval hatası: {e}")
        return []


async def _retrieve_soft_signals(user_id: str, catalog) -> list:
    """
    ADDITIVE/TEMPORAL predicates'leri çek (Soft Signals).
    
    Args:
        user_id: Kullanıcı ID
        catalog: PredicateCatalog instance
    
    Returns:
        List of {subject, predicate, object} dicts
    """
    # Global neo4j_manager kullanılıyor (test mocking için)
    
    # Catalog'dan ADDITIVE/TEMPORAL predicates al
    soft_preds = []
    for key, entry in catalog.by_key.items():
        pred_type = entry.get("type")
        if pred_type in ["ADDITIVE", "TEMPORAL"] and entry.get("enabled", True):
            canonical = entry.get("canonical", key)
            soft_preds.append(canonical)
    
    if not soft_preds:
        return []
    
    # Neo4j'den çek
    query = """
    MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
    WHERE (r.status IS NULL OR r.status = 'ACTIVE')
      AND r.predicate IN $predicates
    RETURN s.name as subject, r.predicate as predicate, o.name as object, r.updated_at as updated_at
    ORDER BY r.updated_at DESC
    LIMIT 20
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {"uid": user_id, "predicates": soft_preds})
        return result if result else []
    except Exception as e:
        logger.warning(f"FAZ6 soft signals retrieval hatası: {e}")
        return []


def _generate_open_questions(identity_facts: list, hard_facts: list, catalog) -> list:
    """
    Açık soruları belirle.
    
    MVP düzeyinde: 
    - EXCLUSIVE predicates için ACTIVE bir değer yoksa "eksik bilgi" olarak işaretle
    
    Args:
        identity_facts: Identity bilgileri
        hard_facts: Hard facts
        catalog: Predicate catalog
    
    Returns:
        List of question strings
    """
    questions = []
    
    # Bilinen EXCLUSIVE predicates
    known_predicates = set()
    for fact in identity_facts:
        known_predicates.add(fact.get("predicate"))
    for fact in hard_facts:
        known_predicates.add(fact.get("predicate"))
    
    # Temel identity predicates'leri kontrol et
    essential_identity = {
        'İSİM': 'Kullanıcının adı bilinmiyor',
        'YAŞI': 'Kullanıcının yaşı bilinmiyor',
        'MESLEĞİ': 'Kullanıcının mesleği bilinmiyor',
        'YAŞAR_YER': 'Kullanıcının yaşadığı yer bilinmiyor'
    }
    
    for pred, question in essential_identity.items():
        if pred not in known_predicates:
            questions.append(question)
    
    # Max 10 soru
    return questions[:10]


def _format_context_v3(
    identity_facts: list,
    hard_facts: list,
    soft_signals: list,
    open_questions: list
) -> str:
    """
    V3 formatında context string oluştur.
    
    Format:
    ### Kullanıcı Profili
    - İSİM: ...
    ### Sert Gerçekler (Hard Facts)
    - subject - predicate - object
    ### Yumuşak Sinyaller (Soft Signals)
    - subject - predicate - object
    ### Açık Sorular (Open Questions)
    - ...
    """
    parts = []
    
    # 1. Kullanıcı Profili
    parts.append("### Kullanıcı Profili")
    if identity_facts:
        for fact in identity_facts[:10]:  # Max 10
            parts.append(f"- {fact['predicate']}: {fact['object']}")
    else:
        parts.append("(Henüz kullanıcı profili bilgisi yok)")
    
    # 2. Hard Facts
    parts.append("\n### Sert Gerçekler (Hard Facts)")
    if hard_facts:
        for fact in hard_facts[:20]:  # Max 20
            parts.append(f"- {fact['subject']} - {fact['predicate']} - {fact['object']}")
    else:
        parts.append("(Henüz sert gerçek bilgisi yok)")
    
    # 3. Soft Signals
    parts.append("\n### Yumuşak Sinyaller (Soft Signals)")
    if soft_signals:
        for signal in soft_signals[:20]:  # Max 20
            parts.append(f"- {signal['subject']} - {signal['predicate']} - {signal['object']}")
    else:
        parts.append("(Henüz yumuşak sinyal bilgisi yok)")
    
    # 4. Open Questions
    parts.append("\n### Açık Sorular (Open Questions)")
    if open_questions:
        for question in open_questions[:10]:  # Max 10
            parts.append(f"- {question}")
    else:
        parts.append("(Şu an açık soru yok)")
    
    return "\n".join(parts)

async def build_chat_context_v1(
    user_id: str,
    session_id: str,
    user_message: str
) -> str:
    """
    Atlas Hibrit Bağlam Paketleyicisi (V1). (RC-3)
    -------------------------------------------
    1. Yakın Geçmiş (Transcript - Son 12 Mesaj)
    2. Uzak Geçmiş (Episodic - Son 3 Özet)
    3. Kişisel Hafıza (Context V3 - Facts/Signals)
    """
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    # 1. Transcript (Son 12 Turn)
    turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=12)
    transcript_text = ""
    if turns:
        lines = []
        for t in turns:
            role = "Kullanıcı" if t["role"] == "user" else "Atlas"
            lines.append(f"{role}: {t['content']}")
        transcript_text = "\n".join(lines)
    else:
        transcript_text = "(Henüz bu oturumda konuşma yapılmadı)"

    # 2. Episodic (Son 3 Episode)
    episodes = await neo4j_manager.get_recent_episodes(user_id, session_id, limit=3)
    episodic_text = ""
    if episodes:
        lines = []
        for ep in episodes:
            lines.append(f"- {ep['summary']} (Turn {ep['start_turn']}-{ep['end_turn']})")
        episodic_text = "\n".join(lines)
    else:
        episodic_text = "(Henüz özetlenmiş eski bir konuşma yok)"

    # 3. Kişisel Hafıza (Context V3)
    memory_v3 = await build_memory_context_v3(user_id, user_message, session_id=session_id)

    # Hibrit Paketleme
    full_context = f"""
### YAKIN GEÇMİŞ (Transcript)
{transcript_text}

### OTURUM ÖZETLERİ (Uzak Geçmiş)
{episodic_text}

### KAYITLI KİŞİSEL BİLGİLER (Long-term)
{memory_v3}
"""
    return full_context.strip()
