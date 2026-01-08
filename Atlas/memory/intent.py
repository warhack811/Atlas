import re

def asciify(s: str) -> str:
    """Türkçe karakterleri ASCII'ye çevirir."""
    tr_map = str.maketrans("ıİşŞçÇöÖüÜğĞ", "iiSSccOOuuGG")
    return s.translate(tr_map).lower()

def classify_intent_tr(user_message: str) -> str:
    """
    Kullanıcı mesajının niyetini (intent) sınıflandırır.
    RC-8: Heuristik bazlı (Türkçe).
    """
    msg_raw = user_message.strip()
    msg = asciify(msg_raw)
    
    # Tetikleyici Kelime Grupları (ASCII halleri)
    PERSONAL_TRIGGERS = [
        "hatirliyor musun", "benim", "bana", "gecen", "daha once", "profilim", 
        "tercih", "seviyorum", "sevmiyorum", "aliskanlik", "isim", "ismim", "yas", 
        "yasim", "nerede yasiyorum", "arkadasim", "hobim", "hobi", "adim", "adimi", 
        "kendim", "hakkinda", "arabam", "evim", "memleket", "kardes", "anne", "baba", 
        "isyerim", "okulum", "hayatim", "planlarim", "hedefim", "ilgi", "alisveris", 
        "oyun", "sirket", "esim", "esim", "borc", "borcum", "sifrem",
        "yanlis", "duzelt", "degil", "muydum", "hatirladin",
        "hangi", "takim", "tutuyorum", "ben"
    ]
    
    # RC-11: Explicit Senior Engineer Overrides (CI Triage)
    PERSONAL_OVERRIDES = ["ben", "bana", "benim", "hatirliyor musun", "duzeltme", "unut", "ayar", "tercih"]
    has_personal_override = any(ov in msg for ov in PERSONAL_OVERRIDES)

    TASK_TRIGGERS = [
        "hatirlat", "remind", "yarin", "bugun", "saat", "gun sonra", 
        "pazartesi", "randevu", "todo", "gorev", "yapmam lazim", "planla", "listele"
    ]
    
    FOLLOWUP_TRIGGERS = [
        "az once", "onceki", "devam", "bunu ac", "neden", "ne demek", 
        "detaylandir", "acikla", "baska", "peki ya"
    ]
    
    GENERAL_TRIGGERS = [
        "nedir", "nasil", "kim", "nerede", "hava", "iklim", "tarih", 
        "bilim", "fizik", "ulke", "sehir", "cografya", "teknoloji", 
        "programlama", "python", "java", "javascript", "okyanus", "deniz"
    ]

    # Sosyal selamlaşma koruması
    if re.search(r"\b(merhaba|selam|nasilsin)\b", msg):
        return "MIXED"

    msg_words = msg.translate(str.maketrans("!?.()", "     ")).split()
    is_general = any(kw in msg_words for kw in GENERAL_TRIGGERS)
    
    # Kişisel veya Görev tespiti (Öncelikli)
    is_personal = any(re.search(rf"\b{kw}\b", msg) for kw in PERSONAL_TRIGGERS)
    is_task = any(re.search(rf"\b{kw}\b", msg) for kw in TASK_TRIGGERS)
    
    # Eğer hava durumu ise, personal/task'tan önce GENERAL döner (Korumalı kontrol)
    if "hava" in msg_words:
        return "GENERAL"

    if has_personal_override:
        return "PERSONAL"

    if is_personal:
        return "PERSONAL"
    if is_task:
        return "TASK"
        
    # Takip (Follow-up) tespiti
    if any(re.search(rf"\b{kw}\b", msg) for kw in FOLLOWUP_TRIGGERS):
        return "FOLLOWUP"
    
    # Soru kalıpları (Genel sorgu sinyali - ASCII)
    question_patterns = [r"\?$", r"\bkim\b", r"\bneler\b", r"\bkac\b", r"\bhow\b", r"\bwhat\b"]
    has_q_pattern = any(re.search(pattern, msg) for pattern in question_patterns)
    
    if is_general or has_q_pattern:
        return "GENERAL"
        
    # Varsayılan
    return "MIXED"
