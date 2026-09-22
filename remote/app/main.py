import ipaddress, json, logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .migrations import migrate_sqlite
from .models import ApplicationSetting, CheckHistory, ConnectionProfile, Device, EquipmentFolder, EquipmentModel, EquipmentVendor, FirmwareEvent, FirmwareSource, User, UserSession, now
from .polling import test_connection
from .schemas import DeviceCreate, DeviceOut
from .security import csrf_token, encrypt_secret, validate_public_url, validate_firmware_source_url
from .versioning import compare_for_vendor
from .firmware.service import check_model_source, latest_release
from .auth import SESSION_COOKIE, active_admin_count, audit, clear_login_failures, create_initial_admin, create_session, hash_password, login_allowed, normalize_username, rate_key, record_login_failure, revoke_session, session_user, token_hash, verify_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE/"templates")

async def scheduled_checks():
    with SessionLocal() as db:
        model_ids=set(db.scalars(select(Device.catalog_model_id).where(Device.auto_check.is_(True),Device.installed_version_source=="snmp",Device.catalog_model_id.is_not(None))).all())
        for model_id in model_ids:
            model=db.get(EquipmentModel,model_id)
            if model: await check_model_source(db,model)

def automation_config(db:Session):
    values={item.key:item.value for item in db.scalars(select(ApplicationSetting).where(ApplicationSetting.key.in_(("auto_check_enabled","auto_check_time")))).all()}
    return values.get("auto_check_enabled","true").lower()=="true",values.get("auto_check_time","08:00")

def configure_automation(app,enabled:bool,check_time:str):
    scheduler=app.state.scheduler
    if scheduler.get_job("firmware-checks"):scheduler.remove_job("firmware-checks")
    if enabled:
        hour,minute=(int(part) for part in check_time.split(":"))
        scheduler.add_job(scheduled_checks,"cron",hour=hour,minute=minute,max_instances=1,id="firmware-checks",replace_existing=True)

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    migrate_sqlite(engine)
    scheduler = AsyncIOScheduler()
    app.state.scheduler = scheduler
    with SessionLocal() as db:
        create_initial_admin(db)
        enabled,check_time=automation_config(db)
        configure_automation(app,enabled,check_time)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")

@app.middleware("http")
async def authentication(request:Request, call_next):
    if settings.auth_disabled or request.url.path=="/health" or request.url.path=="/login" or request.url.path.startswith("/static/"):
        request.state.user=None
        return await call_next(request)
    with SessionLocal() as db:
        user=session_user(db,request.cookies.get(SESSION_COOKIE))
    if not user:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error":"Требуется вход в систему"},status_code=401)
        return RedirectResponse("/login" if request.url.path=="/logout" else f"/login?next={request.url.path}",303)
    request.state.user=user
    password_change_allowed={"/change-password","/logout","/api/session/touch"}
    if user.must_change_password and request.url.path not in password_change_allowed:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error":"Необходимо сменить временный пароль"},status_code=403)
        return RedirectResponse("/change-password",303)
    admin_only=("/settings","/profiles","/users","/api/settings","/api/firmware-sources","/api/vendors","/api/models","/api/connection-profiles")
    viewer_allowed={"/logout","/api/session/touch","/change-password"}
    forbidden=user.role!="admin" and request.url.path not in viewer_allowed and (request.method not in {"GET","HEAD"} or request.url.path.startswith(admin_only) or (request.url.path.startswith("/devices/") and request.url.path.endswith("/edit")))
    if forbidden:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error":"Недостаточно прав"},status_code=403)
        return HTMLResponse("<h1>Недостаточно прав</h1><p>Это действие доступно только администратору.</p>",status_code=403)
    return await call_next(request)

def context(request, **extra):
    token = request.cookies.get("csrf") or csrf_token()
    scheduler = getattr(request.app.state, "scheduler", None); job = scheduler.get_job("firmware-checks") if scheduler and scheduler.running else None
    return {"request":request,"csrf":token,"current_user":getattr(request.state,"user",None),"auto_check_enabled":bool(job),"next_check":job.next_run_time if job else None,**extra}, token

def verify(request, token):
    if not token or token != request.cookies.get("csrf"): raise HTTPException(403,"Некорректный CSRF-токен")

def page(request, name, **extra):
    ctx, token = context(request, **extra); response = templates.TemplateResponse(request,name,ctx)
    response.set_cookie("csrf",token,httponly=True,samesite="strict",secure=settings.session_cookie_secure); return response

