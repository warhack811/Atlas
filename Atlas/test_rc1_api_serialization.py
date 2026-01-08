import unittest
from datetime import datetime
from Atlas.api import serialize_neo4j_value
from neo4j.time import DateTime

class TestApiSerialization(unittest.TestCase):
    def test_serialize_datetime(self):
        dt = datetime(2026, 1, 7, 16, 20, 0)
        self.assertEqual(serialize_neo4j_value(dt), "2026-01-07T16:20:00")

    def test_serialize_neo4j_datetime(self):
        # Neo4j DateTime object
        ndt = DateTime(2026, 1, 7, 16, 20, 0)
        # Neo4j isoformat adds nanoseconds by default
        self.assertEqual(serialize_neo4j_value(ndt), "2026-01-07T16:20:00.000000000")

    def test_serialize_nested_list_dict(self):
        data = {
            "ts": datetime(2026, 1, 7),
            "items": [
                {"t": DateTime(2026, 1, 8)}
            ]
        }
        res = serialize_neo4j_value(data)
        self.assertEqual(res["ts"], "2026-01-07T00:00:00")
        self.assertEqual(res["items"][0]["t"], "2026-01-08T00:00:00.000000000")

if __name__ == "__main__":
    unittest.main()
