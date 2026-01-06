"""
FAZ 3: Identity Resolver Tests
Unit tests for first-person anchor mapping, LAKABI, and self-profile retrieval.
"""

import unittest
from Atlas.memory.identity_resolver import (
    get_user_anchor, is_first_person, is_second_person, is_other_pronoun, normalize_text_for_match
)
from Atlas.memory.extractor import sanitize_triplets
from Atlas.memory.predicate_catalog import get_catalog


class TestIdentityResolver(unittest.TestCase):
    """Test identity resolver helper functions."""
    
    def test_get_user_anchor(self):
        """Test user anchor generation."""
        anchor = get_user_anchor("test_123")
        self.assertEqual(anchor, "__USER__::test_123")
        self.assertIn("__USER__::", anchor)
    
    def test_is_first_person_ben(self):
        """Test first-person: BEN."""
        self.assertTrue(is_first_person("BEN"))
        self.assertTrue(is_first_person("ben"))
        self.assertTrue(is_first_person("  Ben  "))
    
    def test_is_first_person_benim(self):
        """Test first-person: BENIM."""
        self.assertTrue(is_first_person("BENIM"))
        self.assertTrue(is_first_person("benim"))
    
    def test_is_first_person_kendim(self):
        """Test first-person: KENDIM."""
        self.assertTrue(is_first_person("KENDIM"))
        self.assertTrue(is_first_person("kendim"))
    
    def test_is_not_first_person(self):
        """Test non-first-person."""
        self.assertFalse(is_first_person("Ali"))
        self.assertFalse(is_first_person("SEN"))
        self.assertFalse(is_first_person("O"))
    
    def test_is_second_person(self):
        """Test second-person: SEN."""
        self.assertTrue(is_second_person("SEN"))
        self.assertTrue(is_second_person("sen"))
        self.assertTrue(is_second_person("SENIN"))
    
    def test_is_other_pronoun(self):
        """Test other pronouns."""
        self.assertTrue(is_other_pronoun("O"))
        self.assertTrue(is_other_pronoun("ONLAR"))
        self.assertTrue(is_other_pronoun("HOCAM"))
    
    def test_normalize_text(self):
        """Test Turkish normalization."""
        self.assertEqual(normalize_text_for_match("  Benim  "), "BENIM")
        self.assertEqual(normalize_text_for_match("İstanbul"), "ISTANBUL")
        self.assertEqual(normalize_text_for_match("ğüşöç"), "GUSOC")


