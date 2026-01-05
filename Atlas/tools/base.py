"""
ATLAS Yönlendirici - Araç Temel Sınıfı (Base Tool)
-------------------------------------------------
Bu modül, sistemde kullanılacak tüm araçların (search, image gen vb.)
uyması gereken arayüzü (interface) tanımlar.

Temel Özellikler:
1. Soyut Sınıf (ABC): Tüm araçlar bu sınıftan türetilmelidir.
2. Standart Arayüz: `name`, `description` ve `execute()` metotları zorunludur.
3. OpenAI Uyumluluğu: LLM function-calling formatına otomatik dönüşüm.
4. Asenkron Tasarım: `execute()` metodu `async` olmalıdır.

Yeni bir araç eklemek için:
1. Bu sınıftan türetin.
2. `name`, `description`, `input_schema` tanımlayın.
3. `execute()` metodunu implemente edin.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Type
from pydantic import BaseModel

class BaseTool(ABC):
    """
    Tüm araçların türetilmesi gereken soyut temel sınıf.
    """
    # --- ZORUNLU ALANLAR ---
    name: str                       # Araç adı (örn: "search_tool")
    description: str                # LLM'e açıklama metnini sağlar
    input_schema: Type[BaseModel]   # Beklenen parametrelerin Pydantic modeli

    # --- ZORUNLU METOTLAR ---
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Tool'un asıl işini yaptığı metod. Asenkron olmalıdır.
        """
        pass

    def to_openai_function(self) -> Dict[str, Any]:
        """
        Tool'un LLM'e gönderilecek JSON şemasını (OpenAI formatında) döndürür.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema()
            }
        }
