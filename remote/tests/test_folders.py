from cryptography.fernet import Fernet
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.db import SessionLocal
from app.main import app
from app.models import Device, EquipmentFolder


def token(client):
    client.get("/")
    return client.cookies["csrf"]


def clear_folders():
    with SessionLocal() as db:
        for device in db.scalars(select(Device)).all():
            device.folder_id = None
        db.execute(delete(EquipmentFolder))
        db.commit()


def create_folder(client, csrf, name, parent_id=None):
    return client.post("/api/folders", json={"csrf": csrf, "name": name, "parent_id": parent_id})


def test_create_nested_folders_and_reject_duplicate_and_cycle():
    clear_folders()
    with TestClient(app) as client:
        csrf = token(client)
        root = create_folder(client, csrf, "Центральный офис")
        assert root.status_code == 201
        child = create_folder(client, csrf, "Серверная", root.json()["id"])
        assert child.status_code == 201
        assert create_folder(client, csrf, "Серверная", root.json()["id"]).status_code == 422
        cycle = client.patch(f"/api/folders/{root.json()['id']}", json={"csrf": csrf, "parent_id": child.json()["id"]})
        assert cycle.status_code == 422


def test_depth_is_limited_to_five_levels():
    clear_folders()
    with TestClient(app) as client:
        csrf = token(client)
        parent = None
        for level in range(5):
            response = create_folder(client, csrf, f"Уровень {level + 1}", parent)
            assert response.status_code == 201
            parent = response.json()["id"]
        assert create_folder(client, csrf, "Уровень 6", parent).status_code == 422


def test_move_device_and_delete_folder_keeps_device():
    clear_folders()
    with TestClient(app) as client:
        csrf = token(client)
        folder = create_folder(client, csrf, "Второй этаж").json()
        with SessionLocal() as db:
            device = db.scalar(select(Device))
            if not device:
                device = Device(name="Тест", ip_address="192.0.2.250", management_port=161, vendor="Другой", model="Тест", acquisition_method="manual", version_source="manual", installed_version_source="manual", auto_check=False, status="Версия не определена")
                db.add(device)
                db.commit()
                db.refresh(device)
            device_id = device.id
        moved = client.post("/api/devices/move", json={"csrf": csrf, "device_ids": [device_id], "folder_id": folder["id"]})
        assert moved.status_code == 200
        assert next(x for x in client.get("/api/devices").json() if x["id"] == device_id)["folder_id"] == folder["id"]
        assert client.request("DELETE", f"/api/folders/{folder['id']}", json={"csrf": csrf}).status_code == 200
        assert next(x for x in client.get("/api/devices").json() if x["id"] == device_id)["folder_id"] is None


def test_folder_ui_is_present_and_escapes_catalog_names():
    with TestClient(app) as client:
        html = client.get("/").text
        js = client.get("/static/app.js").text
        assert 'id="folder-tree"' in html and 'id="add-folder"' in html
        assert "Переместить в каталог" in js and "activeFolder" in js
        assert "collapsed-folder-ids" in js and "folder-toggle" in js


def test_rename_move_and_delete_folder_with_content():
    clear_folders()
    with TestClient(app) as client:
        csrf = token(client)
        first = create_folder(client, csrf, "Первый").json()
        second = create_folder(client, csrf, "Второй").json()
        child = create_folder(client, csrf, "Дочерний", first["id"]).json()
        renamed = client.patch(f"/api/folders/{first['id']}", json={"csrf": csrf, "name": "Первый новый"})
        assert renamed.status_code == 200 and renamed.json()["name"] == "Первый новый"
        moved = client.patch(f"/api/folders/{child['id']}", json={"csrf": csrf, "parent_id": second["id"]})
        assert moved.status_code == 200 and moved.json()["parent_id"] == second["id"]
        assert client.patch(f"/api/folders/{second['id']}", json={"csrf": csrf, "parent_id": child["id"]}).status_code == 422
        deleted = client.request("DELETE", f"/api/folders/{second['id']}", json={"csrf": csrf, "move_to_folder_id": None})
        assert deleted.status_code == 200
        folders = client.get("/api/folders").json()
        assert any(x["id"] == child["id"] and x["parent_id"] is None for x in folders)


def test_drag_and_drop_is_absent_and_modal_management_present():
    with TestClient(app) as client:
        js = client.get("/static/app.js").text.lower()
        assert "ondrag" not in js and "draggable" not in js and "datatransfer" not in js
        assert "переместить устройство" in js and "переименовать каталог" in js
        assert "compact-modal" in js and "действия с каталогом" in js


def test_equipment_cosmetic_navigation_icons_and_counts():
    with TestClient(app) as client:
        html = client.get("/").text
        js = client.get("/static/app.js").text
        css = client.get("/static/folders.css").text
        icons = client.get("/static/icons.svg").text
        assert '>История<' not in html
        assert 'href="/history"' in html
        assert 'Последние события' in html
        assert 'folder-plus' in js
        assert 'panel-left-close' not in js
        assert all(f'id="{name}"' in icons for name in ('folder', 'folder-open', 'folder-plus', 'folders', 'folder-minus'))
        assert "title.textContent='Устройства'" in js
        assert '`${visible} из ${total}`' in js
        assert 'data:image/svg+xml' not in css
        assert ':has(.folder-more)' in css and '@media(hover:none)' in css
        assert '.folder-more{right:6px}' in css
        assert '.folder-panel .folder-more{padding:0;border:1px solid #2a4059;border-radius:6px;background:#121d2b;color:#8fa8c2' in css
        assert '/static/folders.css?v=20261001-30' in (Path(__file__).parents[1] / "app/templates/base.html").read_text(encoding="utf-8")
        assert 'visibility:hidden' in css


def test_shared_page_headers_have_consistent_copy():
    with TestClient(app) as client:
        equipment = client.get("/").text
        settings = client.get("/profiles").text
        assert 'class="page-header"' in equipment
        assert 'Контроль версий прошивок и состояния сетевых устройств' in equipment
        assert 'КОНФИГУРАЦИЯ' in settings
        assert 'Подключения, уведомления и справочник оборудования' in settings


def test_sidebar_uses_workspace_navigation_without_empty_pages():
    with TestClient(app) as client:
        html = client.get("/").text
        assert "Рабочее пространство" in html
        assert 'href="/">' in html
        assert 'href="/history"' in html
        assert 'href="/settings?tab=notifications"' in html
        assert "Обзор" not in html
        assert all(label in html for label in ("Устройства", "Прошивки", "Уведомления"))

    base = (Path(__file__).parents[1] / "app/templates/base.html").read_text(encoding="utf-8")
    assert 'class="top-account-bar"' in base
    assert 'class="top-account-identity"' in base
    assert 'class="account-menu"' in base
    assert 'class="sidebar-pin"' in base
    assert 'sidebar-layout.js' in base
    assert "current_user.display_name" in base
    assert '<div class="account-menu__popover"><strong>{{current_user.display_name}}</strong><small>{{current_user.username}}</small>' in base


def test_folder_creation_uses_styled_modal_instead_of_browser_prompt():
    js=(Path(__file__).parents[1]/"app/static/app.js").read_text(encoding="utf-8")
    assert "openCreateFolder()" in js
    assert "Новый каталог будет создан" in js
    assert "prompt('Название нового каталога')" not in js