def valid_address(value: str) -> bool:
    try: return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError: return False

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request,error:str=""):
    if not settings.auth_disabled:
        with SessionLocal() as db:
            if session_user(db,request.cookies.get(SESSION_COOKIE)): return RedirectResponse("/",303)
    ctx,token=context(request,error=error)
    response=templates.TemplateResponse(request,"login.html",ctx)
    response.set_cookie("csrf",token,httponly=True,samesite="strict",secure=settings.session_cookie_secure)
    return response

@app.post("/login")
async def login(request:Request,username:str=Form(...),password:str=Form(...),csrf:str=Form(...),next:str=Form("/")):
    verify(request,csrf)
    key=rate_key(request.client.host if request.client else "unknown",username)
    if not login_allowed(key): return RedirectResponse("/login?error=Слишком+много+попыток.+Повторите+позже",303)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username==normalize_username(username)))
        if not user or not user.active or not verify_password(user.password_hash,password):
            record_login_failure(key)
            return RedirectResponse("/login?error=Неверный+логин+или+пароль",303)
        clear_login_failures(key)
        token=create_session(db,user)
    destination="/change-password" if user.must_change_password else (next if next.startswith("/") and not next.startswith("//") and next!="/logout" else "/")
    response=RedirectResponse(destination,303)
    response.set_cookie(SESSION_COOKIE,token,max_age=settings.session_lifetime_hours*3600,httponly=True,samesite="strict",secure=settings.session_cookie_secure)
    return response

@app.post("/logout")
def logout(request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf); revoke_session(db,request.cookies.get(SESSION_COOKIE))
    response=RedirectResponse("/login",303); response.delete_cookie(SESSION_COOKIE); return response

@app.post("/api/session/touch")
async def touch_session(request:Request):
    data=await request.json();verify(request,data.get("csrf"))
    return {"ok":True}

@app.get("/change-password",response_class=HTMLResponse)
def change_password_page(request:Request):
    if not request.state.user.must_change_password:return RedirectResponse("/",303)
    return page(request,"change_password.html",title="Смена пароля")

