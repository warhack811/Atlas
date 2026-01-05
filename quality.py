"""
ATLAS Yönlendirici - Kalite Kapısı (Quality Gate)
--------------------------------------------------
Bu bileşen, üretilen yanıtların kullanıcıya sunulmadan önce belirlenen kalite
kriterlerine (dil, uzunluk, format vb.) uyup uymadığını denetler.

Temel Sorumluluklar:
1. Dil Uyumluluğu: Yanıtın Türkçe karakter kurallarına ve dil saflığına uygunluğu.
2. Format Denetimi: Kodlama gibi teknik niyetlerde markdown bloklarının varlığı.
3. Uzunluk Kontrolü: Çok kısa veya içi boş yanıtların tespiti.
4. Tekrar Tespiti: Modelin döngüye girmesi (looping) ve kendini tekrar etmesi.
5. Markdown Doğrulaması: Kapanmamış kod blokları gibi sözdizimi hatalarını yakalama.
6. Red Tespiti: Modelin standart "bir yapay zeka modeli olarak..." gibi kaçamak yanıtları.
"""

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class QualityIssue:
    """Tespit edilen bir kalite sorununu tanımlayan sınıf."""
    check: str    # Denetim türü: 'DİL', 'FORMAT', 'UZUNLUK', 'TEKRAR' vb.
    details: str  # Sorunun teknik detayı
    severity: str # Ciddiyet: 'UYARI' (WARNING) veya 'ENGELLEME' (BLOCKER)

class QualityGate:
    """Üretilen yanıtların yüksek kalitede olmasını sağlayan kalite kapısı."""
    
    # Türkçe'ye özgü karakterler (küçük harf)
    TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
    
    def check_quality(self, text: str, intent: str) -> Tuple[bool, List[QualityIssue]]:
        """
        Nihai yanıtı kalite süzgecinden geçirir.
        Dönüş: (geçti_mi, sorunlar_listesi)
        """
        issues = []
        is_passed = True
        
        # 1. Uzunluk Kontrolü
        if len(text.strip()) < 10:
            issues.append(QualityIssue(
                check="UZUNLUK",
                details=f"Yanıt çok kısa ({len(text)} karakter)",
                severity="UYARI"
            ))
            
        # 2. Format Kontrolü (Kodlama)
        if intent in ["coding", "debug", "refactor"]:
            if "```" not in text:
                issues.append(QualityIssue(
                    check="FORMAT",
                    details="Kodlama niyeti tespit edildi ancak kod bloğu bulunamadı",
                    severity="UYARI"
                ))
        
        # 3. Dil Kontrolü (Sezgisel)
        # Sadece basit bir kontrol: Türkçe karakter var mı?
        # Bu çok katı olmamalı (sadece kod varsa TR karakter olmayabilir)
        if intent not in ["coding", "math"]:
            has_tr_char = any(c in text for c in self.TR_CHARS)
            if not has_tr_char and len(text) > 50:
                issues.append(QualityIssue(
                    check="DİL",
                    details="Metin ağırlıklı yanıtta Türkçe karakter bulunamadı",
                    severity="UYARI"
                ))

        # 4. Ret Tespiti (Standart AI Uyarıları)
        refusal_phrases = ["as an ai language model", "i cannot", "yapay zeka modeli olarak"]
        if any(p in text.lower() for p in refusal_phrases):
             issues.append(QualityIssue(
                check="RED",
                details="Model cevap vermeyi reddetti (Standart feragatname tespit edildi)",
                severity="UYARI"
            ))

        # 5. Tekrar/Döngü Kontrolü
        # Basit kontrol: Aynı satır 3 kereden fazla tekrar ediyor mu?
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 10]
        from collections import Counter
        if lines:
            most_common = Counter(lines).most_common(1)
            if most_common and most_common[0][1] >= 3:
                issues.append(QualityIssue(
                    check="TEKRAR",
                    details=f"Metin tekrarı tespit edildi: '{most_common[0][0][:20]}...'",
                    severity="ENGELLEME"
                ))

        # 6. Markdown Sözdizimi Kontrolü (Kapanmamış Bloklar)
        if text.count("```") % 2 != 0:
             issues.append(QualityIssue(
                check="MARKDOWN",
                details="Kapanmamış kod bloğu (```) tespit edildi",
                severity="UYARI"
            ))

        # 7. İngilizce Kelime Tespiti (Saf Türkçe Zorunluluğu)
        # Kod blokları dışındaki metni analiz et
        if intent not in ["coding", "debug", "refactor", "math"]:
            english_issues = self._check_english_words(text)
            if english_issues:
                issues.append(QualityIssue(
                    check="LANGUAGE_PURITY",
                    details=f"İngilizce kelimeler tespit edildi: {', '.join(english_issues[:5])}",
                    severity="WARNING"
                ))

        # KRİTİK HATA (BLOCKER) varsa geçişi engelle
        if any(i.severity == "ENGELLEME" or i.severity == "BLOCKER" for i in issues):
            is_passed = False
            
        return is_passed, issues
    
    def _check_english_words(self, text: str) -> list[str]:
        """
        Metinde sık karıştırılan İngilizce kelimeleri tespit et.
        Kod blokları hariç tutulur.
        """
        import re
        
        # Kod bloklarını çıkar
        clean_text = re.sub(r'```[\s\S]*?```', '', text)
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        
        # Sık karıştırılan İngilizce kelimeler (teknik terimler hariç)
        COMMON_ENGLISH_WORDS = [
            # Yaygın karıştırılanlar
            "message", "imagined", "actually", "basically", "literally", "really",
            "because", "about", "think", "maybe", "something", "anything",
            "nothing", "everything", "someone", "anyone", "everyone",
            "please", "sorry", "thank", "thanks", "welcome", "hello", "bye",
            "probably", "definitely", "obviously", "honestly", "seriously",
            "anyway", "however", "therefore", "although", "though",
            "amazing", "awesome", "great", "good", "nice", "cool", "okay", "ok",
            "understand", "know", "feel", "want", "need", "like", "love",
            "just", "only", "also", "too", "very", "much", "more", "less",
            "before", "after", "during", "while", "until", "since",
            "being", "doing", "having", "getting", "going", "coming",
            "the", "and", "for", "with", "from", "that", "this", "which",
            "what", "where", "when", "why", "who", "how",
            "yes", "yeah", "yep", "nope", "sure",
            "right", "wrong", "true", "false",
            # Fiil formları
            "would", "could", "should", "might", "must",
            "will", "shall", "can", "may",
        ]
        
        found_english = []
        words = re.findall(r'\b[a-zA-Z]{3,}\b', clean_text.lower())
        
        for word in words:
            if word in COMMON_ENGLISH_WORDS:
                if word not in found_english:
                    found_english.append(word)
        
        return found_english

# Singleton
quality_gate = QualityGate()
