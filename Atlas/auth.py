import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from itsdangerous import URLSafeTimedSerializer
from Atlas.config import Config

logger = logging.getLogger(__name__)

# Session Secret Key
ATLAS_SESSION_SECRET = Config.ATLAS_SESSION_SECRET

if not ATLAS_SESSION_SECRET:
    # Check if we are in production
    if Config.ATLAS_ENV == "production":
        logger.critical("ATLAS_SESSION_SECRET is missing in production environment!")
        raise ValueError(
            "ATLAS_SESSION_SECRET environment variable is required in production. "
            "Please set it to a secure random string."
        )

    # In development/test, fallback to random but warn
    ATLAS_SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        f"ATLAS_SESSION_SECRET not found! Generated temporary secret for {Config.ATLAS_ENV} mode. "
        f"Set ATLAS_SESSION_SECRET for persistence and security."
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
