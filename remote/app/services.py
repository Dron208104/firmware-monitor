import logging
from .models import CheckHistory, Device, now
from .snmp import SnmpPollingError, read_installed_version
from .vendors import latest_firmware, SourceError
from .versioning import compare, compare_for_vendor
log = logging.getLogger(__name__)

async def poll_installed_version(db,device:Device):
    if device.installed_version_source!="snmp":return device
    try:
        device.installed_version=await read_installed_version(device);device.last_error=None
        release=None
        if device.catalog_model_id:
            from .firmware.service import latest_release
            release=latest_release(db,device.catalog_model_id)
        device.available_version=release.version if release else None
        device.status=compare_for_vendor(device.vendor,device.installed_version,release.version) if release else "Источник не настроен"
    except SnmpPollingError as exc:
        device.status="Версия не определена";device.last_error=str(exc)
    device.last_checked_at=now()
    db.add(CheckHistory(device_id=device.id,installed_version=device.installed_version,available_version=device.available_version,status=device.status,details=device.last_error))
    db.commit();return device

async def check_device(db, device: Device):
    try:
        available, link = await latest_firmware(device.vendor, device.model, device.hardware_revision, device.official_url)
        device.available_version, device.download_url = available, link
        device.status, device.last_error = compare(device.installed_version, available), None
    except SourceError as exc:
        text = str(exc); device.last_error = text
        device.status = "Модель не поддерживается" if text == "Модель не поддерживается" else "Не удалось проверить источник"
        log.warning("Firmware check failed for device %s: %s", device.id, text)
    device.last_checked_at = now()
    db.add(CheckHistory(device_id=device.id, installed_version=device.installed_version, available_version=device.available_version, status=device.status, details=device.last_error))
    db.commit(); return device
