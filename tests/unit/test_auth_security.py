
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import importlib
from Atlas.config import Config

# Ensure repo root is in path
sys.path.append(os.getcwd())

def test_auth_secret_production_enforcement():
    """Test that ATLAS_SESSION_SECRET is required in production."""

    # Reload config to ensure it's in a clean state, and patch ENV vars directly as Config might be immutable or re-read from env
    with patch.dict(os.environ, {"ATLAS_ENV": "production", "ATLAS_SESSION_SECRET": ""}):

        # Reload Atlas.config to reflect env change
        import Atlas.config
        importlib.reload(Atlas.config)

        # We need to ensure Atlas.auth re-reads these values
        if "Atlas.auth" in sys.modules:
            with pytest.raises(ValueError, match="ATLAS_SESSION_SECRET environment variable is required in production"):
                importlib.reload(sys.modules["Atlas.auth"])
        else:
             with pytest.raises(ValueError, match="ATLAS_SESSION_SECRET environment variable is required in production"):
                importlib.import_module("Atlas.auth")

def test_auth_secret_development_fallback():
    """Test that ATLAS_SESSION_SECRET falls back to random in development."""

    with patch.dict(os.environ, {"ATLAS_ENV": "development", "ATLAS_SESSION_SECRET": ""}):

        # Reload Atlas.config to reflect env change
        import Atlas.config
        importlib.reload(Atlas.config)

        import Atlas.auth
        importlib.reload(Atlas.auth)

        # In development fallback, it generates a random token
        assert len(Atlas.auth.ATLAS_SESSION_SECRET) == 64  # 32 bytes hex

def test_auth_secret_provided():
    """Test that ATLAS_SESSION_SECRET is used if provided."""

    fixed_secret = "my_fixed_secret_12345"
    with patch.dict(os.environ, {"ATLAS_ENV": "production", "ATLAS_SESSION_SECRET": fixed_secret}):

        # Reload Atlas.config to reflect env change
        import Atlas.config
        importlib.reload(Atlas.config)

        import Atlas.auth
        importlib.reload(Atlas.auth)

        assert Atlas.auth.ATLAS_SESSION_SECRET == fixed_secret
