from sqlalchemy import func, select
from app.db import SessionLocal, engine
from app.main import app
from app.migrations import migrate_sqlite
from app.models import EquipmentModel, EquipmentVendor
from fastapi.testclient import TestClient

EXPECTED=["QSW-3750-10T-AC-R","QSW-3750-28T-AC-R","QSW-4530-54TX","QSW-4610-10T-POE-AC","QSW-4610-28T-AC","QSW-4700-52TX","QSW-6910-26F"]

def test_qtech_catalog_is_complete_sorted_and_idempotent():
    migrate_sqlite(engine); migrate_sqlite(engine)
    with SessionLocal() as db:
        vendor=db.scalar(select(EquipmentVendor).where(EquipmentVendor.slug=="qtech"))
        models=db.scalars(select(EquipmentModel).where(EquipmentModel.vendor_id==vendor.id).order_by(EquipmentModel.name)).all()
        names=[m.name for m in models if m.name in EXPECTED]
        assert names==EXPECTED
        assert db.scalar(select(func.count()).select_from(EquipmentModel).where(EquipmentModel.vendor_id==vendor.id,EquipmentModel.name.in_(EXPECTED)))==7
        exact=next(m for m in models if m.name=="QSW-4610-28T-AC")
        assert exact.model_requires_clarification is False
        assert all(not m.model_requires_clarification for m in models if m.name in {"QSW-3750-10T-AC-R","QSW-4530-54TX","QSW-4610-10T-POE-AC","QSW-4610-28T-AC","QSW-4700-52TX"})
        assert all(not m.model_requires_clarification for m in models if m.name in EXPECTED)
        assert all(m.latest_check_status != "Требуется уточнить модель" for m in models if m.name in EXPECTED)
        assert "numeric-8.x" in next(m for m in models if m.name=="QSW-4530-54TX").parsing_parameters
        qsw4700=next(m for m in models if m.name=="QSW-4700-52TX")
        assert '"os12"' in qsw4700.parsing_parameters
        assert qsw4700.installed_version_method=="snmp"
        assert qsw4700.version_oid=="1.3.6.1.4.1.27514.1.1.10.2.1.1.2.0"

def test_catalog_api_exposes_clarification_flag():
    with TestClient(app) as client:
        vendor=next(v for v in client.get('/api/vendors').json() if v['slug']=='qtech')
        models=client.get(f"/api/vendors/{vendor['id']}/models").json()
        assert [m['name'] for m in models if m['name'] in EXPECTED]==EXPECTED
        assert all(not m['model_requires_clarification'] for m in models if m['name'] in EXPECTED)

def test_mikrotik_rb4011_models_are_exact_arm_long_term():
    migrate_sqlite(engine)
    with SessionLocal() as db:
        vendor=db.scalar(select(EquipmentVendor).where(EquipmentVendor.slug=="mikrotik"))
        models=db.scalars(select(EquipmentModel).where(EquipmentModel.vendor_id==vendor.id).order_by(EquipmentModel.name)).all()
        assert [m.name for m in models]==["RB4011iGS+5HacQ2HnD-IN","RB4011iGS+RM"]
        assert all((m.series,m.os_family,m.architecture,m.update_channel)==("RB4011","routeros","arm","long-term") for m in models)
