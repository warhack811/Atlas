import asyncio
import logging
from sandbox_router.api import keep_alive_pulse
from sandbox_router.memory.neo4j_manager import neo4j_manager
from unittest.mock import patch, AsyncMock

# Setup logging to see output
logging.basicConfig(level=logging.INFO)

async def test_heartbeat_pulse():
    print("Starting Heartbeat Pulse Test (Accelerated)...")
    
    # Mock query_graph to avoid real network call 
    with patch.object(neo4j_manager, 'query_graph', new_callable=AsyncMock) as mock_query:
        # Patch sleep to be very fast for test
        with patch('asyncio.sleep', return_value=None) as mock_sleep:
            # We will run a few iterations of the loop
            # Since keep_alive_pulse is a 'while True', we need a way to stop it
            # We can use a side_effect on mock_sleep to raise an exception after N calls
            mock_sleep.side_effect = [None, None, Exception("Stop Loop")]
            
            try:
                await keep_alive_pulse()
            except Exception as e:
                if str(e) != "Stop Loop":
                    raise e
            
            print(f"Heartbeat query call count: {mock_query.call_count}")
            assert mock_query.call_count >= 2
            print("Heartbeat Pulse Test: SUCCESS")

if __name__ == "__main__":
    asyncio.run(test_heartbeat_pulse())
