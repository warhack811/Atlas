import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from .memory.neo4j_manager import neo4j_manager
from .config import API_CONFIG, MODEL_GOVERNANCE
from .prompts import OBSERVER_REASONING_PROMPT
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
        
        # LLM Maliyet kontrolü: Çok sık kontrol etme (Minimal 10 dk - Scheduler 15 dk zaten)
        if last_check and (now - last_check).total_seconds() < 600:
            logger.info(f"Gözlemci: {user_id} için kontrol atlanıyor, yakın zamanda kontrol edildi.")
            return

        logger.info(f"Gözlemci: {user_id} kullanıcısı için tetikleyiciler kontrol ediliyor...")
        self._last_check[user_id] = now

        # 1. Hafıza Taraması (Neo4j): Kullanıcının gelecek planlarını veya kritik bilgilerini getir
        cypher = """
        MATCH (u:User {id: $uid})-[:KNOWS]->(s:Entity)-[r:FACT]->(o:Entity)
        RETURN s.name as subject, r.predicate as predicate, o.name as object
        LIMIT 20
        """
        facts = await neo4j_manager.query_graph(cypher, {"uid": user_id})
        if not facts:
            logger.info(f"Gözlemci: {user_id} için hafıza verisi bulunamadı.")
            return

        fact_str = "\n".join([f"- {f['subject']} ({f['predicate']}) {f['object']}" for f in facts])

        # 2. Dış Veri (Dış dünyadaki olayları simüle et)
        # İleride Serper veya Hava Durumu API çağrıları buraya eklenebilir.
        external_data = "Ankara'da yarın şiddetli fırtına ve kar yağışı bekleniyor. Ulaşımda aksamalar olabilir."

        # 3. Akıl Yürütme (Reasoning): Hafıza ve dış veri arasındaki ilişkiyi modele sor
        warning = await self._reason_with_llm(user_id, fact_str, external_data)

        # 4. Bildirim Kuyruğu: Eğer bir uyarı varsa kullanıcıya sunmak üzere kaydet
        if warning:
            if user_id not in self._notifications:
                self._notifications[user_id] = []
            
            notification = {
                "id": f"obs-{int(now.timestamp())}",
                "timestamp": now.isoformat(),
                "message": warning,
                "type": "proactive_warning"
            }
            self._notifications[user_id].append(notification)
            logger.info(f"Gözlemci: {user_id} için yeni bildirim: {warning}")

    async def _reason_with_llm(self, user_id: str, memory: str, external_data: str) -> Optional[str]:
        """LLM kullanarak iki veri seti arasındaki çelişkiyi veya riski analiz eder."""
        from .key_manager import KeyManager
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
                        "model": "llama-3.3-70b-versatile",  # Yüksek akıl yürütme için 70B
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

    def get_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        """Kullanıcının bildirimlerini döndürür."""
        return self._notifications.get(user_id, [])

    def add_notification(self, user_id: str, message: str):
        """Manuel bildirim ekler (Testler için)."""
        if user_id not in self._notifications:
            self._notifications[user_id] = []
        
        self._notifications[user_id].append({
            "id": f"man-{int(datetime.now().timestamp())}",
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": "manual_warning"
        })

# Tekil örnek
observer = Observer()
 