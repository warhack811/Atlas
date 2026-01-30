"""
FAZ-γ Identity Cache - Verification Tests
==========================================
Tests cross-session memory persistence using SessionState cache pattern.
"""

import pytest
from atlas.memory.state import SessionState, state_manager


def test_session_state_has_identity_fields():
    """Test 1: SessionState has FAZ-γ identity cache fields."""
    state = SessionState(session_id="test-session")
    
    # Verify fields exist
    assert hasattr(state, "_identity_cache"), "Missing _identity_cache field"
    assert hasattr(state, "_identity_hydrated"), "Missing _identity_hydrated field"
    
    # Verify defaults
    assert state._identity_cache == {}, "Default _identity_cache should be empty dict"
    assert state._identity_hydrated == False, "Default _identity_hydrated should be False"
    
    print("✅ Test 1 PASSED: SessionState has identity cache fields")


def test_identity_cache_updates():
    """Test 2: Identity cache can be updated and read."""
    state = SessionState(session_id="test-session-2")
    
    # Update cache
    state._identity_cache = {"ISIM": "Muhammet", "YASI": "25"}
    state._identity_hydrated = True
    
    # Verify updates
    assert state._identity_cache["ISIM"] == "Muhammet"
    assert state._identity_cache["YASI"] == "25"
    assert state._identity_hydrated == True
    
    print("✅ Test 2 PASSED: Identity cache updates work")


def test_state_manager_cache_persistence():
    """Test 3: StateManager preserves identity cache across get_state calls."""
    session_id = "test-session-3"
    
    # First access: set cache
    state1 = state_manager.get_state(session_id)
    state1._identity_cache = {"ISIM": "Ali"}
    state1._identity_hydrated = True
    
    # Second access: should preserve cache
    state2 = state_manager.get_state(session_id)
    assert state2._identity_cache["ISIM"] == "Ali", "Cache not preserved"
    assert state2._identity_hydrated == True, "Hydrated flag not preserved"
    
    # Cleanup
    state_manager.clear_state(session_id)
    
    print("✅ Test 3 PASSED: StateManager preserves identity cache")


def test_empty_cache_graceful():
    """Test 4: Empty cache doesn't cause errors."""
    state = SessionState(session_id="test-session-4")
    
    # Empty cache should not raise errors
    assert len(state._identity_cache) == 0
    assert bool(state._identity_cache) == False  # Empty dict is falsy
    
    print("✅ Test 4 PASSED: Empty cache handled gracefully")


if __name__ == "__main__":
    print("Running FAZ-γ Identity Cache Tests...")
    print("=" * 50)
    
    test_session_state_has_identity_fields()
    test_identity_cache_updates()
    test_state_manager_cache_persistence()
    test_empty_cache_graceful()
    
    print("=" * 50)
    print("✅ All 4 tests PASSED!")
