import pytest
from Atlas.memory.text_normalize import normalize_text_for_dedupe

def test_normalize_empty_input():
    """Test that empty or None input returns an empty string."""
    assert normalize_text_for_dedupe(None) == ""
    assert normalize_text_for_dedupe("") == ""
    assert normalize_text_for_dedupe("   ") == ""

def test_basic_normalization():
    """Test basic lowercasing and whitespace handling."""
    assert normalize_text_for_dedupe("Hello World") == "hello world"
    assert normalize_text_for_dedupe("  Hello   World  ") == "hello world"
    assert normalize_text_for_dedupe("HeLLo\tWoRLd\n") == "hello world"

def test_role_removal():
    """Test removal of turn-based role prefixes."""
    assert normalize_text_for_dedupe("Kullanıcı: Merhaba") == "merhaba"
    assert normalize_text_for_dedupe("Atlas: Selam") == "selam"
    assert normalize_text_for_dedupe("Asistan: Nasılsın?") == "nasılsın?"
    # Test case insensitivity for roles
    assert normalize_text_for_dedupe("kullanıcı: test") == "test"
    assert normalize_text_for_dedupe("ATLAS: test") == "test"

def test_predicate_removal():
    """Test removal of predicate-like prefixes."""
    assert normalize_text_for_dedupe("YAŞAR_YER: Ankara") == "ankara"
    assert normalize_text_for_dedupe("user_mood: happy") == "happy"
    # Should not remove if not at start
    assert normalize_text_for_dedupe("Something: value") == "value"

def test_punctuation_handling():
    """Test removal of leading dashes and trailing periods."""
    assert normalize_text_for_dedupe("- Hello.") == "hello"
    assert normalize_text_for_dedupe("--  Test..") == "test"
    # Should not remove internal punctuation
    assert normalize_text_for_dedupe("Hello-World.com") == "hello-world.com"

def test_complex_scenarios():
    """Test combinations of multiple normalization rules."""
    assert normalize_text_for_dedupe("Kullanıcı: YAŞAR_YER: Ankara") == "ankara"
    assert normalize_text_for_dedupe("   -   Test Message.   ") == "test message"
