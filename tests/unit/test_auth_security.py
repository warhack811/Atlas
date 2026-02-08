
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import importlib

# Ensure repo root is in path
sys.path.append(os.getcwd())

def test_auth_secret_production_enforcement():
    """Test that ATLAS_SESSION_SECRET is required in production."""

    # Reload Atlas.config to clear any previous cached values if needed, or just patch
    # The issue in CI is likely that patch replaces with a MagicMock if not specified, or the attribute
    # access on the class is different from instance.
    # However, Atlas.auth uses `from Atlas.config import Config` or `Config.ATLAS_SESSION_SECRET`.

    # We'll use os.environ to be sure, and reload Config, then reload Auth.

    with patch.dict(os.environ, {"ATLAS_ENV": "production", "ATLAS_SESSION_SECRET": ""}):
        # Reload config to pick up env vars
        import Atlas.config
        if "Atlas.config" not in sys.modules:
            sys.modules["Atlas.config"] = Atlas.config
        importlib.reload(Atlas.config)

        # Now reload auth to trigger the check
        with pytest.raises(ValueError, match="ATLAS_SESSION_SECRET environment variable is required in production"):
            if "Atlas.auth" in sys.modules:
                importlib.reload(sys.modules["Atlas.auth"])
            else:
                importlib.import_module("Atlas.auth")

def test_auth_secret_development_fallback():
    """Test that ATLAS_SESSION_SECRET falls back to random in development."""

    with patch.dict(os.environ, {"ATLAS_ENV": "development", "ATLAS_SESSION_SECRET": ""}):
        import Atlas.config
        if "Atlas.config" not in sys.modules:
            sys.modules["Atlas.config"] = Atlas.config
        importlib.reload(Atlas.config)

        import Atlas.auth
        if "Atlas.auth" in sys.modules:
            importlib.reload(sys.modules["Atlas.auth"])
        else:
            importlib.import_module("Atlas.auth")

        # In dev mode, if secret is empty, it generates a random one
        assert len(Atlas.auth.ATLAS_SESSION_SECRET) == 64  # 32 bytes hex

        # Verify it's a string, not a mock
        assert isinstance(Atlas.auth.ATLAS_SESSION_SECRET, str)

def test_auth_secret_provided():
    """Test that ATLAS_SESSION_SECRET is used if provided."""

    fixed_secret = "my_fixed_secret_12345"
    with patch.dict(os.environ, {"ATLAS_ENV": "production", "ATLAS_SESSION_SECRET": fixed_secret}):
        import Atlas.config
        if "Atlas.config" not in sys.modules:
            sys.modules["Atlas.config"] = Atlas.config
        importlib.reload(Atlas.config)

        import Atlas.auth
        if "Atlas.auth" in sys.modules:
            importlib.reload(sys.modules["Atlas.auth"])
        else:
            importlib.import_module("Atlas.auth")

        assert Atlas.auth.ATLAS_SESSION_SECRET == fixed_secret
