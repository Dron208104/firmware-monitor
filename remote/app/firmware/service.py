import asyncio, json, logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from .providers import provider_for
from ..models import Device, EquipmentModel, FirmwareEvent, FirmwareRelease, FirmwareSource, FirmwareSourceCheck, now
from ..versioning import compare_for_vendor
from ..versioning import normalize_dlink_version, normalize_eltex_version, normalize_zyxel_version

log=logging.getLogger(__name__); _locks={}

def add_event_once(db:Session,model:EquipmentModel,event_type:str,category:str,description:str,dedupe_key:str,old_version=None,new_version=None,severity="info"):
    device=db.scalar(select(Device).where(Device.catalog_model_id==model.id).order_by(Device.id))
    if not device:return
    if db.scalar(select(FirmwareEvent.id).where(FirmwareEvent.dedupe_key==dedupe_key)):return
    db.add(FirmwareEvent(model_id=model.id,device_id=device.id,version=new_version or old_version or "—",event_type=event_type,category=category,description=description,dedupe_key=dedupe_key,old_version=old_version,new_version=new_version,severity=severity,notification_payload=json.dumps({"vendor":model.vendor.name,"model":model.name},ensure_ascii=False)))

def latest_release(db:Session,model_id:int):
    return db.scalar(select(FirmwareRelease).where(FirmwareRelease.model_id==model_id).order_by(FirmwareRelease.discovered_at.desc(),FirmwareRelease.id.desc()))

def refresh_device_statuses(db:Session,model:EquipmentModel,status_override:str|None=None):
    release=latest_release(db,model.id)
    for device in db.scalars(select(Device).where(Device.catalog_model_id==model.id)).all():
        if status_override: device.status=status_override
        elif not release: device.status="Источник не настроен"
        elif not device.installed_version: device.status="Нужна проверка"
        else: device.status=compare_for_vendor(model.vendor.name,device.installed_version,release.version)

async def check_model_source(db:Session,model:EquipmentModel):
    if model.model_requires_clarification:
        model.latest_check_status="Требуется уточнить модель"; model.latest_checked_at=now(); model.latest_check_error="Не указана полная аппаратная модификация"
        db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status,error=model.latest_check_error)); refresh_device_statuses(db,model,"Требуется уточнить модель"); db.commit(); return
    lock=_locks.setdefault(model.id,asyncio.Lock())
    if lock.locked(): return
    async with lock:
        provider=provider_for(model.vendor.slug)
        source=db.get(FirmwareSource,model.firmware_source_id) if model.firmware_source_id else None
        if source and not source.enabled:
            model.latest_check_status="Источник отключён";model.latest_checked_at=now();model.latest_check_error=None
            db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status));refresh_device_statuses(db,model,"Источник отключён");db.commit();return
        if not provider or not model.firmware_page_url or not model.firmware_provider:
            model.latest_check_status="Источник не настроен"; model.latest_checked_at=now(); model.latest_check_error="Официальный источник для модели не настроен"
            db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status,error=model.latest_check_error)); refresh_device_statuses(db,model,"Источник не настроен"); db.commit(); return
        try:
            previous_status=model.latest_check_status
            previous_release=latest_release(db,model.id)
            provider.validate_source(model.firmware_page_url); result=await provider.fetch(model.vendor,model)
            result.display_version=result.latest_version
            result.product_page_url=model.product_page_url
            result.source_url=model.firmware_page_url
            result.hardware_revision=result.provider_revision
            result.compatibility_confirmed=result.source_status not in {"compatibility_unconfirmed","firmware_not_found"}
            model.latest_check_status=result.status; model.latest_checked_at=result.checked_at; model.latest_check_error=result.error
            if source:
                source.last_checked_at=result.checked_at;source.last_status=result.status;source.last_error=result.error
                if result.latest_version:source.last_success_at=result.checked_at
            if result.latest_version:
                normalizer={"eltex":normalize_eltex_version,"d-link":normalize_dlink_version,"zyxel":normalize_zyxel_version}.get(model.vendor.slug)
                normalized=normalizer(result.latest_version) if normalizer else None
                result.normalized_version='.'.join(map(str,normalized[1])) if normalized else result.latest_version
                release=db.scalar(select(FirmwareRelease).where(FirmwareRelease.model_id==model.id,FirmwareRelease.version==result.latest_version))
                if not release:
                    db.add(FirmwareRelease(model_id=model.id,version=result.latest_version,normalized_version='.'.join(map(str,normalized[1])) if normalized else None,release_suffix=normalized[2] if normalized and len(normalized)>2 else None,provider_revision=result.provider_revision,release_date=result.release_date,firmware_page_url=result.firmware_page_url,download_url=result.download_url,changelog_url=result.changelog_url,file_size=result.size_bytes,checksum=result.checksum,release_notes=result.release_notes,checked_at=result.checked_at))
                    add_event_once(db,model,"Найдена новая прошивка","updates",f"Для {model.vendor.name} {model.name} найдена версия {result.latest_version}",f"release:{model.id}:{result.latest_version}",previous_release.version if previous_release else None,result.latest_version)
                else:
                    release.checked_at=result.checked_at; release.download_url=result.download_url; release.changelog_url=result.changelog_url; release.file_size=result.size_bytes
                if previous_status in {"Источник недоступен","Используется кэш","Ошибка проверки производителя"}:add_event_once(db,model,"Источник восстановлен","system",f"Источник {model.vendor.name} снова доступен",f"recovered:{model.id}:{result.latest_version}",severity="success")
            db.add(FirmwareSourceCheck(model_id=model.id,status=result.status,error=result.error,discovered_version=result.latest_version)); db.flush(); refresh_device_statuses(db,model,None if result.latest_version else result.status); db.commit()
        except Exception as exc:
            cached=latest_release(db,model.id)
            model.latest_check_status="Используется кэш" if cached else "Источник недоступен"; model.latest_checked_at=now(); model.latest_check_error=type(exc).__name__
            if source:source.last_checked_at=model.latest_checked_at;source.last_status=model.latest_check_status;source.last_error=model.latest_check_error
            refresh_device_statuses(db,model,model.latest_check_status)
            add_event_once(db,model,"Ошибка источника","errors",f"Не удалось проверить источник прошивки для {model.vendor.name} {model.name}",f"source-error:{model.id}:{type(exc).__name__}",severity="error")
            db.add(FirmwareSourceCheck(model_id=model.id,status=model.latest_check_status,error=model.latest_check_error)); db.commit(); log.warning("Firmware source check failed for model %s: %s",model.id,type(exc).__name__)
