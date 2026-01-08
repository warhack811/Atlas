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
        stats = self.metrics.total_stats
        print(f"\n[RC-7.1 ÖZET]: HARD PASS: {stats['hard_pass_count']}/{stats['hard_pass_count']+stats['hard_fail_count']}, SOFT PASS: {stats['soft_pass_count']}/{stats['soft_pass_count']+stats['soft_fail_count']}")
        print(f"[METRİKLER]: Rapor oluşturuldu -> {report_path}")

    @staticmethod
    def asciify(s: str) -> str:
        """Türkçe karakterleri ASCII'ye çevirir."""
        tr_map = str.maketrans("ıİşŞçÇöÖüÜğĞ", "iiSSccOOuuGG")
        return s.translate(tr_map).lower()

    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_user_memory_mode')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.get_recent_turns')
    @patch('Atlas.memory.neo4j_manager.neo4j_manager.query_graph')
    @patch('Atlas.memory.identity_resolver.get_user_anchor')
    @patch('Atlas.memory.predicate_catalog.get_catalog')
    async def test_all_scenarios(self, mock_catalog, mock_anchor, mock_query, mock_turns, mock_mode):
        mock_anchor.return_value = "__USER__::test_user"
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
            severity = sc.get("severity", "SOFT")
            
            mock_mode.return_value = sc.get("policy_mode", "STANDARD")
            mock_turns.return_value = fixtures.get("turns", [])
            
            def query_side_effect(query, params=None):
                params = params or {}
                f_uid = params.get("uid")
                if "MATCH (s:Session {id: $sid})-[:HAS_EPISODE]" in query:
                    return [e for e in fixtures.get("episodes", []) if e.get("status") == "READY"]
                if "r.predicate IN ['İSİM'" in query:
                    res = fixtures.get("identity", [])
                    if f_uid: res = [r for r in res if r.get("uid") == f_uid or "uid" not in r]
                    return res
                if "r.predicate IN $predicates" in query:
                    res = fixtures.get("hard", []) + fixtures.get("soft", [])
                    if f_uid: res = [r for r in res if r.get("uid") == f_uid or "uid" not in r]
                    return res
                if "status: 'CONFLICTED'" in query:
                    # RC-11 conflicts mock
                    raw_conflicts = fixtures.get("conflicts", [])
                    # Gruplanmış formatta dönmesi lazım? 
                    # build_memory_context_v3 -> _retrieve_conflicts -> query_graph
                    # _retrieve_conflicts expect: [{predicate, value, updated_at}]
                    res = []
                    for c in raw_conflicts:
                        res.append({"predicate": c["predicate"], "value": c["new_value"], "updated_at": "2024-01-01"})
                        res.append({"predicate": c["predicate"], "value": c["old_value"], "updated_at": "2023-01-01"})
                    return res
                return []
            mock_query.side_effect = query_side_effect
            
            stats = {}
            error = None
            try:
                raw_context = await build_chat_context_v1(uid, "session_1", user_msg, stats=stats)
                context = self.asciify(raw_context)
                
                hits = 0
                contains_list = sc.get("expected_contains", [])
                for exp in contains_list:
                    if self.asciify(exp) in context: hits += 1
                
                leaks = 0
                not_contains_list = sc.get("expected_not_contains", [])
                for nexp in not_contains_list:
                    if self.asciify(nexp) in context: leaks += 1
                
                success = (hits == len(contains_list)) and (leaks == 0)
                if not success:
                    error = f"Hits: {hits}/{len(contains_list)}, Leaks: {leaks}"
                
                self.metrics.log_scenario(sid, success, stats, contains_list, not_contains_list, hits, leaks, severity, error)
                
                if severity == "HARD" and not success:
                    print(f"\n--- DEBUG FAIL {sid} ({sc['category']}) ---\n{raw_context}\n--------------------")
                    self.fail(f"HARD QUALITY GATE FAILED: Scenario {sid} - {error}")
            except Exception as e:
                self.metrics.log_scenario(sid, False, stats, [], [], 0, 0, severity, str(e))
                if severity == "HARD": raise e

if __name__ == "__main__":
    unittest.main()
