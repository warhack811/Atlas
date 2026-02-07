
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import importlib

# Ensure repo root is in path
sys.path.append(os.getcwd())

def test_auth_secret_production_enforcement():
    """Test that ATLAS_SESSION_SECRET is required in production."""

    # Mock Config.ATLAS_ENV and Config.ATLAS_SESSION_SECRET
    # We need to patch where they are defined: Atlas.config.Config

    with patch("Atlas.config.Config.ATLAS_ENV", "production"), \
         patch("Atlas.config.Config.ATLAS_SESSION_SECRET", None):

        # Reloading Atlas.auth will execute the module-level code
        # Use sys.modules to handle both fresh import and reload scenarios

        with pytest.raises(ValueError, match="ATLAS_SESSION_SECRET environment variable is required in production"):
            if "Atlas.auth" in sys.modules:
                importlib.reload(sys.modules["Atlas.auth"])
            else:
                importlib.import_module("Atlas.auth")

def test_auth_secret_development_fallback():
    """Test that ATLAS_SESSION_SECRET falls back to random in development."""

    with patch("Atlas.config.Config.ATLAS_ENV", "development"), \
         patch("Atlas.config.Config.ATLAS_SESSION_SECRET", None):

        import Atlas.auth
        importlib.reload(Atlas.auth)

        assert len(Atlas.auth.ATLAS_SESSION_SECRET) == 64  # 32 bytes hex
        assert Atlas.auth.ATLAS_SESSION_SECRET != "fixed_secret"

def test_auth_secret_provided():
    """Test that ATLAS_SESSION_SECRET is used if provided."""

    fixed_secret = "my_fixed_secret_12345"
    with patch("Atlas.config.Config.ATLAS_ENV", "production"), \
         patch("Atlas.config.Config.ATLAS_SESSION_SECRET", fixed_secret):

        import Atlas.auth
        importlib.reload(Atlas.auth)

        assert Atlas.auth.ATLAS_SESSION_SECRET == fixed_secret
