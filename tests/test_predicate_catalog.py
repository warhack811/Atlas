"""
FAZ-M: Memory Schema Alignment - Test Suite
===========================================
Tests for dynamic predicate catalog integration and ASCII/Unicode fix.
"""

import pytest
from unittest.mock import MagicMock
from Atlas.memory.predicate_catalog import PredicateCatalog


class TestPredicateCatalogDynamic:
    """Test get_predicates_by_category method"""
    
    def test_get_predicates_identity_category(self):
        """Test: Retrieve identity predicates from catalog"""
        # Arrange
        catalog_data = {
            "KEY_ISIM": {"canonical": "ISIM", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
            "KEY_YASI": {"canonical": "YASI", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
            "KEY_SEVER": {"canonical": "SEVER", "category": "preference", "enabled": True, "type": "EXCLUSIVE"},
        }
        catalog = PredicateCatalog(catalog_data)
        
        # Act
        identity_preds = catalog.get_predicates_by_category("identity")
        
        # Assert
        assert "ISIM" in identity_preds
        assert "YASI" in identity_preds
        assert "SEVER" not in identity_preds, "Non-identity predicates should not be included"
    
    def test_get_predicates_hard_facts_excludes_disabled(self):
        """Test: Disabled predicates should not be returned"""
        # Arrange
        catalog_data = {
            "KEY_SEVER": {"canonical": "SEVER", "category": "preference", "enabled": True, "type": "EXCLUSIVE"},
            "KEY_NEFRET": {"canonical": "NEFRET_EDER", "category": "preference", "enabled": False, "type": "EXCLUSIVE"},
        }
        catalog = PredicateCatalog(catalog_data)
        
        # Act
        hard_facts = catalog.get_predicates_by_category("hard_facts")
        
        # Assert
        assert "SEVER" in hard_facts
        assert "NEFRET_EDER" not in hard_facts, "Disabled predicates should not be returned"
    
    def test_get_predicates_soft_signals(self):
        """Test: ADDITIVE and TEMPORAL predicates for soft signals"""
        # Arrange
        catalog_data = {
            "KEY_HISS": {"canonical": "HISSEDIYOR", "category": "emotional", "enabled": True, "type": "ADDITIVE"},
            "KEY_PLAN": {"canonical": "PLANLADI", "category": "goals", "enabled": True, "type": "TEMPORAL"},
            "KEY_ISIM": {"canonical": "ISIM", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
        }
        catalog = PredicateCatalog(catalog_data)
        
        # Act
        soft_signals = catalog.get_predicates_by_category("soft_signals")
        
        # Assert
        assert "HISSEDIYOR" in soft_signals
        assert "PLANLADI" in soft_signals
        assert "ISIM" not in soft_signals, "EXCLUSIVE predicates should not be in soft_signals"
    
    def test_get_predicates_empty_category(self):
        """Test: Empty catalog or no matches returns empty list"""
        # Arrange
        catalog_data = {}
        catalog = PredicateCatalog(catalog_data)
        
        # Act
        result = catalog.get_predicates_by_category("identity")
        
        # Assert
        assert result == []
    
    def test_get_predicates_unique_sorted(self):
        """Test: Results are unique and sorted"""
        # Arrange
        catalog_data = {
            "KEY1": {"canonical": "ZZZ", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
            "KEY2": {"canonical": "AAA", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
            "KEY3": {"canonical": "MMM", "category": "identity", "enabled": True, "type": "EXCLUSIVE"},
        }
        catalog = PredicateCatalog(catalog_data)
        
        # Act
        result = catalog.get_predicates_by_category("identity")
        
        # Assert
        assert result == ["AAA", "MMM", "ZZZ"], "Should be sorted alphabetically"
        assert len(result) == len(set(result)), "Should have no duplicates"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
