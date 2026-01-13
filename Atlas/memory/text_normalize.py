import re

def normalize_text_for_dedupe(text: str) -> str:
    """Dedupe ve cache için metni normalize eder."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    # Turn bazlı rol eklerini temizle (Kullanıcı:, Atlas:)
    text = re.sub(r'^(kullanıcı|atlas|asistan):\s*', '', text)
    # Predicate temizle (örn. 'YAŞAR_YER: Ankara' -> 'Ankara')
    text = re.sub(r'^[a-z_şığüçö]+:\s*', '', text)
    # Baştaki tire ve noktaları temizle
    text = text.lstrip("- ").rstrip(".")
    return text
