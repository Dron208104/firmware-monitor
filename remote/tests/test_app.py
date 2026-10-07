import os
from cryptography.fernet import Fernet
os.environ["DATABASE_URL"]="sqlite:///./test.db"
os.environ["SECRET_KEY"]="test-secret"
os.environ["ENCRYPTION_KEY"]=Fernet.generate_key().decode()
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.main import app
from app.db import SessionLocal
from app.models import CheckHistory, Device, EquipmentModel, EquipmentVendor, FirmwareEvent, FirmwareRelease, FirmwareSourceCheck
from app.versioning import compare_for_vendor, compare_manual

def clean_devices():
    with SessionLocal() as db:
        db.execute(delete(CheckHistory)); db.execute(delete(Device)); db.execute(delete(FirmwareEvent)); db.execute(delete(FirmwareSourceCheck)); db.execute(delete(FirmwareRelease)); db.commit()
def csrf(client): client.get("/"); return client.cookies.get("csrf")
def catalog(slug="qtech"):
    with SessionLocal() as db:
        vendor=db.scalar(select(EquipmentVendor).where(EquipmentVendor.slug==slug)); model=db.scalar(select(EquipmentModel).where(EquipmentModel.vendor_id==vendor.id)); return vendor.id,model.id
def payload(**changes):
    vendor_id,model_id=catalog(); data={"name":"Тестовый коммутатор","address":"192.0.2.10","vendor_id":vendor_id,"model_id":model_id,"snmp_version":"2c","snmp_port":161,"community":"private-value","auto_check":True}; data.update(changes); return data

def test_health_and_catalog_depends_on_vendor():
    with TestClient(app) as client:
        assert client.get("/health").json()=={"status":"ok"}
        vendors=client.get("/api/vendors").json(); assert {x["name"] for x in vendors}=={"QTECH","Eltex","D-Link","MikroTik","Zyxel"}
        for vendor in vendors:
            models=client.get(f"/api/vendors/{vendor['id']}/models").json()
            assert models and all(x["vendor_id"]==vendor["id"] for x in models)

def test_successful_creation_and_no_secrets():
    clean_devices()
    with TestClient(app) as client:
        data=payload(description="Коммутатор в серверной"); data["csrf"]=csrf(client); response=client.post("/api/devices",json=data)
        assert response.status_code==201 and response.json()["model"]=="QSW-4610-28T-AC" and response.json()["version_source"]=="snmp"
        assert response.json()["description"]=="Коммутатор в серверной"
        raw=str(response.json())+str(client.get("/api/devices").json())
        assert "private-value" not in raw and "community" not in raw and "password" not in raw

def test_device_icon_type_is_persisted_and_validated():
    clean_devices()
    with TestClient(app) as client:
        data=payload(icon_type="router"); data["csrf"]=csrf(client)
        response=client.post("/api/devices",json=data)
        assert response.status_code==201 and response.json()["icon_type"]=="router"
        with SessionLocal() as db:
            assert db.get(Device,response.json()["id"]).icon_type=="router"
        invalid=payload(address="192.0.2.11",icon_type="access-point"); invalid["csrf"]=client.cookies["csrf"]
        assert client.post("/api/devices",json=invalid).status_code==422

def test_model_from_another_vendor_is_rejected():
    clean_devices()
    with TestClient(app) as client:
        qtech,_=catalog("qtech"); _,eltex_model=catalog("eltex"); data=payload(vendor_id=qtech,model_id=eltex_model); data["csrf"]=csrf(client)
        response=client.post("/api/devices",json=data); assert response.status_code==422 and "model_id" in response.json()["errors"]

def test_disabled_model_hidden_and_rejected():
    clean_devices()
    with TestClient(app) as client:
        vendor_id,model_id=catalog(); token=csrf(client)
        assert client.patch(f"/api/models/{model_id}",json={"csrf":token,"enabled":False}).status_code==200
        assert all(x["id"]!=model_id for x in client.get(f"/api/vendors/{vendor_id}/models").json())
        data=payload(vendor_id=vendor_id,model_id=model_id); data["csrf"]=token
        assert client.post("/api/devices",json=data).status_code==422
        client.patch(f"/api/models/{model_id}",json={"csrf":token,"enabled":True})

def test_other_vendor_manual_model():
    clean_devices()
    with TestClient(app) as client:
        data=payload(vendor_id=None,model_id=None,custom_model="Пользовательская модель"); data["csrf"]=csrf(client)
        response=client.post("/api/devices",json=data); assert response.status_code==201
        assert response.json()["vendor"]=="Другой" and response.json()["model"]=="Пользовательская модель"

def test_used_model_cannot_be_deleted():
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client); data=payload(); data["csrf"]=token; device=client.post("/api/devices",json=data); assert device.status_code==201
        _,model_id=catalog(); response=client.request("DELETE",f"/api/models/{model_id}",json={"csrf":token})
        assert response.status_code==409

def test_new_model_appears_without_code_change():
    clean_devices()
    with TestClient(app) as client:
        vendor_id,_=catalog("qtech"); token=csrf(client)
        created=client.post(f"/api/vendors/{vendor_id}/models",json={"csrf":token,"name":"TEST-MODEL-FOR-AUTOMATION"})
        assert created.status_code==201 and any(x["name"]=="TEST-MODEL-FOR-AUTOMATION" for x in client.get(f"/api/vendors/{vendor_id}/models").json())
        assert client.request("DELETE",f"/api/models/{created.json()['id']}",json={"csrf":token}).status_code==200

