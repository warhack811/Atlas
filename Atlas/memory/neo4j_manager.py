import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from Atlas.config import Config

logger = logging.getLogger(__name__)

class Neo4jManager:
    """
    ATLAS Yönlendirici - Neo4j Graf Veritabanı Yöneticisi
    ----------------------------------------------------
    Bu bileşen, kullanıcı bilgilerini ve olaylar arasındaki ilişkileri bir graf 
    yapısı olarak saklayan Neo4j veritabanı ile iletişimi yönetir.

    Temel Sorumluluklar:
    1. Bağlantı Yönetimi: Neo4j sürücüsü (driver) oluşturma ve oturum kontrolü.
    2. Bilgi Kaydı (Triplets): Özne-Yüklem-Nesne yapısındaki bilgileri veritabanına işleme.
    3. Graf Sorgulama: Cypher dili kullanılarak veritabanından ilişkisel bilgi çekme.
    4. Dayanıklılık: AuraDB Free Tier gibi bulut servislerinde oluşan bağlantı kesilmelerine 
       karşı otomatik yeniden bağlanma ve deneme (retry) mantığı.
    5. Singleton Yapısı: Tüm uygulama boyunca tek bir veritabanı sürücüsü üzerinden işlem yapma.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jManager, cls).__new__(cls)
            cls._instance._driver = None
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Sınıf başlatıldığında (eğer daha önce başlatılmadıysa) bağlantıyı kurar."""
        if self._initialized:
            return
        self._connect()

    def _connect(self):
        """Sürücü bağlantısını kurar veya yeniler."""
        uri = Config.NEO4J_URI
        user = Config.NEO4J_USER
        password = Config.NEO4J_PASSWORD
        
        try:
            if self._driver:
                try:
                    # Mevcut bir sürücü varsa kaynakları serbest bırakmak için kapatmayı dene (asenkron)
                    asyncio.create_task(self._driver.close())
                except:
                    pass
            
            self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
            self._initialized = True
            logger.info(f"Neo4j bağlantısı kuruldu: {uri}")
        except Exception as e:
            self._initialized = False
            logger.error(f"Neo4j sürücüsü başlatılamadı: {str(e)}")

    async def close(self):
        """Veritabanı bağlantı sürücüsünü güvenli bir şekilde kapatır."""
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j bağlantısı kapatıldı.")

    async def store_triplets(self, triplets: List[Dict], user_id: str, source_turn_id: str | None = None) -> int:
        """
        Verilen triplet listesini Neo4j graf veritabanına kaydeder.
        
        Args:
            triplets: subject-predicate-object yapısındaki bilgi listesi
            user_id: Kullanıcı kimliği
            source_turn_id: Bu bilginin geldiği konuşma turn'ünün ID'si (RDR request_id) - FAZ2 provenance
        """
        if not triplets or not self._initialized:
            return 0
        
        # FAZ5: Lifecycle engine - EXCLUSIVE/ADDITIVE conflict resolution
        from Atlas.memory.lifecycle_engine import resolve_conflicts, supersede_relationship
        from Atlas.memory.predicate_catalog import get_catalog
        
        catalog = get_catalog()
        new_triplets, supersede_ops = await resolve_conflicts(triplets, user_id, source_turn_id, catalog)
        
        # Execute supersede operations first
        for op in supersede_ops:
            await supersede_relationship(
                op["user_id"],
                op["subject"],
                op["predicate"],
                op["old_object"],
                op["new_turn_id"]
            )
        
        # Then write new triplets
        if not new_triplets:
            return 0
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self._driver or not self._initialized:
                    self._connect()

                async with self._driver.session() as session:
                    # FAZ2: source_turn_id'yi _execute_triplet_merge'e gönder
                    result = await session.execute_write(self._execute_triplet_merge, user_id, new_triplets, source_turn_id)
                    logger.info(f"Başarıyla {result} bilgi (triplet) Neo4j'ye kaydedildi (Kullanıcı: {user_id})")
                    return result
            except (ServiceUnavailable, SessionExpired, ConnectionResetError) as e:
                logger.warning(f"Neo4j bağlantı hatası (Deneme {attempt+1}/{max_retries}): {str(e)}")
                self._connect()
                await asyncio.sleep(1) # Kısa bir bekleme
            except Exception as e:
                logger.error(f"Neo4j kayıt hatası: {str(e)}")
                break
        return 0

    @staticmethod
    async def _execute_triplet_merge(tx, user_id, triplets, source_turn_id=None):
        """
        Cypher sorgusunu çalıştırarak verileri düğüm ve ilişki olarak birleştirir.
        Daha temiz bir hafıza için isimleri normalize eder.
        """
        # Python tarafında isimleri normalize et (Örn: muhammet -> Muhammet)
        normalized_triplets = []
        for t in triplets:
            nt = t.copy()
            nt["subject"] = str(t.get("subject", "")).strip().title()
            nt["object"] = str(t.get("object", "")).strip().title()
            nt["predicate"] = str(t.get("predicate", "")).strip().upper() # İlişkileri büyük harf yap
            normalized_triplets.append(nt)

        # KNOWS ilişkisi için User node'u oluştur
        query = """
        MERGE (u:User {id: $user_id})
        WITH u
        UNWIND $triplets AS t
        MERGE (s:Entity {name: t.subject})
        MERGE (o:Entity {name: t.object})
        // FAZ0.1-1: İlişkiyi hem predicate hem de user_id ile MERGE et (multi-user isolation)
        // Bu sayede farklı kullanıcılar aynı entity'ler arasında farklı ilişkilere sahip olabilir
        MERGE (s)-[r:FACT {predicate: t.predicate, user_id: $user_id}]->(o)
        ON CREATE SET 
            r.confidence = COALESCE(t.confidence, 1.0),
            r.category = COALESCE(t.category, 'general'),
            r.created_at = datetime(),
            r.updated_at = datetime(),
            // FAZ2: Provenance ve schema alanları (yeni relationship'ler için)
            r.schema_version = 2,
            r.status = 'ACTIVE',
            r.source_turn_id_first = $source_turn_id,
            r.source_turn_id_last = $source_turn_id,
            r.modality = 'ASSERTED',
            r.polarity = 'POSITIVE',
            r.attribution = 'USER',
            r.inferred = false
        ON MATCH SET
            r.confidence = COALESCE(t.confidence, r.confidence),
            r.category = COALESCE(t.category, r.category),
            r.updated_at = datetime(),
            // FAZ2: Güncelleme sırasında source_turn_id_last ve schema_version'ı güncelle
            r.source_turn_id_last = $source_turn_id,
            r.schema_version = COALESCE(r.schema_version, 1)
        // User'ın Entity'yi bildiğini işaretle
        MERGE (u)-[:KNOWS]->(s)
        MERGE (u)-[:KNOWS]->(o)
        RETURN count(r)
        """
        
        # FAZ2: source_turn_id parametresini query'ye ekle (şimdilik kullanılmıyor, FAZ2-2'de schema'ya eklenecek)
        records = await self.query_graph(query, {"user_id": user_id, "triplets": normalized_triplets, "source_turn_id": source_turn_id})
        return records[0]['count(r)'] if records else 0

    async def delete_all_memory(self, user_id: str) -> bool:
        """Kullanıcıya ait tüm graf hafızasını siler (Hard Reset).
        FAZ0.1-4: Shared Entity node'ları değil, sadece kullanıcıya ait ilişkileri siler.
        """
        query = """
        MATCH (u:User {id: $uid})
        // Kullanıcının KNOWS ilişkilerini sil
        OPTIONAL MATCH (u)-[k:KNOWS]->(e:Entity)
        DELETE k
        // Kullanıcının FACT ilişkilerini sil (user_id ile filtrelenerek)
        WITH u
        OPTIONAL MATCH ()-[r:FACT {user_id: $uid}]->()
        DELETE r
        // Sadece User node'unu sil, Entity'leri değil (başka kullanıcılar kullanıyor olabilir)
        DELETE u
        """
        try:
            await self.query_graph(query, {"uid": user_id})
            logger.info(f"Kullanıcı {user_id} için tüm hafıza silindi.")
            return True
        except Exception as e:
            logger.error(f"Hafıza silme hatası: {e}")
            return False

    async def forget_fact(self, user_id: str, entity_name: str) -> int:
        """Belirli bir varlık (Entity) ile ilgili kullanıcıya ait ilişkileri siler.
        FAZ0.1-4: Entity node'u silinmez, sadece kullanıcıya ait FACT ve KNOWS ilişkileri silinir.
        """
        query = """
        MATCH (u:User {id: $uid})-[k:KNOWS]->(e:Entity {name: $ename})
        // Önce bu entity ile kullanıcıya ait FACT ilişkilerini sil
        OPTIONAL MATCH (e)-[r:FACT {user_id: $uid}]->()
        DELETE r
        OPTIONAL MATCH ()-[r2:FACT {user_id: $uid}]->(e)
        DELETE r2
        // Sonra KNOWS ilişkisini sil
        DELETE k
        // Entity node'u SİLME - başka kullanıcılar kullanıyor olabilir
        RETURN count(k) as deleted_count
        """
        try:
            records = await self.query_graph(query, {"uid": user_id, "ename": entity_name})
            count = records[0]['deleted_count'] if records else 0
            logger.info(f"Kullanıcı {user_id} için '{entity_name}' bilgisi unutuldu ({count} ilişki).")
            return count
        except Exception as e:
            logger.error(f"Bilgi unutma hatası: {e}")
            return 0

    async def query_graph(self, cypher_query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Graf veritabanı üzerinde Cypher sorgusu çalıştırır ve sonuçları liste olarak döner.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self._driver or not self._initialized:
                    self._connect()

                async with self._driver.session() as session:
                    result = await session.run(cypher_query, **(params or {}))
                    records = await result.data()
                    return records
            except (ServiceUnavailable, SessionExpired, ConnectionResetError) as e:
                logger.warning(f"Neo4j sorgu hatası (Deneme {attempt+1}/{max_retries}): {str(e)}")
                self._connect()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Neo4j sorgu hatası: {str(e)}")
                break
        return []

# Tekil örnek
neo4j_manager = Neo4jManager()
