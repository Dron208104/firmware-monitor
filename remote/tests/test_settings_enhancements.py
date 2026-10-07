from datetime import datetime, timedelta, timezone
import json
import socket

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import mailer
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import ApplicationSetting, ConnectionProfile, Device, EquipmentModel, EquipmentVendor, FirmwareEvent, FirmwareRelease, FirmwareSource
from app.firmware.service import queue_firmware_reminders
from app.source_status import source_status_view


@pytest.fixture
def isolated_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        client.get("/")
        yield client, sessions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def token(client):
    return client.cookies["csrf"]


def test_check_all_rejects_empty_system_and_activates_with_first_device(isolated_client):
    client, sessions = isolated_client
    page = client.get("/")
    assert "Проверить все" in page.text and 'disabled title="Нет устройств для проверки"' in page.text
    assert client.post("/check-all", data={"csrf": token(client)}).status_code == 409
    with sessions() as db:
        db.add(Device(name="First", ip_address="192.0.2.11", vendor="X", model="Y"))
        db.commit()
    page = client.get("/")
    assert 'disabled title="Нет устройств для проверки"' not in page.text
    assert client.post("/check-all", data={"csrf": token(client)}, follow_redirects=False).status_code == 303


def test_profile_empty_state_and_all_snmp_modes_keep_secrets_private(isolated_client):
    client, sessions = isolated_client
    page = client.get("/settings?tab=connections")
    assert page.text.count("Профили подключения ещё не добавлены") == 1
    assert 'colspan="5"' in page.text
    versions = (
        {"name": "v1", "snmp_version": "1", "community": "private-v1"},
        {"name": "v2", "snmp_version": "2c", "community": "private-v2"},
        {"name": "v3-noauth", "snmp_version": "3", "username": "operator", "security_level": "noAuthNoPriv"},
        {"name": "v3-auth", "snmp_version": "3", "username": "operator", "security_level": "authNoPriv", "auth_protocol": "SHA", "auth_password": "auth-secret"},
        {"name": "v3-priv", "snmp_version": "3", "username": "operator", "security_level": "authPriv", "auth_protocol": "MD5", "auth_password": "auth-secret", "privacy_protocol": "AES", "privacy_password": "privacy-secret"},
    )
    ids = []
    for data in versions:
        response = client.post("/api/connection-profiles", json={"csrf": token(client), "port": 161, "timeout_seconds": 5, "retries": 1, **data})
        assert response.status_code == 201, response.text
        assert all(secret not in response.text for secret in ("private-v1", "private-v2", "auth-secret", "privacy-secret"))
        ids.append(response.json()["id"])
    listed = client.get("/api/connection-profiles")
    assert listed.status_code == 200 and len(listed.json()) == 5
    assert all(secret not in listed.text for secret in ("private-v1", "private-v2", "auth-secret", "privacy-secret"))
    page = client.get("/settings?tab=connections")
    assert "Профили подключения ещё не добавлены" not in page.text
    with sessions() as db:
        encrypted = db.get(ConnectionProfile, ids[-1]).secret_encrypted
        assert "auth-secret" not in encrypted and "privacy-secret" not in encrypted
    changed = client.patch(f"/api/connection-profiles/{ids[-1]}", json={"csrf": token(client), "name": "v3-priv", "snmp_version": "3", "username": "operator", "security_level": "authPriv", "auth_protocol": "MD5", "privacy_protocol": "AES", "auth_password": "", "privacy_password": "", "port": 161})
    assert changed.status_code == 200 and changed.json()["secret_saved"] and changed.json()["privacy_secret_saved"]
    with sessions() as db:
        assert db.get(ConnectionProfile, ids[-1]).secret_encrypted != encrypted
    invalid = client.post("/api/connection-profiles", json={"csrf": token(client), "name": "bad", "snmp_version": "3", "username": "operator", "security_level": "authPriv", "auth_protocol": "SHA", "port": 161})
    assert invalid.status_code == 422
    switched = client.patch(f"/api/connection-profiles/{ids[-1]}", json={"csrf": token(client), "name": "v3-priv", "snmp_version": "1", "community": "new-community", "username": "should-not-survive", "auth_password": "should-not-survive", "port": 161})
    assert switched.status_code == 200 and switched.json()["username"] is None


