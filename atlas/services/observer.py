import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from atlas.memory.neo4j_manager import neo4j_manager
from atlas.config import API_CONFIG, MODEL_GOVERNANCE
from atlas.utils.resource_loader import ResourceLoader
OBSERVER_REASONING_PROMPT = ResourceLoader.get_prompt("observer_reasoning_prompt")
import httpx

logger = logging.getLogger(__name__)

class Observer:
    """
    ATLAS Yönlendirici - Proaktif Gözlemci (Observer)
    ------------------------------------------------
    Bu bileşen, arka planda sessizce çalışarak kullanıcının geçmiş bilgileri,
    gelecek planları ve dış dünya verileri (hava durumu, haberler vb.) arasında
    anlamlı bağlantılar kurar. Bir risk veya çelişki tespit ettiğinde kullanıcıya
    proaktif uyarılar üretir.

    Temel Sorumluluklar:
    1. Veri İzleme: Neo4j graf belleğindeki kullanıcı planlarını ve olayları takip etme.
    2. Akıl Yürütme (Reasoning): LLM kullanarak (örn: 70B modeller) iç verilerle 
       dış dünyadaki riskli durumları (fırtına, grev vb.) ilişkilendirme.
    3. Bildirim Yönetimi: Üretilen uyarıları kullanıcıya iletilmek üzere kuyruğa alma.
    4. Maliyet Kontrolü: Kontrolleri belirli aralıklarla (throttle) yaparak API maliyetini yönetme.
    """
    _instance = None
    _notifications: Dict[str, List[Dict[str, Any]]] = {} # user_id -> List of notifications

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Observer, cls).__new__(cls)
            cls._instance._last_check: Dict[str, datetime] = {}
        return cls._instance

    async def check_triggers(self, user_id: str):
        """Kullanıcının verilerini analiz eder ve tetikleyici bir durum olup olmadığını kontrol eder."""
        now = datetime.now()
        last_check = self._last_check.get(user_id)
        
        # LLM Maliyet kontrolü: Çok sık kontrol etme
        if last_check and (now - last_check).total_seconds() < 600:
            logger.info(f"Gözlemci: {user_id} için kontrol atlanıyor, yakın zamanda kontrol edildi.")
            return

        # 0. GATEKEEPING (RC-2 Hardening)
        from atlas.services.notification_gatekeeper import should_emit_notification
        is_allowed, reason = await should_emit_notification(user_id, neo4j_manager, now)
        
        if not is_allowed:
            logger.info(f"Gözlemci GATEKEEPER: {user_id} engellendi. Sebep: {reason}")
            return

        logger.info(f"Gözlemci: {user_id} kullanıcısı için tetikleyiciler kontrol ediliyor...")
        self._last_check[user_id] = now

        # 1. Hafıza Taraması (Neo4j)
        cypher = """
        MATCH (u:User {id: $uid})-[:KNOWS]->(s:Entity)-[r:FACT {user_id: $uid}]->(o:Entity)
        WHERE r.status IS NULL OR r.status = 'ACTIVE'
        RETURN s.name as subject, r.predicate as predicate, o.name as object
        LIMIT 20
        """
        facts = await neo4j_manager.query_graph(cypher, {"uid": user_id})
        if not facts:
            logger.info(f"Gözlemci: {user_id} için hafıza verisi bulunamadı.")
            return

        fact_str = "\n".join([f"- {f['subject']} ({f['predicate']}) {f['object']}" for f in facts])

        # 2. Dış Veri (Simülasyon)
        external_data = "Ankara'da yarın şiddetli fırtına ve kar yağışı bekleniyor. Ulaşımda aksamalar olabilir."

        # 3. Akıl Yürütme (Reasoning)
        warning = await self._reason_with_llm(user_id, fact_str, external_data)

        # 4. Bildirim Kaydı (DB Persistence - FAZ7)
        if warning:
            notif_data = {
                "message": warning,
                "type": "proactive_warning",
                "source": "observer",
                "reason": f"gate={reason}"
            }
            notif_id = await neo4j_manager.create_notification(user_id, notif_data)
            if notif_id:
                logger.info(f"Gözlemci: {user_id} için yeni bildirim DB'ye kaydedildi: {notif_id}")
            else:
                # Fallback to RAM if DB fails
                if user_id not in self._notifications:
                    self._notifications[user_id] = []
                self._notifications[user_id].append({
                    "id": f"obs-{int(now.timestamp())}",
                    "timestamp": now.isoformat(),
                    "message": warning,
                    "type": "proactive_warning_ram_fallback"
                })
                logger.warning(f"Gözlemci: DB hatası, bildirim RAM'e kaydedildi ({user_id})")

    def _is_quiet_hours(self, start: Optional[str], end: Optional[str]) -> bool:
        """Sessiz saatler içinde olup olmadığımızı kontrol eder."""
        if not start or not end:
            return False
        
        try:
            now_time = datetime.now().strftime("%H:%M")
            if start < end:
                return start <= now_time <= end
            else: # Geceyi aşan saatler (örn: 22:00 - 08:00)
                return now_time >= start or now_time <= end
        except:
            return False

    async def _reason_with_llm(self, user_id: str, memory: str, external_data: str) -> Optional[str]:
        """LLM kullanarak iki veri seti arasındaki çelişkiyi veya riski analiz eder."""
        from atlas.services.key_manager import KeyManager
        api_key = KeyManager.get_best_key()
        if not api_key:
            return None

        # Merkezi prompt şablonunu kullan ve değişkenleri doldur
        prompt = OBSERVER_REASONING_PROMPT.format(memory=memory, external_data=external_data)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{API_CONFIG['groq_api_base']}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0
                    }
                )
                if response.status_code == 200:
                    result = response.json()["choices"][0]["message"]["content"].strip()
                    if "SAY_NOTHING" in result:
                        return None
                    return result
        except Exception as e:
            logger.error(f"Gözlemci Akıl Yürütme başarısız oldu: {e}")
        
        return None

    async def get_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        """Kullanıcının bildirimlerini önce DB'den, sonra RAM (fallback)'den döndürür. (FAZ7)"""
        # 1. DB'den oku
        db_notifications = await neo4j_manager.list_notifications(user_id, unread_only=True)
        
        # 2. RAM fallback ile birleştir
        ram_notifications = self._notifications.get(user_id, [])
        
        return db_notifications + ram_notifications

    async def add_notification(self, user_id: str, message: str):
        """Manuel bildirim ekler (DB'ye). (FAZ7)"""
        notif_data = {
            "message": message,
            "type": "manual_warning",
            "source": "manual"
        }
        await neo4j_manager.create_notification(user_id, notif_data)


# Tekil örnek
observer = Observer()
 