
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import importlib

# Ensure repo root is in path
sys.path.append(os.getcwd())

def test_auth_secret_production_enforcement():
    """Test that ATLAS_SESSION_SECRET is required in production."""

    # Ensure config is loaded
    import Atlas.config

    # Mock Config directly
    with patch("Atlas.config.Config") as MockConfig:
        MockConfig.ATLAS_ENV = "production"
        MockConfig.ATLAS_SESSION_SECRET = None

        with pytest.raises(ValueError, match="ATLAS_SESSION_SECRET environment variable is required in production"):
            if "Atlas.auth" in sys.modules:
                importlib.reload(sys.modules["Atlas.auth"])
            else:
                importlib.import_module("Atlas.auth")

def test_auth_secret_development_fallback():
    """Test that ATLAS_SESSION_SECRET falls back to random in development."""

    import Atlas.config

    with patch("Atlas.config.Config") as MockConfig:
        MockConfig.ATLAS_ENV = "development"
        MockConfig.ATLAS_SESSION_SECRET = None

        import Atlas.auth
        importlib.reload(Atlas.auth)

        assert len(Atlas.auth.ATLAS_SESSION_SECRET) == 64  # 32 bytes hex
        assert Atlas.auth.ATLAS_SESSION_SECRET != "fixed_secret"

def test_auth_secret_provided():
    """Test that ATLAS_SESSION_SECRET is used if provided."""

    fixed_secret = "my_fixed_secret_12345"
    import Atlas.config

    with patch("Atlas.config.Config") as MockConfig:
        MockConfig.ATLAS_ENV = "production"
        MockConfig.ATLAS_SESSION_SECRET = fixed_secret

        import Atlas.auth
        importlib.reload(Atlas.auth)

        assert Atlas.auth.ATLAS_SESSION_SECRET == fixed_secret
