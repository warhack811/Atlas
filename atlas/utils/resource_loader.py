"""
Resource Loader Module
----------------------
Loads YAML resources (prompts, reasoning templates) from the resources/ directory.
"""
import yaml
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ResourceLoader:
    _prompts: Dict[str, Any] = {}
    _reasoning: Dict[str, Any] = {}
    _loaded = False

    @classmethod
    def load_resources(cls):
        """Loads all YAML resources into memory."""
        if cls._loaded:
            return

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        resources_dir = os.path.join(base_dir, "resources")

        try:
            with open(os.path.join(resources_dir, "prompts.yaml"), "r", encoding="utf-8") as f:
                cls._prompts = yaml.safe_load(f)

            with open(os.path.join(resources_dir, "reasoning.yaml"), "r", encoding="utf-8") as f:
                cls._reasoning = yaml.safe_load(f)

            cls._loaded = True
            logger.info("Resources loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load resources: {e}")
            raise

    @classmethod
    def get_prompt(cls, key: str, default: Any = None) -> Any:
        if not cls._loaded:
            cls.load_resources()
        return cls._prompts.get(key, default)

    @classmethod
    def get_reasoning(cls, key: str, default: List[str] = None) -> List[str]:
        if not cls._loaded:
            cls.load_resources()
        return cls._reasoning.get(key, default or [])

# Initialize on import
ResourceLoader.load_resources()

def get_prompt(key: str) -> Any:
    return ResourceLoader.get_prompt(key)

def get_reasoning(key: str) -> List[str]:
    return ResourceLoader.get_reasoning(key)

import random

def get_random_synthesis_thought() -> str:
    thoughts = ResourceLoader.get_reasoning("synthesis_thoughts")
    return random.choice(thoughts) if thoughts else "Yanıt oluşturuluyor..."

def get_random_search_thought(query: str) -> str:
    thoughts = ResourceLoader.get_reasoning("search_thoughts")
    if not thoughts: return f"{query} aranıyor..."
    template = random.choice(thoughts)
    return template.format(query=query)

def get_random_flux_thought(prompt: str) -> str:
    thoughts = ResourceLoader.get_reasoning("flux_thoughts")
    if not thoughts: return "Görsel oluşturuluyor..."
    template = random.choice(thoughts)
    return template.format(prompt=prompt)

def get_random_weather_thought(city: str) -> str:
    thoughts = ResourceLoader.get_reasoning("weather_thoughts")
    if not thoughts: return f"{city} hava durumu alınıyor..."
    template = random.choice(thoughts)
    return template.format(city=city)
