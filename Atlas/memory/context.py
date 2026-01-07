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
from typing import Optional, List, Dict
from Atlas.memory.buffer import MessageBuffer
from Atlas.memory.neo4j_manager import neo4j_manager

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

def normalize_text_for_dedupe(text: str) -> str:
    """Dedupe için metni normalize eder."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    # Turn bazlı rol eklerini temizle (Kullanıcı:, Atlas:)
    text = re.sub(r'^(kullanıcı|atlas|asistan):\s*', '', text)
    # Predicate temizle (örn. 'YAŞAR_YER: Ankara' -> 'Ankara')
    text = re.sub(r'^[a-z_şığüçö]+:\s*', '', text)
    # Baştaki tire ve noktaları temizle
    text = text.lstrip("- ").rstrip(".")
    return text

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
    session_id: Optional[str] = None,
    stats: Optional[dict] = None,
    intent: str = "MIXED"
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
        return "[BİLGİ]: Kullanıcı tercihi gereği kişisel hafıza erişimi kapalıdır."
    
    # RC-7: Alakasız sorgularda hafıza basmama (Noise/Leak Guard)
    irrelevant_keywords = ['hava', 'saat', 'kaç', 'nedir', 'kimdir', '1+', '2+', 'hesapla', 'dünya', 'güneş', 'gezegen', 'uzay', 'okyanus', 'deniz', 'göl', 'nehir', 'en büyük', 'ışık', 'hızı', 'nasıl', '+', '-', '*', '/'] 
    is_irrelevant = any(kw in user_message.lower() for kw in irrelevant_keywords)
    
    # RC-8: GENERAL intent ise Noise Guard daha agresif
    if intent == "GENERAL" or (is_irrelevant and len(user_message.split()) < 5):
        return ""
    
    # neo4j_manager modül seviyesinde import edilmiş (test mocking için)
    from Atlas.memory.identity_resolver import get_user_anchor
    from Atlas.memory.predicate_catalog import get_catalog
    
    # Catalog yükle
    catalog = get_catalog()
    if not catalog:
        return _build_minimal_context()
    
    # Anchor-based identity retrieval
    user_anchor = get_user_anchor(user_id)
    identity_facts = await _retrieve_identity_facts(user_id, user_anchor)
    
    # Hard Facts (EXCLUSIVE predicates)
    raw_hard_facts = await _retrieve_hard_facts(user_id, user_anchor, catalog)
    
    # Soft Signals (ADDITIVE/TEMPORAL predicates)
    raw_soft_signals = await _retrieve_soft_signals(user_id, catalog)
    
    # RC-8: Precision Filtering
    hard_facts = []
    soft_signals = []
    
    # PERSONAL/TASK/FOLLOWUP ise alaka süzgeci
    for fact in raw_hard_facts:
        fact_str = f"{fact.get('subject','')} {fact.get('predicate','')} {fact.get('object','')}"
        overlap = get_token_overlap(fact_str, user_message)
        if overlap > 0 or intent in ["PERSONAL", "TASK"]:
            hard_facts.append(fact)
        elif stats is not None:
             stats["semantic_filtered_out_count"] = stats.get("semantic_filtered_out_count", 0) + 1

    for signal in raw_soft_signals:
        sig_str = f"{signal.get('subject','')} {signal.get('predicate','')} {signal.get('object','')}"
        overlap = get_token_overlap(sig_str, user_message)
        if overlap > 0 or intent == "PERSONAL":
            soft_signals.append(signal)
        elif stats is not None:
             stats["semantic_filtered_out_count"] = stats.get("semantic_filtered_out_count", 0) + 1

    # Open Questions (eksik EXCLUSIVE'ler) - Sadece PERSONAL/TASK'ta göster
    open_questions = []
    if intent in ["PERSONAL", "TASK", "MIXED"]:
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

async def build_chat_context_v1(
    user_id: str,
    session_id: str,
    user_message: str,
    stats: Optional[dict] = None
) -> str:
    """
    Atlas Hibrit Bağlam Paketleyicisi (V3 - RC-8).
    -------------------------------------------
    1. İntent Sınıflandırma
    2. Niyete Göre Adaptive Bütçeleme
    3. Skorlama & Hassas Filtreleme
    """
    from Atlas.memory.neo4j_manager import neo4j_manager
    from Atlas.memory.intent import classify_intent_tr
    
    # 0. Stats Hazırlığı
    if stats is not None:
        stats["layer_usage"] = {"transcript": 0, "episodic": 0, "semantic": 0}
        stats["dedupe_count"] = 0
        stats["semantic_filtered_out_count"] = 0
        stats["episode_filtered_out_count"] = 0

    # 1. Niyet ve Bütçe (RC-8)
    intent = classify_intent_tr(user_message)
    if stats is not None: stats["intent"] = intent

    mode = await neo4j_manager.get_user_memory_mode(user_id)
    budgeter = ContextBudgeter(mode=mode, intent=intent)
    
    all_context_texts = [] # Dedupe havuzu

    # 2. Katmanlar (Transcript -> Semantic -> Episodic önceliği)
    
    # A. Transcript (Son konuşmalar)
    transcript_budget = budgeter.get_layer_budget("transcript")
    turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=20)
    
    transcript_lines = []
    current_transcript_size = 0
    if turns:
        for t in turns:
            role = "Kullanıcı" if t["role"] == "user" else "Atlas"
            line = f"{role}: {t['content']}"
            if current_transcript_size + len(line) + 1 <= transcript_budget:
                transcript_lines.append(line)
                current_transcript_size += len(line) + 1
                all_context_texts.append(line)
            else:
                break
        
        if stats is not None:
            stats["layer_usage"]["transcript"] = current_transcript_size
            
        transcript_text = "\n".join(transcript_lines)
    else:
        transcript_text = "(Henüz bu oturumda konuşma yapılmadı)"

    # B. Semantic Memory (RC-3/RC-8 Context V3 with Filter)
    semantic_budget = budgeter.get_layer_budget("semantic")
    memory_v3 = ""
    # OFF modunda bütçe 0 olsa bile uyarıyı almak için içeri giriyoruz 
    # veya doğrudan build_memory_context_v3 çağırıyoruz.
    if mode == "OFF" or semantic_budget > 0:
        memory_v3_raw = await build_memory_context_v3(user_id, user_message, session_id=session_id, stats=stats, intent=intent)
        v3_lines = memory_v3_raw.split("\n")
        final_v3_lines = []
        current_v3_size = 0
        
        for line in v3_lines:
            if line.startswith("###") or not line.strip():
                final_v3_lines.append(line)
                continue
            if "[BİLGİ]" in line: # OFF modu uyarısı bütçeye takılmamalı veya bütçesiz eklenmeli
                final_v3_lines.append(line)
                continue
            if is_duplicate(line, all_context_texts):
                if stats is not None: stats["dedupe_count"] += 1
                continue
            if current_v3_size + len(line) + 1 <= semantic_budget:
                final_v3_lines.append(line)
                current_v3_size += len(line) + 1
                all_context_texts.append(line)
                
        if stats is not None:
            stats["layer_usage"]["semantic"] = current_v3_size
        memory_v3 = "\n".join(final_v3_lines)

    # C. Episodic (RC-8 Scoring V2: Overlap + Recency)
    episodic_budget = budgeter.get_layer_budget("episodic")
    episodic_text = ""
    if episodic_budget > 0:
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_EPISODE]->(e:Episode {status: 'READY'})
        RETURN e.summary as summary, e.start_turn_index as start, e.end_turn_index as end, 
               e.updated_at as updated_at, COALESCE(e.kind, 'REGULAR') as kind
        ORDER BY e.updated_at DESC
        LIMIT 15
        """
        ep_results = await neo4j_manager.query_graph(query, {"sid": session_id})
        
        scored_episodes = []
        for i, ep in enumerate(ep_results):
            # RC-8 Scoring: Overlap + Recency Bonus
            overlap = get_token_overlap(ep['summary'], user_message)
            # Recency: En yeni 3'e 0.2, sonrakilere 0.1 bonus
            recency_bonus = 0.2 if i < 3 else 0.1
            score = overlap + recency_bonus
            
            if score >= 0.15: # Min threshold
                scored_episodes.append((score, ep))
            elif stats is not None:
                stats["episode_filtered_out_count"] += 1
        
        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        
        selected_ep_lines = []
        curr_ep_size = 0
        reg_count = 0
        cons_count = 0
        
        for score, ep in scored_episodes:
            if ep['kind'] == 'REGULAR' and reg_count >= 2: continue
            if ep['kind'] == 'CONSOLIDATED' and cons_count >= 1: continue
            
            line = f"- {ep['summary']} (Turn {ep.get('start', 0)}-{ep.get('end', 0)})"
            if is_duplicate(line, all_context_texts):
                if stats is not None: stats["dedupe_count"] += 1
                continue
            
            if curr_ep_size + len(line) + 1 <= episodic_budget:
                selected_ep_lines.append(line)
                curr_ep_size += len(line) + 1
                all_context_texts.append(line)
                if ep['kind'] == 'REGULAR': reg_count += 1
                else: cons_count += 1
        
        if stats is not None:
            stats["layer_usage"]["episodic"] = curr_ep_size
        episodic_text = "\n".join(selected_ep_lines)

    # 3. Nihai Birleştirme
    final_parts = []
    if transcript_text:
        final_parts.append(f"SON KONUŞMALAR:\n{transcript_text}")
    if episodic_text:
        final_parts.append(f"İLGİLİ GEÇMİŞ BÖLÜMLER:\n{episodic_text}")
    if memory_v3:
        final_parts.append(memory_v3)
        
    final_output = "\n\n".join(final_parts).strip()
    if stats is not None:
        stats["total_chars"] = len(final_output)
        
    return final_output
