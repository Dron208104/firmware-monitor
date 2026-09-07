import asyncio, json, logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from .providers import provider_for
from ..models import Device, EquipmentModel, FirmwareEvent, FirmwareRelease, FirmwareSourceCheck, now
from ..versioning import compare_manual

log=logging.getLogger(__name__); _locks={}

def latest_release(db:Session,model_id:int):
    return db.scalar(select(FirmwareRelease).where(FirmwareRelease.model_id==model_id).order_by(FirmwareRelease.discovered_at.desc(),FirmwareRelease.id.desc()))

def refresh_device_statuses(db:Session,model:EquipmentModel,status_override:str|None=None):
    release=latest_release(db,model.id)
    for device in db.scalars(select(Device).where(Device.catalog_model_id==model.id)).all():
        if status_override: device.status=status_override
        elif not release: device.status="Источник не настроен"
        elif not device.installed_version: device.status="Нужна проверка"
        else: device.status=compare_manual(device.installed_version,release.version)

async def check_model_source(db:Session,model:EquipmentModel):
    lock=_locks.setdefault(model.id,asyncio.Lock())
    if lock.locked(): return
    async with lock:
        provider=provider_for(model.vendor.slug)
        if not provider or not model.firmware_page_url or not model.firmware_provider:
            model.latest_check_status="Источник не настроен"; model.latest_checked_at=now(); model.latest_check_error="Официальный источник для модели не настроен"
            db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status,error=model.latest_check_error)); refresh_device_statuses(db,model,"Источник не настроен"); db.commit(); return
        try:
            provider.validate_source(model.firmware_page_url); result=await provider.fetch(model.vendor,model)
            model.latest_check_status=result.status; model.latest_checked_at=result.checked_at; model.latest_check_error=result.error
            if result.latest_version:
                release=db.scalar(select(FirmwareRelease).where(FirmwareRelease.model_id==model.id,FirmwareRelease.version==result.latest_version))
                if not release:
                    db.add(FirmwareRelease(model_id=model.id,version=result.latest_version,release_date=result.release_date,firmware_page_url=result.firmware_page_url,download_url=result.download_url,changelog_url=result.changelog_url,file_size=result.size_bytes,checksum=result.checksum,release_notes=result.release_notes,checked_at=result.checked_at))
                    db.add(FirmwareEvent(model_id=model.id,version=result.latest_version,notification_payload=json.dumps({"vendor":model.vendor.name,"model":model.name,"version":result.latest_version},ensure_ascii=False)))
                else:
                    release.checked_at=result.checked_at; release.download_url=result.download_url; release.changelog_url=result.changelog_url; release.file_size=result.size_bytes
            db.add(FirmwareSourceCheck(model_id=model.id,status=result.status,error=result.error,discovered_version=result.latest_version)); db.flush(); refresh_device_statuses(db,model,None if result.latest_version else result.status); db.commit()
        except Exception as exc:
            model.latest_check_status="Ошибка проверки производителя"; model.latest_checked_at=now(); model.latest_check_error=type(exc).__name__
            db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status,error=model.latest_check_error)); refresh_device_statuses(db,model,"Ошибка проверки производителя"); db.commit(); log.warning("Firmware source check failed for model %s: %s",model.id,type(exc).__name__)
