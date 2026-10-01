import os
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import SessionLocal
from app.main import app
from app.models import Device


def test_manual_availability_check_returns_json(monkeypatch):
    with SessionLocal() as db:
        device = Device(
            name="Availability check test",
            ip_address="192.0.2.247",
            vendor="QTECH",
            model="Test",
            acquisition_method="snmp",
            version_source="snmp",
            installed_version_source="snmp",
            snmp_version="2c",
            snmp_port=161,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        device_id = device.id

    async def available(address):
        assert address == "192.0.2.247"
        return True, "Ответ получен, задержка 1.2 мс"

    monkeypatch.setattr(main_module, "ping_address", available)
    with TestClient(app) as client:
        client.get("/")
        response = client.post(
            f"/devices/{device_id}/connection",
            data={"csrf": client.cookies["csrf"]},
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True, "message": "Ответ получен, задержка 1.2 мс"}

    with SessionLocal() as db:
        saved = db.get(Device, device_id)
        if saved:
            db.delete(saved)
            db.commit()


def test_availability_action_is_visible_and_runs_without_page_reload():
    root = Path(__file__).parents[1]
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    assert "if(connection)connection.remove()" not in js
    assert "Проверить доступность устройства ${device.name}" in js
    assert "headers:{Accept:'application/json'}" in js
    assert "Устройство доступно:" in js
    assert "Устройство недоступно:" in js
