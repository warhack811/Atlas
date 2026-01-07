import unittest
import json
import os
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.context import build_chat_context_v1

class TestRC5GoldenSet(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        gs_path = os.path.join(os.path.dirname(__file__), "golden_set_rc5.json")
        with open(gs_path, "r", encoding="utf-8") as f:
            self.scenarios = json.load(f)

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns', new_callable=AsyncMock)
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph', new_callable=AsyncMock)
    @patch('Atlas.memory.context.build_memory_context_v3', new_callable=AsyncMock)
    async def test_golden_scenarios(self, mock_v3, mock_query, mock_turns, mock_mode):
        for scene in self.scenarios:
            with self.subTest(scene_id=scene["id"]):
                # Mock settings
                mock_mode.return_value = scene.get("mode", "STD")
                
                # Setup fixtures
                mock_turns.return_value = scene["fixtures"].get("turns", [])
                mock_query.return_value = scene["fixtures"].get("episodes", [])
                
                # Mock build_memory_context_v3 logic
                mode = scene.get("mode", "STD")
                if mode == "OFF":
                    mock_v3.return_value = "[BİLGİ]: Kullanıcı tercihi gereği kişisel hafıza erişimi kapalıdır."
                else:
                    f = scene["fixtures"]
                    v3_parts = []
                    if f.get("identity"):
                        v3_parts.append("### Kullanıcı Profili")
                        for x in f["identity"]: v3_parts.append(f"- {x['predicate']}: {x['object']}")
                    if f.get("soft"):
                        v3_parts.append("\n### Yumuşak Sinyaller (Soft Signals)")
                        for x in f["soft"]: v3_parts.append(f"- {x['subject']} - {x['predicate']} - {x['object']}")
                    if f.get("hard"):
                        v3_parts.append("\n### Sert Gerçekler (Hard Facts)")
                        for x in f["hard"]: v3_parts.append(f"- {x['subject']} - {x['predicate']} - {x['object']}")
                    mock_v3.return_value = "\n".join(v3_parts)

                # Run
                context = await build_chat_context_v1("u_test", "s_test", scene["input"])
                
                # Verify
                try:
                    for s in scene.get("expected_contains", []):
                        self.assertIn(s.lower(), context.lower(), f"Failed {scene['id']}: Expected '{s}' NOT found")
                    
                    for s in scene.get("expected_not_contains", []):
                        self.assertNotIn(s.lower(), context.lower(), f"Failed {scene['id']}: Unexpected '{s}' FOUND")
                except AssertionError as e:
                    with open("debug_context.txt", "a", encoding="utf-8") as f:
                        f.write(f"\n--- FAILED SCENARIO: {scene['id']} ---\nCONTEXT:\n{context}\n-------------------\n")
                    raise e

if __name__ == "__main__":
    unittest.main()
