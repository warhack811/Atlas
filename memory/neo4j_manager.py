import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from ..config import Config

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

    async def store_triplets(self, triplets: List[Dict[str, str]], user_id: str):
        """
        Bilgi parçalarını (üçlüler/triplets) graf veritabanına atomik olarak kaydeder.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self._driver or not self._initialized:
                    self._connect()

                async with self._driver.session() as session:
                    result = await session.execute_write(self._execute_triplet_merge, user_id, triplets)
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
    async def _execute_triplet_merge(tx, user_id, triplets):
        """
        Cypher sorgusunu çalıştırarak verileri düğüm ve ilişki olarak birleştirir.
        Triplet yapısı: {subject, predicate, object, confidence?, category?}
        """
        query = """
        MERGE (u:User {id: $user_id})
        WITH u
        UNWIND $triplets AS t
        MERGE (s:Entity {name: t.subject})
        MERGE (o:Entity {name: t.object})
        MERGE (s)-[r:FACT]->(o)
        SET r.predicate = t.predicate, 
            r.user_id = $user_id,
            r.confidence = COALESCE(t.confidence, 1.0),
            r.category = COALESCE(t.category, 'general'),
            r.updated_at = datetime()
        MERGE (u)-[:KNOWS]->(s)
        RETURN count(r)
        """
        result = await tx.run(query, user_id=user_id, triplets=triplets)
        record = await result.single()
        return record[0] if record else 0

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
