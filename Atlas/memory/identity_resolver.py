"""
Atlas Identity Resolver
-----------------------
FAZ 3: Master User Anchor yönetimi ve 1. şahıs zamir tespiti.

Bu modül, kullanıcı kimliğini temsil eden Master Anchor entity'sini yönetir
ve metindeki 1. şahıs zamirlerini (BEN/BENIM/BANA) tespit eder.

Sorumluluklar:
1. User Anchor: Her kullanıcı için benzersiz bir anchor entity adı üret
2. Pronoun Detection: 1. ve 2. şahıs zamirlerini tespit et
3. Text Normalization: Türkçe karakter normalizasyonu ile metin eşleştirme
"""

# Türkçe karakter normalizasyon haritası (eşleştirme için)
TR_NORMALIZE_MAP = str.maketrans(
    "İĞŞÜÖÇığşüöç",
    "IGSUOCigsüoc"
)

# 1. tekil şahıs zamirleri ve iyelik ekli öz-referanslar (BEN / ADIM / MESLEĞİM vb.)
FIRST_PERSON_PRONOUNS = {
    "BEN", "BENIM", "BANA", "BENDE", "BENDEN",
    "KENDIM", "KENDIMI", "KENDIME", "KENDIMDEN", "KENDIMDE",
    "ADIM", "ISMIM", "MESLEGIM", "YASIM", "LAKABIM", "MEMLEKETIM",
    "KULLANICI"
}

# 2. tekil şahıs zamirleri (SEN/SENIN/SANA vb.)
SECOND_PERSON_PRONOUNS = {
    "SEN", "SENIN", "SANA", "SENDE", "SENDEN"
}

# Diğer zamirler (3. şahıs, çoğul vb. - hala drop edilecekler)
OTHER_PRONOUNS = {
    "O", "ONLAR", "BIZ", "SIZ",
    "HOCAM", "HOCA", "BU", "SU", "BUNLAR", "SUNLAR"
}


def get_user_anchor(user_id: str) -> str:
    """
    Kullanıcı için Master Anchor entity adını döner.
    
    Bu anchor, kullanıcının kimlik bilgilerini (isim, yaş, meslek vb.) 
    temsil eden merkezi bir entity'dir. Her kullanıcının benzersiz bir anchor'u vardır.
    
    Args:
        user_id: Kullanıcı kimliği (session_id)
    
    Returns:
        Master anchor entity adı (örn: "__USER__::session_123")
    
    Örnek:
        >>> get_user_anchor("abc123")
        "__USER__::abc123"
    """
    return f"__USER__::{user_id}"


def is_first_person(token: str) -> bool:
    """
    Verilen token 1. tekil şahıs zamiri mi kontrol eder.
    
    1. şahıs zamirleri: BEN, BENIM, BANA, BENDE, KENDIM vb.
    Bu zamirler FAZ3'te drop edilmeyip user anchor'a map edilir.
    
    Args:
        token: Kontrol edilecek kelime/token (veya phrase)
    
    Returns:
        True ise 1. şahıs zamiri (veya ile başlıyorsa), False değilse
    
    Örnek:
        >>> is_first_person("BEN")
        True
        >>> is_first_person("benim adım")
        True
        >>> is_first_person("Ali")
        False
    """
    normalized = normalize_text_for_match(token)
    if normalized in FIRST_PERSON_PRONOUNS:
        return True

    # Check if phrase starts with a first person pronoun
    parts = normalized.split()
    if len(parts) > 1 and parts[0] in FIRST_PERSON_PRONOUNS:
        return True

    return False


def is_second_person(token: str) -> bool:
    """
    Verilen token 2. tekil şahıs zamiri mi kontrol eder.
    
    2. şahıs zamirleri: SEN, SENIN, SANA, SENDE vb.
    Bu zamirler FAZ3'te hala drop edilir (asistan kimliği tutulmaz).
    
    Args:
        token: Kontrol edilecek kelime/token
    
    Returns:
        True ise 2. şahıs zamiri, False değilse
    """
    normalized = normalize_text_for_match(token)
    if normalized in SECOND_PERSON_PRONOUNS:
        return True

    parts = normalized.split()
    if len(parts) > 1 and parts[0] in SECOND_PERSON_PRONOUNS:
        return True

    return False


def is_other_pronoun(token: str) -> bool:
    """
    Verilen token diğer zamirlerden (O/ONLAR/BIZ/HOCA vb.) biri mi kontrol eder.
    
    Bu zamirler FAZ3'te hala drop edilir.
    
    Args:
        token: Kontrol edilecek kelime/token
    
    Returns:
        True ise diğer zamirlerden biri, False değilse
    """
    normalized = normalize_text_for_match(token)
    if normalized in OTHER_PRONOUNS:
        return True

    parts = normalized.split()
    if len(parts) > 1 and parts[0] in OTHER_PRONOUNS:
        return True

    return False


def normalize_text_for_match(text: str) -> str:
    """
    Metin karşılaştırma için normalize eder.
    
    1. Boşlukları temizle (strip)
    2. Büyük harfe çevir (upper)
    3. Türkçe karakterleri normalize et (İ→I, Ğ→G, Ş→S vb.)
    
    Bu fonksiyon, Türkçe metinlerde tutarlı eşleştirme sağlar.
    
    Args:
        text: Normalize edilecek metin
    
    Returns:
        Normalize edilmiş metin (uppercase, Türkçe karakterler ASCII'ye çevrilmiş)
    
    Örnek:
        >>> normalize_text_for_match("  Benim  ")
        "BENIM"
        >>> normalize_text_for_match("İstanbul")
        "ISTANBUL"
    """
    if not text:
        return ""
    
    # 1. Boşlukları temizle
    cleaned = text.strip()
    
    # 2. Büyük harfe çevir
    upper = cleaned.upper()
    
    # 3. Türkçe karakterleri normalize et
    normalized = upper.translate(TR_NORMALIZE_MAP)
    
    return normalized
