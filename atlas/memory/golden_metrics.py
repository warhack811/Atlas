import json
import os
import tempfile
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class GoldenMetrics:
    """RC-7: Golden Set testleri için metrik raporlama sınıfı."""
    
    def __init__(self):
        self.results = []
        self.total_stats = {
            "pass_count": 0,
            "fail_count": 0,
            "hard_pass_count": 0,
            "hard_fail_count": 0,
            "hard_hit_success": 0,
            "hard_hit_total": 0,
            "hard_leak_success": 0,
            "hard_leak_total": 0,
            "soft_pass_count": 0,
            "soft_fail_count": 0,
            "total_chars": 0,
            "layer_usage": {"transcript": 0, "episodic": 0, "semantic": 0},
            "dedupe_removed_total": 0,
            "hit_success": 0,
            "hit_total": 0,
            "leak_success": 0,
            "leak_total": 0,
            "context_build_ms_total": 0.0,
            "intent_counts": {}
        }
        self.worst_fails = []

    def log_scenario(self, scenario_id: str, success: bool, stats: Dict, 
                    expected_contains: List[str], expected_not_contains: List[str],
                    actual_contains_hits: int, actual_not_contains_leaks: int,
                    severity: str = "SOFT", error: str = None):
        """Bir senaryonun sonuçlarını kaydeder."""
        self.total_stats["pass_count" if success else "fail_count"] += 1
        
        if severity == "HARD":
            self.total_stats["hard_pass_count" if success else "hard_fail_count"] += 1
            self.total_stats["hard_hit_total"] += len(expected_contains)
            self.total_stats["hard_hit_success"] += actual_contains_hits
            self.total_stats["hard_leak_total"] += len(expected_not_contains)
            self.total_stats["hard_leak_success"] += (len(expected_not_contains) - actual_not_contains_leaks)
        else:
            self.total_stats["soft_pass_count" if success else "soft_fail_count"] += 1

        if stats:
            self.total_stats["total_chars"] += stats.get("total_chars", 0)
            for layer, val in stats.get("layer_usage", {}).items():
                self.total_stats["layer_usage"][layer] += val
            self.total_stats["dedupe_removed_total"] += stats.get("dedupe_count", 0)
            self.total_stats["context_build_ms_total"] += stats.get("context_build_ms", 0.0)
            
            intent = stats.get("intent", "UNKNOWN")
            self.total_stats["intent_counts"][intent] = self.total_stats["intent_counts"].get(intent, 0) + 1

        # Global Hit/Leak Metrikleri
        self.total_stats["hit_total"] += len(expected_contains)
        self.total_stats["hit_success"] += actual_contains_hits
        
        self.total_stats["leak_total"] += len(expected_not_contains)
        self.total_stats["leak_success"] += (len(expected_not_contains) - actual_not_contains_leaks)

        res = {
            "id": scenario_id,
            "success": success,
            "severity": severity,
            "stats": stats,
            "error": error
        }
        self.results.append(res)

        if not success and len(self.worst_fails) < 5:
            self.worst_fails.append({"id": scenario_id, "severity": severity, "error": error})

    def generate_report(self) -> str:
        """Raporu JSON olarak temp dizinine yazar ve yolu döner."""
        hard_total = self.total_stats['hard_pass_count'] + self.total_stats['hard_fail_count']
        soft_total = self.total_stats['soft_pass_count'] + self.total_stats['soft_fail_count']
        
        report = {
            "summary": {
                "overall_pass_rate": f"{(self.total_stats['pass_count'] / len(self.results) * 100):.1f}%" if self.results else "0%",
                "hard_pass_rate": f"{(self.total_stats['hard_pass_count'] / hard_total * 100):.1f}%" if hard_total else "0%",
                "hard_leak_rate": f"{( (self.total_stats['hard_leak_total'] - self.total_stats['hard_leak_success']) / self.total_stats['hard_leak_total'] * 100):.1f}%" if self.total_stats['hard_leak_total'] else "0%",
                "soft_pass_rate": f"{(self.total_stats['soft_pass_count'] / soft_total * 100):.1f}%" if soft_total else "0%",
                "hit_rate": f"{(self.total_stats['hit_success'] / self.total_stats['hit_total'] * 100):.1f}%" if self.total_stats['hit_total'] else "0%",
                "leak_rate": f"{( (self.total_stats['leak_total'] - self.total_stats['leak_success']) / self.total_stats['leak_total'] * 100):.1f}%" if self.total_stats['leak_total'] else "0%",
                "avg_chars": int(self.total_stats['total_chars'] / len(self.results)) if self.results else 0,
                "total_dedupe": self.total_stats['dedupe_removed_total'],
                "avg_context_build_ms": f"{(self.total_stats['context_build_ms_total'] / len(self.results)):.2f}ms" if self.results else "0ms",
                "intent_distribution": self.total_stats["intent_counts"]
            },
            "total_stats": self.total_stats,
            "worst_fails": self.worst_fails
        }
        
        fd, path = tempfile.mkstemp(suffix="_rc7_metrics.json")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return path
