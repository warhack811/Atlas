"""
ATLAS Yönlendirici - Araç Kayıt Yöneticisi (Tool Registry)
---------------------------------------------------------
Bu bileşen, sistemdeki tüm araçların (tools) dinamik olarak yüklenmesini,
kaydedilmesini ve yönetilmesini sağlar. JSON tanımlamalarını okuyarak
ilgili handler sınıflarını belleğe yükler.
"""
import os
import json
import importlib
import logging
from typing import Dict, Optional, Type
from sandbox_router.tools.base import BaseTool

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Sistemdeki tüm tool'ları yöneten merkezi kayıt sınıfı (Singleton).
    """
    _instance = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
        return cls._instance

    def load_tools(self, definitions_path: str, handlers_package: str = "sandbox_router.tools.handlers"):
        """
        Tanımlanan dizindeki JSON dosyalarını tarar ve ilgili handler'ları yükler.
        """
        if not os.path.exists(definitions_path):
            logger.error(f"Definitions path not found: {definitions_path}")
            return

        for filename in os.listdir(definitions_path):
            if filename.endswith(".json"):
                file_path = os.path.join(definitions_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    tool_name = config.get("name")
                    handler_module_name = config.get("handler_module")
                    handler_class_name = config.get("handler_class")

                    if not all([tool_name, handler_module_name, handler_class_name]):
                        logger.warning(f"Invalid config in {filename}: Missing name, handler_module or handler_class")
                        continue

                    # Dinamik yükleme
                    full_module_path = f"{handlers_package}.{handler_module_name}"
                    module = importlib.import_module(full_module_path)
                    tool_class: Type[BaseTool] = getattr(module, handler_class_name)
                    
                    # Tool'u başlat ve kaydet
                    tool_instance = tool_class()
                    # JSON'dan gelen name ve description'ı override edebiliriz veya tool_class içinde tanımlı bırakabiliriz.
                    # Burada tool_class'tan gelenleri kullanacağız ama config'den de besleyebiliriz.
                    self._tools[tool_name] = tool_instance
                    logger.info(f"Loaded tool: {tool_name} (from {handler_module_name}.{handler_class_name})")

                except Exception as e:
                    logger.error(f"Error loading tool from {filename}: {str(e)}")
                    # Bir hata olsa bile diğer tool'ları yüklemeye devam et

    def register_tool(self, name: str, tool_instance: BaseTool):
        """
        Manuel olarak bir tool kaydeder (Özellikle testler için).
        """
        self._tools[name] = tool_instance
        logger.info(f"Registered tool: {name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        İsmi verilen tool'u döndürür.
        """
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, BaseTool]:
        """
        Yüklü tüm tool'ları döndürür.
        """
        return self._tools

    def get_openai_schemas(self):
        """
        Tüm tool'ların OpenAI function şemalarını döndürür.
        """
        return [tool.to_openai_function() for tool in self._tools.values()]
