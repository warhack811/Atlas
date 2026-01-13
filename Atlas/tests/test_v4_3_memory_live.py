import asyncio
import os
import sys
from datetime import datetime, timedelta
import logging
import json

# Proje kök dizinini yol listesine ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Atlas.memory.neo4j_manager import neo4j_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("v4.3-test")

async def run_v43_test():
    USER_ID = "test_observer_43"
    
    print(f"\n--- TEST START: {USER_ID} ---\n")
    
    # 0. Clean
    await neo4j_manager.delete_all_memory(USER_ID)
    print("0. Deleted all memory for test user.")
    
    # 1. First Entry (Confidence 1.0 to ensure it's ACTIVE)
    triplets = [{"subject": "__USER__", "predicate": "MESLEĞİ", "object": "Yazılım Geliştirici", "confidence": 1.0}]
    print(f"1. Writing: {triplets}")
    res1 = await neo4j_manager.store_triplets(triplets, USER_ID, "turn_001")
    print(f"   Result count: {res1}")
    
    check1 = await neo4j_manager.query_graph(
        "MATCH (u:User {id: $uid})-[:KNOWS]->(s:Entity)-[r:FACT]->(o:Entity) WHERE r.predicate = 'MESLEĞİ' "
        "RETURN r.status as status, o.name as value, r.predicate as pred",
        {"uid": USER_ID}
    )
    print(f"   Check 1: {check1}")
    
    # 2. Update (Confidence 1.0 -> will cause CONFLICT if threshold is 0.7)
    # To test SUPERSEDED, I will use lower confidence for the first one next time, 
    # but let's see why this specific test fails.
    print("\n2. Writing update: Proje Yöneticisi")
    triplets2 = [{"subject": "__USER__", "predicate": "MESLEĞİ", "object": "Proje Yöneticisi", "confidence": 1.0}]
    res2 = await neo4j_manager.store_triplets(triplets2, USER_ID, "turn_002")
    print(f"   Result count: {res2}")
    
    check2 = await neo4j_manager.query_graph(
        "MATCH (u:User {id: $uid})-[:KNOWS]->(s:Entity)-[r:FACT]->(o:Entity) WHERE r.predicate = 'MESLEĞİ' "
        "RETURN r.status as status, o.name as value, r.predicate as pred",
        {"uid": USER_ID}
    )
    print(f"   Check 2 (Everything for MESLEĞİ):")
    for row in check2:
        print(f"      - {row}")
    
    # 3. Memory Archiving (Mood)
    print("\n3. Testing Mood Archiving...")
    query_mood = """
    MATCH (u:User {id: $uid})
    MERGE (ue:Entity {name: "__USER__"})
    MERGE (mood:Entity {name: "Mutlu"})
    MERGE (ue)-[r:FACT {predicate: 'HİSSEDİYOR', user_id: $uid, object_name_internal: 'Mutlu'}]->(mood)
    SET r.created_at = datetime() - duration({days: 4}),
        r.status = 'ACTIVE'
    """
    await neo4j_manager.query_graph(query_mood, {"uid": USER_ID})
    archived = await neo4j_manager.archive_expired_moods(days=3)
    print(f"   Archived mood count: {archived}")
    
    # 4. Final Summary
    print("\n--- TEST SUMMARY ---")
    final_state = await neo4j_manager.query_graph(
        "MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity) "
        "RETURN s.name as sub, r.predicate as pred, o.name as obj, r.status as status",
        {"uid": USER_ID}
    )
    for f in final_state:
        print(f"   {f}")
    print("\n--- TEST END ---\n")

async def main():
    try:
        await run_v43_test()
    finally:
        await neo4j_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
