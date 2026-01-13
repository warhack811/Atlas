import asyncio
from Atlas.memory.neo4j_manager import neo4j_manager

async def migrate():
    try:
        print("--- Migrating case-sensitive anchors ---")
        # 1. Merge __User__::Admin into __USER__::admin
        query = """
        MATCH (old:Entity)
        WHERE old.name IN ['__User__::Admin', '__USER__::Admin', '__User__::admin']
        MERGE (new:Entity {name: '__USER__::admin'})
        WITH old, new
        MATCH (old)-[r:FACT]->(target)
        MERGE (new)-[new_r:FACT {predicate: r.predicate, user_id: r.user_id}]->(target)
        ON CREATE SET new_r += properties(r)
        DELETE r
        WITH old, new
        MATCH (source)-[r:FACT]->(old)
        MERGE (source)-[new_r:FACT {predicate: r.predicate, user_id: r.user_id}]->(new)
        ON CREATE SET new_r += properties(r)
        DELETE r
        DELETE old
        """
        await neo4j_manager.query_graph(query)
        print("Anchor migration done.")

        # 3. Resolve 'admin' name conflict by forcing 'Muhammet'
        query = """
        MATCH (s:Entity {name: '__USER__::admin'})-[r:FACT {predicate: 'İSİM'}]->(o:Entity)
        WHERE o.name IN ['Kullanıcı', 'Verilmemiş', 'Bilinmiyor', 'Adı Verilmemiş', 'Bilgi Yok', 'Verilmemis', 'Isim Yok']
        DELETE r
        """
        await neo4j_manager.query_graph(query)
        
        query = """
        MATCH (s:Entity {name: '__USER__::admin'})-[r:FACT {predicate: 'İSİM'}]->(o:Entity)
        WHERE o.name = 'Muhammet'
        SET r.status = 'ACTIVE'
        """
        await neo4j_manager.query_graph(query)
        print("Admin identity conflict resolved.")

        # 5. Purge legacy episodes for 'admin' to avoid summary confusion
        query = """
        MATCH (u:User {id: 'admin'})-[:HAS_SESSION]->(s:Session)-[:HAS_EPISODE]->(e:Episode)
        DETACH DELETE e
        """
        await neo4j_manager.query_graph(query)
        print("Legacy episodes purged.")

    finally:
        await neo4j_manager.close()

if __name__ == "__main__":
    asyncio.run(migrate())
