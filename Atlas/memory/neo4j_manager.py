import asyncio
import logging
import time
import uuid
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

    async def fact_exists(self, user_id: str, subject: str, predicate: str, obj: str) -> bool:
        """
        Belirli bir triplet'in ACTIVE olup olmadığını kontrol eder. (FAZ5)
        """
        query = """
        MATCH (s:Entity {name: $sub})-[r:FACT {predicate: $pred, user_id: $uid}]->(o:Entity {name: $obj})
        WHERE r.status = 'ACTIVE' OR r.status IS NULL
        RETURN count(r) > 0 as exists
        """
        results = await self.query_graph(query, {"uid": user_id, "sub": subject, "pred": predicate, "obj": obj})
        return results[0]["exists"] if results else False

    async def create_notification(self, user_id: str, data: Dict[str, Any]) -> str:
        """
        Yeni bir bildirim (Notification) oluşturur ve kullanıcıya bağlar. (FAZ7)
        """
        notification_id = uuid.uuid4().hex
        query = """
        MATCH (u:User {id: $uid})
        CREATE (n:Notification {
            id: $nid,
            user_id: $uid,
            created_at: datetime(),
            message: $message,
            type: $type,
            read: false,
            source: $source,
            score_relevance: $relevance,
            score_urgency: $urgency,
            score_fatigue: $fatigue,
            reason: $reason,
            related_task_id: $task_id
        })
        MERGE (u)-[:HAS_NOTIFICATION]->(n)
        RETURN n.id as id
        """
        try:
            await self.query_graph(query, {
                "uid": user_id,
                "nid": notification_id,
                "message": data.get("message"),
                "type": data.get("type", "proactive_warning"),
                "source": data.get("source", "observer"),
                "relevance": data.get("score_relevance", 1.0),
                "urgency": data.get("score_urgency", 1.0),
                "fatigue": data.get("score_fatigue", 1.0),
                "reason": data.get("reason", ""),
                "task_id": data.get("related_task_id")
            })
            return notification_id
        except Exception as e:
            logger.error(f"Bildirim oluşturma hatası: {e}")
            return None

    async def list_notifications(self, user_id: str, limit: int = 10, unread_only: bool = False) -> List[Dict]:
        """
        Kullanıcının bildirimlerini listeler. (FAZ7)
        """
        where_clause = "WHERE n.read = false" if unread_only else ""
        query = f"""
        MATCH (u:User {{id: $uid}})-[:HAS_NOTIFICATION]->(n:Notification)
        {where_clause}
        RETURN n.id as id, n.message as message, n.type as type, n.created_at as created_at, 
               n.read as read, n.reason as reason
        ORDER BY n.created_at DESC
        LIMIT $limit
        """
        try:
            results = await self.query_graph(query, {"uid": user_id, "limit": limit})
            return results if results else []
        except Exception as e:
            logger.error(f"Bildirim listeleme hatası: {e}")
            return []

    async def acknowledge_notification(self, user_id: str, notification_id: str) -> bool:
        """
        Bildirimi okundu (read=true) olarak işaretler. (FAZ7)
        """
        query = """
        MATCH (u:User {id: $uid})-[:HAS_NOTIFICATION]->(n:Notification {id: $nid})
        SET n.read = true
        RETURN count(n) as updated
        """
        try:
            results = await self.query_graph(query, {"uid": user_id, "nid": notification_id})
            return results[0]["updated"] > 0 if results else False
        except Exception as e:
            logger.error(f"Bildirim onaylama hatası: {e}")
            return False

    async def get_notification_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Kullanıcının bildirim tercihlerini getirir. (FAZ7)
        """
        query = """
        MATCH (u:User {id: $uid})
        RETURN u.notifications_enabled as enabled,
               u.notification_mode as mode,
               u.quiet_hours_start as quiet_start,
               u.quiet_hours_end as quiet_end,
               u.max_notifications_per_day as max_daily
        """
        try:
            results = await self.query_graph(query, {"uid": user_id})
            if not results:
                return {
                    "enabled": False,
                    "mode": "STANDARD",
                    "quiet_start": None,
                    "quiet_end": None,
                    "max_daily": 5
                }
            res = results[0]
            return {
                "enabled": res.get("enabled", False),
                "mode": res.get("mode", "STANDARD"),
                "quiet_start": res.get("quiet_start"),
                "quiet_end": res.get("quiet_end"),
                "max_daily": res.get("max_daily") if res.get("max_daily") is not None else 5
            }
        except Exception as e:
            logger.error(f"Bildirim ayarları getirme hatası: {e}")
            return {"enabled": False}

    async def count_daily_notifications(self, user_id: str) -> int:
        """
        Kullanıcının bugün aldığı bildirim sayısını döndürür. (FAZ7)
        """
        query = """
        MATCH (u:User {id: $uid})-[:HAS_NOTIFICATION]->(n:Notification)
        WHERE n.created_at >= datetime({hour: 0, minute: 0, second: 0})
        RETURN count(n) as daily_count
        """
        try:
            results = await self.query_graph(query, {"uid": user_id})
            return results[0]["daily_count"] if results else 0
        except Exception as e:
            logger.error(f"Günlük bildirim sayma hatası: {e}")
            return 0

    async def get_user_memory_mode(self, user_id: str) -> str:
        """Kullanıcının hafıza modunu getirir (OFF/STANDARD/FULL)."""
        settings = await self.get_user_settings(user_id)
        return settings.get("memory_mode", "STANDARD")

    async def ensure_user_session(self, user_id: str, session_id: str):
        """
        Kullanıcı ve oturum arasındaki ilişkiyi kurar/günceller. (RC-2)
        """
        query = """
        MERGE (u:User {id: $uid})
        ON CREATE SET u.created_at = datetime(), u.notifications_enabled = true
        MERGE (s:Session {id: $sid})
        ON CREATE SET s.created_at = datetime()
        SET s.last_seen_at = datetime()
        MERGE (u)-[:HAS_SESSION]->(s)
        """
        await self.query_graph(query, {"uid": user_id, "sid": session_id})

    async def get_user_settings(self, user_id: str) -> dict:
        """
        Kullanıcının politikalarını ve bildirim ayarlarını getirir. (RC-2)
        """
        query = "MATCH (u:User {id: $uid}) RETURN u"
        results = await self.query_graph(query, {"uid": user_id})
        
        default_settings = {
            "memory_mode": os.getenv("ATLAS_DEFAULT_MEMORY_MODE", "STANDARD"),
            "notifications_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "max_notifications_per_day": 5,
            "notification_mode": "STANDARD"
        }
        
        if results and results[0].get("u"):
            # Neo4j node objesinden verileri çek
            u = dict(results[0]["u"])
            return {
                "memory_mode": u.get("memory_mode", default_settings["memory_mode"]),
                "notifications_enabled": u.get("notifications_enabled", default_settings["notifications_enabled"]),
                "quiet_hours_start": u.get("quiet_hours_start", default_settings["quiet_hours_start"]),
                "quiet_hours_end": u.get("quiet_hours_end", default_settings["quiet_hours_end"]),
                "max_notifications_per_day": u.get("max_notifications_per_day", default_settings["max_notifications_per_day"]),
                "notification_mode": u.get("notification_mode", default_settings["notification_mode"])
            }
        return default_settings

    async def set_user_settings(self, user_id: str, patch: dict) -> dict:
        """
        Kullanıcının ayarlarını günceller. (RC-2)
        """
        keys = []
        valid_keys = ["memory_mode", "notifications_enabled", "quiet_hours_start", "quiet_hours_end", "max_notifications_per_day", "notification_mode"]
        for k in patch.keys():
            if k in valid_keys:
                keys.append(f"u.{k} = ${k}")
        
        if not keys:
            return await self.get_user_settings(user_id)
            
        set_clause = ", ".join(keys)
        query = f"MERGE (u:User {{id: $uid}}) SET {set_clause} RETURN u"
        params = {"uid": user_id, **patch}
        await self.query_graph(query, params)
        return await self.get_user_settings(user_id)

    async def try_acquire_lock(self, lock_name: str, holder_id: str, ttl_seconds: int) -> bool:
        """
        Neo4j üzerinde dağıtık kilit (Distributed Lock) almaya çalışır. (FAZ7-R)
        """
        query = """
        MERGE (l:SchedulerLock {name: $name})
        WITH l
        WHERE l.holder IS NULL 
           OR datetime() >= l.expires_at 
           OR l.holder = $holder
        SET l.holder = $holder, 
            l.expires_at = datetime() + duration({seconds: $ttl}),
            l.updated_at = datetime()
        RETURN count(l) > 0 as success
        """
        try:
            results = await self.query_graph(query, {
                "name": lock_name,
                "holder": holder_id,
                "ttl": ttl_seconds
            })
            return results[0]["success"] if results else False
        except Exception as e:
            logger.error(f"Kilit alma hatası ({lock_name}): {e}")
            return False

    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        """
        Kilidi serbest bırakır.
        """
        query = """
        MATCH (l:SchedulerLock {name: $name, holder: $holder})
        SET l.holder = null, l.expires_at = null
        RETURN count(l) > 0 as success
        """
        try:
            results = await self.query_graph(query, {"name": lock_name, "holder": holder_id})
            return results[0]["success"] if results else False
        except Exception as e:
            logger.error(f"Kilit bırakma hatası ({lock_name}): {e}")
            return False

# Tekil örnek
neo4j_manager = Neo4jManager()
