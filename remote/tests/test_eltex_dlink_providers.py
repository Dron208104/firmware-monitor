from pathlib import Path
import pytest
from app.firmware.providers.eltex import EltexFirmwareProvider
from app.firmware.providers.dlink import DlinkFirmwareProvider
from app.versioning import normalize_eltex_version,normalize_dlink_version

FIXTURES=Path(__file__).parent/'fixtures'

def test_eltex_mes24xx_selects_numeric_latest_and_notes():
    found=EltexFirmwareProvider.parse((FIXTURES/'eltex_mes2428p.html').read_text(),'https://eltex.ru/download/','MES2428P')
    assert found[0]=='10.3.6.11' and found[1].endswith('MES2428P-10.3.6.11.bin') and found[2].endswith('release-notes.pdf')

def test_eltex_versions_are_vendor_specific():
    assert normalize_eltex_version('10.3.10')[1]>normalize_eltex_version('10.3.9')[1]
    assert normalize_eltex_version('10.4.1')[1]>normalize_eltex_version('10.3.12')[1]
    assert normalize_eltex_version('10.3.6.11')[1]>normalize_eltex_version('10.3.6.2')[1]
    assert normalize_eltex_version('release') is None

def test_dlink_exact_model_revision_firmware_and_notes():
    found=DlinkFirmwareProvider.parse((FIXTURES/'dlink_dgs1100_08v2_reva.html').read_text(),'https://support.dlink.com/resource/products/DGS-1100-08V2/REVA/FIRMWARE/')
    assert found[0]=='1.01.003' and '08V2_REVA_FIRMWARE' in found[1] and found[2].endswith('v1.01.003.pdf')
    assert '08PV2' not in found[1] and 'REVB' not in found[1]

def test_dlink_discovers_exact_model_from_general_catalog():
    catalog='<a href="DGS-1100-08/">old</a><a href="DGS-1100-08V2/">target</a><a href="DGS-1100-08PV2/">poe</a>'
    assert DlinkFirmwareProvider._directory(catalog,'https://ftp.dlink.ru/pub/Switch/','DGS-1100-08V2')=='https://ftp.dlink.ru/pub/Switch/DGS-1100-08V2/'

def test_dlink_parses_shared_05v2_08v2_firmware_names():
    html='<a href="DGS-1100-05V2_08V2_1.00.B014.bin">old</a><a href="DGS-1100-05V2_08V2_V1.00.015_FW.bin">new</a><a href="DGS-1100-08PV2_V9.99.999_FW.bin">wrong model</a>'
    found=DlinkFirmwareProvider.parse(html,'https://ftp.dlink.ru/pub/Switch/DGS-1100-08V2/Firmware/',model_name='DGS-1100-08V2')
    assert found[0]=='1.00.015' and found[1].endswith('DGS-1100-05V2_08V2_V1.00.015_FW.bin')

@pytest.mark.parametrize('value',['1.00.003','1.01.003','1.00.B020','V1.01.B012'])
def test_dlink_normalizer(value): assert normalize_dlink_version(value)

def test_dlink_numeric_comparison():
    assert normalize_dlink_version('1.01.003')[1]>normalize_dlink_version('1.00.100')[1]
    assert normalize_dlink_version('1.00.010')[1]>normalize_dlink_version('1.00.003')[1]

@pytest.mark.parametrize('provider,url',[ (EltexFirmwareProvider(),'https://example.com/a'),(DlinkFirmwareProvider(),'https://example.com/a') ])
def test_providers_reject_non_official_domains(provider,url):
    with pytest.raises(ValueError):provider.validate_source(url)
