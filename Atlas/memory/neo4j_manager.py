import os
import asyncio
import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from Atlas.config import Config
from datetime import datetime, timedelta
import math

# Professional Logging Configuration: Suppress noisy Neo4j notifications about missing properties/labels
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logging.getLogger("neo4j.io").setLevel(logging.ERROR)

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
        try:
            self._connect()
        except Exception:
            # Hata zaten _connect içinde loglandı
            pass

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
            raise e

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
        
        # Execute supersede/conflict operations first
        for op in supersede_ops:
            # V4.3: Physical delete replaced with status='SUPERSEDED' in supersede_relationship
            await supersede_relationship(
                op["user_id"],
                op["subject"],
                op["predicate"],
                op["old_object"],
                op["new_turn_id"],
                op.get("type", "SUPERSEDE")
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
                try:
                    self._connect()
                except Exception:
                    pass
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
        # CRITICAL FIX: Don't apply .title() to __USER__ anchors!
        normalized_triplets = []
        importance_map = {
            "İSİM": 1.0, "MESLEĞİ": 1.0, "YAŞI": 1.0, "YAŞAR_YER": 1.0,
            "LAKABI": 0.8, "HOBİ": 0.5, "YEMEK_TERCİHİ": 0.4, "GÜNLÜK_AKTİVİTE": 0.3
        }
        for t in triplets:
            nt = t.copy()
            # FAZ-γ FIX: Preserve __USER__ anchors, don't apply .title()
            subject_str = str(t.get("subject", "")).strip()
            object_str = str(t.get("object", "")).strip()
            
            nt["subject"] = subject_str if subject_str.startswith("__USER__") else subject_str.title()
            nt["object"] = object_str if object_str.startswith("__USER__") else object_str.title()
            pred = str(t.get("predicate", "")).strip().upper()
            nt["predicate"] = pred
            nt["confidence"] = t.get("confidence", 1.0)
            nt["status"] = t.get("status", "ACTIVE")
            nt["category"] = t.get("category", "general")
            
            logger.info(f"[NEO4J WRITE DEBUG] Normalized triplet: subject='{nt['subject']}', pred='{pred}', object='{nt['object']}', status='{nt['status']}'")
            normalized_triplets.append(nt)

        # KNOWS ilişkisi için User node'u oluştur
        query = """
        MERGE (u:User {id: $user_id})
        WITH u
        UNWIND $triplets AS t
        MERGE (s:Entity {name: t.subject})
        MERGE (o:Entity {name: t.object})
        WITH u, s, o, t
        
        
        // V4.3: Versioning over Erasure (EXCLUSIVE conflict handling)
        CALL {
            WITH s, t, u
            OPTIONAL MATCH (s)-[old_r:FACT {predicate: t.predicate, user_id: $user_id}]->(old_o:Entity)
            WHERE t.is_exclusive = true 
              AND old_o IS NOT NULL 
              AND old_o.name <> t.object 
              AND (old_r.status = 'ACTIVE' OR old_r.status IS NULL)
            SET old_r.status = 'SUPERSEDED', old_r.valid_until = datetime(), old_r.updated_at = datetime()
        }

        // FAZ0.1-1: İlişkiyi hem predicate hem de user_id ile MERGE et (multi-user isolation)
        MERGE (s)-[r:FACT {predicate: t.predicate, user_id: $user_id, object_name_internal: t.object}]->(o)
        ON CREATE SET 
            r.confidence = COALESCE(t.confidence, 1.0),
            r.importance_score = COALESCE(t.importance_score, 0.5),
            r.category = COALESCE(t.category, 'general'),
            r.created_at = datetime(),
            r.updated_at = datetime(),
            r.last_verified_at = datetime(),
            r.schema_version = 2,
            r.status = COALESCE(t.status, 'ACTIVE'),
            r.source_turn_id_first = $source_turn_id,
            r.source_turn_id_last = $source_turn_id,
            r.modality = 'ASSERTED',
            r.polarity = 'POSITIVE',
            r.attribution = 'USER',
            r.inferred = false
        ON MATCH SET
            r.confidence = COALESCE(t.confidence, r.confidence),
            r.importance_score = COALESCE(t.importance_score, r.importance_score),
            r.category = COALESCE(t.category, r.category),
            r.status = COALESCE(t.status, r.status),
            r.updated_at = datetime(),
            r.last_verified_at = datetime(),
            r.source_turn_id_last = $source_turn_id,
            r.schema_version = COALESCE(r.schema_version, 2)
        
        // User'ın Entity'yi bildiğini işaretle
        MERGE (u)-[:KNOWS]->(s)
        MERGE (u)-[:KNOWS]->(o)
        RETURN count(r) as count
        """
        
        # EXCLUSIVE bilgisini triplet'lere enjekte et (catalog bazlı)
        from Atlas.memory.predicate_catalog import get_catalog
        catalog = get_catalog()
        for nt in normalized_triplets:
            entry = catalog.by_key.get(nt["predicate"], {})
            nt["is_exclusive"] = entry.get("type") == "EXCLUSIVE" if entry else False

        logger.info(f"[NEO4J WRITE DEBUG] Executing query with user_id={user_id}, triplet_count={len(normalized_triplets)}")
        result = await tx.run(query, {"user_id": user_id, "triplets": normalized_triplets, "source_turn_id": source_turn_id})
        records = await result.data()
        write_count = records[0]['count'] if records else 0
        logger.info(f"[NEO4J WRITE DEBUG] Query completed. Wrote {write_count} FACT relationships")
        return write_count

    async def delete_all_memory(self, user_id: str) -> bool:
        """Kullanıcıya ait tüm graf hafızasını siler (Hard Reset).
        V4.3: FACT ilişkileriyle birlikte Turn, Session ve Episode düğümlerini de temizler.
        Ayrıca Qdrant, Semantic Cache ve RAM State'i de temizler.
        """
        # 1. Graf Temizliği (Neo4j)
        query = """
        MATCH (u:User {id: $uid})
        OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
        OPTIONAL MATCH (s)-[:HAS_TURN]->(t:Turn)
        OPTIONAL MATCH (s)-[:HAS_EPISODE]->(e:Episode)
        OPTIONAL MATCH ()-[r:FACT {user_id: $uid}]->()
        OPTIONAL MATCH (u)-[k:KNOWS]->(ent:Entity)
        DETACH DELETE t, e, s, r, k, u
        """
        
        try:
            # Neo4j Silme
            await self.query_graph(query, {"uid": user_id})
            logger.info(f"Neo4j: Kullanıcı {user_id} için tüm hafıza ve konuşma geçmişi silindi.")
            
            # 2. Vektör Temizliği (Qdrant)
            try:
                from Atlas.memory.qdrant_manager import qdrant_manager
                await qdrant_manager.delete_by_user(user_id)
                logger.info(f"Qdrant: '{user_id}' için vektör kayıtları temizlendi.")
            except Exception as qe:
                logger.error(f"Qdrant temizleme hatası: {qe}")

            # 3. RAM Temizliği (Identity Cache & State)
            try:
                from Atlas.memory.state import state_manager
                state_manager.clear_user_cache(user_id)
                logger.info(f"RAM: '{user_id}' için session state ve identity cache temizlendi.")
            except Exception as se:
                logger.error(f"RAM temizleme hatası: {se}")

            # 4. Semantic Cache Temizliği (Redis)
            try:
                from Atlas.memory.semantic_cache import semantic_cache
                await semantic_cache.clear_user(user_id)
                logger.info(f"Redis: '{user_id}' için semantic cache temizlendi.")
            except Exception as ce:
                logger.error(f"Redis temizleme hatası: {ce}")

            return True
        except Exception as e:
            logger.error(f"Global hafıza silme hatası ({user_id}): {e}")
            return False

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """Belirli bir oturumu ve ona bağlı turları/episodları siler."""
        query = """
        MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session {id: $sid})
        OPTIONAL MATCH (s)-[:HAS_TURN]->(t:Turn)
        OPTIONAL MATCH (s)-[:HAS_EPISODE]->(e:Episode)
        DETACH DELETE t, e, s
        """
        try:
            await self.query_graph(query, {"uid": user_id, "sid": session_id})
            logger.info(f"Session silindi: {session_id} (User: {user_id})")
            return True
        except Exception as e:
            logger.error(f"delete_session hatası: {e}")
            return False

    async def delete_all_sessions(self, user_id: str) -> bool:
        """Kullanıcının TÜM oturumlarını siler (User ve Fact düğümleri kalır)."""
        query = """
        MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session)
        OPTIONAL MATCH (s)-[:HAS_TURN]->(t:Turn)
        OPTIONAL MATCH (s)-[:HAS_EPISODE]->(e:Episode)
        DETACH DELETE t, e, s
        """
        try:
            await self.query_graph(query, {"uid": user_id})
            logger.info(f"Tüm sessionlar silindi: {user_id}")
            return True
        except Exception as e:
            logger.error(f"delete_all_sessions hatası: {e}")
            return False

    async def forget_fact(self, user_id: str, entity_name: str, hard_delete: bool = False) -> int:
        """
        Belirli bir varlık (Entity) ile ilgili kullanıcıya ait ilişkileri arşivler veya siler.
        V4.3: Varsayılan olarak soft-delete (SUPERSEDED) yapar, hard_delete=True ise fiziksel siler.
        """
        if hard_delete:
            query = """
            MATCH (u:User {id: $uid})-[k:KNOWS]->(e:Entity)
            WHERE toLower(e.name) = toLower($ename)
            OPTIONAL MATCH (e)-[r:FACT {user_id: $uid}]->()
            DELETE r
            OPTIONAL MATCH ()-[r2:FACT {user_id: $uid}]->(e)
            DELETE r2
            DELETE k
            RETURN count(k) as count
            """
        else:
            query = """
            MATCH (u:User {id: $uid})-[k:KNOWS]->(e:Entity)
            WHERE toLower(e.name) = toLower($ename)
            
            // 1. Entity'nin ÖZNE olduğu durumlar
            OPTIONAL MATCH (e)-[r1:FACT {user_id: $uid}]->()
            WHERE (r1.status = 'ACTIVE' OR r1.status IS NULL)
            SET r1.status = 'SUPERSEDED', r1.valid_until = datetime(), r1.updated_at = datetime()
            WITH e, count(r1) as count1, $uid as uid
            
            // 2. Entity'nin NESNE olduğu durumlar
            OPTIONAL MATCH ()-[r2:FACT {user_id: uid}]->(e)
            WHERE (r2.status = 'ACTIVE' OR r2.status IS NULL)
            SET r2.status = 'SUPERSEDED', r2.valid_until = datetime(), r2.updated_at = datetime()
            WITH count1, count(r2) as count2
            RETURN count1 + count2 as count
            """
            
        try:
            records = await self.query_graph(query, {"uid": user_id, "ename": entity_name})
            count = records[0]['count'] if records else 0
            action = "silindi" if hard_delete else "arşivlendi"
            
            # FAZ-Y: RAM Cache senkronizasyonu
            try:
                from Atlas.memory.state import state_manager
                state_manager.clear_user_cache(user_id)
            except: pass

            logger.info(f"Kullanıcı {user_id} için '{entity_name}' bilgisi {action} ({count} ilişki).")
            return count
        except Exception as e:
            logger.error(f"Bilgi unutma hatası: {e}")
            return 0

    async def correct_memory(
        self, 
        user_id: str, 
        target_type: str, 
        predicate: str, 
        new_value: Optional[str], 
        mode: str, 
        reason: Optional[str] = None,
        subject_id: Optional[str] = None,
        fact_id: Optional[str] = None
    ):
        """
        Kullanıcı geri bildirimi ile hafızayı düzeltir (RC-11).
        mode: 'replace' | 'retract'
        """
        # Scoping logic
        match_clause = "(s:Entity)-[r:FACT {predicate: $pred, user_id: $uid}]->(o:Entity)"
        if fact_id:
            # RELATIONSHIP hex id veya custom id ile bulma (Neo4j elementId)
            match_clause = "(s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity) WHERE elementId(r) = $fid"
        elif subject_id:
            match_clause = "(s:Entity {name: $sid})-[r:FACT {predicate: $pred, user_id: $uid}]->(o:Entity)"

        if mode == "retract":
            # İlişkiyi 'RETRACTED' yap
            query = f"""
            MATCH {match_clause}
            WHERE r.status = 'ACTIVE' OR r.status IS NULL
            SET r.status = 'RETRACTED',
                r.retraction_reason = $reason,
                r.updated_at = datetime()
            RETURN count(r) as count
            """
            params = {"uid": user_id, "pred": predicate, "reason": reason, "sid": subject_id, "fid": fact_id}
            result = await self.query_graph(query, params)
            return result[0]["count"] if result else 0
        
        elif mode == "replace" and new_value:
            # Önce aktifleri retract et, sonra yeniyi MERGE et
            retracted_count = await self.correct_memory(
                user_id, target_type, predicate, None, "retract", reason, subject_id, fact_id
            )
            
            # Yeni değeri yaz
            triplet = {
                "subject": subject_id if subject_id else "__USER__",
                "predicate": predicate,
                "object": new_value,
                "confidence": 1.0, # Manuel düzeltme tam güvendir
                "category": "personal",
                "attribution": "USER_CORRECTION"
            }
            
            if not subject_id:
                # Identity resolver anchor'ını bul
                from Atlas.memory.identity_resolver import get_user_anchor
                anchor = get_user_anchor(user_id)
                triplet["subject"] = anchor
            
            await self.store_triplets([triplet], user_id)
            return retracted_count + 1
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
                try:
                    self._connect()
                except Exception:
                    pass
                await asyncio.sleep(1)
                if attempt == max_retries - 1:
                    logger.error(f"Neo4j critical failure after {max_retries} retries: {e}")
                    raise e
            except Exception as e:
                logger.error(f"Neo4j query error: {str(e)}")
                raise e
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

    async def decay_soft_signals(self, decay_rate: float = 0.05):
        """
        Soft signal'ların confidence değerlerini düşürür (RC-11).
        Confidence threshold altına düşenler DEPRECATED olur.
        """
        query = """
        MATCH ()-[r:FACT {category: 'soft_signal', status: 'ACTIVE'}]->()
        SET r.confidence = r.confidence - $rate,
            r.updated_at = datetime()
        WITH r
        WHERE r.confidence < 0.2
        SET r.status = 'DEPRECATED'
        RETURN count(r) as decayed_count
        """
        try:
            results = await self.query_graph(query, {"rate": decay_rate})
            count = results[0]["decayed_count"] if results else 0
            if count > 0:
                logger.info(f"RC-11: {count} soft signal decay edildi.")
        except Exception as e:
            logger.error(f"Decay hatası: {e}")

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
        MATCH (u:User {{id: $uid}})
        OPTIONAL MATCH (u)-[:HAS_NOTIFICATION]->(n:Notification)
        {where_clause}
        RETURN n.id as id, coalesce(n.message, '') as message, coalesce(n.type, 'system') as type, 
               n.created_at as created_at, coalesce(n.read, false) as read, coalesce(n.reason, '') as reason
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
        MATCH (u:User {id: $uid})
        OPTIONAL MATCH (u)-[:HAS_NOTIFICATION]->(n:Notification)
        WHERE n.created_at >= datetime({hour: 0, minute: 0, second: 0})
        RETURN count(n) as daily_count
        """
        try:
            results = await self.query_graph(query, {"uid": user_id})
            return results[0]["daily_count"] if results else 0
        except Exception as e:
            logger.error(f"Günlük bildirim sayma hatası: {e}")
            return 0

    async def get_active_conflicts(self, user_id: str, limit: int = 3) -> List[Dict]:
        """
        FAZ-Y Final: Kullanıcıya ait aktif çelişkileri (CONFLICTED) getirir.
        """
        query = """
        MATCH (s:Entity)-[r:FACT {user_id: $uid, status: 'CONFLICTED'}]->(o:Entity)
        RETURN s.name as subject, r.predicate as predicate, o.name as value, r.updated_at as updated_at
        ORDER BY r.updated_at DESC
        LIMIT $limit
        """
        try:
            return await self.query_graph(query, {"uid": user_id, "limit": limit})
        except Exception as e:
            logger.error(f"Aktif çelişki sorgu hatası: {e}")
            return []

    async def get_last_active_entity(self, user_id: str, session_id: str) -> Optional[str]:
        """
        FAZ-Y Final: Son turlarda geçen ve önemi yüksek olan son güncellenmiş Entity'yi bulur.
        DST (Zamir Çözümleme) için referans sağlar.
        """
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_TURN]->(t:Turn)
        MATCH (u:User {id: $uid})-[:KNOWS]->(e:Entity)
        MATCH (e)-[r:FACT {user_id: $uid}]->()
        WHERE t.turn_index >= (
            MATCH (s)-[:HAS_TURN]->(total:Turn) 
            RETURN max(total.turn_index) - 2
        )
        AND r.importance_score > 0.5
        RETURN e.name as name, r.updated_at as updated_at
        ORDER BY r.updated_at DESC
        LIMIT 1
        """
        try:
            results = await self.query_graph(query, {"uid": user_id, "sid": session_id})
            return results[0]["name"] if results else None
        except Exception as e:
            logger.error(f"Son aktif varlık sorgu hatası: {e}")
            return None

    async def get_user_names(self, user_id: str) -> list:
        """
        Kullanıcının bilinen isimlerini döner.
        Identity resolution için kullanılır. (FAZ-γ)
        """
        query = """
        MATCH (s:Entity)-[r:FACT {user_id: $uid, predicate: 'İSİM'}]->(o:Entity)
        WHERE (r.status IS NULL OR r.status = 'ACTIVE' OR r.status = 'CONFLICTED')
        RETURN DISTINCT o.name as name
        """
        results = await self.query_graph(query, {"uid": user_id})
        return [r["name"] for r in results]

    async def get_facts_by_date_range(self, user_id: str, start_date, end_date) -> List[Dict]:
        """Belirli bir tarih aralığındaki tüm AKTİF veya SÜPERSEDED kayıtları getirir."""
        query = """
        MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
        WHERE (r.created_at >= $start AND r.created_at <= $end)
           OR (r.valid_until >= $start AND r.valid_until <= $end)
        RETURN s.name as subject, r.predicate as predicate, o.name as object, 
               toString(r.created_at) as ts, r.status as status
        ORDER BY r.created_at DESC
        LIMIT 20
        """
        try:
            return await self.query_graph(query, {
                "uid": user_id,
                "start": start_date,
                "end": end_date
            })
        except Exception as e:
            logger.error(f"Zamansal sorgu hatası: {e}")
            return []

    async def get_historical_facts(self, user_id: str, limit: int = 5) -> List[Dict]:
        """Kullanıcının arşivlenmiş (SUPERSEDED) önemli bilgilerini getirir."""
        query = """
        MATCH (s:Entity)-[r:FACT {user_id: $uid, status: 'SUPERSEDED'}]->(o:Entity)
        RETURN s.name as subject, r.predicate as predicate, o.name as object, 
               toString(r.created_at) as valid_from, toString(r.valid_until) as valid_to
        ORDER BY r.valid_until DESC
        LIMIT $limit
        """
        try:
            return await self.query_graph(query, {"uid": user_id, "limit": limit})
        except Exception as e:
            logger.error(f"Tarihsel hafıza çekme hatası: {e}")
            return []

    async def archive_expired_moods(self, days: int = 3) -> int:
        """3 günü dolan AKTİF duyguları otomatik olarak SUPERSEDED statüsüne taşır."""
        query = """
        MATCH ()-[r:FACT {predicate: 'HİSSEDİYOR'}]->()
        WHERE (r.status = 'ACTIVE' OR r.status IS NULL) 
          AND r.created_at < datetime() - duration({days: $days})
        SET r.status = 'SUPERSEDED', r.valid_until = datetime(), r.updated_at = datetime()
        RETURN count(r) as count
        """
        try:
            res = await self.query_graph(query, {"days": days})
            return res[0]['count'] if res else 0
        except Exception as e:
            logger.error(f"Duygu arşivleme hatası: {e}")
            return 0

    async def get_user_memory_mode(self, user_id: str) -> str:
        """Kullanıcının hafıza modunu getirir (OFF/STANDARD/FULL)."""
        settings = await self.get_user_settings(user_id)
        return settings.get("memory_mode", "STANDARD")

    async def ensure_user_session(self, user_id: str, session_id: str):
        """
        Kullanıcı ve oturum arasındaki ilişkiyi kurar/günceller. (RC-2.1)
        Varsayılanlar: notifications_enabled=false (opt-in), memory_mode='STANDARD'.
        Oturumlar user_id kapsamındadır.
        """
        query = """
        MERGE (u:User {id: $uid})
        ON CREATE SET 
            u.created_at = datetime(), 
            u.notifications_enabled = false,
            u.memory_mode = COALESCE($default_mode, 'STANDARD')
        
        // RC-2.1 FIX: Session uniqueness should be based on ID alone to prevent duplicates
        // during login/logout transitions for the same session.
        MERGE (s:Session {id: $sid})
        ON CREATE SET 
            s.created_at = datetime(),
            s.user_id = $uid
        ON MATCH SET
            s.user_id = $uid // Update ownership if changed
        
        SET s.last_seen_at = datetime()
        MERGE (u)-[:HAS_SESSION]->(s)
        """
        await self.query_graph(query, {
            "uid": user_id, 
            "sid": session_id,
            "default_mode": os.getenv("ATLAS_DEFAULT_MEMORY_MODE", "STANDARD")
        })

    async def get_user_timezone(self, user_id: str) -> str:
        """
        Kullanıcının zaman dilimini (timezone) getirir. Varsayılan: Europe/Istanbul
        """
        query = "MATCH (u:User {id: $uid}) RETURN u.timezone as tz"
        results = await self.query_graph(query, {"uid": user_id})
        if results and results[0].get("tz"):
            return results[0]["tz"]
        return "Europe/Istanbul"

    async def get_last_user_mood(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        FAZ-β: Kullanıcının en son kaydedilmiş duygu durumunu getirir.
        
        Args:
            user_id: Kullanıcı kimliği
            
        Returns:
            {"mood": str, "timestamp": str} dict veya None (veri yoksa)
            timestamp ISO 8601 formatında (UTC)
        """
        query = """
        MATCH (u:User {id: $uid})-[:KNOWS]->(:Entity)-[r:FACT]->(o:Entity)
        WHERE r.predicate IN ['HİSSEDİYOR', 'FEELS'] 
        RETURN o.name as mood, toString(r.created_at) as timestamp
        ORDER BY r.created_at DESC LIMIT 1
        """
        try:
            results = await self.query_graph(query, {"uid": user_id})
            if results and results[0].get("mood"):
                return {
                    "mood": results[0]["mood"],
                    "timestamp": results[0]["timestamp"]
                }
            return None
        except Exception as e:
            logger.error(f"FAZ-β: get_last_user_mood hatası: {e}")
            return None

    async def get_session_topic(self, session_id: str) -> Optional[str]:
        """
        FAZ-α Final: Oturumun veritabanındaki aktif konusunu getirir.
        State hydration (yeniden başlatma sonrası kurtarma) için kullanılır.
        
        Args:
            session_id: Session kimliği
            
        Returns:
            str: Aktif topic adı veya None (topic yoksa)
        """
        query = """
        MATCH (s:Session {id: $sid})-[r:HAS_TOPIC {status: 'ACTIVE'}]->(t:Topic)
        RETURN t.name as topic
        LIMIT 1
        """
        try:
            results = await self.query_graph(query, {"sid": session_id})
            if results and results[0].get("topic"):
                return results[0]["topic"]
            return None
        except Exception as e:
            logger.error(f"FAZ-α: Topic fetch hatası: {e}")
            return None

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

    # --- RC-3: Transcript & Episodic Memory ---

    async def append_turn(self, user_id: str, session_id: str, role: str, content: str) -> int:
        """
        Oturuma yeni bir konuşma turu (turn) ekler. (RC-3)
        Geriye dönük uyumluluk: user_id yoksa session_id kullanılır.
        """
        query = """
        MATCH (s:Session {id: $sid})
        WHERE s.user_id = $uid OR $uid IS NULL
        OPTIONAL MATCH (s)-[:HAS_TURN]->(t:Turn)
        WITH s, count(t) as turn_count
        CREATE (nt:Turn {
            id: $sid + "::" + toString(turn_count),
            turn_index: turn_count,
            role: $role,
            content: $content,
            created_at: datetime()
        })
        MERGE (s)-[:HAS_TURN]->(nt)
        RETURN nt.turn_index as index
        """
        results = await self.query_graph(query, {
            "uid": user_id,
            "sid": session_id,
            "role": role,
            "content": content
        })
        return results[0]["index"] if results else 0

    async def get_recent_turns(self, user_id: str, session_id: str, limit: int = 12) -> list:
        """
        Son N konuşma turunu getirir. (RC-3)
        Returns: List of {role, content, turn_index}
        """
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_TURN]->(t:Turn)
        WHERE s.user_id = $uid OR $uid IS NULL
        RETURN t.role as role, t.content as content, t.turn_index as turn_index
        ORDER BY t.turn_index DESC
        LIMIT $limit
        """
        results = await self.query_graph(query, {
            "uid": user_id,
            "sid": session_id,
            "limit": limit
        })
        # UI/LLM beklediği sıra için reverse et (Chronological order)
        return sorted(results, key=lambda x: x["turn_index"])

    async def get_global_recent_turns(self, user_id: str, exclude_session_id: str = None, limit: int = 10) -> list:
        """
        Kullanıcının TÜM oturumlarındaki son N mesajı getirir. (Kademeli Hafıza - Tier 2 Bridge)
        exclude_session_id: Mevcut session'ı tekrar etmemek için hariç tutar.
        """
        query = """
        MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session)-[:HAS_TURN]->(t:Turn)
        WHERE s.id <> $excluded_sid OR $excluded_sid IS NULL
        RETURN t.role as role, t.content as content, t.turn_index as turn_index, s.id as session_id, t.created_at as created_at
        ORDER BY t.created_at DESC
        LIMIT $limit
        """
        results = await self.query_graph(query, {
            "uid": user_id,
            "excluded_sid": exclude_session_id,
            "limit": limit
        })
        # Kronolojik sıra (En eski yukarıda)
        try:
            return sorted(results, key=lambda x: x["created_at"])
        except:
            return results

    async def count_turns(self, user_id: str, session_id: str) -> int:
        """Oturumdaki toplam tur (mesaj) sayısını döner. (RC-3)"""
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_TURN]->(t:Turn)
        WHERE s.user_id = $uid OR $uid IS NULL
        RETURN count(t) as total
        """
        results = await self.query_graph(query, {"uid": user_id, "sid": session_id})
        return results[0]["total"] if results else 0

    async def create_episode(self, user_id: str, session_id: str, summary: str, start_turn: int, end_turn: int):
        """
        Konuşma grubundan bir episod özeti oluşturur. (RC-3)
        """
        query = """
        MATCH (s:Session {id: $sid})
        WHERE s.user_id = $uid OR $uid IS NULL
        CREATE (e:Episode {
            id: $sid + "::ep_" + toString(start_turn) + "_" + toString(end_turn),
            user_id: $uid,
            session_id: $sid,
            summary: $summary,
            start_turn: $start_turn,
            end_turn: $end_turn,
            created_at: datetime()
        })
        MERGE (s)-[:HAS_EPISODE]->(e)
        RETURN e.id as episode_id
        """
        await self.query_graph(query, {
            "uid": user_id,
            "sid": session_id,
            "summary": summary,
            "start_turn": start_turn,
            "end_turn": end_turn
        })

    async def create_episode_pending(self, user_id: str, session_id: str, start_turn: int, end_turn: int, kind: str = "REGULAR"):
        """
        Idempotent olarak PENDING durumunda bir episode oluşturur.
        Aynı aralık için zaten varsa oluşturmaz.
        RC-6: 'kind' alanı eklendi (REGULAR/CONSOLIDATED).
        """
        query = """
        MATCH (s:Session {id: $sid})
        WHERE s.user_id = $uid OR $uid IS NULL
        MERGE (e:Episode {
            id: $sid + "::ep_" + toString(start_turn) + "_" + toString(end_turn) + "_" + $kind
        })
        ON CREATE SET 
            e.user_id = $uid,
            e.session_id = $sid,
            e.status = "PENDING",
            e.kind = $kind,
            e.start_turn_index = $start_turn,
            e.end_turn_index = $end_turn,
            e.created_at = datetime(),
            e.updated_at = datetime()
        MERGE (s)-[:HAS_EPISODE]->(e)
        RETURN e.id as episode_id
        """
        await self.query_graph(query, {
            "uid": user_id,
            "sid": session_id,
            "start_turn": start_turn,
            "end_turn": end_turn,
            "kind": kind
        })

    async def claim_pending_episode(self) -> Optional[dict]:
        """
        PENDING durumundaki bir REGULAR episode'u atomik olarak IN_PROGRESS yapar ve döner.
        """
        query = """
        MATCH (e:Episode {status: "PENDING"})
        WHERE e.kind IS NULL OR e.kind = "REGULAR"
        WITH e ORDER BY e.created_at ASC LIMIT 1
        SET e.status = "IN_PROGRESS", e.updated_at = datetime()
        RETURN e.id as id, e.user_id as user_id, e.session_id as session_id, 
               e.start_turn_index as start_turn, e.end_turn_index as end_turn
        """
        results = await self.query_graph(query)
        return results[0] if results else None

    async def mark_episode_ready(
        self,
        episode_id: str,
        summary: str,
        model: str,
        embedding: Optional[List[float]] = None,
        embedding_model: Optional[str] = None,
        vector_status: str = "PENDING",
        vector_updated_at: Optional[str] = None,
        vector_error: Optional[str] = None
    ):
        """
        Episode'u READY yapar ve vector metadata kaydeder.
        
        Y.4: vector_status, vector_updated_at, vector_error fields added.
             STORE_EPISODE_EMBEDDING_IN_NEO4J flag support for future migration.
        """
        from Atlas.config import STORE_EPISODE_EMBEDDING_IN_NEO4J
        
        # Backward compat: Store embedding in Neo4j by default
        # Future: Can migrate to Qdrant-only retrieval
        final_embedding = embedding if STORE_EPISODE_EMBEDDING_IN_NEO4J else None
        
        query = """
        MATCH (e:Episode {id: $id})
        SET e.status = "READY",
            e.summary = $summary,
            e.model = $model,
            e.embedding = $embedding,
            e.embedding_model = $embedding_model,
            e.vector_status = $vector_status,
            e.vector_updated_at = $vector_updated_at,
            e.vector_error = $vector_error,
            e.updated_at = datetime()
        """
        await self.query_graph(query, {
            "id": episode_id,
            "summary": summary,
            "model": model,
            "embedding": final_embedding,
            "embedding_model": embedding_model,
            "vector_status": vector_status,
            "vector_updated_at": vector_updated_at,
            "vector_error": vector_error
        })

    async def create_vector_index(self, dimension: Optional[int] = None):
        """
        Neo4j üzerinde vektör indeksi oluşturur (idempotent) - PRODUCTION-SAFE.
        
        Y.4: ATLAS_EMBED_DIM env support + dimension mismatch detection.
             Prevents destructive drop/recreate on dimension change.
        
        Args:
            dimension: Vector dimension (default: ATLAS_EMBED_DIM from config)
        
        Returns:
            True if index created/validated, False on failure
        """
        from Atlas.config import ATLAS_EMBED_DIM
        
        target_dimension = dimension or ATLAS_EMBED_DIM
        
        # Step 1: Check existing index
        check_query = "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options WHERE name = 'episode_embeddings' RETURN name, options"
        
        try:
            existing = await self.query_graph(check_query)
            
            if existing:
                # Index exists - check dimension
                options = existing[0].get("options", {})
                current_dim = options.get("indexConfig", {}).get("vector.dimensions")
                
                if current_dim and current_dim != target_dimension:
                    # PRODUCTION-SAFE: Don't auto-drop, warn + guide
                    logger.warning(
                        f"\n{'='*70}\n"
                        f"NEO4J VECTOR INDEX DIMENSION MISMATCH!\n"
                        f"{'='*70}\n"
                        f"Existing index: {current_dim} dimensions\n"
                        f"Target index: {target_dimension} dimensions\n\n"
                        f"MANUAL MIGRATION REQUIRED:\n"
                        f"1. Check Oracle prod for existing embeddings:\n"
                        f"   MATCH (e:Episode) WHERE e.embedding IS NOT NULL RETURN count(e)\n\n"
                        f"2. If count > 0, plan migration:\n"
                        f"   - Option A: Create second index 'episode_embeddings_{target_dimension}'\n"
                        f"   - Option B: Drop old + recreate (data loss if embeddings exist)\n\n"
                        f"3. If count = 0 (fresh install):\n"
                        f"   DROP INDEX episode_embeddings;\n"
                        f"   (then restart to auto-create {target_dimension}-dim index)\n\n"
                        f"4. Update ATLAS_EMBED_DIM={target_dimension} in environment\n"
                        f"{'='*70}"
                    )
                    
                    # Try to create alternative index name
                    alt_index_name = f"episode_embeddings_{target_dimension}"
                    alt_query = f"""
                    CREATE VECTOR INDEX {alt_index_name} IF NOT EXISTS
                    FOR (e:Episode)
                    ON (e.embedding)
                    OPTIONS {{
                      indexConfig: {{
                        `vector.dimensions`: {target_dimension},
                        `vector.similarity_function`: 'cosine'
                      }}
                    }}
                    """
                    
                    try:
                        await self.query_graph(alt_query)
                        logger.info(
                            f"✅ Created alternative index '{alt_index_name}' "
                            f"({target_dimension} dim) for gradual migration"
                        )
                        return True
                    except Exception as alt_e:
                        logger.warning(f"Could not create alternative index: {alt_e}")
                        return False
                
                else:
                    # Dimension matches or no dimension info
                    logger.info(f"Neo4j Vektör İndeksi mevcut (Boyut: {current_dim or 'unknown'})")
                    return True
        
        except Exception as check_e:
            # SHOW INDEXES may not be supported in older Neo4j versions
            logger.debug(f"Index check failed (proceeding with creation): {check_e}")
        
        # Step 2: Create index (if doesn't exist or check failed)
        create_query = f"""
        CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
        FOR (e:Episode)
        ON (e.embedding)
        OPTIONS {{
          indexConfig: {{
            `vector.dimensions`: {target_dimension},
            `vector.similarity_function`: 'cosine'
          }}
        }}
        """
        
        try:
            await self.query_graph(create_query)
            logger.info(f"Neo4j Vektör İndeksi oluşturuldu/doğrulandı (Boyut: {target_dimension})")
            return True
        except Exception as e:
            logger.warning(
                f"Neo4j Vektör İndeksi oluşturulamadı (Gelişmiş arama devre dışı kalabilir): {e}"
            )
            return False

    async def mark_episode_failed(self, episode_id: str, error: str):
        """Episode'u FAILED yapar."""
        query = """
        MATCH (e:Episode {id: $id})
        SET e.status = "FAILED",
            e.error = $error,
            e.updated_at = datetime()
        """
        await self.query_graph(query, {"id": episode_id, "error": error})

    async def get_recent_episodes(self, user_id: str, session_id: str, limit: int = 3) -> list:
        """Son N episod özetini döner. (RC-3)"""
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_EPISODE]->(e:Episode)
        WHERE s.user_id = $uid OR $uid IS NULL
        RETURN e.summary as summary, e.start_turn as start_turn, e.end_turn as end_turn
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        results = await self.query_graph(query, {"uid": user_id, "sid": session_id, "limit": limit})
        return results

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

    # --- RC-6: Retention & Consolidation ---

    async def prune_turns(self, retention_days: int, max_per_session: int):
        """Eski ve limit aşan konuşma turlarını siler."""
        # 1. Zamana göre silme
        query_time = """
        MATCH (t:Turn)
        WHERE t.created_at < datetime() - duration('P' + toString($days) + 'D')
        DELETE t
        """
        await self.query_graph(query_time, {"days": retention_days})

        # 2. Session başına limit aşımına göre silme
        query_limit = """
        MATCH (s:Session)-[:HAS_TURN]->(t:Turn)
        WITH s, t ORDER BY t.turn_index DESC
        WITH s, collect(t)[$max..] AS extra_turns
        UNWIND extra_turns AS et
        DELETE et
        """
        await self.query_graph(query_limit, {"max": max_per_session})

    async def prune_episodes(self, retention_days: int):
        """Eski episodları siler."""
        query = """
        MATCH (e:Episode)
        WHERE e.created_at < datetime() - duration('P' + toString($days) + 'D')
        DELETE e
        """
        await self.query_graph(query, {"days": retention_days})

    async def prune_notifications(self, retention_days: int):
        """Okunmuş ve eski bildirimleri siler."""
        query = """
        MATCH (n:Notification)
        WHERE n.read = true AND n.created_at < datetime() - duration('P' + toString($days) + 'D')
        DELETE n
        """
        await self.query_graph(query, {"days": retention_days})

    async def prune_tasks(self, retention_days: int):
        """Tamamlanmış ve eski görevleri siler."""
        query = """
        MATCH (task:Task)
        WHERE task.status IN ['DONE', 'CLOSED'] 
          AND task.updated_at < datetime() - duration('P' + toString($days) + 'D')
        DELETE task
        """
        await self.query_graph(query, {"days": retention_days})

    async def get_last_user_mood(self, user_id: str) -> Optional[str]:
        """
        Kullanıcının son 3 gün içindeki en son duygu durumunu getirir. (FAZ-β.1)
        """
        query = """
        MATCH (u:User {id: $uid})-[:KNOWS]->(:Entity)-[r:FACT]->(o:Entity)
        WHERE r.predicate IN ['HİSSEDİYOR', 'FEELS'] 
          AND r.created_at > datetime() - duration('P3D')
        RETURN o.name as mood
        ORDER BY r.created_at DESC LIMIT 1
        """
        try:
            results = await self.query_graph(query, {"uid": user_id})
            return results[0]["mood"] if results else None
        except Exception as e:
            logger.error(f"Mood retrieval error: {e}")
            return None

    async def prune_low_importance_memory(self, importance_threshold: float = 0.4, age_days: int = 30) -> int:
        """
        Düşük öncelikli ve eski hafıza kayıtlarını temizler (Pruning).
        Y.6 gereksinimi.
        """
        query = """
        MATCH (u:User)-[r:FACT]->(o:Entity)
        WHERE r.importance_score < $threshold
          AND r.created_at < datetime() - duration('P' + toString($days) + 'D')
          AND r.status <> 'ACTIVE'  // Sadece aktif olmayanları veya conflict olanları sil (Güvenli mod)
        DELETE r
        RETURN count(r) as deleted_count
        """
        try:
            results = await self.query_graph(query, {"threshold": importance_threshold, "days": age_days})
            count = results[0]["deleted_count"] if results else 0
            if count > 0:
                logger.info(f"Memory Pruning: {count} önemsiz kayıt silindi.")
            return count
        except Exception as e:
            logger.error(f"Memory pruning hatası: {e}")
            return 0

    async def create_consolidation_pending(self, session_id: str, window: int, min_age_days: int):
        """Çok sayıdaki REGULAR episoddan konsolide bir episod tetikler."""
        query = """
        MATCH (s:Session {id: $sid})-[:HAS_EPISODE]->(e:Episode {status: 'READY'})
        WHERE (e.kind IS NULL OR e.kind = 'REGULAR')
          AND e.created_at < datetime() - duration('P' + toString($min_age) + 'D')
          AND NOT (s)-[:HAS_EPISODE]->(:Episode {kind: 'CONSOLIDATED', start_turn_index: e.start_turn_index})
        WITH s, e ORDER BY e.start_turn_index ASC
        WITH s, collect(e) as episodes
        WHERE size(episodes) >= $window
        WITH s, episodes[0..$window] as batch
        WITH s, batch, batch[0] as first, batch[-1] as last
        MERGE (ce:Episode {
            id: $sid + "::consolidated_" + toString(first.start_turn_index) + "_" + toString(last.end_turn_index)
        })
        ON CREATE SET
            ce.user_id = s.user_id,
            ce.session_id = $sid,
            ce.status = "PENDING",
            ce.kind = "CONSOLIDATED",
            ce.start_turn_index = first.start_turn_index,
            ce.end_turn_index = last.end_turn_index,
            ce.source_episode_ids = [ep in batch | ep.id],
            ce.created_at = datetime(),
            ce.updated_at = datetime()
        MERGE (s)-[:HAS_EPISODE]->(ce)
        """
        await self.query_graph(query, {"sid": session_id, "window": window, "min_age": min_age_days})

    async def claim_pending_consolidation(self) -> Optional[dict]:
        """PENDING durumundaki bir CONSOLIDATED episod'u atomik olarak devralır."""
        query = """
        MATCH (e:Episode {status: "PENDING", kind: "CONSOLIDATED"})
        WITH e ORDER BY e.created_at ASC LIMIT 1
        SET e.status = "IN_PROGRESS", e.updated_at = datetime()
        RETURN e.id as id, e.user_id as user_id, e.session_id as session_id, 
               e.source_episode_ids as source_ids
        """
        results = await self.query_graph(query)
        return results[0] if results else None

    async def get_episodes_by_ids(self, episode_ids: List[str]) -> List[Dict]:
        """ID listesine göre episodları getirir."""
        query = "MATCH (e:Episode) WHERE e.id IN $ids RETURN e.summary as summary, e.id as id"
        return await self.query_graph(query, {"ids": episode_ids})

    async def get_facts_by_date_range(self, user_id: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Belirli bir tarih aralığındaki gerçekleri getirir.
        """
        query = """
        MATCH (s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
        WHERE (r.created_at >= datetime($start) AND r.created_at <= datetime($end))
           OR (r.updated_at >= datetime($start) AND r.updated_at <= datetime($end))
        RETURN s.name as subject, r.predicate as predicate, o.name as object,
               toString(r.updated_at) as ts
        ORDER BY r.updated_at DESC
        LIMIT 20
        """
        params = {
            "uid": user_id,
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
        return await self.query_graph(query, params)

    async def update_session_topic(self, user_id: str, session_id: str, new_topic: str):
        """
        Oturumun aktif konusunu günceller. Eski konuyu STALE yapar.
        """
        if not new_topic or new_topic in ["SAME", "CHITCHAT"]:
            return

        query = """
        MATCH (s:Session {id: $sid})
        OPTIONAL MATCH (s)-[r:HAS_TOPIC {status: 'ACTIVE'}]->(t:Topic)
        SET r.status = 'STALE', r.end_time = datetime()
        
        MERGE (nt:Topic {name: $topic})
        MERGE (s)-[nr:HAS_TOPIC]->(nt)
        SET nr.status = 'ACTIVE', nr.start_time = datetime(), nr.user_id = $uid
        """
        try:
            await self.query_graph(query, {"sid": session_id, "topic": new_topic.title(), "uid": user_id})
        except Exception as e:
            logger.error(f"Neo4j Topic update hatası: {e}")

# Tekil örnek
neo4j_manager = Neo4jManager()