def test_source_states_are_distinct_and_model_actions_are_accessible(isolated_client):
    client, sessions = isolated_client
    source = FirmwareSource(name="Test", vendor="X", source_type="https", base_url="https://example.com", allowed_domains="example.com", last_status="Не проверялся")
    assert source_status_view(source) == ("Не проверен", "off")
    source.last_checked_at = datetime.now(timezone.utc)
    for raw, expected in (
        ("configuration valid", ("Источник доступен", "ok")),
        ("Проверка выполнена", ("Проверка выполнена", "ok")),
        ("Доступны обновления", ("Доступны обновления", "warn")),
        ("Источник недоступен", ("Ошибка проверки", "error")),
    ):
        source.last_status = raw
        assert source_status_view(source) == expected
    with sessions() as db:
        db.add(source)
        db.commit()
    data = client.get("/api/firmware-sources").json()[0]
    assert data["last_status"] == "Источник недоступен" and data["display_status"] == "Ошибка проверки"
    page = client.get("/settings?tab=equipment")
    assert 'data-model-tooltip="Открыть источник"' in page.text or 'data-model-tooltip="Проверить модель"' not in page.text


def test_equipment_type_is_a_validated_choice(isolated_client):
    client, sessions = isolated_client
    with sessions() as db:
        vendor = EquipmentVendor(name="Type vendor", slug="type-vendor")
        db.add(vendor)
        db.commit()
        vendor_id = vendor.id
    page = client.get("/settings?tab=equipment")
    assert '<select name="device_type" required>' in page.text
    assert '<option value="Коммутатор">Коммутатор</option>' in page.text
    assert '<option value="Маршрутизатор">Маршрутизатор</option>' in page.text
    created = client.post(f"/api/vendors/{vendor_id}/models", json={"csrf": token(client), "name": "Router 1", "device_type": "Маршрутизатор"})
    assert created.status_code == 201 and created.json()["device_type"] == "Маршрутизатор"
    model_id = created.json()["id"]
    changed = client.patch(f"/api/models/{model_id}", json={"csrf": token(client), "device_type": "Коммутатор"})
    assert changed.status_code == 200 and changed.json()["device_type"] == "Коммутатор"
    invalid = client.patch(f"/api/models/{model_id}", json={"csrf": token(client), "device_type": "Сервер"})
    assert invalid.status_code == 422 and "device_type" in invalid.json()["errors"]


def test_smtp_save_test_delivery_and_secret_masking(isolated_client, monkeypatch):
    client, sessions = isolated_client
    config = {"enabled": True, "host": "smtp.example.com", "port": 587, "encryption": "starttls", "username": "mailer", "password": "smtp-private-password", "sender_email": "monitor@example.com", "sender_name": "Firmware Monitor", "recipients": "one@example.com, TWO@Example.com", "event_types": ["new_firmware", "source_error"], "reminder_count": 3}
    saved = client.post("/api/settings/smtp", json={"csrf": token(client), **config})
    assert saved.status_code == 200, saved.text
    assert "smtp-private-password" not in saved.text
    assert saved.json()["settings"]["recipients"] == ["one@example.com", "TWO@example.com"]
    assert saved.json()["settings"]["reminder_count"] == 3
    assert saved.json()["settings"]["password_saved"] is True
    with sessions() as db:
        row = db.get(ApplicationSetting, mailer.PASSWORD_KEY)
        assert "smtp-private-password" not in row.value
    with sessions() as restarted_db:
        restored = mailer.public_smtp_config(restarted_db)
    assert restored["enabled"] and restored["password_saved"] and restored["host"] == "smtp.example.com"
    assert "smtp-private-password" not in client.get("/api/settings/smtp").text
    assert "smtp-private-password" not in client.get("/settings?tab=notifications").text
    sent = []
    monkeypatch.setattr(mailer, "_send_email", lambda cfg, password, subject, body: sent.append((cfg, password, subject, body)))
    with sessions() as db:
        mailer.send_test_email(db)
    assert sent[-1][1] == "smtp-private-password"
    assert "настроены успешно" in sent[-1][3]
    assert "SMTP-сервер" in sent[-1][3]
    monkeypatch.setattr("app.db.SessionLocal", sessions)
    assert mailer.send_selected_notification("new_firmware", "New", "Version") is True
    assert mailer.send_selected_notification("device_error", "Ignored", "Ignored") is False
    assert len(sent) == 2
    updated = client.post("/api/settings/smtp", json={"csrf": token(client), **{**config, "password": ""}})
    assert updated.status_code == 200 and updated.json()["settings"]["password_saved"]
    bad = client.post("/api/settings/smtp", json={"csrf": token(client), **{**config, "recipients": "not-email"}})
    assert bad.status_code == 422
    monkeypatch.setattr(mailer, "send_test_email_from_store", lambda: (_ for _ in ()).throw(mailer.MailDeliveryError("Не удалось подключиться к SMTP-серверу")))
    response = client.post("/api/settings/smtp/test", json={"csrf": token(client)})
    assert response.status_code == 502 and "SMTP-серверу" in response.json()["error"]
    monkeypatch.setattr(mailer, "send_test_email_from_store", lambda: None)
    assert client.post("/api/settings/smtp/test", json={"csrf": token(client)}).status_code == 200


