import ipaddress, json, logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .migrations import migrate_sqlite
from .models import CheckHistory, ConnectionProfile, Device, EquipmentModel, EquipmentVendor
from .polling import test_connection
from .schemas import DeviceCreate, DeviceOut
from .security import csrf_token, encrypt_secret, validate_public_url
from .services import check_device
from .versioning import compare_manual
from .firmware.service import check_model_source, latest_release

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE/"templates")

async def scheduled_checks():
    with SessionLocal() as db:
        model_ids=set(db.scalars(select(Device.catalog_model_id).where(Device.auto_check.is_(True),Device.installed_version_source=="snmp",Device.catalog_model_id.is_not(None))).all())
        for model_id in model_ids:
            model=db.get(EquipmentModel,model_id)
            if model: await check_model_source(db,model)

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    migrate_sqlite(engine)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_checks, "interval", hours=settings.firmware_check_interval_hours, max_instances=1, id="firmware-checks", replace_existing=True)
    scheduler.start(); app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")

def context(request, **extra):
    token = request.cookies.get("csrf") or csrf_token()
    scheduler = getattr(request.app.state, "scheduler", None); running = bool(scheduler and scheduler.running)
    job = scheduler.get_job("firmware-checks") if running else None
    return {"request":request,"csrf":token,"auto_check_enabled":running,"next_check":job.next_run_time if job else None,**extra}, token

def verify(request, token):
    if not token or token != request.cookies.get("csrf"): raise HTTPException(403,"Некорректный CSRF-токен")

def page(request, name, **extra):
    ctx, token = context(request, **extra); response = templates.TemplateResponse(request,name,ctx)
    response.set_cookie("csrf",token,httponly=True,samesite="strict"); return response

def valid_address(value: str) -> bool:
    try: return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError: return False

def serialize(device: Device, db:Session|None=None) -> dict:
    release=latest_release(db,device.catalog_model_id) if db and device.catalog_model_id else None
    model=device.catalog_model
    return DeviceOut(id=device.id,name=device.name,address=device.ip_address,vendor=device.vendor,model=device.model,acquisition_method=device.acquisition_method,version_source=device.installed_version_source,management_port=device.management_port,installed_version=device.installed_version,available_version=release.version if release else None,description=device.description,auto_check=device.auto_check,status=device.status,last_checked_at=device.last_checked_at.isoformat() if device.last_checked_at else None,latest_checked_at=model.latest_checked_at.isoformat() if model and model.latest_checked_at else None,latest_check_status=model.latest_check_status if model else "Источник не настроен",download_url=release.download_url if release else None,firmware_page_url=release.firmware_page_url if release else (model.firmware_page_url if model else None),changelog_url=release.changelog_url if release else None).model_dump()

def validate_device(data: DeviceCreate, db: Session) -> tuple[dict[str,str], EquipmentVendor | None, EquipmentModel | None]:
    errors={}
    if not data.name.strip(): errors["name"]="Укажите название устройства"
    if not valid_address(data.address.strip()): errors["address"]="Укажите корректный IPv4-адрес"
    vendor=db.get(EquipmentVendor,data.vendor_id) if data.vendor_id else None
    model=db.get(EquipmentModel,data.model_id) if data.model_id else None
    if data.vendor_id is None:
        if not (data.custom_model or "").strip(): errors["custom_model"]="Укажите модель"
    else:
        if not vendor or not vendor.enabled: errors["vendor_id"]="Выберите производителя"
        if not model: errors["model_id"]="Выберите модель"
        elif model.vendor_id!=data.vendor_id: errors["model_id"]="Модель не относится к выбранному производителю"
        elif not model.enabled: errors["model_id"]="Эта модель временно отключена"
    if data.version_source not in {"snmp","manual"}: errors["version_source"]="Выберите источник установленной версии"
    if data.version_source=="snmp":
        if not 1 <= data.snmp_port <= 65535: errors["snmp_port"]="Порт должен быть от 1 до 65535"
        if data.snmp_version not in {"2c","3"}: errors["snmp_version"]="Выберите версию SNMP"
        if data.snmp_version=="2c" and not data.community: errors["community"]="Укажите Community"
        if data.snmp_version=="3":
            if not data.snmpv3_username: errors["snmpv3_username"]="Укажите пользователя SNMPv3"
            if data.security_level not in {"noAuthNoPriv","authNoPriv","authPriv"}: errors["security_level"]="Выберите уровень безопасности"
            if data.security_level in {"authNoPriv","authPriv"}:
                if not data.auth_protocol: errors["auth_protocol"]="Выберите протокол аутентификации"
                if not data.auth_password: errors["auth_password"]="Укажите пароль аутентификации"
            if data.security_level=="authPriv":
                if not data.privacy_protocol: errors["privacy_protocol"]="Выберите протокол шифрования"
                if not data.privacy_password: errors["privacy_password"]="Укажите пароль шифрования"
    else:
        if not (data.installed_version or "").strip(): errors["installed_version"]="Укажите установленную версию"
    return errors,vendor,model

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request,q:str="",vendor:str="",status:str="",db:Session=Depends(get_db)):
    stmt=select(Device)
    if q: stmt=stmt.where(or_(Device.name.contains(q),Device.ip_address.contains(q),Device.vendor.contains(q),Device.model.contains(q)))
    if vendor: stmt=stmt.where(Device.vendor==vendor)
    if status: stmt=stmt.where(Device.status==status)
    devices=db.scalars(stmt.order_by(Device.name)).all(); all_devices=db.scalars(select(Device)).all()
    attention_statuses={"Доступно обновление","Есть обновление","Требуется проверка","Версия не определена","Устройство недоступно","Не удалось проверить источник","Модель не поддерживается"}
    update_statuses={"Доступно обновление","Есть обновление"}; current_statuses={"Актуальная версия","Актуально"}
    counts={"total":len(all_devices),"updates":sum(x.status in update_statuses for x in all_devices),"current":sum(x.status in current_statuses for x in all_devices),"review":sum(x.status not in update_statuses|current_statuses for x in all_devices)}
    return page(request,"dashboard.html",devices=devices,counts=counts,attention=[x for x in all_devices if x.status in attention_statuses],q=q,vendor=vendor,status=status)