@app.post("/change-password")
def change_password(request:Request,password:str=Form(...),confirmation:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    verify(request,csrf);user=db.get(User,request.state.user.id)
    error=""
    if password!=confirmation:error="Пароли не совпадают"
    elif verify_password(user.password_hash,password):error="Новый пароль должен отличаться от временного"
    else:
        try:user.password_hash=hash_password(password)
        except ValueError as exc:error=str(exc)
    if error:return page(request,"change_password.html",title="Смена пароля",error=error)
    user.must_change_password=False
    current_hash=token_hash(request.cookies.get(SESSION_COOKIE,""))
    db.query(UserSession).filter(UserSession.user_id==user.id,UserSession.token_hash!=current_hash,UserSession.revoked_at.is_(None)).update({UserSession.revoked_at:now()})
    audit(db,user,"user.first_password_change",user.username);db.commit()
    return RedirectResponse("/",303)

def serialize(device: Device, db:Session|None=None) -> dict:
    release=latest_release(db,device.catalog_model_id) if db and device.catalog_model_id else None
    model=device.catalog_model
    if model and model.model_requires_clarification: release=None
    return DeviceOut(id=device.id,name=device.name,address=device.ip_address,vendor=device.vendor,model=device.model,hardware_revision=device.hardware_revision,folder_id=device.folder_id,acquisition_method=device.acquisition_method,version_source=device.installed_version_source,management_port=device.management_port,installed_version=device.installed_version,available_version=release.version if release else None,description=device.description,auto_check=device.auto_check,status=device.status,last_checked_at=device.last_checked_at.isoformat() if device.last_checked_at else None,latest_checked_at=model.latest_checked_at.isoformat() if model and model.latest_checked_at else None,latest_check_status=model.latest_check_status if model else "Источник не настроен",download_url=release.download_url if release else None,firmware_page_url=release.firmware_page_url if release else (model.firmware_page_url if model else None),changelog_url=release.changelog_url if release else None).model_dump()

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
        elif model.hardware_revision_required:
            allowed={value.upper() for revision in model.hardware_revisions if revision.enabled for value in (revision.display_revision,revision.provider_revision)}
            if (data.hardware_revision or "").upper() not in allowed:errors["hardware_revision"]="Выберите аппаратную ревизию из списка для этой модели"
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
    if data.folder_id is not None and not db.get(EquipmentFolder,data.folder_id): errors["folder_id"]="Каталог не найден"
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
    updates=[x for x in all_devices if x.status in update_statuses]; problems=[x for x in all_devices if x.status in attention_statuses-update_statuses]
    return page(request,"dashboard.html",devices=devices,counts=counts,attention=updates+problems,attention_updates=updates,attention_problems=problems,q=q,vendor=vendor,status=status)

@app.get("/api/devices",response_model=list[DeviceOut])
def api_devices(db:Session=Depends(get_db)): return [serialize(x,db) for x in db.scalars(select(Device).order_by(Device.name)).all()]

def vendor_json(v): return {"id":v.id,"name":v.name,"slug":v.slug,"enabled":v.enabled}
def model_json(m): return {"id":m.id,"vendor_id":m.vendor_id,"vendor":m.vendor.name,"name":m.name,"display_name":m.display_name or f"{m.vendor.name} {m.name}","normalized_name":m.normalized_name,"series":m.series,"firmware_family":m.firmware_family,"compatibility_group":m.compatibility_group,"product_page_url":m.product_page_url,"device_type":m.device_type,"installed_version_method":m.installed_version_method,"version_oid":m.version_oid,"firmware_source_id":m.firmware_source_id,"hardware_revision_required":m.hardware_revision_required,"hardware_revisions":[{"display_revision":r.display_revision,"provider_revision":r.provider_revision,"firmware_path":r.firmware_path} for r in m.hardware_revisions if r.enabled],"model_requires_clarification":m.model_requires_clarification,"support_status":m.support_status,"os_family":m.os_family,"architecture":m.architecture,"update_channel":m.update_channel,"enabled":m.enabled,"snmp_profile":json.loads(m.snmp_profile) if m.snmp_profile else None,"latest_check_status":m.latest_check_status,"latest_checked_at":m.latest_checked_at.isoformat() if m.latest_checked_at else None,"created_at":m.created_at.isoformat() if m.created_at else None,"updated_at":m.updated_at.isoformat() if m.updated_at else None}

def source_json(s,db):
    return {"id":s.id,"name":s.name,"vendor":s.vendor,"source_type":s.source_type,"base_url":s.base_url,"allowed_domains":[x.strip() for x in s.allowed_domains.split(',') if x.strip()],"config":json.loads(s.config or "{}"),"builtin":bool(s.builtin_provider),"enabled":s.enabled,"draft":s.draft,"last_status":s.last_status,"last_checked_at":s.last_checked_at.isoformat() if s.last_checked_at else None,"last_success_at":s.last_success_at.isoformat() if s.last_success_at else None,"models_count":db.scalar(select(func.count(EquipmentModel.id)).where(EquipmentModel.firmware_source_id==s.id)) or 0}

@app.get("/api/firmware-sources")
def api_firmware_sources(db:Session=Depends(get_db)): return [source_json(x,db) for x in db.scalars(select(FirmwareSource).order_by(FirmwareSource.vendor)).all()]

@app.post("/api/firmware-sources",status_code=201)
async def api_create_firmware_source(request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); url=str(data.get("base_url","")).strip()
    try: validate_firmware_source_url(url)
    except ValueError as exc: return JSONResponse(status_code=422,content={"errors":{"base_url":str(exc)}})
    domains=[str(x).strip().lower() for x in data.get("allowed_domains",[]) if str(x).strip()]
    from urllib.parse import urlparse
    if urlparse(url).hostname.lower() not in domains: return JSONResponse(status_code=422,content={"errors":{"allowed_domains":"Домен базового URL должен быть в списке разрешённых"}})
    source=FirmwareSource(name=str(data.get("name","")).strip(),vendor=str(data.get("vendor","")).strip(),source_type=str(data.get("source_type","https")),base_url=url,allowed_domains=','.join(domains),config=json.dumps(data.get("config") or {},ensure_ascii=False),enabled=False,draft=True,last_status="Черновик")
    if not source.name or not source.vendor: return JSONResponse(status_code=422,content={"errors":{"name":"Укажите название и производителя"}})
    db.add(source)
    try: db.commit()
    except IntegrityError: db.rollback(); return JSONResponse(status_code=422,content={"errors":{"name":"Источник с таким названием уже существует"}})
    db.refresh(source); return source_json(source,db)

@app.post("/api/firmware-sources/{source_id}/test")
async def api_test_firmware_source(source_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); source=db.get(FirmwareSource,source_id)
    if not source: raise HTTPException(404,"Источник не найден")
    try: validate_firmware_source_url(source.base_url)
    except ValueError as exc: source.last_status="Ошибка"; source.last_error=str(exc); source.last_checked_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc); db.commit(); return JSONResponse(status_code=422,content={"ok":False,"error":str(exc)})
    source.last_status="Конфигурация допустима"; source.last_error=None; source.last_checked_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc); db.commit(); db.refresh(source)
    return {"ok":True,"message":"Источник проверен","source":source_json(source,db)}

