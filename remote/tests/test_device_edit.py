import json
import os

from cryptography.fernet import Fernet

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.connection_profiles import apply_profile_data
from app.main import app
from app.models import ConnectionProfile, Device
from app.security import decrypt_secret, encrypt_secret


def test_edit_device_can_change_snmp_version_and_preserve_blank_secrets():
    with SessionLocal() as db:
        previous = db.scalar(select(Device).where(Device.ip_address == "192.0.2.249"))
        if previous:
            db.delete(previous)
            db.commit()
        device = Device(
            name="SNMP edit test",
            ip_address="192.0.2.249",
            vendor="QTECH",
            model="Test",
            acquisition_method="snmp",
            version_source="snmp",
            installed_version_source="snmp",
            snmp_version="3",
            snmp_port=161,
            snmpv3_username="monitor",
            security_level="authPriv",
            auth_protocol="SHA",
            privacy_protocol="AES",
            credentials_encrypted=encrypt_secret(json.dumps({"auth_password": "old-auth", "privacy_password": "old-privacy"})),
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        device_id = device.id

    with TestClient(app) as client:
        page = client.get(f"/devices/{device_id}/edit")
        assert page.status_code == 200
        assert "Параметры SNMP устройства" in page.text
        csrf = client.cookies["csrf"]
        response = client.post("/devices/save", data={
            "csrf": csrf, "device_id": device_id, "name": "SNMP edit test", "ip_address": "192.0.2.249",
            "vendor": "QTECH", "model": "Test", "icon_type": "router", "acquisition_method": "snmp", "profile_id": "",
            "snmp_version": "3", "snmp_port": "161", "snmpv3_username": "monitor",
            "security_level": "authPriv", "auth_protocol": "SHA", "auth_password": "",
            "privacy_protocol": "AES", "privacy_password": "", "installed_version": "",
            "hardware_revision": "", "official_url": "", "description": "", "auto_check": "on",
        }, follow_redirects=False)
        assert response.status_code == 303

    with SessionLocal() as db:
        saved = db.get(Device, device_id)
        assert saved.snmp_version == "3"
        assert saved.icon_type == "router"
        assert json.loads(decrypt_secret(saved.credentials_encrypted)) == {"auth_password": "old-auth", "privacy_password": "old-privacy"}
        db.delete(saved)
        db.commit()


def test_create_device_can_use_connection_profile_without_exposing_profile_secret():
    with SessionLocal() as db:
        previous = db.scalar(select(Device).where(Device.ip_address == "192.0.2.248"))
        if previous:
            db.delete(previous)
            db.flush()
        previous_profile = db.scalar(select(ConnectionProfile).where(ConnectionProfile.name == "Create device profile"))
        if previous_profile:
            db.delete(previous_profile)
            db.flush()
        profile = ConnectionProfile()
        apply_profile_data(profile, {"name": "Create device profile", "snmp_version": "2c", "community": "profile-secret", "port": 1161})
        db.add(profile)
        db.commit()
        db.refresh(profile)
        profile_id = profile.id

    with TestClient(app) as client:
        csrf = client.get("/").cookies.get("csrf") or client.cookies["csrf"]
        response = client.post("/api/devices", json={
            "csrf": csrf, "name": "Profile device", "address": "192.0.2.248",
            "vendor_id": None, "model_id": None, "custom_model": "Test profile",
            "version_source": "snmp", "profile_id": profile_id, "description": "", "auto_check": True,
        })
        assert response.status_code == 201, response.text

    with SessionLocal() as db:
        saved = db.scalar(select(Device).where(Device.ip_address == "192.0.2.248"))
        assert saved.profile_id == profile_id
        assert saved.credentials_encrypted is None
        db.delete(saved)
        db.delete(db.get(ConnectionProfile, profile_id))
        db.commit()