def test_smtp_form_rows_are_ordered_in_complete_pairs(isolated_client):
    client, _sessions = isolated_client
    page = client.get("/settings?tab=notifications").text
    sender_name = page.index('name="sender_name"')
    reminders = page.index('name="reminder_count"')
    recipients = page.index('name="recipients"')
    assert sender_name < reminders < recipients
    assert 'class="smtp-wide">Получатели уведомлений' in page


def test_firmware_reminders_are_limited_and_persisted(isolated_client, monkeypatch):
    _client, sessions = isolated_client
    queued = []
    monkeypatch.setattr(mailer, "queue_notification", lambda *args: queued.append(args))
    with sessions() as db:
        vendor = EquipmentVendor(name="Reminder vendor", slug="reminder-vendor")
        model = EquipmentModel(vendor=vendor, name="Switch R", normalized_name="SWITCH R", firmware_page_url="https://example.com/firmware")
        db.add_all((
            model,
            ApplicationSetting(key=mailer.CONFIG_KEY, value=json.dumps({"enabled": True, "event_types": ["new_firmware"], "reminder_count": 1})),
        ))
        db.flush()
        db.add_all((
            FirmwareRelease(model_id=model.id, version="2.0", firmware_page_url="https://example.com/firmware"),
            Device(name="Core", ip_address="192.0.2.25", vendor="Reminder vendor", model="Switch R", catalog_model_id=model.id, installed_version="1.0", status="Есть обновление"),
            FirmwareEvent(model_id=model.id, version="2.0", new_version="2.0", event_type="Найдена новая прошивка", category="updates"),
        ))
        db.commit()
        cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
        assert queue_firmware_reminders(db, created_before=cutoff) == 1
        assert queue_firmware_reminders(db, created_before=cutoff) == 0
        event = db.scalar(select(FirmwareEvent))
        assert event.email_reminders_sent == 1 and event.last_email_reminder_at is not None
    assert len(queued) == 1 and "1 из 1" in queued[0][2]


def test_smtp_rejects_excessive_reminder_count():
    with pytest.raises(ValueError, match="от 0 до 10"):
        mailer.normalize_smtp_config({**mailer.DEFAULT_CONFIG, "reminder_count": 11})


def test_smtp_dns_failure_is_sanitized(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("private-host.example")
    monkeypatch.setattr(mailer.smtplib, "SMTP", fail)
    with pytest.raises(mailer.MailDeliveryError, match="Не удалось подключиться") as exc:
        mailer._send_email({"host": "private-host.example", "port": 25, "encryption": "none", "username": "", "sender_email": "from@example.com", "sender_name": "Monitor", "recipients": ["to@example.com"]}, "", "Test", "Body")
    assert "private-host.example" not in str(exc.value)
