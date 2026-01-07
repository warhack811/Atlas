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
            "total_chars": 0,
            "layer_usage": {"transcript": 0, "episodic": 0, "semantic": 0},
            "dedupe_removed_total": 0,
            "hit_success": 0,
            "hit_total": 0,
            "leak_success": 0,
            "leak_total": 0
        }
        self.worst_fails = []

    def log_scenario(self, scenario_id: str, success: bool, stats: Dict, 
                    expected_contains: List[str], expected_not_contains: List[str],
                    actual_contains_hits: int, actual_not_contains_leaks: int,
                    error: str = None):
        """Bir senaryonun sonuçlarını kaydeder."""
        self.total_stats["pass_count" if success else "fail_count"] += 1
        
        if stats:
            self.total_stats["total_chars"] += stats.get("total_chars", 0)
            for layer, val in stats.get("layer_usage", {}).items():
                self.total_stats["layer_usage"][layer] += val
            self.total_stats["dedupe_removed_total"] += stats.get("dedupe_count", 0)

        # Hit/Leak Metrikleri
        self.total_stats["hit_total"] += len(expected_contains)
        self.total_stats["hit_success"] += actual_contains_hits
        
        self.total_stats["leak_total"] += len(expected_not_contains)
        # Sızıntı yoksa success (leaks count = 0 ise hepsi başarılı)
        self.total_stats["leak_success"] += (len(expected_not_contains) - actual_not_contains_leaks)

        res = {
            "id": scenario_id,
            "success": success,
            "stats": stats,
            "error": error
        }
        self.results.append(res)

        if not success and len(self.worst_fails) < 5:
            self.worst_fails.append({"id": scenario_id, "error": error})

    def generate_report(self) -> str:
        """Raporu JSON olarak temp dizinine yazar ve yolu döner."""
        report = {
            "summary": {
                "pass_rate": f"{(self.total_stats['pass_count'] / len(self.results) * 100):.1f}%" if self.results else "0%",
                "hit_rate": f"{(self.total_stats['hit_success'] / self.total_stats['hit_total'] * 100):.1f}%" if self.total_stats['hit_total'] else "0%",
                "leak_rate": f"{( (self.total_stats['leak_total'] - self.total_stats['leak_success']) / self.total_stats['leak_total'] * 100):.1f}%" if self.total_stats['leak_total'] else "0%",
                "avg_chars": int(self.total_stats['total_chars'] / len(self.results)) if self.results else 0,
                "total_dedupe": self.total_stats['dedupe_removed_total']
            },
            "total_stats": self.total_stats,
            "worst_fails": self.worst_fails
        }
        
        fd, path = tempfile.mkstemp(suffix="_rc7_metrics.json")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return path