@app.get("/api/devices",response_model=list[DeviceOut])
def api_devices(db:Session=Depends(get_db)): return [serialize(x,db) for x in db.scalars(select(Device).order_by(Device.name)).all()]

def vendor_json(v): return {"id":v.id,"name":v.name,"slug":v.slug,"enabled":v.enabled}
def model_json(m): return {"id":m.id,"vendor_id":m.vendor_id,"name":m.name,"normalized_name":m.normalized_name,"enabled":m.enabled,"snmp_profile":json.loads(m.snmp_profile) if m.snmp_profile else None,"created_at":m.created_at.isoformat() if m.created_at else None,"updated_at":m.updated_at.isoformat() if m.updated_at else None}

@app.get("/api/vendors")
def api_vendors(include_disabled:bool=False,db:Session=Depends(get_db)):
    stmt=select(EquipmentVendor).order_by(EquipmentVendor.name)
    if not include_disabled: stmt=stmt.where(EquipmentVendor.enabled.is_(True))
    return [vendor_json(x) for x in db.scalars(stmt).all()]

@app.get("/api/vendors/{vendor_id}/models")
def api_vendor_models(vendor_id:int,include_disabled:bool=False,db:Session=Depends(get_db)):
    if not db.get(EquipmentVendor,vendor_id): raise HTTPException(404,"Производитель не найден")
    stmt=select(EquipmentModel).where(EquipmentModel.vendor_id==vendor_id).order_by(EquipmentModel.name)
    if not include_disabled: stmt=stmt.where(EquipmentModel.enabled.is_(True))
    return [model_json(x) for x in db.scalars(stmt).all()]

@app.post("/api/vendors/{vendor_id}/models",status_code=201)
async def api_add_model(vendor_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); vendor=db.get(EquipmentVendor,vendor_id)
    if not vendor: raise HTTPException(404,"Производитель не найден")
    name=str(data.get("name","")).strip()
    if not name: return JSONResponse(status_code=422,content={"errors":{"name":"Укажите название модели"}})
    model=EquipmentModel(vendor_id=vendor_id,name=name,normalized_name=name.upper(),enabled=True,snmp_profile=None); db.add(model)
    try: db.commit()
    except IntegrityError: db.rollback(); return JSONResponse(status_code=422,content={"errors":{"name":"Такая модель уже существует"}})
    db.refresh(model); return model_json(model)

@app.patch("/api/models/{model_id}")
async def api_update_model(model_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); model=db.get(EquipmentModel,model_id)
    if not model: raise HTTPException(404,"Модель не найдена")
    if "name" in data:
        name=str(data["name"]).strip()
        if not name: return JSONResponse(status_code=422,content={"errors":{"name":"Укажите название модели"}})
        model.name=name; model.normalized_name=name.upper()
    if "enabled" in data: model.enabled=bool(data["enabled"])
    try: db.commit()
    except IntegrityError: db.rollback(); return JSONResponse(status_code=422,content={"errors":{"name":"Такая модель уже существует"}})
    db.refresh(model); return model_json(model)