def folder_json(folder:EquipmentFolder,db:Session):
    return {"id":folder.id,"name":folder.name,"parent_id":folder.parent_id,"description":folder.description,"device_count":db.scalar(select(func.count(Device.id)).where(Device.folder_id==folder.id)) or 0,"child_count":db.scalar(select(func.count(EquipmentFolder.id)).where(EquipmentFolder.parent_id==folder.id)) or 0}

def folder_descendant_ids(db:Session,folder_id:int)->set[int]:
    result=set(); pending=[folder_id]
    while pending:
        children=set(db.scalars(select(EquipmentFolder.id).where(EquipmentFolder.parent_id.in_(pending))).all())-result
        result.update(children); pending=list(children)
    return result

def folder_subtree_height(db:Session,folder_id:int)->int:
    children=db.scalars(select(EquipmentFolder.id).where(EquipmentFolder.parent_id==folder_id)).all()
    return 1+max((folder_subtree_height(db,x) for x in children),default=0)

def validate_folder_parent(db:Session,parent_id:int|None,current_id:int|None=None):
    depth=1; seen=set()
    while parent_id is not None:
        if parent_id==current_id or parent_id in seen: raise HTTPException(422,"Нельзя переместить каталог внутрь самого себя")
        seen.add(parent_id); parent=db.get(EquipmentFolder,parent_id)
        if not parent: raise HTTPException(422,"Родительский каталог не найден")
        depth+=1
        if depth>5: raise HTTPException(422,"Допустимо не более пяти уровней каталогов")
        parent_id=parent.parent_id

@app.get("/api/folders")
def api_folders(db:Session=Depends(get_db)):
    return [folder_json(x,db) for x in db.scalars(select(EquipmentFolder).order_by(EquipmentFolder.name)).all()]

@app.post("/api/folders",status_code=201)
async def api_create_folder(request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); name=str(data.get("name","")).strip(); parent_id=data.get("parent_id")
    if not name: return JSONResponse(status_code=422,content={"errors":{"name":"Укажите название каталога"}})
    if len(name)>120 or any(char in name for char in "<>&"): return JSONResponse(status_code=422,content={"errors":{"name":"Название содержит недопустимые символы"}})
    validate_folder_parent(db,parent_id)
    duplicate=db.scalar(select(EquipmentFolder.id).where(EquipmentFolder.name==name,EquipmentFolder.parent_id==parent_id)) if parent_id is not None else db.scalar(select(EquipmentFolder.id).where(EquipmentFolder.name==name,EquipmentFolder.parent_id.is_(None)))
    if duplicate: return JSONResponse(status_code=422,content={"errors":{"name":"Каталог с таким названием уже существует"}})
    folder=EquipmentFolder(name=name,parent_id=parent_id,description=str(data.get("description","")).strip() or None); db.add(folder); db.commit(); db.refresh(folder); return folder_json(folder,db)

