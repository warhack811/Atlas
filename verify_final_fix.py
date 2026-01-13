import httpx
import asyncio
import json
import uuid

BASE_URL = "http://localhost:8081" # Testing port

async def run_final_test():
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("--- Starting Final Memory Verification ---")
        
        session_id = f"final-test-{uuid.uuid4().hex[:8]}"
        print(f"Session ID: {session_id}")
        
        # 1. Login first to ensure user 'admin'
        print("\n1. Logging in as 'admin'...")
        login_resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "adminmami"}
        )
        auth_cookie = login_resp.cookies.get("atlas_session")
        
        # 2. Assert Identity
        print("\n2. Asserting Identity: 'Benim adım Muhammet, 32 yaşındayım.'")
        await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "Selam, benim adım Muhammet ve 32 yaşındayım. Beni kaydet.",
                "session_id": session_id
            },
            cookies={"atlas_session": auth_cookie} if auth_cookie else None
        )
        
        # Give some time for background extraction
        print("Waiting for extraction...")
        await asyncio.sleep(8)
        
        # 3. New Session Recall
        new_session_id = f"final-test-recall-{uuid.uuid4().hex[:8]}"
        print(f"\n3. New Session Recall Test: {new_session_id}")
        response = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "Selam, beni hatırladın mı? Adım ve yaşım neydi?",
                "session_id": new_session_id
            },
            cookies={"atlas_session": auth_cookie} if auth_cookie else None
        )
        
        resp_text = response.json().get("response", "")
        print(f"AI Response: {resp_text}")
        
        recall_passed = "Muhammet" in resp_text and "32" in resp_text
        print(f"\nRECALL RESULT: {'✅ PASS' if recall_passed else '❌ FAIL'}")
        
        if recall_passed:
            print("🎉 Memory Amnesia Fixed!")
        else:
            print("Refining extraction logic may be needed or checking logs.")

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    asyncio.run(run_final_test())
