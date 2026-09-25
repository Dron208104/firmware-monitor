import os

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import Device, EquipmentModel, FirmwareEvent


def csrf(client: TestClient) -> str:
    client.get("/")
    return client.cookies.get("csrf")


def clear_events() -> None:
    with SessionLocal() as db:
        db.execute(delete(FirmwareEvent))
        db.commit()


def create_event(category: str = "updates", dedupe_key: str = "release:1:2.0") -> int:
    with SessionLocal() as db:
        model = db.scalar(select(EquipmentModel).join(Device,Device.catalog_model_id==EquipmentModel.id)) or db.scalar(select(EquipmentModel))
        device = db.scalar(select(Device).where(Device.catalog_model_id==model.id))
        if not device:
            device=Device(name="Notification fixture",ip_address="192.0.2.250",vendor=model.vendor.name,model=model.name,catalog_model_id=model.id,installed_version="1.0",installed_version_source="manual",version_source="manual",acquisition_method="manual",auto_check=False)
            db.add(device);db.flush()
        is_error = category == "errors"
        event = FirmwareEvent(
            model_id=model.id,
            device_id=device.id,
            version="source-error" if is_error else "2.0",
            event_type="Ошибка источника" if is_error else "Доступна новая версия",
            category=category,
            old_version="1.0",
            new_version="2.0",
            description="Обнаружена подтверждённая версия 2.0",
            dedupe_key=dedupe_key,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event.id


def test_notifications_page_redirects_to_email_settings():
    with TestClient(app) as client:
        response=client.get("/notifications",follow_redirects=False)
        assert response.status_code==303
        assert response.headers["location"]=="/settings?tab=notifications"

def test_notification_disabled_buttons_have_inactive_style():
    css=(__import__("pathlib").Path(__file__).parents[1]/"app/static/notifications.css").read_text(encoding="utf-8")
    assert ".event-toolbar .btn:disabled" in css
    assert "cursor:not-allowed" in css and ".btn:disabled:hover" in css


def test_notification_read_delete_and_clear_read():
    clear_events()
    with TestClient(app) as client:
        token = csrf(client)
        first = create_event(dedupe_key="release:1:2.1")
        second = create_event(category="errors", dedupe_key="source-error:1")
        assert client.post(f"/api/notifications/{first}/read", json={"csrf": token}).status_code == 200
        with SessionLocal() as db:
            assert db.get(FirmwareEvent, first).read_at is not None
        assert client.post("/api/notifications/read-all", json={"csrf": token}).status_code == 200
        assert client.request("DELETE", f"/api/notifications/{second}", json={"csrf": token}).status_code == 200
        assert client.request("DELETE", "/api/notifications/clear-read", json={"csrf": token}).status_code == 200
        with SessionLocal() as db:
            assert list(db.scalars(select(FirmwareEvent)).all()) == []


def test_notification_dedupe_key_is_indexed_and_unique_at_service_level():
    from app.firmware.service import add_event_once

    clear_events()
    with SessionLocal() as db:
        model = db.scalar(select(EquipmentModel).join(Device,Device.catalog_model_id==EquipmentModel.id))
        add_event_once(db, model, "Ошибка источника", "errors", "Недоступен", "same-key")
        add_event_once(db, model, "Ошибка источника", "errors", "Недоступен", "same-key")
        db.commit()
        assert len(db.scalars(select(FirmwareEvent).where(FirmwareEvent.dedupe_key == "same-key")).all()) == 1


def test_models_without_devices_do_not_create_or_show_firmware_notifications():
    from app.firmware.service import add_event_once

    clear_events()
    with SessionLocal() as db:
        model=db.scalar(select(EquipmentModel).where(~EquipmentModel.id.in_(select(Device.catalog_model_id).where(Device.catalog_model_id.is_not(None)))))
        assert model is not None
        add_event_once(db,model,"Найдена новая прошивка","updates","Не должна отображаться","orphan-release")
        db.commit()
        assert db.scalar(select(FirmwareEvent).where(FirmwareEvent.dedupe_key=="orphan-release")) is None


def test_event_cards_align_dates_and_hide_duplicate_model_caption():
    css=(__import__("pathlib").Path(__file__).parents[1]/"app/static/notifications-fix.css").read_text(encoding="utf-8")
    assert "right: 250px" in css and "font-variant-numeric: tabular-nums" in css
    assert "top: 50%" in css and "transform: translateY(-50%)" in css
    assert ".event-content > small:last-child" in css and "display: none" in css