@app.patch("/api/folders/{folder_id}")
async def api_update_folder(folder_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); folder=db.get(EquipmentFolder,folder_id)
    if not folder: raise HTTPException(404,"Каталог не найден")
    name=str(data.get("name",folder.name)).strip(); parent_id=data.get("parent_id",folder.parent_id)
    if not name: return JSONResponse(status_code=422,content={"errors":{"name":"Укажите название каталога"}})
    if len(name)>120 or any(char in name for char in "<>&"): return JSONResponse(status_code=422,content={"errors":{"name":"Название содержит недопустимые символы"}})
    validate_folder_parent(db,parent_id,folder_id)
    parent_depth=0; current=parent_id
    while current is not None: parent_depth+=1; current=db.get(EquipmentFolder,current).parent_id
    if parent_depth+folder_subtree_height(db,folder_id)>5: raise HTTPException(422,"Допустимо не более пяти уровней каталогов")
    duplicate=db.scalar(select(EquipmentFolder.id).where(EquipmentFolder.id!=folder_id,EquipmentFolder.name==name,EquipmentFolder.parent_id==parent_id)) if parent_id is not None else db.scalar(select(EquipmentFolder.id).where(EquipmentFolder.id!=folder_id,EquipmentFolder.name==name,EquipmentFolder.parent_id.is_(None)))
    if duplicate: return JSONResponse(status_code=422,content={"errors":{"name":"Каталог с таким названием уже существует"}})
    folder.name=name; folder.parent_id=parent_id; db.commit(); db.refresh(folder); return folder_json(folder,db)

@app.delete("/api/folders/{folder_id}")
async def api_delete_folder(folder_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); folder=db.get(EquipmentFolder,folder_id)
    if not folder: raise HTTPException(404,"Каталог не найден")
    target_id=data.get("move_to_folder_id",folder.parent_id)
    if target_id is not None and not db.get(EquipmentFolder,target_id): raise HTTPException(404,"Целевой каталог не найден")
    if target_id==folder_id or target_id in folder_descendant_ids(db,folder_id): raise HTTPException(422,"Нельзя переместить содержимое в удаляемый каталог или его потомка")
    try:
        for child in db.scalars(select(EquipmentFolder).where(EquipmentFolder.parent_id==folder_id)).all():
            validate_folder_parent(db,target_id,child.id); child.parent_id=target_id
        for device in db.scalars(select(Device).where(Device.folder_id==folder_id)).all(): device.folder_id=target_id
        db.delete(folder); db.commit()
    except Exception: db.rollback(); raise
    return {"ok":True}

@app.post("/api/devices/move")
async def api_move_devices(request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); folder_id=data.get("folder_id"); ids=data.get("device_ids") or []
    if folder_id is not None and not db.get(EquipmentFolder,folder_id): raise HTTPException(404,"Каталог не найден")
    if not isinstance(ids,list) or not ids: return JSONResponse(status_code=422,content={"error":"Выберите оборудование"})
    devices=db.scalars(select(Device).where(Device.id.in_(ids))).all()
    if len(devices)!=len(set(ids)): raise HTTPException(404,"Часть устройств не найдена")
    for device in devices: device.folder_id=folder_id
    db.commit(); return {"ok":True,"moved":len(devices)}

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
    source_id=data.get("firmware_source_id")
    if source_id and not db.get(FirmwareSource,int(source_id)): return JSONResponse(status_code=422,content={"errors":{"firmware_source_id":"Источник не найден"}})
    method=str(data.get("installed_version_method","manual"))
    if method not in {"manual","snmp"}: return JSONResponse(status_code=422,content={"errors":{"installed_version_method":"Выберите способ получения версии"}})
    model=EquipmentModel(vendor_id=vendor_id,name=name,normalized_name=name.upper(),enabled=True,snmp_profile=None,device_type=str(data.get("device_type","")).strip() or None,firmware_source_id=int(source_id) if source_id else None,installed_version_method=method,version_oid=str(data.get("version_oid","")).strip() or None,latest_check_status="Источник не настроен" if not source_id else "Не проверялся"); db.add(model)
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