def test_form_resets_model_and_has_custom_input():
    with TestClient(app) as client:
        html=client.get("/").text; js=client.get("/static/app.js").text
        assert "Сначала выберите производителя" in html and 'name="custom_model"' in html
        assert "select.replaceChildren()" in js and "custom.value=''" in js

def test_snmp_is_default_and_manual_switch_is_client_side():
    with TestClient(app) as client:
        html=client.get("/").text; js=client.get("/static/app.js").text
        assert 'name="version_source" value="snmp" checked' in html
        assert 'name="version_source" value="manual"' in html
        assert "switchSource" in js and "Версии прошивки будут указаны вручную" in js
        assert "if(data.snmp_port!==undefined)" in js

def test_manual_versions_required_and_hidden_snmp_not_validated():
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client); data=payload(version_source="manual",community=None,snmp_port=0,installed_version=""); data["csrf"]=token
        errors=client.post("/api/devices",json=data).json()["errors"]
        assert "installed_version" in errors and "available_version" not in errors
        assert "community" not in errors and "snmp_port" not in errors

def test_manual_status_is_calculated_by_backend_and_has_no_secrets():
    assert compare_manual("1.9","1.10")=="Есть обновление"
    assert compare_manual("v7.0.5","7.0.5")=="Актуально"
    assert compare_manual("7.0.5","7.0.3")=="Требуется проверка"
    assert compare_manual("release-7","7.0")=="Версия не определена"
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client); data=payload(version_source="manual",installed_version="1.9",community="must-not-be-stored",auto_check=True); data["csrf"]=token
        result=client.post("/api/devices",json=data); assert result.status_code==201
        assert result.json()["status"] in {"Проверка версии производителя","Источник не настроен"} and result.json()["auto_check"] is False and result.json()["available_version"] is None
        with SessionLocal() as db:
            saved=db.get(Device,result.json()["id"]); assert saved.credentials_encrypted is None and saved.version_source=="manual"

def test_vendor_specific_version_comparison():
    assert compare_for_vendor("Eltex", "10.3.2.2", "10.4.5 R3") == "Есть обновление"
    assert compare_for_vendor("Eltex", "10.3.6.6", "4.0.27.2") == "Требуется проверка"
    assert compare_for_vendor("Zyxel", "1", "V2.90(AAHH.2)C0") == "Есть обновление"
    assert compare_for_vendor("Zyxel", "V2.90(AAHH.2)C0", "2.90(AAHH.2)C0") == "Актуально"

def test_manual_device_is_excluded_from_scheduled_checks(monkeypatch):
    import asyncio, app.main as main_module
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client)
        manual=payload(version_source="manual",installed_version="1.0",community=None); manual["csrf"]=token
        client.post("/api/devices",json=manual)
        snmp=payload(address="192.0.2.11"); snmp["csrf"]=token; snmp_id=client.post("/api/devices",json=snmp).json()["id"]
        checked=[]
        async def fake_check(_db,model): checked.append(model.id)
        monkeypatch.setattr(main_module,"check_model_source",fake_check)
        asyncio.run(main_module.scheduled_checks())
        assert len(checked)==1

def test_manual_device_can_adopt_latest_discovered_version():
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client); data=payload(version_source="manual",installed_version="1.0",community=None); data["csrf"]=token
        created=client.post("/api/devices",json=data); assert created.status_code==201
        device_id=created.json()["id"]; _,model_id=catalog()
        with SessionLocal() as db:
            db.add(FirmwareRelease(model_id=model_id,version="2.0",firmware_page_url="https://example.com/firmware")); db.commit()
        adopted=client.post(f"/api/devices/{device_id}/adopt-latest-version",json={"csrf":token})
        assert adopted.status_code==200 and adopted.json()["installed_version"]=="2.0"
        assert adopted.json()["available_version"]=="2.0" and adopted.json()["status"]=="Актуально"
        assert adopted.json()["last_checked_at"] is not None
        with SessionLocal() as db:
            history=db.scalar(select(CheckHistory).where(CheckHistory.device_id==device_id).order_by(CheckHistory.id.desc()))
            assert history and history.installed_version=="2.0" and "актуализирована вручную" in history.details
        already_current=client.post(f"/api/devices/{device_id}/adopt-latest-version",json={"csrf":token})
        assert already_current.status_code==409 and "уже актуально" in already_current.json()["error"]
        repeated=client.post(f"/api/devices/{device_id}/adopt-latest-version",json={"csrf":token,"version":"3.0"})
        assert repeated.status_code==422

def test_ipv4_duplicate_and_snmp_validation():
    clean_devices()
    with TestClient(app) as client:
        token=csrf(client)
        for changes,field in [({"address":"switch.local"},"address"),({"snmp_port":65536},"snmp_port"),({"community":""},"community")]:
            data=payload(**changes); data["csrf"]=token; assert field in client.post("/api/devices",json=data).json()["errors"]
        data=payload(); data["csrf"]=token; assert client.post("/api/devices",json=data).status_code==201
        duplicate=payload(snmp_port=1161); duplicate["csrf"]=token; assert client.post("/api/devices",json=duplicate).status_code==422
