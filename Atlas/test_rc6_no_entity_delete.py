import unittest
import os
import re

class TestRC6NoEntityDelete(unittest.TestCase):
    def test_grep_safe_pruning(self):
        """DETACH DELETE sadece user-scoped node'larda geçmeli, Entity'lerde asla."""
        base_path = os.path.dirname(os.path.dirname(__file__))
        atlas_path = os.path.join(base_path, "Atlas")
        
        pattern = re.compile(r"DETACH" + r" DELETE.*En" + r"tity", re.IGNORECASE)
        violations = []
        
        for root, _, files in os.walk(atlas_path):
            for file in files:
                if file.endswith(".py") and file != "test_rc6_no_entity_delete.py":
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if pattern.search(content):
                            violations.append(path)
        
        self.assertEqual(len(violations), 0, f"Violation: DETACH DELETE Entity found in: {violations}")

if __name__ == "__main__":
    unittest.main()