@app.post("/api/models/{model_id}/check-firmware")
async def api_check_model_firmware(model_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); model=db.get(EquipmentModel,model_id)
    if not model: raise HTTPException(404,"Модель не найдена")
    await check_model_source(db,model); db.refresh(model)
    release=latest_release(db,model.id)
    return {"ok":model.latest_check_status not in {"Ошибка проверки производителя","Источник не настроен","Требуется уточнить модель"},"message":f"Проверка завершена: {model.latest_check_status}","model":model_json(model),"latest_version":release.version if release else None}

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
    clarification=bool(catalog_model and catalog_model.model_requires_clarification)
    revision=None
    if catalog_model and data.hardware_revision:
        selected=next((r for r in catalog_model.hardware_revisions if data.hardware_revision.upper() in {r.display_revision.upper(),r.provider_revision.upper()}),None)
        revision=selected.display_revision if selected else None
    device=Device(name=data.name.strip(),ip_address=data.address.strip(),management_port=port,vendor=vendor_name,model=model_name,hardware_revision=revision,catalog_model_id=catalog_model.id if catalog_model else None,folder_id=data.folder_id,acquisition_method="manual" if manual else "snmp",version_source=data.version_source,installed_version_source=data.version_source,snmp_version=None if manual else data.snmp_version,snmp_port=data.snmp_port,snmpv3_username=data.snmpv3_username if not manual and data.snmp_version=="3" else None,security_level=data.security_level if not manual and data.snmp_version=="3" else None,auth_protocol=data.auth_protocol if not manual and data.snmp_version=="3" else None,privacy_protocol=data.privacy_protocol if not manual and data.snmp_version=="3" else None,credentials_encrypted=encrypted,installed_version=installed,available_version=None,description=(data.description or "").strip() or None,auto_check=False if manual or clarification else data.auto_check,status="Требуется уточнить модель" if clarification else "Проверка версии производителя")
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
    device.installed_version=installed; device.available_version=None; device.status=compare_for_vendor(device.vendor,installed,release.version) if release else "Источник не настроен"; db.commit(); db.refresh(device)
    return serialize(device,db)

@app.get("/devices/new",response_class=HTMLResponse)
@app.get("/devices/{device_id}/edit",response_class=HTMLResponse)
def device_form(request:Request,device_id:int|None=None,db:Session=Depends(get_db)):
    device=db.get(Device,device_id) if device_id else None; return page(request,"device_form.html",device=device,profiles=db.scalars(select(ConnectionProfile)).all())

@app.post("/devices/save")
def save_device(request:Request,csrf:str=Form(...),device_id:str=Form(""),name:str=Form(...),ip_address:str=Form(...),vendor:str=Form(...),model:str=Form(...),hardware_revision:str=Form(""),installed_version:str=Form(""),acquisition_method:str=Form(...),profile_id:str=Form(""),official_url:str=Form(""),description:str=Form(""),auto_check:str|None=Form(None),db:Session=Depends(get_db)):
    verify(request,csrf)
    if not valid_address(ip_address): raise HTTPException(422,"Некорректный IPv4-адрес")
    if official_url:
        try: validate_public_url(official_url)
        except ValueError as exc: raise HTTPException(422,str(exc))
    device=db.get(Device,int(device_id)) if device_id else Device()
    for k,v in {"name":name,"ip_address":ip_address,"vendor":vendor,"model":model,"hardware_revision":hardware_revision or None,"installed_version":installed_version or None,"acquisition_method":acquisition_method,"profile_id":int(profile_id) if profile_id else None,"official_url":official_url or None,"description":description.strip() or None,"auto_check":bool(auto_check)}.items(): setattr(device,k,v)
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

@app.get("/settings",response_class=HTMLResponse)
def settings_page(request:Request,tab:str="connections",db:Session=Depends(get_db)):
    allowed={"connections","sources","equipment","notifications","general"}; tab=tab if tab in allowed else "connections"
    profiles=db.scalars(select(ConnectionProfile).order_by(ConnectionProfile.name)).all(); sources=db.scalars(select(FirmwareSource).order_by(FirmwareSource.vendor)).all(); models=db.scalars(select(EquipmentModel).order_by(EquipmentModel.name)).all(); vendors=db.scalars(select(EquipmentVendor).order_by(EquipmentVendor.name)).all()
    profile_usage={p.id:db.scalar(select(func.count(Device.id)).where(Device.profile_id==p.id)) or 0 for p in profiles}
    auto_enabled,auto_time=automation_config(db)
    return page(request,"profiles.html",tab=tab,profiles=profiles,profile_usage=profile_usage,sources=sources,models=models,vendors=vendors,automation_enabled=auto_enabled,automation_time=auto_time)

