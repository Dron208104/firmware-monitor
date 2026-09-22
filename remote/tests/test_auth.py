from datetime import timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import SESSION_COOKIE, hash_password, token_hash, utcnow
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AdminAuditLog, User, UserSession

def clean_auth():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.execute(delete(AdminAuditLog));db.execute(delete(UserSession));db.execute(delete(User));db.commit()

def add_user(username="admin",role="admin",active=True,password="SecurePassword123!"):
    with SessionLocal() as db:
        user=User(username=username,display_name=username.title(),password_hash=hash_password(password),role=role,active=active);db.add(user);db.commit();db.refresh(user);return user.id

def login(client,username="admin",password="SecurePassword123!"):
    client.get("/login");csrf=client.cookies["csrf"]
    return client.post("/login",data={"csrf":csrf,"username":username,"password":password,"next":"/"},follow_redirects=False)

def test_login_logout_and_protected_page(monkeypatch):
    clean_auth();add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        assert client.get("/",follow_redirects=False).status_code==303
        response=login(client);assert response.status_code==303 and SESSION_COOKIE in response.cookies
        assert client.get("/").status_code==200
        csrf=client.cookies["csrf"];assert client.post("/logout",data={"csrf":csrf},follow_redirects=False).status_code==303
        assert client.get("/",follow_redirects=False).status_code==303

def test_viewer_is_read_only_and_cannot_open_settings(monkeypatch):
    clean_auth();add_user("viewer","viewer");monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client,"viewer")
        assert client.get("/").status_code==200
        assert client.get("/notifications").status_code==200
        assert client.get("/settings").status_code==403
        assert client.post("/check-all",data={"csrf":client.cookies["csrf"]}).status_code==403
        assert client.post("/api/folders",json={"csrf":client.cookies["csrf"],"name":"Запрещено"}).status_code==403

def test_blocked_user_and_expired_session_are_rejected(monkeypatch):
    clean_auth();add_user("blocked","viewer",False);user_id=add_user("active","viewer");monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        assert SESSION_COOKIE not in login(client,"blocked").cookies
        login(client,"active")
        with SessionLocal() as db:
            session=db.scalar(select(UserSession).where(UserSession.user_id==user_id));session.expires_at=utcnow()-timedelta(seconds=1);db.commit()
        assert client.get("/",follow_redirects=False).status_code==303

def test_inactive_session_is_revoked(monkeypatch):
    clean_auth();user_id=add_user();monkeypatch.setattr(settings,"auth_disabled",False);monkeypatch.setattr(settings,"session_inactivity_minutes",15)
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            session=db.scalar(select(UserSession).where(UserSession.user_id==user_id));session.last_seen_at=utcnow()-timedelta(minutes=16);db.commit()
        response=client.get("/",follow_redirects=False)
        assert response.status_code==303 and response.headers["location"].startswith("/login")
        with SessionLocal() as db:
            assert db.scalar(select(UserSession).where(UserSession.user_id==user_id)).revoked_at is not None

def test_activity_touch_is_available_to_viewer(monkeypatch):
    clean_auth();add_user("viewer","viewer");monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client,"viewer")
        response=client.post("/api/session/touch",json={"csrf":client.cookies["csrf"]})
        assert response.status_code==200 and response.json()=={"ok":True}

def test_authenticated_pages_include_idle_timeout_script():
    root=Path(__file__).parents[1]
    html=(root/"app"/"templates"/"base.html").read_text(encoding="utf-8")
    js=(root/"app"/"static"/"session.js").read_text(encoding="utf-8")
    assert '/static/session.js' in html
    assert '15*60*1000' in js and '/login?expired=1' in js

def test_last_active_admin_cannot_be_disabled(monkeypatch):
    clean_auth();admin_id=add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client);csrf=client.cookies["csrf"]
        response=client.patch(f"/api/users/{admin_id}",json={"csrf":csrf,"active":False})
        assert response.status_code==409 and "последнего" in response.json()["error"]

def test_admin_role_cannot_be_changed_even_when_another_admin_exists(monkeypatch):
    clean_auth();admin_id=add_user();add_user("second-admin","admin");monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client);csrf=client.cookies["csrf"]
        response=client.patch(f"/api/users/{admin_id}",json={"csrf":csrf,"role":"viewer"})
        assert response.status_code==409 and response.json()["error"]=="Роль администратора нельзя изменить"
        with SessionLocal() as db:assert db.get(User,admin_id).role=="admin"

def test_admin_role_selector_is_disabled_in_ui():
    html=(Path(__file__).parents[1]/"app"/"templates"/"users.html").read_text(encoding="utf-8")
    assert "Роль администратора нельзя изменить" in html
    assert "if user.role=='admin'" in html and 'class="user-role-static"' in html
    assert "if(role)role.onchange" in (Path(__file__).parents[1]/"app"/"static"/"users.js").read_text(encoding="utf-8")

