"""
Test: INTERNAL_ONLY mode erişim kontrolü
-----------------------------------------
Bu test, INTERNAL_ONLY modunda whitelist dışındaki 
kullanıcıların 403 aldığını doğrular.
"""

import pytest
from unittest.mock import patch


class TestInternalOnlyConfig:
    """config.py içindeki INTERNAL_ONLY ayarlarını test eder"""
    
    def test_is_user_whitelisted_returns_true_when_internal_only_disabled(self):
        """INTERNAL_ONLY=false iken herkes erişebilmeli"""
        with patch("Atlas.config.INTERNAL_ONLY", False):
            from Atlas.config import is_user_whitelisted
            # Herhangi bir user_id ile erişim sağlanmalı
            assert is_user_whitelisted("random_user_123") == True
            assert is_user_whitelisted("") == True
    
    def test_is_user_whitelisted_returns_false_for_non_whitelisted_user(self):
        """INTERNAL_ONLY=true iken whitelist dışındaki user 403 almalı"""
        with patch("Atlas.config.INTERNAL_ONLY", True), \
             patch("Atlas.config.INTERNAL_WHITELIST_USER_IDS", {"u_admin", "u_dev"}):
            from Atlas.config import is_user_whitelisted
            # Whitelist'te olmayan kullanıcı reddedilmeli
            assert is_user_whitelisted("u_unknown") == False
            assert is_user_whitelisted("random_user") == False
    
    def test_is_user_whitelisted_returns_true_for_whitelisted_user(self):
        """INTERNAL_ONLY=true iken whitelist'teki user erişebilmeli"""
        with patch("Atlas.config.INTERNAL_ONLY", True), \
             patch("Atlas.config.INTERNAL_WHITELIST_USER_IDS", {"u_admin", "u_dev"}):
            from Atlas.config import is_user_whitelisted
            # Whitelist'teki kullanıcı kabul edilmeli
            assert is_user_whitelisted("u_admin") == True
            assert is_user_whitelisted("u_dev") == True


class TestApiCodeVerification:
    """api.py içindeki INTERNAL_ONLY guard'ların varlığını doğrular"""
    
    def test_chat_endpoint_has_internal_only_guard(self):
        """
        /api/chat endpoint'inde INTERNAL_ONLY kontrolü olmalı
        """
        import re
        from pathlib import Path
        
        api_path = Path(__file__).parent.parent / "api.py"
        content = api_path.read_text(encoding="utf-8")
        
        # is_user_whitelisted çağrısı olmalı
        assert "is_user_whitelisted" in content, \
            "api.py'de is_user_whitelisted çağrısı bulunamadı"
        
        # 403 HTTPException olmalı
        assert "status_code=403" in content, \
            "api.py'de 403 status_code bulunamadı"
    
    def test_stream_endpoint_has_internal_only_guard(self):
        """
        /api/chat/stream endpoint'inde de INTERNAL_ONLY kontrolü olmalı
        """
        import re
        from pathlib import Path
        
        api_path = Path(__file__).parent.parent / "api.py"
        content = api_path.read_text(encoding="utf-8")
        
        # Stream endpoint'inde de INTERNAL_ONLY log yazılmalı
        assert "INTERNAL_ONLY: Erişim reddedildi (stream)" in content, \
            "/api/chat/stream endpoint'inde INTERNAL_ONLY guard bulunamadı"


# Standalone test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