@app.delete("/api/models/{model_id}")
async def api_delete_model(model_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); model=db.get(EquipmentModel,model_id)
    if not model: raise HTTPException(404,"Модель не найдена")
    if db.scalar(select(Device.id).where(Device.catalog_model_id==model_id)):
        return JSONResponse(status_code=409,content={"error":"Модель используется устройствами и не может быть удалена"})
    db.delete(model); db.commit(); return {"ok":True}

@app.post("/api/devices",response_model=DeviceOut,status_code=201)
def api_create_device(data:DeviceCreate,request:Request,db:Session=Depends(get_db)):
    verify(request,data.csrf); errors,vendor,catalog_model=validate_device(data,db)
    port=data.snmp_port if data.version_source=="snmp" else 0
    if db.scalar(select(Device.id).where(Device.ip_address==data.address.strip())):
        errors["address"]="Устройство с таким IP-адресом уже существует"
    if errors: return JSONResponse(status_code=422,content={"errors":errors})
    secrets={k:v for k,v in {"community":data.community,"auth_password":data.auth_password,"privacy_password":data.privacy_password}.items() if v} if data.version_source=="snmp" else {}
    try: encrypted=encrypt_secret(json.dumps(secrets)) if secrets else None
    except RuntimeError: return JSONResponse(status_code=503,content={"errors":{"form":"Ключ шифрования ENCRYPTION_KEY не настроен"}})
    vendor_name=vendor.name if vendor else "Другой"; model_name=catalog_model.name if catalog_model else (data.custom_model or "").strip()
    manual=data.version_source=="manual"; installed=(data.installed_version or "").strip() if manual else None
    device=Device(name=data.name.strip(),ip_address=data.address.strip(),management_port=port,vendor=vendor_name,model=model_name,catalog_model_id=catalog_model.id if catalog_model else None,acquisition_method="manual" if manual else "snmp",version_source=data.version_source,installed_version_source=data.version_source,snmp_version=None if manual else data.snmp_version,snmp_port=data.snmp_port,snmpv3_username=data.snmpv3_username if not manual and data.snmp_version=="3" else None,security_level=data.security_level if not manual and data.snmp_version=="3" else None,auth_protocol=data.auth_protocol if not manual and data.snmp_version=="3" else None,privacy_protocol=data.privacy_protocol if not manual and data.snmp_version=="3" else None,credentials_encrypted=encrypted,installed_version=installed,available_version=None,description=(data.description or "").strip() or None,auto_check=False if manual else data.auto_check,status="Проверка версии производителя")
    db.add(device)
    try: db.commit()
    except IntegrityError: db.rollback(); return JSONResponse(status_code=422,content={"errors":{"address":"Устройство с таким IP-адресом уже существует"}})
    db.refresh(device)
    return serialize(device,db)

@app.delete("/api/devices/{device_id}")
async def api_delete_device(device_id:int,request:Request,db:Session=Depends(get_db)):
    payload=await request.json(); verify(request,payload.get("csrf")); device=db.get(Device,device_id)
    if not device: raise HTTPException(404,"Устройство не найдено")
    db.delete(device); db.commit(); return {"ok":True}

@app.post("/api/devices/{device_id}/check-firmware",response_model=DeviceOut)
async def api_check_firmware(device_id:int,request:Request,db:Session=Depends(get_db)):
    payload=await request.json(); verify(request,payload.get("csrf"))
    if set(payload)-{"csrf"}: return JSONResponse(status_code=422,content={"error":"Параметры источника задаются только в справочнике моделей"})
    device=db.get(Device,device_id)
    if not device: raise HTTPException(404,"Устройство не найдено")
    if not device.catalog_model_id: return JSONResponse(status_code=409,content={"error":"Для устройства не выбрана модель из справочника"})
    await check_model_source(db,device.catalog_model); db.refresh(device)
    return serialize(device,db)

