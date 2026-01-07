import unittest
import json
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from Atlas.memory.context import build_chat_context_v1
from Atlas.memory.golden_metrics import GoldenMetrics

class TestRC7GoldenSet(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # JSON yükle
        path = os.path.join(os.path.dirname(__file__), "golden_set_rc7.json")
        with open(path, "r", encoding="utf-8") as f:
            self.scenarios = json.load(f)
        self.metrics = GoldenMetrics()

    async def asyncTearDown(self):
        # Sonuçları raporla
        report_path = self.metrics.generate_report()
        print(f"\n[METRİKLER]: Rapor oluşturuldu -> {report_path}")

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph')
    @patch('Atlas.memory.identity_resolver.get_user_anchor')
    @patch('Atlas.memory.predicate_catalog.get_catalog')
    async def test_all_scenarios(self, mock_catalog, mock_anchor, mock_query, mock_turns, mock_mode):
        # Sabitler
        mock_anchor.return_value = "__USER__::test_user"
        
        # Katalog mock
        cat_mock = MagicMock()
        cat_mock.by_key = {
            "İSİM": {"type": "EXCLUSIVE", "canonical": "İSİM"},
            "YAŞI": {"type": "EXCLUSIVE", "canonical": "YAŞI"},
            "MESLEĞİ": {"type": "EXCLUSIVE", "canonical": "MESLEĞİ"},
            "YAŞAR_YER": {"type": "EXCLUSIVE", "canonical": "YAŞAR_YER"},
            "SEVER": {"type": "ADDITIVE", "canonical": "SEVER"},
            "RENK_SEVER": {"type": "ADDITIVE", "canonical": "RENK_SEVER"},
            "TUTAR": {"type": "ADDITIVE", "canonical": "TUTAR"}
        }
        mock_catalog.return_value = cat_mock

        for sc in self.scenarios:
            sid = sc["id"]
            user_msg = sc["user_message"]
            fixtures = sc.get("fixtures", {})
            uid = sc.get("user_id", "test_user")
            
            # Mock setup
            mock_mode.return_value = sc.get("policy_mode", "STANDARD")
            mock_turns.return_value = fixtures.get("turns", [])
            
            # Query graph mock (Episodic + Identity + Hard + Soft)
            def query_side_effect(query, params=None):
                params = params or {}
                # Filter by UID if MULTI_USER test
                f_uid = params.get("uid")
                
                if "MATCH (s:Session {id: $sid})-[:HAS_EPISODE]" in query:
                    eps = fixtures.get("episodes", [])
                    return [e for e in eps if e.get("status") == "READY"]
                
                if "r.predicate IN ['İSİM', 'YAŞI', 'MESLEĞİ'" in query:
                    res = fixtures.get("identity", [])
                    if f_uid: res = [r for r in res if r.get("uid") == f_uid or "uid" not in r]
                    return res
                
                if "entry.get(\"type\") == \"EXCLUSIVE\"" in query or "EXCLUSIVE" in query:
                    res = fixtures.get("hard", [])
                    if f_uid: res = [r for r in res if r.get("uid") == f_uid or "uid" not in r]
                    return res
                
                if "ADDITIVE" in query or "TEMPORAL" in query:
                    res = fixtures.get("soft", [])
                    if f_uid: res = [r for r in res if r.get("uid") == f_uid or "uid" not in r]
                    return res
                
                return []

            mock_query.side_effect = query_side_effect
            
            # Run
            stats = {}
            error = None
            try:
                context = await build_chat_context_v1(uid, "session_1", user_msg, stats=stats)
                
                # Assertions
                hits = 0
                for exp in sc.get("expected_contains", []):
                    if exp.lower() in context.lower(): hits += 1
                
                leaks = 0
                for nexp in sc.get("expected_not_contains", []):
                    if nexp.lower() in context.lower(): leaks += 1
                
                success = True
                if sc.get("expected_contains") and hits < len(sc["expected_contains"]): success = False
                if sc.get("expected_not_contains") and leaks > 0: success = False
                
                if not success:
                    error = f"Hits: {hits}/{len(sc.get('expected_contains', []))}, Leaks: {leaks}"
                
                self.metrics.log_scenario(sid, success, stats, 
                                        sc.get("expected_contains", []), 
                                        sc.get("expected_not_contains", []),
                                        hits, leaks, error)
                
            except Exception as e:
                self.metrics.log_scenario(sid, False, stats, [], [], 0, 0, str(e))

if __name__ == "__main__":
    unittest.main()
