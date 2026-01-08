import asyncio
import sys
import os

# Ensure we are in the right path
sys.path.append(os.getcwd())

from Atlas.memory.context import build_chat_context_v1
import inspect

sig = inspect.signature(build_chat_context_v1)
print(f"Signature: {sig}")

async def test():
    try:
        # Call with stats
        res = await build_chat_context_v1("u1", "s1", "hi", stats={})
        print("Success call with stats")
    except TypeError as e:
        print(f"Failure call with stats: {e}")

asyncio.run(test())
