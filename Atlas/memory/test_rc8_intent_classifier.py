import unittest
from Atlas.memory.intent import classify_intent_tr

class TestRC8Intent(unittest.TestCase):
    def test_personal_intent(self):
        self.assertEqual(classify_intent_tr("Adımı hatırlıyor musun?"), "PERSONAL")
        self.assertEqual(classify_intent_tr("Benim tercihlerim neler?"), "PERSONAL")
        self.assertEqual(classify_intent_tr("Nerede yaşıyorum?"), "PERSONAL")

    def test_task_intent(self):
        self.assertEqual(classify_intent_tr("Yarın toplantıyı hatırlat"), "TASK")
        self.assertEqual(classify_intent_tr("Bugün yapmam lazım olanlar?"), "TASK")

    def test_followup_intent(self):
        self.assertEqual(classify_intent_tr("Biraz daha detaylandır"), "FOLLOWUP")
        self.assertEqual(classify_intent_tr("Devam et lütfen"), "FOLLOWUP")

    def test_general_intent(self):
        self.assertEqual(classify_intent_tr("Python nedir?"), "GENERAL")
        self.assertEqual(classify_intent_tr("Hava nasıl bugün?"), "GENERAL")
        self.assertEqual(classify_intent_tr("Dünyanın çevresi kaç km?"), "GENERAL")

    def test_mixed_intent(self):
        self.assertEqual(classify_intent_tr("Merhaba nasılsın"), "MIXED")

if __name__ == "__main__":
    unittest.main()
