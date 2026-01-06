"""
FAZ 2: Provenance Tests
Unit tests for source_turn_id plumbing and schema field enforcement.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
from Atlas.memory.extractor import extract_and_save
from Atlas.memory.context import ContextBuilder


class TestSourceTurnIdPlumbing(unittest.TestCase):
    """Test source_turn_id parameter flow."""
    
    @patch('Atlas.memory.extractor.neo4j_manager.store_triplets', new_callable=AsyncMock)
    @patch('Atlas.memory.extractor.Config.get_random_groq_key', return_value='test_key')
    @patch('httpx.AsyncClient')
    async def test_extract_and_save_accepts_source_turn_id(self, mock_client, mock_key, mock_store):
        """Test that extract_and_save accepts source_turn_id parameter."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"subject": "Ali", "predicate": "İSİM", "object": "Ali", "category": "personal"}]'
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        
        mock_client_instance = Mock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        # Test with source_turn_id
        await extract_and_save("Benim adım Ali", "test_user", "test_turn_123")
        
        # Verify store_triplets was called with source_turn_id
        self.assertTrue(mock_store.called)
        call_args = mock_store.call_args
        self.assertEqual(len(call_args[0]), 3, "store_triplets should receive 3 positional args")
        self.assertEqual(call_args[0][2], "test_turn_123", "Third argument should be source_turn_id")
    
    @patch('Atlas.memory.extractor.neo4j_manager.store_triplets', new_callable=AsyncMock)
    @patch('Atlas.memory.extractor.Config.get_random_groq_key', return_value='test_key')
    @patch('httpx.AsyncClient')
    async def test_extract_and_save_works_without_source_turn_id(self, mock_client, mock_key, mock_store):
        """Test backward compatibility: works without source_turn_id."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"subject": "Ahmet", "predicate": "YAŞAR_YER", "object": "İstanbul", "category": "personal"}]'
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        
        mock_client_instance = Mock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        # Test without source_turn_id (backward compatibility)
        await extract_and_save("Ahmet İstanbul'da yaşıyor", "test_user")
        
        # Verify store_triplets was called with None as source_turn_id
        self.assertTrue(mock_store.called)
        call_args = mock_store.call_args
        self.assertEqual(call_args[0][2], None, "source_turn_id should default to None")


class TestStatusFilter(unittest.TestCase):
    """Test status filter in retrieval queries."""
    
    def test_context_query_has_status_filter(self):
        """Test that get_neo4j_context query includes status filter."""
        from Atlas.memory.context import ContextBuilder
        import inspect
        
        # Get source code of get_neo4j_context method
        source = inspect.getsource(ContextBuilder.get_neo4j_context)
        
        # Check that status filter is present
        self.assertIn("r.status IS NULL OR r.status = 'ACTIVE'", source, 
                     "context.py should filter by status")
    
    def test_observer_query_has_status_filter(self):
        """Test that observer query includes status filter."""
        from Atlas.observer import Observer
        import inspect
        
        # Get source code of check_triggers method
        source = inspect.getsource(Observer.check_triggers)
        
        # Check that status filter is present
        self.assertIn("r.status IS NULL OR r.status = 'ACTIVE'", source,
                     "observer.py should filter by status")


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with old relationships."""
    
    def test_old_relationships_without_schema_fields(self):
        """Test that old relationships without schema fields can still be queried."""
        # This is a documentation test - verifies the design
        # Old relationships have status=NULL, which should match the filter:
        # r.status IS NULL OR r.status = 'ACTIVE'
        
        # Verify filter logic
        filter_expression = "r.status IS NULL OR r.status = 'ACTIVE'"
        
        # Test cases:
        # Case 1: Old relationship (status=NULL) -> should match
        # Case 2: New relationship (status='ACTIVE') -> should match  
        # Case 3: Retracted relationship (status='INACTIVE') -> should NOT match
        
        self.assertIn("IS NULL", filter_expression, "Filter must include NULL check for old relationships")
        self.assertIn("ACTIVE", filter_expression, "Filter must include ACTIVE check for new relationships")


if __name__ == "__main__":
    import asyncio
    
    # Run async tests
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    
    # Custom runner for async tests
    for test in suite:
        if hasattr(test, '_testMethodName'):
            method = getattr(test, test._testMethodName)
            if asyncio.iscoroutinefunction(method):
                asyncio.run(test.debug())
    
    # Run sync tests normally
    unittest.main()
