import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from itsdangerous import URLSafeTimedSerializer
from atlas.config import getenv

logger = logging.getLogger(__name__)

# Session Secret Key
ATLAS_SESSION_SECRET = getenv("ATLAS_SESSION_SECRET", None)
if not ATLAS_SESSION_SECRET:
    ATLAS_SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        f"ATLAS_SESSION_SECRET env'de bulunamadı! Dev modu için geçici secret üretildi. "
        f"Production'da kalıcı bir secret set edin."
    )

# Serializer for signed cookies
serializer = URLSafeTimedSerializer(ATLAS_SESSION_SECRET)

def create_session_token(username: str, role: str) -> str:
    """Kullanıcı bilgileriyle imzalı bir session token oluşturur."""
    data = {
        "username": username,
        "role": role,
        "iat": datetime.now(timezone.utc).timestamp()
    }
    return serializer.dumps(data)

def decode_session_token(token: str, max_age: int = 604800) -> Optional[Dict]:
    """Tokenı çözer ve doğrular. Hatalıysa None döner."""
    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except Exception as e:
        logger.debug(f"Auth: Geçersiz session token: {e}")
        return None

def verify_credentials(username: str, password: str) -> Optional[str]:
    """
    Kullanıcı bilgilerini doğrular ve rol döner. 
    Hatalıysa None döner.
    
    Kurallar:
    - username == "admin" ise sadece password == "adminmami" kabul.
    - username != "admin" ise sadece password == "mami" kabul.
    """
    if not username or not password:
        return None
        
    if username == "admin":
        if password == "adminmami":
            return "admin"
        else:
            return None
    else:
        # Username admin değilse sadece "mami" parolası kabul edilir
        if password == "mami":
            return "user"
        else:
            return None
