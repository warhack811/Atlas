"""
Unit tests for TimeContext class in Atlas/time_context.py
"""
import pytest
from datetime import datetime
from Atlas.time_context import TimeContext
from Atlas.prompts import LANGUAGE_DISCIPLINE_PROMPT

class TestTimeContext:

    @pytest.mark.parametrize("hour, expected_greeting", [
        (6, "Günaydın"),
        (11, "Günaydın"),
        (12, "İyi günler"),
        (17, "İyi günler"),
        (18, "İyi akşamlar"),
        (21, "İyi akşamlar"),
        (22, "İyi geceler"),
        (4, "İyi geceler"),
        (0, "İyi geceler"),
    ])
    def test_get_greeting(self, hour, expected_greeting):
        # Create a datetime object with the specified hour
        dt = datetime(2023, 10, 27, hour, 0)
        tc = TimeContext(now=dt)
        assert tc.get_greeting() == expected_greeting

    @pytest.mark.parametrize("hour, expected_period", [
        (6, "sabah"),
        (11, "sabah"),
        (12, "öğle"),
        (13, "öğle"),
        (14, "öğleden sonra"),
        (17, "öğleden sonra"),
        (18, "akşam"),
        (21, "akşam"),
        (22, "gece"),
        (4, "gece"),
    ])
    def test_get_time_period(self, hour, expected_period):
        dt = datetime(2023, 10, 27, hour, 0)
        tc = TimeContext(now=dt)
        assert tc.get_time_period() == expected_period

    def test_get_formatted_date(self):
        # Friday, October 27, 2023
        dt = datetime(2023, 10, 27, 10, 0)
        tc = TimeContext(now=dt)
        # 0=Monday, 4=Friday
        assert dt.weekday() == 4
        # expected: "27 Ekim 2023, Cuma"
        assert tc.get_formatted_date() == "27 Ekim 2023, Cuma"

    def test_get_formatted_time(self):
        dt = datetime(2023, 10, 27, 8, 5)
        tc = TimeContext(now=dt)
        assert tc.get_formatted_time() == "08:05"

    def test_get_context_injection(self):
        dt = datetime(2023, 10, 27, 15, 30)
        tc = TimeContext(now=dt)
        # Period for 15:30 is "öğleden sonra"
        expected = "Şu an 27 Ekim 2023, Cuma, saat 15:30 (öğleden sonra)."
        assert tc.get_context_injection() == expected

    @pytest.mark.parametrize("message, expected_urgent, expected_keywords", [
        ("Bu çok acil bir durum", True, ["acil"]),
        ("Hemen cevap ver", True, ["hemen"]),
        ("Sakin bir gün", False, []),
        ("deadline yarın", True, ["deadline"]),
        ("ACİL yardım", True, ["acil"]), # Case insensitivity check
        ("Lütfen hızlı ol", False, []), # "hızlı" is not in the list (unless updated)
    ])
    def test_detect_urgency(self, message, expected_urgent, expected_keywords):
        tc = TimeContext()
        is_urgent, keywords = tc.detect_urgency(message)
        assert is_urgent == expected_urgent
        # Check if expected keywords are present in the result
        for kw in expected_keywords:
            assert kw in keywords

    def test_get_system_prompt_addition_no_urgency(self):
        dt = datetime(2023, 10, 27, 10, 0)
        tc = TimeContext(now=dt)
        addition = tc.get_system_prompt_addition("Merhaba")

        assert "[ZAMAN BAĞLAMI]" in addition
        assert "Şu an 27 Ekim 2023, Cuma, saat 10:00 (sabah)." in addition
        assert "ACİL İŞARETİ TESPİT EDİLDİ" not in addition

    def test_get_system_prompt_addition_with_urgency(self):
        dt = datetime(2023, 10, 27, 10, 0)
        tc = TimeContext(now=dt)
        addition = tc.get_system_prompt_addition("Bu çok acil!")

        assert "[ZAMAN BAĞLAMI]" in addition
        assert "⚠️ ACİL İŞARETİ TESPİT EDİLDİ: acil" in addition
        assert "Bu mesaja öncelik ver ve hızlı yanıt ver." in addition

    def test_inject_time_context(self):
        dt = datetime(2023, 10, 27, 10, 0)
        tc = TimeContext(now=dt)
        system_prompt = "Sen bir asistansın."
        user_message = "Merhaba"

        injected = tc.inject_time_context(system_prompt, user_message)

        assert system_prompt in injected
        assert "[ZAMAN BAĞLAMI]" in injected
        assert LANGUAGE_DISCIPLINE_PROMPT in injected
