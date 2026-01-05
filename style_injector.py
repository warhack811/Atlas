"""
ATLAS Yönlendirici - Stil Enjeksiyonu (Style Injection)
------------------------------------------------------
Bu bileşen, yapay zekanın sahip olacağı karakteri (persona), konuşma tonunu
ve biçimsel özelliklerini LLM sistem talimatlarına (system prompt) dinamik
olarak giydirir.

Temel Sorumluluklar:
1. Persona Yönetimi: Profesyonel, samimi, kanka gibi farklı kişiliklerin tanımlanması.
2. Ton Ayarları: Resmi, günlük veya samimi konuşma tarzlarının enjeksiyonu.
3. Biçim Denetimi: Yanıt uzunluğu, emoji düzeyi ve detay seviyesinin ayarlanması.
4. Bağlam Birleştirme: Zaman ve kullanıcı bağlamıyla stili tek bir prompt'ta harmanlama.
5. Tutarlılık Doğrulaması: Üretilen yanıtın seçilen stile (örn: resmi tonda argo kullanımı) 
   uygunluğunu denetleme.
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass


class Tone(str, Enum):
    """Ton seçenekleri."""
    FORMAL = "formal"      # Resmi, profesyonel
    CASUAL = "casual"      # Günlük, rahat
    KANKA = "kanka"        # Samimi, sokak dili izinli


class Length(str, Enum):
    """Yanıt uzunluğu."""
    SHORT = "short"        # Kısa, öz
    MEDIUM = "medium"      # Orta uzunluk
    DETAILED = "detailed"  # Detaylı, kapsamlı


class EmojiLevel(str, Enum):
    """Emoji kullanım seviyesi."""
    NONE = "none"          # Emoji yok
    MINIMAL = "minimal"    # Az emoji
    HIGH = "high"          # Çok emoji


class DetailLevel(str, Enum):
    """Detay seviyesi."""
    SUMMARY = "summary"              # Özet
    BALANCED = "balanced"            # Dengeli
    COMPREHENSIVE = "comprehensive"  # Kapsamlı


class StyleProfile(BaseModel):
    """Kullanıcının tercih ettiği konuşma tarzını tanımlayan veri modeli."""
    persona: str = Field(default="friendly", description="Persona adı")
    tone: Tone = Field(default=Tone.CASUAL, description="Konuşma tonu")
    length: Length = Field(default=Length.MEDIUM, description="Yanıt uzunluğu")
    emoji: EmojiLevel = Field(default=EmojiLevel.MINIMAL, description="Emoji seviyesi")
    detail: DetailLevel = Field(default=DetailLevel.BALANCED, description="Detay seviyesi")
    mirror_hitap: bool = Field(default=False, description="Kullanıcı hitabını yansıt")
    
    def to_dict(self) -> Dict:
        return {
            "persona": self.persona,
            "tone": self.tone.value,
            "length": self.length.value,
            "emoji": self.emoji.value,
            "detail": self.detail.value,
            "mirror_hitap": self.mirror_hitap
        }


@dataclass
class PersonaDefinition:
    """Bir personanın temel özelliklerini ve talimatlarını saklayan veri sınıfı."""
    name: str
    description: str
    base_prompt: str
    allowed_slang: bool = False
    default_tone: Tone = Tone.CASUAL


class StyleInjector:
    """
    Stil enjeksiyonu yöneticisi.
    
    Kullanım:
        injector = StyleInjector()
        system_prompt = injector.build_system_prompt(
            base_prompt="Sen bir yazılım geliştiricisin.",
            style=StyleProfile(persona="kanka", tone=Tone.KANKA)
        )
    """
    
    # Persona tanımları (base_prompt'lar prompts.py'den import edilir)
    from .prompts import PERSONA_PROMPTS as _PERSONA_PROMPTS
    PERSONAS: Dict[str, PersonaDefinition] = {
        "professional": PersonaDefinition(
            name="Professional",
            description="Profesyonel ve resmi asistan",
            base_prompt=_PERSONA_PROMPTS["professional"],
            allowed_slang=False,
            default_tone=Tone.FORMAL
        ),
        "friendly": PersonaDefinition(
            name="Friendly",
            description="Samimi ve yardımsever asistan",
            base_prompt=_PERSONA_PROMPTS["friendly"],
            allowed_slang=False,
            default_tone=Tone.CASUAL
        ),
        "kanka": PersonaDefinition(
            name="Kanka",
            description="Arkadaş canlısı, samimi asistan",
            base_prompt=_PERSONA_PROMPTS["kanka"],
            allowed_slang=True,
            default_tone=Tone.KANKA
        ),
        "teacher": PersonaDefinition(
            name="Teacher",
            description="Eğitici ve sabırlı öğretmen",
            base_prompt=_PERSONA_PROMPTS["teacher"],
            allowed_slang=False,
            default_tone=Tone.CASUAL
        ),
        "expert": PersonaDefinition(
            name="Expert",
            description="Alanında uzman danışman",
            base_prompt=_PERSONA_PROMPTS["expert"],
            allowed_slang=False,
            default_tone=Tone.FORMAL
        ),
        "girlfriend": PersonaDefinition(
            name="Kız Arkadaş",
            description="Sevgi dolu, flörtöz ve samimi kız arkadaş",
            base_prompt=_PERSONA_PROMPTS["girlfriend"],
            allowed_slang=True,
            default_tone=Tone.KANKA
        ),
        "sincere": PersonaDefinition(
            name="Sincere",
            description="İçten ve empati kuran asistan",
            base_prompt=_PERSONA_PROMPTS["sincere"],
            allowed_slang=False,
            default_tone=Tone.CASUAL
        ),
        "creative": PersonaDefinition(
            name="Creative",
            description="Yaratıcı ve ilham verici asistan",
            base_prompt=_PERSONA_PROMPTS["creative"],
            allowed_slang=False,
            default_tone=Tone.CASUAL
        )
    }
    
    # Ton direktifleri (prompts.py'den import)
    from .prompts import TONE_DIRECTIVES as _TONE_DIRECTIVES
    TONE_DIRECTIVES = {
        Tone.FORMAL: _TONE_DIRECTIVES["formal"],
        Tone.CASUAL: _TONE_DIRECTIVES["casual"],
        Tone.KANKA: _TONE_DIRECTIVES["kanka"]
    }
    
    # Uzunluk direktifleri (prompts.py'den import)
    from .prompts import LENGTH_DIRECTIVES as _LENGTH_DIRECTIVES
    LENGTH_DIRECTIVES = {
        Length.SHORT: _LENGTH_DIRECTIVES["short"],
        Length.MEDIUM: _LENGTH_DIRECTIVES["medium"],
        Length.DETAILED: _LENGTH_DIRECTIVES["detailed"]
    }
    
    # Emoji direktifleri (prompts.py'den import)
    from .prompts import EMOJI_DIRECTIVES as _EMOJI_DIRECTIVES
    EMOJI_DIRECTIVES = {
        EmojiLevel.NONE: _EMOJI_DIRECTIVES["none"],
        EmojiLevel.MINIMAL: _EMOJI_DIRECTIVES["minimal"],
        EmojiLevel.HIGH: _EMOJI_DIRECTIVES["high"]
    }
    
    # Detay direktifleri (prompts.py'den import)
    from .prompts import DETAIL_DIRECTIVES as _DETAIL_DIRECTIVES
    DETAIL_DIRECTIVES = {
        DetailLevel.SUMMARY: _DETAIL_DIRECTIVES["summary"],
        DetailLevel.BALANCED: _DETAIL_DIRECTIVES["balanced"],
        DetailLevel.COMPREHENSIVE: _DETAIL_DIRECTIVES["comprehensive"]
    }
    
    def __init__(self):
        self.default_style = StyleProfile()
    
    def get_persona(self, name: str) -> PersonaDefinition:
        """Persona tanımını al."""
        return self.PERSONAS.get(name, self.PERSONAS["friendly"])
    
    def build_system_prompt(
        self,
        base_prompt: str,
        style: Optional[StyleProfile] = None,
        intent: Optional[str] = None
    ) -> str:
        """
        Belirlenen stil profilini temel talimatlara giydirerek nihai system prompt'u oluşturur.
        """
        if style is None:
            style = self.default_style
        
        # Persona bilgisini al
        persona = self.get_persona(style.persona)
        
        # Prompt parçalarını birleştir
        parts = []
        
        # 1. Persona base prompt
        parts.append(persona.base_prompt)
        
        # 2. Intent bazlı orijinal prompt (varsa)
        if base_prompt and base_prompt != persona.base_prompt:
            parts.append(f"\nGörevin: {base_prompt}")
        
        # 3. Ton direktifi
        parts.append(f"\n{self.TONE_DIRECTIVES[style.tone]}")
        
        # 4. Uzunluk direktifi
        parts.append(f"\n{self.LENGTH_DIRECTIVES[style.length]}")
        
        # 5. Emoji direktifi
        parts.append(f"\n{self.EMOJI_DIRECTIVES[style.emoji]}")
        
        # 6. Detay direktifi
        parts.append(f"\n{self.DETAIL_DIRECTIVES[style.detail]}")
        
        # 7. Mirror Hitap (samimi modlarda)
        if style.mirror_hitap and style.tone in [Tone.CASUAL, Tone.KANKA]:
            from .prompts import MIRROR_HITAP_PROMPT
            parts.append("\n" + MIRROR_HITAP_PROMPT)
        
        # 8. SAF TÜRKÇE DİREKTİFİ (prompts.py'den import)
        from .prompts import PURE_TURKISH_DIRECTIVE
        parts.append(PURE_TURKISH_DIRECTIVE)
        
        # 9. Zaman Bağlamı
        from .time_context import TimeContext
        tc = TimeContext()
        parts.append(f"\n{tc.get_context_injection()}")
        
        return "\n".join(parts)
    
    def validate_tone_consistency(
        self,
        response: str,
        style: StyleProfile
    ) -> tuple[bool, Optional[str]]:
        """
        Üretilen yanıtın seçilen konuşma tonuna ve kurallarına uygunluğunu doğrular.
        """
        issues = []
        
        # Formal tonda slang kontrolü
        if style.tone == Tone.FORMAL:
            slang_words = ["lan", "ya", "yav", "moruk", "kanka", "abi", "hacı"]
            found_slang = [w for w in slang_words if w in response.lower()]
            if found_slang:
                issues.append(f"Resmi tonda slang kelimeler: {', '.join(found_slang)}")
        
        # Emoji kontrolü
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "]+", flags=re.UNICODE
        )
        emoji_count = len(emoji_pattern.findall(response))
        
        if style.emoji == EmojiLevel.NONE and emoji_count > 0:
            issues.append(f"Emoji kullanılmamalıydı ama {emoji_count} emoji var")
        elif style.emoji == EmojiLevel.MINIMAL and emoji_count > 5:
            issues.append(f"Çok fazla emoji: {emoji_count}")
        
        # Uzunluk kontrolü
        word_count = len(response.split())
        if style.length == Length.SHORT and word_count > 150:
            issues.append(f"Kısa olmalıydı ama {word_count} kelime")
        
        if issues:
            return False, "; ".join(issues)
        return True, None
    
    def get_available_personas(self) -> list[Dict]:
        """Mevcut personaları listele."""
        return [
            {
                "id": pid,
                "name": p.name,
                "description": p.description,
                "default_tone": p.default_tone.value,
                "slang_allowed": p.allowed_slang
            }
            for pid, p in self.PERSONAS.items()
        ]


# Tekil örnek
style_injector = StyleInjector()


# Preset stil profilleri
STYLE_PRESETS = {
    "default": StyleProfile(),
    "professional": StyleProfile(
        persona="professional",
        tone=Tone.FORMAL,
        length=Length.MEDIUM,
        emoji=EmojiLevel.NONE,
        detail=DetailLevel.BALANCED
    ),
    "friendly": StyleProfile(
        persona="friendly",
        tone=Tone.CASUAL,
        length=Length.MEDIUM,
        emoji=EmojiLevel.MINIMAL,
        detail=DetailLevel.BALANCED
    ),
    "kanka": StyleProfile(
        persona="kanka",
        tone=Tone.KANKA,
        length=Length.MEDIUM,
        emoji=EmojiLevel.HIGH,
        detail=DetailLevel.BALANCED
    ),
    "concise": StyleProfile(
        persona="expert",
        tone=Tone.FORMAL,
        length=Length.SHORT,
        emoji=EmojiLevel.NONE,
        detail=DetailLevel.SUMMARY
    ),
    "detailed": StyleProfile(
        persona="teacher",
        tone=Tone.CASUAL,
        length=Length.DETAILED,
        emoji=EmojiLevel.MINIMAL,
        detail=DetailLevel.COMPREHENSIVE
    ),
    "girlfriend": StyleProfile(
        persona="girlfriend",
        tone=Tone.KANKA,
        length=Length.MEDIUM,
        emoji=EmojiLevel.HIGH,
        detail=DetailLevel.BALANCED,
        mirror_hitap=True
    ),
    "standard": StyleProfile(
        persona="friendly",
        tone=Tone.CASUAL,
        length=Length.MEDIUM,
        emoji=EmojiLevel.MINIMAL,
        detail=DetailLevel.BALANCED
    ),
    "sincere": StyleProfile(
        persona="sincere",
        tone=Tone.CASUAL,
        length=Length.MEDIUM,
        emoji=EmojiLevel.HIGH,
        detail=DetailLevel.BALANCED
    ),
    "creative": StyleProfile(
        persona="creative",
        tone=Tone.CASUAL,
        length=Length.DETAILED,
        emoji=EmojiLevel.MINIMAL,
        detail=DetailLevel.COMPREHENSIVE
    )
}

def get_system_instruction(mode: str) -> str:
    """Belirli bir mod için system prompt talimatını döndürür."""
    profile = STYLE_PRESETS.get(mode, STYLE_PRESETS["standard"])
    return style_injector.build_system_prompt("", profile)
