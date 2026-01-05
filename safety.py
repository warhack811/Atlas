"""
ATLAS Yönlendirici - Güvenlik Katmanı (Safety Gate)
--------------------------------------------------
Bu bileşen, sisteme giren ve sistemden çıkan her veriyi zararlı içeriklere
ve veri sızıntılarına karşı denetler.

Temel Sorumluluklar:
1. PII Maskeleme: E-posta, telefon, TCKN gibi kişisel verileri otomatik maskeleme.
2. Enjeksiyon Engelleme (Prompt Injection): Sistemin talimatlarını değiştirmeye 
   çalışan saldırgan ifadeleri tespit etme.
3. AI Guard Entegrasyonu: LlamaGuard gibi uzman güvenlik modelleriyle derin analiz yapma.
4. Beyaz Liste (Whitelist): Zararsız ama riskli görünen kelimeleri (örn: "şifre") 
   analizden hariç tutma.
5. Çok Katmanlı Koruma: Önce hızlı Regex kuralları, ardından kapsamlı LLM denetimi.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class SafetyIssue:
    """Tespit edilen bir güvenlik ihlalini tanımlayan sınıf."""
    type: str     # İhlal türü: 'PII', 'ENJEKSİYON', 'AI_ENGELİ'
    details: str  # İhlale dair teknik detaylar
    severity: str # Şiddet derecesi: 'LOW', 'MEDIUM', 'HIGH'

class SafetyGate:
    """Giriş ve çıkış trafiğini filtreleyen güvenlik kapısı."""
    
    # PII için Regex Kalıpları (Geliştirilmiş)
    PII_PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE_TR": r'\b(?:\+90|0)?\s*5[0-9]{2}\s*[0-9]{3}\s*[0-9]{2}\s*[0-9]{2}\b',
        "CREDIT_CARD": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        "TCKN": r'\b[1-9]{1}[0-9]{10}\b',
        "IBAN_TR": r'\bTR[0-9]{2}\s*(?:[0-9]{4}\s*){5}[0-9]{2}\b',
        "ADDRESS": r'\b(?:Mahalle|Sokak|Cadde|Bulvar)\b.*?\b(?:No|Daire|Kat)\b\s*\d+',
    }
    
    # Basit Enjeksiyon Anahtar Kelimeleri (İngilizce/Türkçe)
    INJECTION_KEYWORDS = [
        r"ignore previous instructions",
        r"önceki talimatları unut",
        r"give me the system prompt",
        r"sistem talimatlarını ver",
        r"dan mode",
        r"dev mode",
        r"jailbreak",
        r"şifreyi ver",
        r"password",
        r"bypass safety",
        r"<script>",
        r"sql injection"
    ]

    # Beyaz Liste: Yanlış pozitifleri önlemek için güvenli kelimeler
    SAFE_KEYWORDS = [
        "tasarımsal", "limit", "mesaj", "istek", "nasıl", "nedir", "betimle", 
        "analiz", "anlat", "görsel", "resim", "ücret", "fiyat", "sınır"
    ]
    
    def __init__(self):
        self.injection_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_KEYWORDS]
        self.pii_patterns = {k: re.compile(v) for k, v in self.PII_PATTERNS.items()}

    async def check_input_safety(self, text: str) -> Tuple[bool, str, List[SafetyIssue]]:
        """
        Kullanıcı girişini güvenlik sorunları için kontrol et.
        Dönüş: (güvenli_mi, temizlenmiş_metin, sorunlar_listesi)
        """
        from .config import MODEL_GOVERNANCE, API_CONFIG
        from .key_manager import KeyManager
        import httpx
        
        issues = []
        sanitized_text = text
        
        # 1. TEMEL REGEX KONTROLLERİ (Her zaman devrede)
        # A. Enjeksiyon Kontrolü (Engelle)
        for pattern in self.injection_patterns:
            if pattern.search(text):
                issues.append(SafetyIssue(
                    type="ENJEKSİYON", 
                    details=f"Zararlı kalıp tespit edildi: {pattern.pattern}", 
                    severity="YÜKSEK"
                ))
                return False, text, issues
        # B. PII Kontrolü (Maskele)
        for pii_type, pattern in self.pii_patterns.items():
            if pattern.search(sanitized_text):
                issues.append(SafetyIssue(
                    type="PII",
                    details=f"{pii_type} verisi tespit edildi",
                    severity="ORTA"
                ))
                sanitized_text = pattern.sub(f"[{pii_type}]", sanitized_text)

        # 1.5 BEYAZ LİSTE KONTROLÜ (Whitelist Bypass)
        # Eğer mesajda güvenli kelimeler ağırlıktaysa AI Guard'ı atla
        lowered_text = text.lower()
        if any(word in lowered_text for word in self.SAFE_KEYWORDS):
            # Eğer içinde tehlikeli regex'ler yoksa (yukarıda kontrol edildi), güvenli say
            if not issues:
                return True, sanitized_text, [SafetyIssue(type="BEYAZ_LISTE", details="Güvenli kelimeler nedeniyle kabul edildi", severity="DÜŞÜK")]

        # 2. GELİŞMİŞ AI GUARD KONTROLLERİ
        safety_models = MODEL_GOVERNANCE.get("safety", [])
        
        for model in safety_models:
            if model == "pass-through" or model == "regex-rule-based":
                continue # Zaten regex yaptık veya atla
                
            try:
                api_key = KeyManager.get_best_key()
                if not api_key:
                    continue

                # AI Guard modeline gönderilecek promptu hazırla
                from .prompts import LLAMA_GUARD_PROMPT
                full_safety_prompt = f"{LLAMA_GUARD_PROMPT}\n\nAnaliz Edilecek Mesaj: {text}"

                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{API_CONFIG['groq_api_base']}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": full_safety_prompt}],
                            "temperature": 0.0
                        }
                    )
                    
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        if "unsafe" in content.lower():
                            violation_code = content.split('\n')[-1] if '\n' in content else "AI_Guard_Blocked"
                            issues.append(SafetyIssue(
                                type="AI_KORUMA_ENGELİ",
                                details=f"Yapay Zeka Koruması ({model}) engelledi: {violation_code}",
                                severity="YÜKSEK"
                            ))
                            return False, sanitized_text, issues
            except Exception as e:
                print(f"[HATA] {model} için Yapay Zeka Koruması kontrolü başarısız: {e}")
                continue 
        
        return True, sanitized_text, issues

# Tekil örnek (Singleton)
safety_gate = SafetyGate()