class TestFirstPersonAnchorMapping(unittest.TestCase):
    """Test first-person subject → user anchor mapping in sanitize_triplets."""
    
    def setUp(self):
        """Ensure catalog is loaded."""
        self.catalog = get_catalog()
        self.assertIsNotNone(self.catalog, "Catalog must be loaded")
    
    def test_first_person_subject_maps_to_anchor(self):
        """Test BEN subject → __USER__::<user_id>."""
        triplets = [
            {"subject": "BEN", "predicate": "İSİM", "object": "Ali", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user_faz3", "test")
        
        self.assertEqual(len(cleaned), 1, "Triplet should not be dropped")
        self.assertEqual(cleaned[0]["subject"], "__USER__::test_user_faz3", "BEN should map to user anchor")
        self.assertEqual(cleaned[0]["predicate"], "İSİM")
        self.assertEqual(cleaned[0]["object"], "Ali")
    
    def test_first_person_multiple_forms(self):
        """Test BENIM, BANA also map to anchor."""
        triplets = [
            {"subject": "BENIM", "predicate": "YAŞI", "object": "25", "category": "personal"},
            {"subject": "BANA", "predicate": "LAKABI", "object": "Mami", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "user_456", "test")
        
        self.assertEqual(len(cleaned), 2, "Both triplets should pass")
        for t in cleaned:
            self.assertEqual(t["subject"], "__USER__::user_456", "All first-person should map to anchor")
    
    def test_second_person_still_dropped(self):
        """Test SEN subject still dropped."""
        triplets = [
            {"subject": "SEN", "predicate": "İSİM", "object": "Asistan", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 0, "SEN should still be dropped")
    
    def test_object_pronoun_still_dropped(self):
        """Test pronouns in object position still dropped."""
        triplets = [
            {"subject": "Ali", "predicate": "SEVER", "object": "BEN", "category": "personal"},
            {"subject": "Ali", "predicate": "SEVER", "object": "SEN", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "test_user", "test")
        
        self.assertEqual(len(cleaned), 0, "Object pronouns should still be dropped")


class TestLakabiPredicate(unittest.TestCase):
    """Test LAKABI predicate support."""
    
    def setUp(self):
        self.catalog = get_catalog()
        self.assertIsNotNone(self.catalog)
    
    def test_lakabi_allowed_by_catalog(self):
        """Test LAKABI resolves correctly."""
        key = self.catalog.resolve_predicate("LAKABI")
        self.assertIsNotNone(key, "LAKABI should exist in catalog")
        
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "LAKABI")
        
        enabled = self.catalog.get_enabled(key)
        self.assertTrue(enabled, "LAKABI should be enabled")
    
    def test_lakabi_aliases(self):
        """Test LAKABI aliases: LAKAP, NICK."""
        # LAKAP alias
        key = self.catalog.resolve_predicate("LAKAP")
        self.assertIsNotNone(key, "LAKAP alias should resolve")
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "LAKABI", "LAKAP should map to LAKABI")
        
        # NICK alias
        key = self.catalog.resolve_predicate("NICK")
        self.assertIsNotNone(key, "NICK alias should resolve")
        canonical = self.catalog.get_canonical(key)
        self.assertEqual(canonical, "LAKABI")
    
    def test_lakabi_in_sanitize_triplets(self):
        """Test LAKABI passes through sanitize_triplets."""
        triplets = [
            {"subject": "BEN", "predicate": "LAKABI", "object": "Mami", "category": "personal"}
        ]
        cleaned = sanitize_triplets(triplets, "user_789", "test")
        
        self.assertEqual(len(cleaned), 1, "LAKABI triplet should pass")
        self.assertEqual(cleaned[0]["predicate"], "LAKABI")
        self.assertEqual(cleaned[0]["subject"], "__USER__::user_789")


class TestSelfProfileRetrieval(unittest.TestCase):
    """Test self-profile detection in context.py."""
    
    def test_context_imports_identity_resolver(self):
        """Test that context.py imports get_user_anchor."""
        from Atlas.memory.context import ContextBuilder
        import inspect
        
        # Get source code
        source = inspect.getsource(ContextBuilder.get_neo4j_context)
        
        # Check for identity_resolver import
        self.assertIn("get_user_anchor", source, "context.py should import get_user_anchor")
    
    def test_self_profile_keywords_present(self):
        """Test that SELF_PROFILE_KEYWORDS exist in context.py."""
        from Atlas.memory.context import ContextBuilder
        import inspect
        
        source = inspect.getsource(ContextBuilder.get_neo4j_context)
        
        # Check for self-profile detection
        self.assertIn("SELF_PROFILE_KEYWORDS", source, "Should have self-profile keyword detection")
        self.assertIn("ben", source.lower(), "Should detect 'ben' keyword")
        self.assertIn("adım", source.lower() or "adim" in source.lower(), "Should detect 'adım' keyword")
    
    def test_anchor_query_in_context(self):
        """Test that anchor query exists in context.py."""
        from Atlas.memory.context import ContextBuilder
        import inspect
        
        source = inspect.getsource(ContextBuilder.get_neo4j_context)
        
        # Check for anchor-based query
        self.assertIn("anchor", source.lower(), "Should have anchor query")
        self.assertIn("İSİM", source, "Anchor query should retrieve İSİM")
        self.assertIn("LAKABI", source, "Anchor query should retrieve LAKABI")


if __name__ == "__main__":
    unittest.main()
