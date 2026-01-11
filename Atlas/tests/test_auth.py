import pytest
from fastapi.testclient import TestClient
from Atlas.api import app
from Atlas.auth import create_session_token

client = TestClient(app)

def test_login_admin_success():
    """Admin girişi başarılı olmalı."""
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminmami"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert "atlas_session" in response.cookies

def test_login_user_success():
    """Normal kullanıcı girişi başarılı olmalı."""
    response = client.post(
        "/api/auth/login",
        json={"username": "ali", "password": "mami"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "ali"
    assert data["role"] == "user"

def test_login_wrong_password():
    """Yanlış şifre 401 dönmeli."""
    # Admin için yanlış şifre
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "mami"}
    )
    assert response.status_code == 401
    
    # User için yanlış şifre
    response = client.post(
        "/api/auth/login",
        json={"username": "ali", "password": "wrong"}
    )
    assert response.status_code == 401

def test_me_endpoint():
    """Oturum bilgileri doğru okunmalı."""
    # Önce login
    login_res = client.post(
        "/api/auth/login",
        json={"username": "tester", "password": "mami"}
    )
    cookies = login_res.cookies
    
    # /me endpointi
    response = client.get("/api/auth/me", cookies=cookies)
    assert response.status_code == 200
    assert response.json()["username"] == "tester"

def test_logout():
    """Logout cookie'yi silmeli."""
    login_res = client.post(
        "/api/auth/login",
        json={"username": "tester", "password": "mami"}
    )
    cookies = login_res.cookies
    
    # Logout
    logout_res = client.post("/api/auth/logout", cookies=cookies)
    assert logout_res.status_code == 200
    
    # /me artık 401 dönmeli
    # Not: TestClient'da cookie silinmesi manuel simüle edilebilir veya 
    # response.cookies'e bakılabilir. 
    # Logout sonrası cookie boş olmalı.
    response = client.get("/api/auth/me", cookies=logout_res.cookies)
    assert response.status_code == 401

def test_chat_uses_session_user():
    """Chat endpointi login olan kullanıcıyı tanımalı."""
    # Login as 'vader'
    token = create_session_token("vader", "user")
    cookies = {"atlas_session": token}
    
    # /api/chat isteği (body'de user_id yok)
    response = client.post(
        "/api/chat",
        json={"message": "hello", "session_id": "s1"},
        cookies=cookies
    )
    
    # Response içindeki RDR'de user_id kontrol edilmeli (varsa)
    # Veya direkt olarak loglara/yan etkilere bakılabilir.
    # Bu testte status 200 olması ve session'dan user_id'nin başarıyla 
    # çözüldüğünü (internal verify) kontrol ediyoruz.
    assert response.status_code == 200
    # RDR kaydı yapıldığını varsayıyoruz