def test_protected_user_delete_buttons_are_disabled_in_ui():
    html=(Path(__file__).parents[1]/"app"/"templates"/"users.html").read_text(encoding="utf-8")
    css=(Path(__file__).parents[1]/"app"/"static"/"auth.css").read_text(encoding="utf-8")
    assert "user.id==current_user.id" in html
    assert "active_admins<=1" in html
    assert "Нельзя удалить текущую учётную запись" in html
    assert "В системе должен остаться хотя бы один администратор" in html
    assert ".user-actions button:disabled" in css and "cursor:not-allowed" in css

def test_passwords_are_argon2_and_not_returned(monkeypatch):
    clean_auth();add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client);csrf=client.cookies["csrf"]
        response=client.post("/api/users",json={"csrf":csrf,"username":"observer","display_name":"Наблюдатель","role":"viewer","password":"AnotherSecure123!"})
        assert response.status_code==201 and "password" not in response.text.lower()
        with SessionLocal() as db: assert db.scalar(select(User).where(User.username=="observer")).password_hash.startswith("$argon2id$")

def test_password_change_uses_application_dialog_not_browser_prompt():
    from pathlib import Path
    root=Path(__file__).parents[1]
    html=(root/"app"/"templates"/"users.html").read_text(encoding="utf-8")
    js=(root/"app"/"static"/"users.js").read_text(encoding="utf-8")
    assert 'class="user-dialog password-dialog"' in html
    assert 'name="confirmation"' in html
    assert "password!==confirmation" in js
    assert "prompt(" not in js
    assert 'minlength="8"' in html and "password.length<8" in js

def test_password_minimum_is_eight_characters():
    import pytest
    assert hash_password("12345678").startswith("$argon2id$")
    with pytest.raises(ValueError,match="8 символов"):
        hash_password("1234567")

def test_admin_can_login_with_new_password_after_self_reset(monkeypatch):
    clean_auth();admin_id=add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client);csrf=client.cookies["csrf"]
        changed=client.post(f"/api/users/{admin_id}/reset-password",json={"csrf":csrf,"password":"NewPass88"})
        assert changed.status_code==200
        assert client.get("/",follow_redirects=False).status_code==303
        response=login(client,password="NewPass88")
        assert response.status_code==303 and response.headers["location"]=="/"

def test_login_never_redirects_to_logout(monkeypatch):
    clean_auth();add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        client.get("/login?next=/logout");csrf=client.cookies["csrf"]
        response=client.post("/login",data={"csrf":csrf,"username":"admin","password":"SecurePassword123!","next":"/logout"},follow_redirects=False)
        assert response.status_code==303 and response.headers["location"]=="/"

def test_new_user_can_be_forced_to_change_password(monkeypatch):
    clean_auth();admin_id=add_user();monkeypatch.setattr(settings,"auth_disabled",False)
    with TestClient(app) as client:
        login(client);csrf=client.cookies["csrf"]
        created=client.post("/api/users",json={"csrf":csrf,"username":"firstlogin","display_name":"Первый вход","role":"viewer","password":"Temporary88","must_change_password":True})
        assert created.status_code==201
        with SessionLocal() as db:assert db.scalar(select(User).where(User.username=="firstlogin")).must_change_password is True
    with TestClient(app) as client:
        response=login(client,"firstlogin","Temporary88")
        assert response.status_code==303 and response.headers["location"]=="/change-password"
        assert client.get("/",follow_redirects=False).headers["location"]=="/change-password"
        page_response=client.get("/change-password")
        csrf=client.cookies["csrf"]
        changed=client.post("/change-password",data={"csrf":csrf,"password":"Permanent88","confirmation":"Permanent88"},follow_redirects=False)
        assert changed.status_code==303 and changed.headers["location"]=="/"
        assert client.get("/").status_code==200
    with TestClient(app) as client:
        assert SESSION_COOKIE not in login(client,"firstlogin","Temporary88").cookies
        assert login(client,"firstlogin","Permanent88").headers["location"]=="/"

def test_first_login_password_must_differ(monkeypatch):
    clean_auth();user_id=add_user("forced","viewer",password="Temporary88");monkeypatch.setattr(settings,"auth_disabled",False)
    with SessionLocal() as db:
        user=db.get(User,user_id);user.must_change_password=True;db.commit()
    with TestClient(app) as client:
        login(client,"forced","Temporary88");client.get("/change-password");csrf=client.cookies["csrf"]
        response=client.post("/change-password",data={"csrf":csrf,"password":"Temporary88","confirmation":"Temporary88"})
        assert response.status_code==200 and "отличаться от временного" in response.text