@app.patch("/api/devices/{device_id}/versions",response_model=DeviceOut)
async def api_update_manual_versions(device_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); device=db.get(Device,device_id)
    if not device: raise HTTPException(404,"Устройство не найдено")
    if device.installed_version_source!="manual": return JSONResponse(status_code=409,content={"error":"Версия этого устройства получается по SNMP"})
    if set(data)-{"csrf","installed_version"}: return JSONResponse(status_code=422,content={"error":"Актуальная версия не задаётся для устройства"})
    installed=str(data.get("installed_version","")).strip()
    errors={}
    if not installed: errors["installed_version"]="Укажите установленную версию"
    if errors: return JSONResponse(status_code=422,content={"errors":errors})
    release=latest_release(db,device.catalog_model_id) if device.catalog_model_id else None
    device.installed_version=installed; device.available_version=None; device.status=compare_manual(installed,release.version) if release else "Источник не настроен"; db.commit(); db.refresh(device)
    return serialize(device,db)

@app.get("/devices/new",response_class=HTMLResponse)
@app.get("/devices/{device_id}/edit",response_class=HTMLResponse)
def device_form(request:Request,device_id:int|None=None,db:Session=Depends(get_db)):
    device=db.get(Device,device_id) if device_id else None; return page(request,"device_form.html",device=device,profiles=db.scalars(select(ConnectionProfile)).all())

@app.post("/devices/save")
def save_device(request:Request,csrf:str=Form(...),device_id:str=Form(""),name:str=Form(...),ip_address:str=Form(...),vendor:str=Form(...),model:str=Form(...),hardware_revision:str=Form(""),installed_version:str=Form(""),acquisition_method:str=Form(...),profile_id:str=Form(""),official_url:str=Form(""),auto_check:str|None=Form(None),db:Session=Depends(get_db)):
    verify(request,csrf)
    if not valid_address(ip_address): raise HTTPException(422,"Некорректный IPv4-адрес")
    if official_url:
        try: validate_public_url(official_url)
        except ValueError as exc: raise HTTPException(422,str(exc))
    device=db.get(Device,int(device_id)) if device_id else Device()
    for k,v in {"name":name,"ip_address":ip_address,"vendor":vendor,"model":model,"hardware_revision":hardware_revision or None,"installed_version":installed_version or None,"acquisition_method":acquisition_method,"profile_id":int(profile_id) if profile_id else None,"official_url":official_url or None,"auto_check":bool(auto_check)}.items(): setattr(device,k,v)
    if not device.installed_version: device.status="Версия не указана"
    db.add(device); db.commit(); return RedirectResponse("/",303)

@app.post("/devices/{device_id}/delete")
def delete_device(device_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf); device=db.get(Device,device_id)
    if not device: raise HTTPException(404)
    db.delete(device); db.commit(); return RedirectResponse("/",303)

@app.post("/devices/{device_id}/check")
async def run_check(device_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf); device=db.get(Device,device_id)
    if not device: raise HTTPException(404)
    if not device.catalog_model_id: device.status="Источник не настроен"; db.commit()
    else: await check_model_source(db,device.catalog_model)
    return RedirectResponse("/",303)

@app.post("/devices/{device_id}/connection")
async def connection(device_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf); device=db.get(Device,device_id)
    if not device: raise HTTPException(404)
    ok,message=await test_connection(device); return page(request,"message.html",title="Проверка подключения",message=message,ok=ok)

@app.post("/check-all")
async def check_all(request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf)
    for model_id in set(db.scalars(select(Device.catalog_model_id).where(Device.catalog_model_id.is_not(None))).all()):
        model=db.get(EquipmentModel,model_id)
        if model: await check_model_source(db,model)
    return RedirectResponse("/",303)

@app.get("/history",response_class=HTMLResponse)
def history(request:Request,db:Session=Depends(get_db)):
    return page(request,"history.html",rows=db.execute(select(CheckHistory,Device).join(Device).order_by(CheckHistory.checked_at.desc()).limit(500)).all())

@app.get("/profiles",response_class=HTMLResponse)
def profiles(request:Request,db:Session=Depends(get_db)): return page(request,"profiles.html",profiles=db.scalars(select(ConnectionProfile)).all())

@app.post("/profiles")
def add_profile(request:Request,csrf:str=Form(...),name:str=Form(...),method:str=Form(...),username:str=Form(""),secret:str=Form(...),snmp_version:str=Form("2c"),port:str=Form(""),db:Session=Depends(get_db)):
    verify(request,csrf); db.add(ConnectionProfile(name=name,method=method,username=username or None,secret_encrypted=encrypt_secret(secret),snmp_version=snmp_version,port=int(port) if port else None)); db.commit(); return RedirectResponse("/profiles",303)

@app.get("/notifications",response_class=HTMLResponse)
def notifications(request:Request): return page(request,"message.html",title="Уведомления",message="Почтовый модуль подготовлен. Настройка SMTP будет добавлена без хранения секретов в интерфейсе.",ok=True)
