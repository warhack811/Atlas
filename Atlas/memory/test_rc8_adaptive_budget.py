import unittest
from Atlas.memory.context import ContextBudgeter

class TestRC8Budget(unittest.TestCase):
    def test_general_budget(self):
        # GENERAL: transcript 0.8, episodic 0.2, semantic 0.0
        budgeter = ContextBudgeter(intent="GENERAL")
        self.assertEqual(budgeter.get_layer_budget("transcript"), 4800)
        self.assertEqual(budgeter.get_layer_budget("episodic"), 1200)
        self.assertEqual(budgeter.get_layer_budget("semantic"), 0)

    def test_personal_budget(self):
        # PERSONAL: transcript 0.3, episodic 0.2, semantic 0.5
        budgeter = ContextBudgeter(intent="PERSONAL")
        self.assertEqual(budgeter.get_layer_budget("transcript"), 1800)
        self.assertEqual(budgeter.get_layer_budget("episodic"), 1200)
        self.assertEqual(budgeter.get_layer_budget("semantic"), 3000)

    def test_off_mode_mixed_budget(self):
        # MIXED: transcript 0.4, episodic 0.3, semantic 0.3
        # OFF modunda semantic (0.3) diğerlerine oransal dağılır
        # transcript's share in others: 0.4 / (0.4+0.3) = 0.4/0.7 approx 0.57
        # transcript new weight: 0.4 + 0.3 * (0.4/0.7) = 0.4 + 0.1714 = 0.5714
        budgeter = ContextBudgeter(mode="OFF", intent="MIXED")
        self.assertEqual(budgeter.get_layer_budget("semantic"), 0)
        self.assertGreater(budgeter.get_layer_budget("transcript"), 2400) # 0.4*6000=2400
        self.assertGreater(budgeter.get_layer_budget("episodic"), 1800)

if __name__ == "__main__":
    unittest.main()
