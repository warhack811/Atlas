import unittest
from Atlas.memory.context import ContextBudgeter

class TestRC5Budgeter(unittest.TestCase):
    def test_std_budget_allocation(self):
        budgeter = ContextBudgeter(mode="STD")
        self.assertEqual(budgeter.get_layer_budget("transcript"), 2400)
        self.assertEqual(budgeter.get_layer_budget("episodic"), 1800)
        self.assertEqual(budgeter.get_layer_budget("semantic"), 1800)
    
    def test_off_budget_allocation(self):
        budgeter = ContextBudgeter(mode="OFF")
        self.assertEqual(budgeter.get_layer_budget("transcript"), 3600)
        self.assertEqual(budgeter.get_layer_budget("episodic"), 2400)
        self.assertEqual(budgeter.get_layer_budget("semantic"), 0)

if __name__ == "__main__":
    unittest.main()
