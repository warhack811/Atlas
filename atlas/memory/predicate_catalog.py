"""
Atlas Predicate Catalog Loader
-------------------------------
This module loads and manages the predicate catalog (predicate_catalog.yml)
which defines allowed predicates for the memory system.

Responsibilities:
1. Load and validate predicate catalog from YAML
2. Normalize Turkish characters for predicate matching
3. Resolve raw predicates to canonical forms
4. Provide metadata (enabled, durability, type, category)
5. Map catalog categories to Neo4j graph categories (personal/general)
"""

import yaml
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Set, List

logger = logging.getLogger(__name__)

# Turkish character normalization map for matching
TURKISH_NORMALIZE_MAP = str.maketrans(
    "İĞŞÜÖÇığşüöç",
    "IGSUOCIGSUOC"
)

class PredicateCatalog:
    """Manages the predicate catalog and provides lookup/validation functions."""
    
    def __init__(self, catalog_data: Dict):
        """Initialize catalog from parsed YAML data."""
        self.by_key: Dict[str, Dict] = catalog_data
        self.alias_map: Dict[str, str] = {}  # normalized -> KEY
        self._build_alias_map()
    
    def _build_alias_map(self):
        """Build alias map for fast lookup: normalized(alias/canonical/key) -> KEY."""
        for key, entry in self.by_key.items():
            # Map KEY itself
            normalized_key = self.normalize_predicate(key)
            self.alias_map[normalized_key] = key
            
            # Map canonical
            canonical = entry.get("canonical", "")
            if canonical:
                normalized_canonical = self.normalize_predicate(canonical)
                self.alias_map[normalized_canonical] = key
            
            # Map aliases
            aliases = entry.get("aliases", [])
            for alias in aliases:
                normalized_alias = self.normalize_predicate(alias)
                self.alias_map[normalized_alias] = key
        
        logger.info(f"Predicate catalog loaded: {len(self.by_key)} predicates, {len(self.alias_map)} mappings")
    
    @staticmethod
    def normalize_predicate(predicate: str) -> str:
        """Normalize predicate for matching.
        
        1. Strip whitespace
        2. Uppercase
        3. Replace spaces with underscores
        4. Normalize Turkish chars (İ->I, Ğ->G, etc.)
        5. Keep only [A-Z0-9_]
        """
        if not predicate:
            return ""
        
        # Strip and uppercase
        p = predicate.strip().upper()
        
        # Replace spaces with underscore
        p = p.replace(" ", "_")
        
        # Normalize Turkish characters
        p = p.translate(TURKISH_NORMALIZE_MAP)
        
        # Keep only alphanumeric and underscore
        p = re.sub(r'[^A-Z0-9_]', '_', p)
        
        # Remove consecutive underscores
        p = re.sub(r'_+', '_', p)
        
        # Strip leading/trailing underscores
        p = p.strip('_')
        
        return p
    
    def resolve_predicate(self, raw_predicate: str) -> Optional[str]:
        """Resolve raw predicate to catalog KEY.
        
        Returns:
            KEY if found in catalog, None otherwise
        """
        normalized = self.normalize_predicate(raw_predicate)
        return self.alias_map.get(normalized)
    
    def get_canonical(self, key: str) -> str:
        """Get canonical form of predicate."""
        entry = self.by_key.get(key, {})
        return entry.get("canonical", key)
    
    def get_enabled(self, key: str) -> bool:
        """Check if predicate is enabled."""
        entry = self.by_key.get(key, {})
        return entry.get("enabled", True)
    
    def get_durability(self, key: str) -> str:
        """Get durability level (EPHEMERAL/SESSION/SITUATIONAL/LONG_TERM/PROSPECTIVE/STATIC)."""
        entry = self.by_key.get(key, {})
        return entry.get("durability", "LONG_TERM")
    
    def get_type(self, key: str) -> str:
        """Get predicate type (EXCLUSIVE/ADDITIVE/TEMPORAL/META/etc)."""
        entry = self.by_key.get(key, {})
        return entry.get("type", "ADDITIVE")
    
    def get_graph_category(self, key: str) -> str:
        """Map catalog category to Neo4j graph category (personal/general).
        
        Faz 1 bridge:
        - Personal: identity, preference, relationship, ownership, goals, prospective, procedural
        - General: external, static, content, meta, ability, attribute
        """
        entry = self.by_key.get(key, {})
        catalog_category = entry.get("category", "general")
        
        personal_categories = {
            "identity", "preference", "relationship", "ownership", 
            "goals", "prospective", "procedural", "emotional", "location"
        }
        
        if catalog_category in personal_categories:
            return "personal"
        else:
            return "general"
    
    def get_enabled_predicates(self) -> List[str]:
        """Get list of enabled canonical predicates for prompt injection."""
        enabled = []
        for key, entry in self.by_key.items():
            if entry.get("enabled", True):
                canonical = entry.get("canonical", key)
                enabled.append(canonical)
        return sorted(enabled)
    
    def get_predicates_by_category(self, target_category: str) -> List[str]:
        """
        Belirtilen kategorideki (örn: 'identity', 'preferences') tüm predicate'lerin
        CANONICAL anahtarlarını döndürür.
        
        Kategori eşleşmesi yaparken:
        - catalog entry içindeki 'category' alanına bakar.
        - Eğer enabled=False ise dahil etmez.
        
        Args:
            target_category: Hedef kategori (identity, hard_facts, soft_signals)
            
        Returns:
            List of canonical predicate names (sorted, unique)
        """
        result = []
        target = target_category.lower()
        
        for key, entry in self.by_key.items():
            if not entry.get("enabled", True):
                continue
                
            # Entry kategorisini kontrol et
            cat = entry.get("category", "general").lower()
            pred_type = entry.get("type", "ADDITIVE")
            
            # Bazı özel maplemeler (Faz 1 bridge ile uyumlu)
            if target == "identity" and cat == "identity":
                result.append(entry.get("canonical", key))
            elif target == "hard_facts" and pred_type == "EXCLUSIVE" and cat != "identity":
                result.append(entry.get("canonical", key))
            elif target == "soft_signals" and pred_type in ["ADDITIVE", "TEMPORAL"]:
                result.append(entry.get("canonical", key))
                
        return sorted(list(set(result)))  # Unique ve sıralı
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> Optional['PredicateCatalog']:
        """Load catalog from YAML file.
        
        Returns:
            PredicateCatalog instance or None if load fails (fail-open)
        """
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                logger.error(f"CATALOG_LOAD_ERROR: Invalid YAML structure in {yaml_path}")
                return None
            
            return cls(data)
            
        except FileNotFoundError:
            logger.error(f"CATALOG_LOAD_ERROR: File not found: {yaml_path}")
            return None
        except yaml.YAMLError as e:
            logger.error(f"CATALOG_LOAD_ERROR: YAML parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"CATALOG_LOAD_ERROR: Unexpected error: {e}")
            return None


# Global singleton catalog instance
DEFAULT_CATALOG_PATH = Path(__file__).parent / "predicate_catalog.yml"
_catalog_instance: Optional[PredicateCatalog] = None

def get_catalog() -> Optional[PredicateCatalog]:
    """Get global catalog instance (singleton).
    
    Returns:
        PredicateCatalog instance or None if catalog failed to load (fail-open mode)
    """
    global _catalog_instance
    
    if _catalog_instance is None:
        _catalog_instance = PredicateCatalog.from_yaml(DEFAULT_CATALOG_PATH)
        
        if _catalog_instance is None:
            logger.warning("CATALOG_DISABLED_FAILOPEN: Predicate catalog failed to load, operating in fail-open mode")
    
    return _catalog_instance