@app.post("/api/settings/automation")
async def api_save_automation(request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"))
    enabled=data.get("enabled")
    check_time=str(data.get("time","")).strip()
    if not isinstance(enabled,bool):return JSONResponse(status_code=422,content={"error":"Укажите состояние автоматической проверки"})
    if len(check_time)!=5 or check_time[2] != ":":return JSONResponse(status_code=422,content={"error":"Укажите время в формате ЧЧ:ММ"})
    try:hour,minute=(int(part) for part in check_time.split(":"))
    except ValueError:return JSONResponse(status_code=422,content={"error":"Укажите корректное время"})
    if not 0<=hour<=23 or not 0<=minute<=59:return JSONResponse(status_code=422,content={"error":"Укажите корректное время"})
    for key,value in (("auto_check_enabled","true" if enabled else "false"),("auto_check_time",check_time)):
        item=db.get(ApplicationSetting,key)
        if item:item.value=value
        else:db.add(ApplicationSetting(key=key,value=value))
    db.commit();configure_automation(request.app,enabled,check_time)
    job=request.app.state.scheduler.get_job("firmware-checks")
    return {"ok":True,"enabled":enabled,"time":check_time,"next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None,"message":"Настройки автопроверки сохранены"}

@app.get("/profiles",response_class=HTMLResponse)
def profiles(request:Request): return RedirectResponse("/settings?tab=connections",307)

@app.post("/profiles")
def add_profile(request:Request,csrf:str=Form(...),name:str=Form(...),method:str=Form("snmp"),username:str=Form(""),secret:str=Form(...),snmp_version:str=Form("2c"),port:str=Form("161"),timeout_seconds:int=Form(5),retries:int=Form(1),db:Session=Depends(get_db)):
    verify(request,csrf); db.add(ConnectionProfile(name=name,method="snmp",username=username or None if snmp_version=="3" else None,secret_encrypted=encrypt_secret(secret),snmp_version=snmp_version,port=int(port),timeout_seconds=timeout_seconds,retries=retries)); db.commit(); return RedirectResponse("/settings?tab=connections",303)

@app.delete("/api/connection-profiles/{profile_id}")
async def api_delete_connection_profile(profile_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json(); verify(request,data.get("csrf")); profile=db.get(ConnectionProfile,profile_id)
    if not profile: raise HTTPException(404,"Профиль подключения не найден")
    used=db.scalar(select(func.count(Device.id)).where(Device.profile_id==profile_id)) or 0
    if used:return JSONResponse(status_code=409,content={"error":f"Невозможно удалить профиль: он используется устройствами — {used}. Сначала назначьте им другой профиль."})
    db.delete(profile);db.commit();return {"ok":True,"message":"Профиль подключения удалён"}

@app.get("/notifications",response_class=HTMLResponse)
def notifications(request:Request,kind:str="all",db:Session=Depends(get_db)):
    allowed={"all","updates","errors","system"};kind=kind if kind in allowed else "all"
    monitored_models=select(Device.catalog_model_id).where(Device.catalog_model_id.is_not(None))
    stmt=select(FirmwareEvent).where(FirmwareEvent.model_id.in_(monitored_models)).order_by(FirmwareEvent.created_at.desc(),FirmwareEvent.id.desc())
    if kind!="all":stmt=stmt.where(FirmwareEvent.category==kind)
    events=db.scalars(stmt.limit(500)).all();model_ids={e.model_id for e in events}
    models={m.id:m for m in db.scalars(select(EquipmentModel).where(EquipmentModel.id.in_(model_ids))).all()} if model_ids else {}
    devices={mid:db.scalar(select(Device).where(Device.catalog_model_id==mid).order_by(Device.name)) for mid in model_ids}
    total_events=db.scalar(select(func.count(FirmwareEvent.id)).where(FirmwareEvent.model_id.in_(monitored_models))) or 0
    unread=db.scalar(select(func.count(FirmwareEvent.id)).where(FirmwareEvent.read_at.is_(None),FirmwareEvent.model_id.in_(monitored_models))) or 0
    read_events=total_events-unread
    return page(request,"message.html",events=events,models=models,devices=devices,kind=kind,unread=unread,total_events=total_events,read_events=read_events)

@app.post("/api/notifications/read-all")
async def notifications_read_all(request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));db.execute(update(FirmwareEvent).where(FirmwareEvent.read_at.is_(None)).values(read_at=now()));db.commit();return {"ok":True,"message":"Все уведомления отмечены прочитанными"}

@app.delete("/api/notifications/clear-read")
async def notifications_clear_read(request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));result=db.execute(delete(FirmwareEvent).where(FirmwareEvent.read_at.is_not(None)));db.commit();return {"ok":True,"deleted":result.rowcount,"message":"Прочитанные уведомления очищены"}

@app.post("/api/notifications/{event_id}/read")
async def notification_read(event_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));event=db.get(FirmwareEvent,event_id)
    if not event:raise HTTPException(404,"Уведомление не найдено")
    event.read_at=now();db.commit();return {"ok":True}

