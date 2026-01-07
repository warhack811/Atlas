import unittest
from Atlas.memory.context import is_duplicate

class TestRC5Dedupe(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(is_duplicate("Ankara'da yaşıyorum.", ["Ankara'da yaşıyorum."]))
    
    def test_prefix_match(self):
        # Semantic fact vs turn match
        self.assertTrue(is_duplicate("YAŞAR_YER: Ankara", ["Kullanıcı: Ankara'da yaşıyorum."]))
    
    def test_normalization(self):
        self.assertTrue(is_duplicate("  BÖREK  sever  ", ["Atlas: Börek sever."]))

    def test_no_duplicate(self):
        self.assertFalse(is_duplicate("Hava güzel.", ["Fiyatlar arttı."]))

if __name__ == "__main__":
    unittest.main()
