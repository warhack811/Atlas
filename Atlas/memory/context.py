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
import re
from typing import Optional, List, Dict, Any
from Atlas.memory.buffer import MessageBuffer
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.memory.intent import classify_intent_tr
import dateparser
import dateparser.search
from datetime import datetime, timedelta
from Atlas.memory.state import state_manager

# Professional Logging Configuration: Suppress noisy Neo4j notifications about missing properties/labels
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j.io").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

class ContextBudgeter:
    """RC-5/RC-8: Katman bazlı bütçe yönetimi sınıfı."""
    def __init__(self, mode: str = "STD", intent: str = "MIXED"):
        from Atlas.config import CONTEXT_BUDGET, CONTEXT_BUDGET_PROFILES
        self.max_total = CONTEXT_BUDGET.get("max_total_chars", 6000)
        
        # RC-8: Niyete göre profil seçimi
        profile = CONTEXT_BUDGET_PROFILES.get(intent, CONTEXT_BUDGET_PROFILES["MIXED"])
        self.weights = profile.copy()
        
        # OFF modunda semantic bütçesi 0, diğerlerine dağıtılır
        if mode == "OFF":
            # Semantic bütçesini sıfırla ve diğerlerine oransal dağıt
            old_sem = self.weights.get("semantic", 0)
            self.weights["semantic"] = 0.0
            if old_sem > 0:
                # Kalan ağırlıkların toplamı
                other_sum = self.weights["transcript"] + self.weights["episodic"]
                if other_sum > 0:
                    self.weights["transcript"] += old_sem * (self.weights["transcript"] / other_sum)
                    self.weights["episodic"] += old_sem * (self.weights["episodic"] / other_sum)
                else:
                    # Teorik olarak imkansız ama fallback
                    self.weights["transcript"] = 0.6
                    self.weights["episodic"] = 0.4
            
    def get_layer_budget(self, layer_name: str) -> int:
        return int(self.max_total * self.weights.get(layer_name, 0))

from Atlas.memory.text_normalize import normalize_text_for_dedupe

def is_duplicate(new_text: str, existing_texts: List[str], threshold: float = 0.85) -> bool:
    """Basit prefix ve exact match ile dublike kontrolü."""
    norm_new = normalize_text_for_dedupe(new_text)
    for ext in existing_texts:
        norm_ext = normalize_text_for_dedupe(ext)
        if norm_new in norm_ext or norm_ext in norm_new:
            return True
    return False

def get_token_overlap(text1: str, text2: str) -> float:
    """İki metin arasındaki token overlap oranını döner."""
    def get_tokens(t):
        t = re.sub(r'[^\w\s]', ' ', t.lower())
        return set(t.split())
    
    tokens1 = get_tokens(text1)
    tokens2 = get_tokens(text2)
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1.intersection(tokens2)
    # user_message'a (tokens2) göre ne kadar kapsıyor?
    return len(intersection) / len(tokens1) if tokens1 else 0.0

