from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app, automation_config


def csrf(client):
    client.get("/")
    return client.cookies.get("csrf")


def test_automation_can_be_disabled_and_rescheduled():
    with TestClient(app) as client:
        token=csrf(client)
        disabled=client.post("/api/settings/automation",json={"csrf":token,"enabled":False,"time":"21:35"})
        assert disabled.status_code==200
        assert disabled.json()["enabled"] is False
        assert disabled.json()["next_run_time"] is None
        assert app.state.scheduler.get_job("firmware-checks") is None
        with SessionLocal() as db:assert automation_config(db)==(False,"21:35")
        dashboard=client.get("/")
        assert "Мониторинг выключен" in dashboard.text
        general=client.get("/settings?tab=general")
        assert 'name="enabled" checked' not in general.text

        enabled=client.post("/api/settings/automation",json={"csrf":token,"enabled":True,"time":"08:00"})
        assert enabled.status_code==200
        assert enabled.json()["enabled"] is True
        assert enabled.json()["next_run_time"]
        assert app.state.scheduler.get_job("firmware-checks") is not None


def test_automation_rejects_invalid_time():
    with TestClient(app) as client:
        response=client.post("/api/settings/automation",json={"csrf":csrf(client),"enabled":True,"time":"25:90"})
        assert response.status_code==422
