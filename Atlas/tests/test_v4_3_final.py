import asyncio
import os
import sys
from datetime import datetime, timedelta
import logging

# Proje kök dizinini yol listesine ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Atlas.memory.neo4j_manager import neo4j_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("v4.3-final-test")

async def run_detailed_verification():
    USER_ID = "test_user_v43_final"
    print(f"\n--- V4.3 PROTOCOL FINAL VERIFICATION: {USER_ID} ---\n")
    
    # 0. Clean
    await neo4j_manager.delete_all_memory(USER_ID)
    
    # TEST 1: Sequential Versioning (EXCLUSIVE SUPERSEDE)
    print("TEST 1: EXCLUSIVE Predicate Superseding (Low Conf -> High Conf)")
    # First: Low confidence info
    await neo4j_manager.store_triplets(
        [{"subject": "__USER__", "predicate": "MESLEĞİ", "object": "Stajyer", "confidence": 0.5}], 
        USER_ID, "turn_1"
    )
    # Second: High confidence update
    await neo4j_manager.store_triplets(
        [{"subject": "__USER__", "predicate": "MESLEĞİ", "object": "Mühendis", "confidence": 1.0}], 
        USER_ID, "turn_2"
    )
    
    results = await neo4j_manager.query_graph(
        "MATCH (s:Entity)-[r:FACT {user_id: $uid, predicate: 'MESLEĞİ'}]->(o:Entity) "
        "RETURN r.status as status, o.name as value, toString(r.valid_until) as valid_until",
        {"uid": USER_ID}
    )
    for res in results:
        print(f"   Row: {res}")
        if res["value"] == "Stajyer":
            assert res["status"] == "SUPERSEDED"
            assert res["valid_until"] is not None
        if res["value"] == "Mühendis":
            assert res["status"] == "ACTIVE"
    print("[OK] TEST 1 PASSED: Versioning over Erasure confirmed.\n")

    # TEST 2: Implicit Retraction (Forgotten Fact)
    print("TEST 2: Soft Retraction (forget_fact)")
    await neo4j_manager.store_triplets(
        [{"subject": "__USER__", "predicate": "SEVER", "object": "Elma", "confidence": 1.0}], 
        USER_ID, "turn_3"
    )
    # User forgets: "Elma sevdiğimi unut" -> hard_delete=False (Archival)
    await neo4j_manager.forget_fact(USER_ID, "Elma", hard_delete=False)
    
    res_forget = await neo4j_manager.query_graph(
        "MATCH (s:Entity)-[r:FACT {user_id: $uid, predicate: 'SEVER'}]->(o:Entity {name: 'Elma'}) "
        "RETURN r.status as status",
        {"uid": USER_ID}
    )
    print(f"   Forget result: {res_forget}")
    assert res_forget[0]["status"] == "SUPERSEDED"
    print("[OK] TEST 2 PASSED: Soft retraction confirmed.\n")

    # TEST 3: Session Deletion Persistence
    print("TEST 3: Persistent Session Deletion")
    SESSION_ID = "temp_session_v43"
    await neo4j_manager.ensure_user_session(USER_ID, SESSION_ID)
    await neo4j_manager.append_turn(USER_ID, SESSION_ID, "user", "Test message")
    
    # Delete
    await neo4j_manager.delete_session(USER_ID, SESSION_ID)
    
    # Verify persistence
    check_session = await neo4j_manager.query_graph(
        "MATCH (s:Session {id: $sid}) RETURN s", {"sid": SESSION_ID}
    )
    print(f"   Check session: {check_session}")
    assert len(check_session) == 0
    print("[OK] TEST 3 PASSED: Session deletion persistence confirmed.\n")

    print("\n--- ALL V4.3 TESTS PASSED SUCCESSFULLY! ---\n")

async def main():
    try:
        await run_detailed_verification()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await neo4j_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
