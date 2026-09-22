from pathlib import Path
import pytest
from app.firmware.providers.qtech import QtechFirmwareProvider
from app.versioning import compare_manual

URL="https://ftp.qtech.ru/Switch/Access/QSW-4610/Firmware/QSW-4610-28T-AC/"

def test_extracts_highest_firmware_and_related_links():
    html=(Path(__file__).parent/"fixtures"/"qtech_qsw4610.html").read_text(encoding="utf-8")
    version,download,changelog,changed,size=QtechFirmwareProvider.parse(html,URL)
    assert version=="8.2.1.256"
    assert download==URL+"QSW-4610-28T(52T)-X_8.2.1.256_nos.img"
    assert changelog==URL+"8.2.1.256%20Changelog.txt"
    assert size==10*1024*1024 and changed.year==2026
    assert compare_manual("8.2.1.251",version)=="Есть обновление"
    assert compare_manual(version,version)=="Актуально"

@pytest.mark.parametrize("html",["", "<html><a href='manual.pdf'>8.2.1.999 manual.pdf</a>","broken < html"])
def test_no_confirmed_firmware(html):
    assert QtechFirmwareProvider.parse(html,URL) is None

def test_rejects_arbitrary_domain():
    with pytest.raises(ValueError): QtechFirmwareProvider().validate_source("https://example.com/firmware/")

def test_rejects_non_https():
    with pytest.raises(ValueError): QtechFirmwareProvider().validate_source("http://ftp.qtech.ru/firmware/")
