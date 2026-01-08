"""
Unit tests for Predicate Catalog (Faz 1)
Test catalog resolution, alias mapping, filtering, and sanitize_triplets logic.
"""

import unittest
from Atlas.memory.predicate_catalog import PredicateCatalog, get_catalog
from Atlas.memory.extractor import sanitize_triplets


class TestPredicateCatalog(unittest.TestCase):
    """Test predicate catalog loading and resolution."""
    
    def setUp(self):
        """Load catalog before each test."""
        self.catalog = get_catalog()
        self.assertIsNotNone(self.catalog, "Catalog should load successfully")
    
    def test_alias_resolution_isim(self):
        """Test AD → İSİM canonical mapping."""
        key = self.catalog.resolve_predicate("AD")
        self.assertIsNotNone(key, "AD should resolve to a KEY")
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "İSİM", "AD should map to İSİM canonical")
    
    def test_alias_resolution_sevmez(self):
        """Test SEVMEZ → SEVMİYOR canonical mapping."""
        key = self.catalog.resolve_predicate("SEVMEZ")
        self.assertIsNotNone(key, "SEVMEZ should resolve to a KEY")
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "SEVMİYOR", "SEVMEZ should map to SEVMİYOR canonical")
    
    def test_disabled_predicate(self):
        """Test that disabled predicates are marked as such."""
        # MERHABA should be disabled
        key = self.catalog.resolve_predicate("MERHABA")
        self.assertIsNotNone(key, "MERHABA should exist in catalog")
        enabled = self.catalog.get_enabled(key)
        self.assertFalse(enabled, "MERHABA should be disabled")
    
    def test_ephemeral_durability(self):
        """Test NEREDE has EPHEMERAL durability."""
        key = self.catalog.resolve_predicate("NEREDE")
        self.assertIsNotNone(key, "NEREDE should exist in catalog")
        durability = self.catalog.get_durability(key)
        self.assertEqual(durability, "EPHEMERAL", "NEREDE should be EPHEMERAL")
    
    def test_unknown_predicate(self):
        """Test unknown predicates return None."""
        key = self.catalog.resolve_predicate("BU_PREDICATE_YOK")
        self.assertIsNone(key, "Unknown predicate should return None")


class TestSanitizeTriplets(unittest.TestCase):
    """Test sanitize_triplets filtering logic."""
    
    def setUp(self):
        """Ensure catalog is loaded."""
        self.catalog = get_catalog()
        self.assertIsNotNone(self.catalog, "Catalog must be loaded for sanitization tests")
    
    def test_alias_canonicalization(self):
        """Test that AD gets canonicalized to İSİM."""
        triplets = [
            {"subject": "Ali", "predicate": "AD", "object": "Ali", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 1, "One triplet should pass")
        self.assertEqual(cleaned[0]["predicate"], "İSİM", "AD should be canonicalized to İSİM")
    
    def test_disabled_predicate_drop(self):
        """Test disabled predicates are dropped."""
        triplets = [
            {"subject": "Ali", "predicate": "MERHABA", "object": "Ayşe", "category": "general"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 0, "Disabled predicate MERHABA should be dropped")
    
    def test_ephemeral_durability_drop(self):
        """Test EPHEMERAL predicates are dropped."""
        triplets = [
            {"subject": "Ali", "predicate": "NEREDE", "object": "Evde", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 0, "EPHEMERAL predicate NEREDE should be dropped")
    
    def test_unknown_predicate_drop(self):
        """Test unknown predicates are dropped."""
        triplets = [
            {"subject": "Ali", "predicate": "UNKNOWN_PRED", "object": "Mehmet", "category": "general"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 0, "Unknown predicate should be dropped")
    
    def test_pronoun_filter(self):
        """Test pronouns in subject/object are dropped."""
        triplets = [
            {"subject": "BEN", "predicate": "SEVER", "object": "Pizza", "category": "personal"},
            {"subject": "Ali", "predicate": "SEVER", "object": "SEN", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        # FAZ3: BEN mapping sayesinde 1. triplet geçer (mapped), 2. triplet (SEN) drop edilir.
        self.assertEqual(len(cleaned), 1, "BEN mapped triplets should pass in FAZ3, SEN should be dropped")
        self.assertEqual(cleaned[0]["subject"], "__USER__::test_user")
    
    def test_valid_triplet_passes(self):
        """Test valid triplet passes all filters."""
        triplets = [
            {"subject": "Ali", "predicate": "SEVER", "object": "Pizza", "category": "general"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 1, "Valid triplet should pass")
        self.assertEqual(cleaned[0]["subject"], "Ali")
        self.assertEqual(cleaned[0]["predicate"], "SEVER")
        self.assertEqual(cleaned[0]["object"], "Pizza")
    
    def test_category_bridge(self):
        """Test catalog category overrides extractor category."""
        triplets = [
            {"subject": "Ali", "predicate": "İSİM", "object": "Ali", "category": "general"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 1, "Triplet should pass")
        # İSİM is identity category, should map to "personal"
        self.assertEqual(cleaned[0]["category"], "personal", "Identity category should map to personal")


class TestTurkishNormalization(unittest.TestCase):
    """Test Turkish character normalization."""
    
    def setUp(self):
        self.catalog = get_catalog()
        self.assertIsNotNone(self.catalog)
    
    def test_turkish_char_normalization(self):
        """Test İ->I, Ğ->G normalization."""
        # YAŞAR_YER has Turkish chars
        normalized = PredicateCatalog.normalize_predicate("YAŞAR_YER")
        self.assertEqual(normalized, "YASAR_YER", "Turkish chars should be normalized")
        
        # Should still resolve
        key = self.catalog.resolve_predicate("YASAR_YER")  # Normalized version
        self.assertIsNotNone(key, "Normalized predicate should resolve")
        
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "YAŞAR_YER", "Canonical should preserve Turkish chars")


if __name__ == "__main__":
    unittest.main()
