from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.firmware.providers.eltex import EltexFirmwareProvider
from app.firmware.providers.dlink import DlinkFirmwareProvider
from app.firmware.providers.zyxel import ZyxelFirmwareProvider
from app.main import app
from app.migrations import migrate_sqlite
from app.models import EquipmentModel, EquipmentVendor, FirmwareSource, ModelHardwareRevision
from app.versioning import normalize_eltex_version, normalize_zyxel_version


FIXTURES=Path(__file__).parent/'fixtures'


def test_vendor_sources_models_and_revisions_are_idempotent():
    migrate_sqlite(engine);migrate_sqlite(engine)
    with SessionLocal() as db:
        sources={s.vendor:s for s in db.scalars(select(FirmwareSource)).all() if s.builtin_provider}
        assert {'QTECH','MikroTik','Eltex','D-Link','Zyxel'} <= set(sources)
        assert sources['Eltex'].base_url=='https://eltex.ru/'
        assert sources['D-Link'].base_url=='https://ftp.dlink.ru/pub/Switch/'
        assert sources['Zyxel'].base_url=='https://www.zyxel.com/'
        expected={'Eltex':{'MES2300B-48','MES3400-24','MES2308R','MES2428P'},'D-Link':{'DGS-1100-08V2','DGS-1100-08','DGS-1100-05'},'Zyxel':{'GS1900-8'}}
        for vendor_name,names in expected.items():
            vendor=db.scalar(select(EquipmentVendor).where(EquipmentVendor.name==vendor_name))
            models=db.scalars(select(EquipmentModel).where(EquipmentModel.vendor_id==vendor.id,EquipmentModel.name.in_(names))).all()
            assert {m.name for m in models}==names
            assert all(m.firmware_source_id==sources[vendor_name].id for m in models)
            if vendor_name=='Eltex':
                mes2428p=next(m for m in models if m.name=='MES2428P')
                assert mes2428p.installed_version_method=='snmp'
                assert mes2428p.version_oid=='1.3.6.1.4.1.2076.81.1.3.0'
        dlink=db.scalar(select(EquipmentVendor).where(EquipmentVendor.slug=='d-link'))
        models={m.name:m for m in db.scalars(select(EquipmentModel).where(EquipmentModel.vendor_id==dlink.id)).all()}
        assert {r.display_revision for r in models['DGS-1100-08V2'].hardware_revisions}=={'A'}
        assert {r.display_revision for r in models['DGS-1100-08'].hardware_revisions}=={'A','B'}
        assert db.scalar(select(func.count()).select_from(ModelHardwareRevision).where(ModelHardwareRevision.equipment_model_id==models['DGS-1100-05'].id))==2


def test_vendor_specific_version_normalizers():
    assert normalize_eltex_version('10.4.5 R3')[1]>normalize_eltex_version('10.4.5 R2')[1]
    assert normalize_eltex_version('6.6.12.1')
    assert normalize_zyxel_version('V2.90(AAHH.1)C0')[1]>normalize_zyxel_version('2.90(AAHH.0)C0')[1]
    assert normalize_zyxel_version('V2.90(AAHI.9)C0') is None


def test_zyxel_parser_accepts_only_gs1900_8_aahh():
    found=ZyxelFirmwareProvider.parse((FIXTURES/'zyxel_gs1900_8.html').read_text(),'https://www.zyxel.com/global/en/support/download?model=gs1900-8')
    assert found[0]=='V2.90(AAHH.1)C0'
    assert 'GS1900-8HP' not in found[1]
    assert found[2].endswith('.pdf')


def test_eltex_exact_model_boundary_and_release_suffix():
    html='<html><body><h1>MES2428P</h1><a href="/files/mes2400-1045-R3.zip">Версия ПО 10.4.5 R3</a><a href="/files/MES2428-99.0.0.zip">MES2428 firmware 99.0.0</a></body></html>'
    found=EltexFirmwareProvider.parse(html,'https://eltex.ru/product/kommutator_dostupa_mes2428p/','MES2428P')
    assert found[0]=='10.4.5 R3'


def test_eltex_accepts_official_version_asset_on_exact_product_page():
    html='<html><body><h1>MES2300B-48</h1><a href="/storage/firmware.zip">Версия ПО 6.6.12.1 R1</a></body></html>'
    assert EltexFirmwareProvider.parse(html,'https://eltex.ru/product/kommutator_dostupa_mes2300b-48/','MES2300B-48')[0]=='6.6.12.1 R1'


def test_dlink_ftp_parser_respects_hardware_revision():
    html='<a href="DGS-1100-08-A1_FW_V1_10_B047.bin">A</a><a href="DGS-1100-05_08_B1_V1.00.B028.bin">B</a>'
    assert DlinkFirmwareProvider.parse(html,'https://ftp.dlink.ru/pub/Switch/DGS-1100-08/Firmware/','REVA','DGS-1100-08')[0]=='1.10.B047'
    assert DlinkFirmwareProvider.parse(html,'https://ftp.dlink.ru/pub/Switch/DGS-1100-08/Firmware/','REVB','DGS-1100-08')[0]=='1.00.B028'


def test_device_form_api_exposes_dlink_revision_choices():
    with TestClient(app) as client:
        vendor=next(v for v in client.get('/api/vendors').json() if v['slug']=='d-link')
        models=client.get(f"/api/vendors/{vendor['id']}/models").json()
        plain=next(m for m in models if m['name']=='DGS-1100-08')
        assert {(r['display_revision'],r['provider_revision']) for r in plain['hardware_revisions']}=={('A','REVA'),('B','REVB')}