@app.delete("/api/notifications/{event_id}")
async def notification_delete(event_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));event=db.get(FirmwareEvent,event_id)
    if not event:raise HTTPException(404,"Уведомление не найдено")
    db.delete(event);db.commit();return {"ok":True,"message":"Уведомление удалено"}

@app.get("/users",response_class=HTMLResponse)
def users_page(request:Request,db:Session=Depends(get_db)):
    return page(request,"users.html",title="Пользователи",users=db.scalars(select(User).order_by(User.username)).all(),active_admins=active_admin_count(db))

def user_payload(user:User):
    return {"id":user.id,"username":user.username,"display_name":user.display_name,"role":user.role,"active":user.active,"last_login_at":user.last_login_at.isoformat() if user.last_login_at else None}

@app.post("/api/users",status_code=201)
async def create_user(request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));username=normalize_username(str(data.get("username","")));display_name=str(data.get("display_name","")).strip();role=str(data.get("role","viewer"));password=str(data.get("password",""));errors={}
    if not username or len(username)>80:errors["username"]="Укажите корректный логин"
    if not display_name or len(display_name)>120:errors["display_name"]="Укажите имя пользователя"
    if role not in {"admin","viewer"}:errors["role"]="Выберите роль"
    if db.scalar(select(User).where(User.username==username)):errors["username"]="Такой логин уже используется"
    try:password_hash=hash_password(password)
    except ValueError as exc:errors["password"]=str(exc);password_hash=""
    if errors:return JSONResponse({"errors":errors},422)
    must_change_password=bool(data.get("must_change_password",False))
    user=User(username=username,display_name=display_name,password_hash=password_hash,role=role,active=True,must_change_password=must_change_password);db.add(user);audit(db,request.state.user,"user.create",username,f"role={role}; must_change_password={must_change_password}");db.commit();db.refresh(user);return user_payload(user)

@app.patch("/api/users/{user_id}")
async def update_user(user_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));user=db.get(User,user_id)
    if not user:raise HTTPException(404,"Пользователь не найден")
    role=data.get("role",user.role);active=bool(data.get("active",user.active))
    if role not in {"admin","viewer"}:return JSONResponse({"error":"Некорректная роль"},422)
    if user.role=="admin" and role!="admin":return JSONResponse({"error":"Роль администратора нельзя изменить"},409)
    if user.role=="admin" and user.active and (role!="admin" or not active) and active_admin_count(db)<=1:return JSONResponse({"error":"Нельзя заблокировать или понизить последнего активного администратора"},409)
    if user.id==request.state.user.id and not active:return JSONResponse({"error":"Нельзя заблокировать собственную учётную запись"},409)
    user.role=role;user.active=active
    if "display_name" in data:
        name=str(data["display_name"]).strip()
        if not name:return JSONResponse({"error":"Имя не может быть пустым"},422)
        user.display_name=name[:120]
    db.query(UserSession).filter(UserSession.user_id==user.id,UserSession.revoked_at.is_(None)).update({UserSession.revoked_at:now()})
    audit(db,request.state.user,"user.update",user.username,f"role={role}; active={active}");db.commit();db.refresh(user);return user_payload(user)

@app.post("/api/users/{user_id}/reset-password")
async def reset_user_password(user_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));user=db.get(User,user_id)
    if not user:raise HTTPException(404,"Пользователь не найден")
    try:user.password_hash=hash_password(str(data.get("password","")))
    except ValueError as exc:return JSONResponse({"error":str(exc)},422)
    db.query(UserSession).filter(UserSession.user_id==user.id,UserSession.revoked_at.is_(None)).update({UserSession.revoked_at:now()})
    audit(db,request.state.user,"user.password_reset",user.username);db.commit();return {"ok":True}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id:int,request:Request,db:Session=Depends(get_db)):
    data=await request.json();verify(request,data.get("csrf"));user=db.get(User,user_id)
    if not user:raise HTTPException(404,"Пользователь не найден")
    if user.id==request.state.user.id:return JSONResponse({"error":"Нельзя удалить собственную учётную запись"},409)
    if user.role=="admin" and user.active and active_admin_count(db)<=1:return JSONResponse({"error":"Нельзя удалить последнего активного администратора"},409)
    username=user.username;db.delete(user);audit(db,request.state.user,"user.delete",username);db.commit();return {"ok":True}