def calculate_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """İki vektör arasındaki kosinüs benzerliğini hesaplar."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    
    import numpy as np
    a = np.array(v1)
    b = np.array(v2)
    
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return float(dot_product / (norm_a * norm_b))

# Yaklaşık token limitleri ve tahminleri
MAX_CONTEXT_TOKENS = 4000
TOKENS_PER_MESSAGE = 100  # Ortalama mesaj başına tahmin edilen token


class ContextBuilder:
    """LLM için kapsamlı bağlam (context) hazırlayan sınıf."""
    
    def __init__(self, session_id: str, user_id: str = "anonymous"):
        self.session_id = session_id
        self.user_id = user_id
        self._system_prompt: Optional[str] = None
        self._user_facts: dict = {}  
        self._semantic_results: list = []  
        self._neo4j_context: str = "" 
    
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
    session_id: Optional[str] = None,
    stats: Optional[dict] = None,
    intent: str = "MIXED",
    trace: Optional[Any] = None
) -> str:
    # Policy kontrolü
    if policy is None:
        from Atlas.memory.neo4j_manager import neo4j_manager
        mode = await neo4j_manager.get_user_memory_mode(user_id)
        from Atlas.memory.memory_policy import get_default_policy
        policy = get_default_policy(mode)
    
    # RC-1/RC-7/RC-8: MemoryPolicy.OFF ise kişisel hafıza kapalı uyarısı her zaman dönmeli
    if policy.mode == "OFF":
        if stats is not None: stats["semantic_mode"] = "OFF"
        if trace: trace.add_reason("OFF mode → semantic access disabled")
        return "[BİLGİ]: Kullanıcı tercihi gereği kişisel hafıza erişimi kapalıdır."
    
    # RC-7: Alakasız sorgularda hafıza basmama (Noise/Leak Guard)
    irrelevant_keywords = ['hava', 'saat', 'kaç', 'nedir', 'kimdir', '1+', '2+', 'hesapla', 'dünya', 'güneş', 'gezegen', 'uzay', 'okyanus', 'deniz', 'göl', 'nehir', 'en büyük', 'ışık', 'hızı', 'nasıl', '+', '-', '*', '/'] 
    is_irrelevant = any(kw in user_message.lower() for kw in irrelevant_keywords)
    
    # RC-8: SADECE GENERAL intent ise Noise Guard ("memory mute") tetiklenebilir.
    # PERSONAL/TASK/FOLLOWUP her durumda context üretmeli.
    if intent == "GENERAL" and (is_irrelevant and len(user_message.split()) < 5):
        if trace: trace.add_reason(f"Noise Guard → filtered (intent={intent}, irrelevant={is_irrelevant})")
        return ""
    
    # neo4j_manager modül seviyesinde import edilmiş (test mocking için)
    from Atlas.memory.identity_resolver import get_user_anchor
    from Atlas.memory.predicate_catalog import get_catalog
    
    # Catalog yükle
    catalog = get_catalog()
    if not catalog:
        return _build_minimal_context()
    
    # RC-11: Trace Metrics initialization
    if trace and not hasattr(trace, "metrics"):
        trace.metrics = {"selected_facts_count": 0, "selected_signals_count": 0, "conflicts_detected_count": 0}

    # Anchor-based identity retrieval
    user_anchor = get_user_anchor(user_id)
    identity_facts = await _retrieve_identity_facts(user_id, user_anchor)
    
    # FAZ-γ Side-effect: Hydrate SessionState identity cache for cross-component awareness
    if session_id and identity_facts:
        state = state_manager.get_state(session_id)
        if not state._identity_hydrated:
            # En güncel bilgileri (DESC order'dan dolayı ilk gelenler) cache'e yaz
            for fact in reversed(identity_facts): # Eskiden yeniye ki yeni olan overwritre etsin
                pred = fact.get("predicate")
                obj = fact.get("object")
                if pred and obj:
                    state._identity_cache[pred] = obj
            state._identity_hydrated = True
            logger.info(f"IDENTITY_RAM_HYDRATED: session_id={session_id}, facts={len(state._identity_cache)}")
    
    # Hard & Soft Facts (RC-3/RC-8)
    from time import perf_counter
    t_start = perf_counter()
    raw_hard_facts = await _retrieve_hard_facts(user_id, user_anchor, catalog)
    raw_soft_signals = await _retrieve_soft_signals(user_id, catalog)
    conflicts = await _retrieve_conflicts(user_id) # RC-11
    
    if trace: 
        trace.timings_ms["fetch_semantic_ms"] += (perf_counter() - t_start) * 1000
        trace.metrics["conflicts_detected_count"] = len(conflicts)
    
    # RC-8: Precision Filtering
    hard_facts = []
    soft_signals = []
    
    # PERSONAL/TASK/FOLLOWUP ise alaka süzgeci
    for fact in raw_hard_facts:
        fact_str = f"{fact.get('subject','')} {fact.get('predicate','')} {fact.get('object','')}"
        overlap = get_token_overlap(fact_str, user_message)
        if overlap > 0 or intent in ["PERSONAL", "TASK"]:
            hard_facts.append(fact)
            if trace: trace.metrics["selected_facts_count"] += 1
        elif stats is not None:
             stats["semantic_filtered_out_count"] = stats.get("semantic_filtered_out_count", 0) + 1

    for signal in raw_soft_signals:
        sig_str = f"{signal.get('subject','')} {signal.get('predicate','')} {signal.get('object','')}"
        overlap = get_token_overlap(sig_str, user_message)
        if overlap > 0 or intent == "PERSONAL":
            soft_signals.append(signal)
            if trace: 
                trace.selected["fact_ids"].append(str(signal.get('id', 'soft_signal')))
                trace.metrics["selected_signals_count"] += 1
        elif stats is not None:
             stats["semantic_filtered_out_count"] = stats.get("semantic_filtered_out_count", 0) + 1
             if trace: trace.filtered_counts["semantic_filtered"] += 1

    # Open Questions (eksik EXCLUSIVE'ler + RC-11 CONFLICTS)
    open_questions = []
    if intent in ["PERSONAL", "TASK", "MIXED"]:
        open_questions = _generate_open_questions(identity_facts, hard_facts, catalog)
        # RC-11: Add conflicts to Open Questions
        for c in conflicts:
            # Daha kısa ve net format
            open_questions.append(f"Hangi bilgi doğru? ({c['predicate']}): '{c['old_value']}' mi yoksa '{c['new_value']}' mi?")
    
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
    # FAZ-M: Catalog'dan dinamik predicate listesi al
    from Atlas.memory.predicate_catalog import get_catalog
    
    catalog = get_catalog()
    if catalog:
        identity_preds = catalog.get_predicates_by_category("identity")
    else:
        identity_preds = []
    
    # Fallback: Catalog yoksa ASCII predicates kullan (DB ile uyumlu)
    if not identity_preds:
        identity_preds = ['ISIM', 'YASI', 'MESLEGI', 'YASAR_YER', 'LAKABI', 'GELDIGI_YER']
    
    logger.info(f"[IDENTITY RETRIEVAL DEBUG] user_id={user_id}, user_anchor={user_anchor}")
    logger.info(f"[IDENTITY RETRIEVAL DEBUG] identity_preds={identity_preds}")
    
    query = """
    MATCH (s:Entity {name: $anchor})-[r:FACT {user_id: $uid}]->(o:Entity)
    WHERE (r.status IS NULL OR r.status = 'ACTIVE' OR r.status = 'CONFLICTED')
      AND r.predicate IN $predicates
    RETURN r.predicate as predicate, o.name as object, r.updated_at as updated_at
    ORDER BY r.updated_at DESC
    LIMIT 10
    """
    
    try:
        result = await neo4j_manager.query_graph(query, {
            "anchor": user_anchor, 
            "uid": user_id,
            "predicates": identity_preds
        })
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
    
    # FAZ-M: Catalog'dan EXCLUSIVE predicates al (dinamik)
    if catalog:
        exclusive_preds = catalog.get_predicates_by_category("hard_facts")
    else:
        exclusive_preds = []
    
    # Fallback: Manual EXCLUSIVE predicates (ASCII, identity hariç)
    if not exclusive_preds:
        exclusive_preds = ['SEVER', 'NEFRET_EDER', 'BILIR', 'YAPABILDIGI']
    
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
    
    # FAZ-M: Catalog'dan ADDITIVE/TEMPORAL predicates al (dinamik)
    if catalog:
        soft_preds = catalog.get_predicates_by_category("soft_signals")
    else:
        soft_preds = []
    
    # Fallback: Manual ADDITIVE/TEMPORAL predicates (ASCII)
    if not soft_preds:
        soft_preds = ['HISSEDIYOR', 'ILGILENIYOR', 'DUSUYOR', 'PLANLADI']
    
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


async def _retrieve_conflicts(user_id: str) -> list:
    """
    RC-11: Çelişkili bilgileri (CONFLICTED) çek.
    """
    query = """
    MATCH (s:Entity)-[r:FACT {user_id: $uid, status: 'CONFLICTED'}]->(o:Entity)
    RETURN r.predicate as predicate, o.name as value, r.updated_at as updated_at
    ORDER BY r.predicate, r.updated_at DESC
    """
    try:
        results = await neo4j_manager.query_graph(query, {"uid": user_id})
        # Aynı predicate için birden fazla CONFLICTED varsa grupla
        conflicts = []
        by_pred = {}
        for res in results:
            pred = res["predicate"]
            if pred not in by_pred: by_pred[pred] = []
            by_pred[pred].append(res["value"])
        
        for pred, values in by_pred.items():
            if len(values) >= 2:
                conflicts.append({
                    "predicate": pred,
                    "old_value": values[1],
                    "new_value": values[0]
                })
        if conflicts:
            logger.info(f"RC-11: {len(conflicts)} adet çelişki Open Question'a dönüştürülecek")
        return conflicts
    except Exception as e:
        logger.warning(f"RC-11 conflicts retrieval hatası: {e}")
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
    
    # NOT: Placeholder soru ekleme kaldırıldı
    # "Kullanıcının adı bilinmiyor" gibi ifadeler LLM'e sızıyor ve
    # robotik yanıtlara neden oluyordu.
    # Bilgi yoksa hiç bir şey ekleme - sessiz kal.
    
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
            parts.append(f"- {fact.get('predicate', 'BİLGİ')}: {fact.get('object', 'N/A')}")
    else:
        parts.append("(Henüz kullanıcı profili bilgisi yok)")
    
    # 2. Hard Facts
    parts.append("\n### Sert Gerçekler (Hard Facts)")
    if hard_facts:
        for fact in hard_facts[:20]:  # Max 20
            subj = fact.get('subject', '__USER__')
            pred = fact.get('predicate', 'BİLGİ')
            obj = fact.get('object', 'N/A')
            parts.append(f"- {subj} - {pred} - {obj}")
    else:
        parts.append("(Henüz sert gerçek bilgisi yok)")
    
    # 3. Soft Signals
    parts.append("\n### Yumuşak Sinyaller (Soft Signals)")
    if soft_signals:
        for signal in soft_signals[:20]:  # Max 20
            subj = signal.get('subject', '__USER__')
            pred = signal.get('predicate', 'SİNYAL')
            obj = signal.get('object', 'N/A')
            parts.append(f"- {subj} - {pred} - {obj}")
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

def is_reference_needed(text: str) -> bool:
    """
    FAZ-Y Final: Türkçe zamirleri (DST) yakalayan Regex kontrolü.
    'o', 'bu', 'şu', 'ora', 'bura', 'şura', 'diğer', 'öbür', 'öteki' ve türevlerini yakalar.
    """
    pattern = r"\b(o|onu|ona|onda|ondan|onlar|onun|bu|bunu|buna|bunda|bundan|bunlar|bunun|şu|şunu|şuna|şunda|şundan|şunlar|şunun|orası|oraya|orada|oradan|burası|buraya|burada|buradan|şurası|şuraya|şurada|şuradan|diğer|diğeri|öbür|öbürü|öteki|ötekisi|ötekinin|öbeğindeki)\b"
    return bool(re.search(pattern, text, re.IGNORECASE))

def extract_date_range(query: str) -> Optional[tuple[datetime, datetime]]:
    """
    Sorgudaki zaman ifadelerini yakalar ve (başlangıç, bitiş) aralığı döner.
    dateparser kullanarak 'dün', 'geçen hafta', '2023 yılında' gibi ifadeleri destekler.
    """
    # dateparser.search.search_dates metni parçalar ve tarihleri bulur
    settings = {
        'PREFER_DATES_FROM': 'past',
        'DATE_ORDER': 'DMY',
        'RETURN_AS_TIMEZONE_AWARE': False
    }
    
    found_dates = dateparser.search.search_dates(query, languages=['tr'], settings=settings)
    
    if not found_dates:
        return None
    
    # En kapsamlı aralığı bulmaya çalış (basit yaklaşım)
    dates = [d[1] for d in found_dates]
    
    if not dates:
        return None
        
    start_date = min(dates)
    end_date = max(dates)
    
    # Eğer tek bir tarih varsa (örneğin 'dün'), o günün başlangıcı ve sonunu al
    if len(dates) == 1 or (end_date - start_date).total_seconds() < 60:
        start_date = start_date.replace(hour=0, minute=0, second=0)
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        # Eğer bir aralık yakalandıysa (örn: 2023 ile 2024 arası), sınırları geniş tut
        start_date = start_date.replace(hour=0, minute=0, second=0)
        end_date = end_date.replace(hour=23, minute=59, second=59)

    return (start_date, end_date)

async def build_chat_context_v1(
    user_id: str,
    session_id: str,
    user_message: str,
    stats: Optional[dict] = None,
    trace: Optional[Any] = None,
    embedder: Optional[Any] = None  # Staff: Added for deterministic testing strategy
) -> str:
    """
    Atlas Hibrit Bağlam Paketleyicisi (V4 - Staff RC-12).
    -------------------------------------------
    1. İntent Sınıflandırma
    2. Niyete Göre Adaptive Bütçeleme
    3. Skorlama & Hassas Filtreleme
    4. Y.6: Hybrid Retrieval (Vector + Graph Fusion) - Opt-in
    5. FAZ-Y Final: Turkish DST & Conflict Injection
    """
    from Atlas.config import (
        ENABLE_HYBRID_RETRIEVAL, BYPASS_VECTOR_SEARCH, BYPASS_GRAPH_SEARCH,
        HYBRID_WEIGHT_VECTOR, HYBRID_WEIGHT_GRAPH, HYBRID_WEIGHT_RECENCY,
        HYBRID_RECENCY_HALFLIFE_DAYS, HYBRID_VECTOR_TOP_K, HYBRID_VECTOR_THRESHOLD,
        HYBRID_GRAPH_TOP_K, BYPASS_MEMORY_INJECTION, BYPASS_ADAPTIVE_BUDGET
    )
    from time import perf_counter
    from Atlas.memory.trace import ContextTrace
    import re

    b_start = perf_counter()
    all_context_texts = [] # Dedupe havuzu
    
    if embedder is None:
        from Atlas.memory.gemini_embedder import GeminiEmbedder
        embedder = GeminiEmbedder()

    # 0. FAZ-γ: Identity Hydration (Freshness check)
    # Stale identity_cache'i build_memory_context_v3 içinde taze olarak çektiğimiz için 
    # burada redundant hydration yapmıyoruz. Sadece state nesnesini alıyoruz.
    state = state_manager.get_state(session_id)

    # 0. FAZ-β: Emotional Continuity (Turn 0 Only)
    emotional_continuity_note = ""
    try:
        turn_count = await neo4j_manager.count_turns(user_id, session_id)
        if turn_count == 0:  # Sadece yeni session başlangıcında
            last_mood_data = await neo4j_manager.get_last_user_mood(user_id)
            if last_mood_data and last_mood_data.get("mood") and last_mood_data.get("timestamp"):
                # Zaman delta hesaplama (UTC-aware)
                from datetime import datetime, timezone
                
                # ISO timestamp parsing (Neo4j datetime format)
                ts_str = last_mood_data["timestamp"]
                # Neo4j datetime format: "2024-01-13T00:00:00Z" veya "2024-01-13T00:00:00.000000000Z"
                if ts_str.endswith("Z"):
                    ts_str = ts_str.replace("Z", "+00:00")
                
                mood_timestamp = datetime.fromisoformat(ts_str)
                # Timezone-unaware ise UTC olarak kabul et
                if mood_timestamp.tzinfo is None:
                    mood_timestamp = mood_timestamp.replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                delta = now - mood_timestamp
                
                # KURAL 1: 3 günden eski -> EKLEME (Unut)
                if delta.days > 3:
                    if trace: trace.add_reason(f"FAZ-β: Mood expired ({delta.days} days old)")
                    pass  # Context'e ekleme
                
                # KURAL 2: 10 dakikadan yeni -> EKLEME (Aktif sohbet devam ediyor)
                elif delta.total_seconds() < 600:
                    if trace: trace.add_reason(f"FAZ-β: Mood too recent ({int(delta.total_seconds())}s ago, active chat)")
                    pass  # Context'e ekleme
                
                else:
                    # Geçerli aralık: 10 dk - 3 gün arası
                    # Türkçe zaman ifadesi oluştur
                    if delta.total_seconds() < 3600:  # 1 saatten az
                        time_expr = "birkaç saat önce"
                    elif delta.days == 0:  # Bugün (1 saatten fazla ama aynı gün)
                        time_expr = "bugün"
                    elif delta.days == 1:  # Dün
                        time_expr = "dün"
                    else:  # 2-3 gün arası
                        time_expr = "birkaç gün önce"
                    
                    mood_value = last_mood_data["mood"]
                    emotional_continuity_note = (
                        f"[ÖNCEKİ DUYGU DURUMU]: Kullanıcı {time_expr} '{mood_value}' hissediyordu. "
                        f"Selamlamada buna değin.\n\n"
                    )
                    if trace: 
                        trace.add_reason(f"FAZ-β: Emotional continuity injected (mood={mood_value}, {time_expr})")
                    logger.info(f"FAZ-β: Emotional continuity activated for {user_id}: {mood_value} ({time_expr})")
    except Exception as e:
        logger.error(f"FAZ-β: Emotional continuity injection failed: {e}")

    # 0.5: USER PROFILE INJECTION (Handled in build_memory_context_v3)
    user_profile_block = ""

    # 1. FAZ-Y Final: Conflicts Injection (Highest Priority)
    conflict_block = ""
    try:
        active_conflicts = await neo4j_manager.get_active_conflicts(user_id, limit=3)
        if active_conflicts:
            conflict_block = "[ÇÖZÜLMESİ GEREKEN DURUM]: Aşağıdaki bilgilerde çelişki var, lütfen kullanıcıyla netleştir:\n"
            for c in active_conflicts:
                conflict_block += f"- {c['subject']} {c['predicate']} bilgisi hem '{c['value']}' hem de başka bir değer olarak görünüyor.\n"
            conflict_block += "\n"
    except Exception as e:
        logger.error(f"Conflict injection failed: {e}")

    # 2. FAZ-Y Final: DST (Dialogue State Tracking) Reference Resolution
    dst_reference_note = ""
    if is_reference_needed(user_message):
        potential_entity = None
        try:
            # a) MessageBuffer'dan (RAM) bulmaya çalış
            recent_history = MessageBuffer.get_llm_messages(session_id, limit=2)
            for msg in reversed(recent_history):
                # Basit büyük harfle başlayan kelime yakalama (isim/nesne tahmini)
                proper_nouns = re.findall(r'\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\b', msg["content"])
                if proper_nouns:
                    potential_entity = proper_nouns[0]
                    break
            
            # b) RAM'de yoksa Neo4j'den sor
            if not potential_entity:
                potential_entity = await neo4j_manager.get_last_active_entity(user_id, session_id)
                
            if potential_entity:
                dst_reference_note = f"[DST_REFERENCE]: Kullanıcı '{potential_entity}' hakkında konuşuyor olabilir.\n\n"
        except Exception as e:
            logger.error(f"DST resolution failed: {e}")

    # --- Phase 2.5: Temporal Awareness ---
    temporal_context = ""
    date_range = extract_date_range(user_message)
    if date_range:
        start_dt, end_dt = date_range
        logger.info(f"Temporal Match: {start_dt} - {end_dt}")
        temporal_facts = await neo4j_manager.get_facts_by_date_range(user_id, start_dt, end_dt)
        if temporal_facts:
            temporal_context = f"\n[ZAMAN FİLTRESİ]: Kullanıcının belirttiği tarih aralığındaki ({start_dt.date()} - {end_dt.date()}) kayıtlar:\n"
            for f in temporal_facts[:10]:
                temporal_context += f"- {f['subject']} {f['predicate']} {f['object']} (Tarih: {f.get('ts','')})\n"
            temporal_context += "\n"

    # 3. Niyet ve Bütçe (RC-8)
    if trace is None:
        trace = ContextTrace(request_id=f"trace_{int(perf_counter())}", user_id=user_id, session_id=session_id)
    
    intent = classify_intent_tr(user_message)
    if stats is not None: stats["intent"] = intent
    trace.intent = intent

    mode = await neo4j_manager.get_user_memory_mode(user_id)
    trace.memory_mode = mode
    
    budgeter = ContextBudgeter(mode=mode, intent=intent if not BYPASS_ADAPTIVE_BUDGET else "MIXED")
    
    # 4. Layers Retrieval
    # A. Transcript (Tiered Retrieval)
    transcript_budget = budgeter.get_layer_budget("transcript")
    
    # Tier 1: Active Session (Current chat)
    active_turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=20)
    
    # Tier 2: Contextual Bridge (Global Recency for cross-session continuity)
    # If active session is very new (< 5 turns), fetch last 10 turns globally
    bridge_turns = []
    from Atlas.config import ENABLE_CONTEXT_BRIDGE
    if ENABLE_CONTEXT_BRIDGE and len(active_turns) < 5:
        bridge_turns = await neo4j_manager.get_global_recent_turns(user_id, exclude_session_id=session_id, limit=10)
    
    transcript_lines = []
    
    # Prepend Bridge turns if they exist
    if bridge_turns:
        if trace: trace.active_tiers.append("Bridge")
        transcript_lines.append("[ÖNCEKİ YAKIN KONUŞMALAR (Diğer Oturumlardan)]:")
        for t in bridge_turns:
            line = f"- {'Kullanıcı' if t['role'] == 'user' else 'Atlas'}: {t['content']}"
            transcript_lines.append(line)
        transcript_lines.append("") # Spacer
        transcript_lines.append("[BU OTURUMDAKİ KONUŞMALAR]:")

    if active_turns:
        if trace: trace.active_tiers.append("Active")
        for t in active_turns:
            line = f"{'Kullanıcı' if t['role'] == 'user' else 'Atlas'}: {t['content']}"
            all_context_texts.append(line) # Dedupe havuzuna ekle (Episode tekrarını önlemek için)
            transcript_lines.append(line)
    
    if not active_turns and not bridge_turns:
        transcript_text = "(Henüz konuşma yok)"
    else:
        transcript_text = "\n".join(transcript_lines)

    # B. Episodic Memory (RC-3/RC-8/RC-10)
    episodic_budget = budgeter.get_layer_budget("episodic")
    episodic_text = ""
    if mode != "OFF" and episodic_budget > 0:
        query = """
        MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session)-[:HAS_EPISODE]->(e:Episode {status: "READY"})
        WHERE s.id <> $sid
        RETURN e.summary as summary, e.embedding as embedding, e.kind as kind, 
               e.start_turn_index as start, e.end_turn_index as end, e.id as id
        LIMIT 10
        """
        results = await neo4j_manager.query_graph(query, {"uid": user_id, "sid": session_id})
        scored_episodes = []
        query_emb = await embedder.embed(user_message)
        for res in results:
            score = 0.0
            if res.get("embedding"):
                score = calculate_cosine_similarity(query_emb, res.get("embedding"))
            if res.get("kind") == "CONSOLIDATED": score *= 1.1 
            scored_episodes.append((score, res))
        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        selected_ep_lines = []
        curr_ep_size = 0
        for score, ep in scored_episodes:
            line = f"- {ep['summary']} (Turn {ep.get('start', 0)}-{ep.get('end', 0)})"
            if is_duplicate(line, all_context_texts): continue
            if curr_ep_size + len(line) + 1 <= episodic_budget:
                selected_ep_lines.append(line)
                curr_ep_size += len(line) + 1
                all_context_texts.append(line)
        episodic_text = "\n".join(selected_ep_lines)
        if episodic_text and trace:
            trace.active_tiers.append("Episodic")

    # C. Semantic V3
    memory_v3 = await build_memory_context_v3(user_id, user_message, session_id=session_id, stats=stats, intent=intent, trace=trace)

    # D. Hybrid Retrieval (V4)
    hybrid_context = ""
    if ENABLE_HYBRID_RETRIEVAL:
        try:
            v_candidates = await _build_hybrid_candidates_vector(user_id, user_message, embedder)
            g_candidates = await _build_hybrid_candidates_graph(user_id)
            fused = _score_fuse_candidates(v_candidates + g_candidates)
            unique_hybrid = _dedupe_top_k(fused, all_context_texts)
            if unique_hybrid:
                h_lines = [f"- [{u['source'].upper()} | Skor: {u['final_score']:.2f}]: {u['text'][:200]}" for u in unique_hybrid]
                hybrid_context = "\n### Hibrit Hafıza (Vector+Graph)\n" + "\n".join(h_lines)
        except Exception as e:
            logger.error(f"Hybrid retrieval breakdown: {e}")
    
    # 0.5: USER PROFILE INJECTION (Handled in build_memory_context_v3 for freshness)
    # We rely on memory_v3 for the Profile block to avoid redundant DB queries and sync issues.

    # 5. Final Assembly (PREPEND Conflicts & DST)
    final_parts = []
    if transcript_text:
        final_parts.append(f"SON KONUŞMALAR:\n{transcript_text}")
    if episodic_text:
         final_parts.append(f"İLGİLİ GEÇMİŞ BÖLÜMLER:\n{episodic_text}")
    if memory_v3:
        final_parts.append(memory_v3)
    if hybrid_context:
        final_parts.append(hybrid_context)
        
    final_main = "\n\n".join(final_parts).strip()
    
    # FAZ-α.2: Topic Injection
    state = state_manager.get_state(session_id)
    topic_block = f"[AKTİF OTURUM KONUSU]: {state.current_topic or 'Genel'}\n\n"
    
    # FAZ-β: Emotional continuity PREPEND (Highest priority for greeting)
    # RC-12: user_profile_block is now part of memory_v3 (final_main) to avoid duplication.
    final_output = emotional_continuity_note + conflict_block + dst_reference_note + topic_block + temporal_context + final_main
    
    if trace: 
        trace.timings_ms["build_total_ms"] = (perf_counter() - b_start) * 1000
        if stats is not None: 
            stats["context_build_ms"] = trace.timings_ms["build_total_ms"]
            stats["total_chars"] = len(final_output)
            
    return final_output

# --- Hybrid Retrieval Helper Functions [RC-12] ---

async def _build_hybrid_candidates_vector(user_id: str, query: str, embedder: Any) -> List[Dict]:
    """Fetches candidates from Qdrant vector database."""
    from Atlas.config import BYPASS_VECTOR_SEARCH, HYBRID_VECTOR_TOP_K, HYBRID_VECTOR_THRESHOLD
    if BYPASS_VECTOR_SEARCH: return []
    
    try:
        from Atlas.memory.qdrant_manager import QdrantManager
        q_manager = QdrantManager()
        query_emb = await embedder.embed(query)
        v_results = await q_manager.vector_search(
            query_embedding=query_emb,
            user_id=user_id,
            top_k=HYBRID_VECTOR_TOP_K,
            score_threshold=HYBRID_VECTOR_THRESHOLD
        )
        return [{
            "id": vr.get("episode_id"),
            "text": vr.get("text", ""),
            "vector_score": vr.get("score", 0.0),
            "graph_score": 0.0,
            "timestamp": vr.get("timestamp", ""),
            "source": "vector"
        } for vr in v_results]
    except Exception as e:
        logger.warning(f"Vector retrieval failed: {e}")
        return []

async def _build_hybrid_candidates_graph(user_id: str) -> List[Dict]:
    """Fetches facts from Neo4j graph database."""
    from Atlas.config import BYPASS_GRAPH_SEARCH, HYBRID_GRAPH_TOP_K
    if BYPASS_GRAPH_SEARCH: return []
    
    try:
        from Atlas.memory.neo4j_manager import neo4j_manager
        graph_query = """
        // 1-Hop Facts
        MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
        WHERE (r.status IS NULL OR r.status = 'ACTIVE')
        WITH s, r, o
        RETURN s.name as subject, r.predicate as predicate, o.name as object,
               coalesce(r.confidence, 0.5) as confidence, coalesce(r.updated_at, '') as ts, 1 as hop
        ORDER BY ts DESC LIMIT $limit
        
        UNION
        
        // 2-Hop Facts (Limitli ve kontrollü)
        MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(m:Entity)-[r2:FACT {user_id: $uid}]->(o:Entity)
        WHERE (r.status IS NULL OR r.status = 'ACTIVE') AND (r2.status IS NULL OR r2.status = 'ACTIVE')
        WITH s, r, m, r2, o
        RETURN s.name + ' (' + r.predicate + ') -> ' + m.name as subject, 
               r2.predicate as predicate, o.name as object,
               coalesce(r2.confidence, 0.4) as confidence, coalesce(r2.updated_at, '') as ts, 2 as hop
        ORDER BY ts DESC LIMIT 5
        """
        g_results = await neo4j_manager.query_graph(graph_query, {"uid": user_id, "limit": HYBRID_GRAPH_TOP_K})
        return [{
            "id": None,
            "text": f"{gr['subject']} {gr['predicate']} {gr['object']}",
            "vector_score": 0.0,
            "graph_score": gr.get("confidence", 0.5),
            "timestamp": gr.get("ts", ""),
            "source": "graph"
        } for gr in g_results]
    except Exception as e:
        logger.warning(f"Graph retrieval failed: {e}")
        return []

def _score_fuse_candidates(candidates: List[Dict]) -> List[Dict]:
    """Applies weight fusion and recency decay to candidates."""
    from Atlas.config import (
        HYBRID_WEIGHT_VECTOR, HYBRID_WEIGHT_GRAPH, HYBRID_WEIGHT_RECENCY,
        HYBRID_RECENCY_HALFLIFE_DAYS
    )
    import math
    from datetime import datetime
    
    def get_recency(ts_str):
        if not ts_str: return 0.0
        try:
            delta = datetime.utcnow() - datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            days = delta.total_seconds() / 86400
            # FAZ-Y: math.exp tabanlı exponential decay (halflife=7 gün)
            halflife = 7.0 # ROADMAP ADIM 2.1
            decay_constant = math.log(2) / halflife
            return math.exp(-decay_constant * days)
        except: return 0.0

    for c in candidates:
        r_score = get_recency(c.get("timestamp"))
        c["final_score"] = (HYBRID_WEIGHT_VECTOR * c["vector_score"] + 
                            HYBRID_WEIGHT_GRAPH * c["graph_score"] + 
                            HYBRID_WEIGHT_RECENCY * r_score)
    return candidates

def _dedupe_top_k(candidates: List[Dict], existing_texts: List[str], top_k: int = 10) -> List[Dict]:
    """Deduplicates candidates and returns top_k."""
    import hashlib
    # Modüler text_normalize import'u fonksiyon içinde yapılır (circular import riskini azaltmak için)
    from Atlas.memory.text_normalize import normalize_text_for_dedupe
    
    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    seen_hashes = set()
    unique_results = []
    
    for c in candidates:
        h = hashlib.md5(normalize_text_for_dedupe(c["text"]).encode()).hexdigest()
        if h not in seen_hashes and not is_duplicate(c["text"], existing_texts):
            seen_hashes.add(h)
            unique_results.append(c)
            if len(unique_results) >= top_k: break
            
    return unique_results
