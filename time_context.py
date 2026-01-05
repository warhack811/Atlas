"""
ATLAS Yönlendirici - Zaman ve Bağlam Farkındalığı (Time & Context)
-----------------------------------------------------------------
Bu bileşen, yapay zekanın "şimdi" kavramına sahip olmasını sağlar. Güncel tarih,
saat, günün periyodu ve aciliyet durumlarını analiz ederek modelin daha 
insansı ve bağlam odaklı yanıtlar vermesini destekler.

Temel Sorumluluklar:
1. Zaman Enjeksiyonu: LLM'e güncel tarih ve saat bilgisini otomatik bildirme.
2. Dinamik Selamlama: Günün saatine göre (Sabah, Akşam vb.) uygun hitap seçimi.
3. Aciliyet Tespiti: "Acil", "Hemen" gibi kelimeleri analiz ederek sistemde öncelik tetikleme.
4. Yerelleştirme: Tarih ve gün bilgilerini Türkçe formatında sunma.
"""

from datetime import datetime
from typing import Optional
import re


class TimeContext:
    """Zaman ve bağlam farkındalığı sağlar."""
    
    # Acil anahtar kelimeler
    URGENCY_KEYWORDS = [
        "acil", "hemen", "çabuk", "ivedi", "derhal",
        "deadline", "son tarih", "bugün", "şimdi",
        "urgent", "asap", "immediately"
    ]
    
    # Türkçe gün isimleri
    DAYS_TR = {
        0: "Pazartesi",
        1: "Salı",
        2: "Çarşamba",
        3: "Perşembe",
        4: "Cuma",
        5: "Cumartesi",
        6: "Pazar"
    }
    
    # Türkçe ay isimleri
    MONTHS_TR = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
        5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
        9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    
    def __init__(self, now: Optional[datetime] = None):
        self.now = now or datetime.now()
    
    def get_greeting(self) -> str:
        """Saat bazlı selamlama döndür."""
        hour = self.now.hour
        
        if 5 <= hour < 12:
            return "Günaydın"
        elif 12 <= hour < 18:
            return "İyi günler"
        elif 18 <= hour < 22:
            return "İyi akşamlar"
        else:
            return "İyi geceler"
    
    def get_time_period(self) -> str:
        """Günün zaman dilimini döndür."""
        hour = self.now.hour
        
        if 5 <= hour < 12:
            return "sabah"
        elif 12 <= hour < 14:
            return "öğle"
        elif 14 <= hour < 18:
            return "öğleden sonra"
        elif 18 <= hour < 22:
            return "akşam"
        else:
            return "gece"
    
    def get_formatted_date(self) -> str:
        """Türkçe formatında tarih döndür."""
        day_name = self.DAYS_TR[self.now.weekday()]
        month_name = self.MONTHS_TR[self.now.month]
        return f"{self.now.day} {month_name} {self.now.year}, {day_name}"
    
    def get_formatted_time(self) -> str:
        """Saat formatı döndür."""
        return self.now.strftime("%H:%M")
    
    def get_context_injection(self) -> str:
        """LLM için bağlam enjeksiyonu oluştur."""
        date_str = self.get_formatted_date()
        time_str = self.get_formatted_time()
        period = self.get_time_period()
        
        return f"Şu an {date_str}, saat {time_str} ({period})."
    
    def detect_urgency(self, message: str) -> tuple[bool, list[str]]:
        """
        Mesajda aciliyet tespiti yap.
        
        Returns:
            (acil_mi, bulunan_kelimeler)
        """
        message_lower = message.lower()
        found_keywords = []
        
        for keyword in self.URGENCY_KEYWORDS:
            if keyword in message_lower:
                found_keywords.append(keyword)
        
        return bool(found_keywords), found_keywords
    
    def get_system_prompt_addition(self, message: str = "") -> str:
        """
        System prompt'a eklenecek zaman bağlamı.
        
        Args:
            message: Kullanıcı mesajı (aciliyet tespiti için)
        
        Returns:
            Enjekte edilecek bağlam metni
        """
        parts = []
        
        # Tarih/saat bilgisi
        parts.append(f"\n[ZAMAN BAĞLAMI]")
        parts.append(self.get_context_injection())
        
        # Aciliyet tespiti
        if message:
            is_urgent, keywords = self.detect_urgency(message)
            if is_urgent:
                parts.append(f"⚠️ ACİL İŞARETİ TESPİT EDİLDİ: {', '.join(keywords)}")
                parts.append("Bu mesaja öncelik ver ve hızlı yanıt ver.")
        
        return "\n".join(parts)

    def inject_time_context(self, system_prompt: str, user_message: str = "") -> str:
        """
        System prompt'a zaman bağlamı ekle.
        """
        from .prompts import LANGUAGE_DISCIPLINE_PROMPT
        addition = self.get_system_prompt_addition(user_message)
        # Dil disiplini ekle - prompts.py'den merkezi import
        return system_prompt + addition + "\n" + LANGUAGE_DISCIPLINE_PROMPT


# Singleton
time_context = TimeContext()
