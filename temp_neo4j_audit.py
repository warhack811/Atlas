import asyncio
import json
import os
import sys

# Project root'u ekle
sys.path.append(os.getcwd())

async def run_audit_queries():
    try:
        from Atlas.memory.neo4j_manager import neo4j_manager
        
        queries = {
            "rel_types_props": """
                MATCH ()-[r]->()
                RETURN type(r) AS rel_type, keys(r) AS props, count(*) AS c
                ORDER BY c DESC
                LIMIT 20
            """,
            "predicates": """
                MATCH ()-[r]->()
                WHERE r.predicate IS NOT NULL
                RETURN r.predicate AS predicate, count(*) AS c
                ORDER BY c DESC
                LIMIT 200
            """,
            "timestamps": """
                MATCH ()-[r]->()
                WHERE r.created_at IS NOT NULL OR r.updated_at IS NOT NULL
                RETURN count(r) AS with_time_props
            """
        }
        
        results = {}
        for name, cypher in queries.items():
            print(f"Executing {name}...")
            res = await neo4j_manager.query_graph(cypher)
            results[name] = res
            
        print("\n--- QUERY RESULTS ---")
        with open("neo4j_audit_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str, ensure_ascii=False)
        print("Results saved to neo4j_audit_results.json")
        
        # Explicit driver closure to prevent event loop errors
        await neo4j_manager.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_audit_queries())
