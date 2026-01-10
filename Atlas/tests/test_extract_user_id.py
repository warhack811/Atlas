"""
Test: extract_and_save user_id argüman doğrulaması
---------------------------------------------------
Bu test, api.py içindeki extract_and_save çağrılarının 
doğru user_id parametresiyle yapıldığını doğrular.

Regression test for memory user_id bug fix.
"""

import pytest
import re
from pathlib import Path


class TestApiCodeVerification:
    """api.py içindeki düzeltmenin varlığını doğrular (static check)"""
    
    def test_no_session_id_in_extract_and_save_calls(self):
        """
        api.py'de extract_and_save çağrısı session_id KULLANMAMALI
        """
        api_path = Path(__file__).parent.parent / "api.py"
        content = api_path.read_text(encoding="utf-8")
        
        # Hatalı pattern: session_id ile çağrı
        buggy_pattern = r"add_task\(extract_and_save_task,\s*[\w.]+,\s*session_id,"
        buggy_matches = re.findall(buggy_pattern, content)
        
        assert len(buggy_matches) == 0, \
            f"BUG TESPIT: extract_and_save hala session_id kullanıyor! Eşleşmeler: {buggy_matches}"
    
    def test_user_id_used_in_extract_and_save_calls(self):
        """
        api.py'de extract_and_save çağrısı user_id KULLANMALI
        """
        api_path = Path(__file__).parent.parent / "api.py"
        content = api_path.read_text(encoding="utf-8")
        
        # Doğru pattern: user_id ile çağrı (user_message veya request.message olabilir)
        correct_pattern = r"add_task\(extract_and_save_task,\s*[\w.]+,\s*user_id,"
        correct_matches = re.findall(correct_pattern, content)
        
        assert len(correct_matches) >= 2, \
            f"Beklenen: 2 adet user_id çağrısı (/api/chat ve /api/chat/stream), Bulunan: {len(correct_matches)}"
    
    def test_user_id_fallback_logic_exists(self):
        """
        api.py'de user_id fallback mantığı (user_id = request.user_id if request.user_id else session_id) OLMALI
        """
        api_path = Path(__file__).parent.parent / "api.py"
        content = api_path.read_text(encoding="utf-8")
        
        # Fallback pattern
        fallback_pattern = r"user_id\s*=\s*request\.user_id\s+if\s+request\.user_id\s+else\s+session_id"
        fallback_matches = re.findall(fallback_pattern, content)
        
        assert len(fallback_matches) >= 2, \
            f"Beklenen: 2 adet fallback mantığı, Bulunan: {len(fallback_matches)}"


# Standalone test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
