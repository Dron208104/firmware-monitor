from sqlalchemy import bindparam, inspect, text

COLUMNS = {
    "management_port": "INTEGER NOT NULL DEFAULT 161",
    "description": "TEXT",
    "snmp_version": "VARCHAR(10)",
    "snmp_port": "INTEGER NOT NULL DEFAULT 161",
    "snmpv3_username": "VARCHAR(120)",
    "security_level": "VARCHAR(30)",
    "auth_protocol": "VARCHAR(20)",
    "privacy_protocol": "VARCHAR(20)",
    "credentials_encrypted": "TEXT",
    "catalog_model_id": "INTEGER",
    "folder_id": "INTEGER",
    "version_source": "VARCHAR(20) NOT NULL DEFAULT 'snmp'",
    "installed_version_source": "VARCHAR(20) NOT NULL DEFAULT 'snmp'",
}

MODEL_COLUMNS = {
    "display_name": "VARCHAR(180)",
    "series": "VARCHAR(120)",
    "model_requires_clarification": "BOOLEAN NOT NULL DEFAULT 0",
    "hardware_revision_required": "BOOLEAN NOT NULL DEFAULT 0",
    "os_family": "VARCHAR(40)",
    "architecture": "VARCHAR(40)",
    "update_channel": "VARCHAR(30)",
    "firmware_page_url": "TEXT",
    "product_page_url": "TEXT",
    "firmware_family": "VARCHAR(120)",
    "compatibility_group": "VARCHAR(180)",
    "firmware_filename_pattern": "TEXT",
    "version_pattern": "TEXT",
    "changelog_url": "TEXT",
    "download_rule": "TEXT",
    "support_status": "VARCHAR(30) NOT NULL DEFAULT 'supported'",
    "firmware_provider": "VARCHAR(40)",
    "model_aliases": "TEXT",
    "parsing_parameters": "TEXT",
    "latest_check_status": "VARCHAR(60) NOT NULL DEFAULT 'Источник не настроен'",
    "latest_checked_at": "DATETIME",
    "latest_check_error": "TEXT",
    "firmware_source_id": "INTEGER",
    "device_type": "VARCHAR(60)",
    "installed_version_method": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
    "version_oid": "VARCHAR(255)",
    "installed_version_pattern": "TEXT",
    "source_path": "TEXT",
    "firmware_file_pattern": "TEXT",
    "latest_version_pattern": "TEXT",
    "version_comparator": "VARCHAR(40) NOT NULL DEFAULT 'numeric'",
}
PROFILE_COLUMNS={"timeout_seconds":"INTEGER NOT NULL DEFAULT 5","retries":"INTEGER NOT NULL DEFAULT 1","enabled":"BOOLEAN NOT NULL DEFAULT 1","security_level":"VARCHAR(30)","auth_protocol":"VARCHAR(20)","privacy_protocol":"VARCHAR(20)"}
RELEASE_COLUMNS = {"changelog_url":"TEXT","file_size":"INTEGER","normalized_version":"VARCHAR(120)","release_suffix":"VARCHAR(30)","provider_revision":"VARCHAR(30)"}
SOURCE_COLUMNS = {"last_success_at":"DATETIME"}
EVENT_COLUMNS={"device_id":"INTEGER","category":"VARCHAR(30) NOT NULL DEFAULT 'updates'","old_version":"VARCHAR(120)","new_version":"VARCHAR(120)","description":"TEXT","read_at":"DATETIME","dedupe_key":"VARCHAR(255)","severity":"VARCHAR(20) NOT NULL DEFAULT 'info'","email_reminders_sent":"INTEGER NOT NULL DEFAULT 0","last_email_reminder_at":"DATETIME"}

def migrate_sqlite(engine):
    if engine.dialect.name != "sqlite": return
    existing = {column["name"] for column in inspect(engine).get_columns("devices")}
    model_existing = {column["name"] for column in inspect(engine).get_columns("equipment_models")}
    release_existing = {column["name"] for column in inspect(engine).get_columns("firmware_releases")}
    profile_existing = {column["name"] for column in inspect(engine).get_columns("connection_profiles")}
    source_existing = {column["name"] for column in inspect(engine).get_columns("firmware_sources")}
    event_existing = {column["name"] for column in inspect(engine).get_columns("firmware_events")}
    session_existing = {column["name"] for column in inspect(engine).get_columns("user_sessions")} if "user_sessions" in inspect(engine).get_table_names() else set()
    user_existing = {column["name"] for column in inspect(engine).get_columns("users")} if "users" in inspect(engine).get_table_names() else set()
    with engine.begin() as connection:
        for name, definition in COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE devices ADD COLUMN {name} {definition}"))
        for name, definition in MODEL_COLUMNS.items():
            if name not in model_existing:
                connection.execute(text(f"ALTER TABLE equipment_models ADD COLUMN {name} {definition}"))
        for name, definition in RELEASE_COLUMNS.items():
            if name not in release_existing: connection.execute(text(f"ALTER TABLE firmware_releases ADD COLUMN {name} {definition}"))
        for name, definition in PROFILE_COLUMNS.items():
            if name not in profile_existing: connection.execute(text(f"ALTER TABLE connection_profiles ADD COLUMN {name} {definition}"))
        for name, definition in SOURCE_COLUMNS.items():
            if name not in source_existing: connection.execute(text(f"ALTER TABLE firmware_sources ADD COLUMN {name} {definition}"))
        for name, definition in EVENT_COLUMNS.items():
            if name not in event_existing: connection.execute(text(f"ALTER TABLE firmware_events ADD COLUMN {name} {definition}"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_firmware_events_dedupe_key ON firmware_events(dedupe_key)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS model_hardware_revisions (id INTEGER PRIMARY KEY,equipment_model_id INTEGER NOT NULL REFERENCES equipment_models(id),display_revision VARCHAR(30) NOT NULL,provider_revision VARCHAR(30) NOT NULL,firmware_path TEXT,enabled BOOLEAN NOT NULL DEFAULT 1,CONSTRAINT uq_model_hardware_revision UNIQUE(equipment_model_id,display_revision))"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_model_hardware_revisions_model ON model_hardware_revisions(equipment_model_id)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS application_settings (key VARCHAR(80) PRIMARY KEY,value TEXT NOT NULL,updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY,username VARCHAR(80) NOT NULL UNIQUE,display_name VARCHAR(120) NOT NULL,password_hash TEXT NOT NULL,role VARCHAR(20) NOT NULL DEFAULT 'viewer',active BOOLEAN NOT NULL DEFAULT 1,must_change_password BOOLEAN NOT NULL DEFAULT 0,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,last_login_at DATETIME)"))
        if user_existing and "must_change_password" not in user_existing:
            connection.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS user_sessions (id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,token_hash VARCHAR(64) NOT NULL UNIQUE,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,expires_at DATETIME NOT NULL,revoked_at DATETIME)"))
        if session_existing and "last_seen_at" not in session_existing:
            connection.execute(text("ALTER TABLE user_sessions ADD COLUMN last_seen_at DATETIME"))
            connection.execute(text("UPDATE user_sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE last_seen_at IS NULL"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash ON user_sessions(token_hash)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions(user_id)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS user_folder_access (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,folder_id INTEGER NOT NULL REFERENCES equipment_folders(id) ON DELETE CASCADE,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,folder_id))"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_folder_access_folder_id ON user_folder_access(folder_id)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS admin_audit_log (id INTEGER PRIMARY KEY,actor_user_id INTEGER REFERENCES users(id),action VARCHAR(80) NOT NULL,target VARCHAR(160) NOT NULL,details TEXT,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_audit_actor ON admin_audit_log(actor_user_id)"))
        connection.execute(text("INSERT OR IGNORE INTO application_settings(key,value) VALUES ('auto_check_enabled','true')"))
        connection.execute(text("INSERT OR IGNORE INTO application_settings(key,value) VALUES ('auto_check_time','08:00')"))
        for source in (
            {"name":"QTECH Official","vendor":"QTECH","provider":"qtech","url":"https://ftp.qtech.ru/","domains":"ftp.qtech.ru"},
            {"name":"MikroTik Official","vendor":"MikroTik","provider":"mikrotik","url":"https://mikrotik.com/download/","domains":"mikrotik.com,download.mikrotik.com"},
        ):
            connection.execute(text("INSERT OR IGNORE INTO firmware_sources(name,vendor,source_type,base_url,allowed_domains,config,builtin_provider,enabled,draft,last_status,created_at,updated_at) VALUES (:name,:vendor,'builtin',:url,:domains,'{}',:provider,1,0,'Готов',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),source)
        connection.execute(text("UPDATE equipment_models SET firmware_source_id=(SELECT id FROM firmware_sources WHERE builtin_provider=equipment_models.firmware_provider) WHERE firmware_provider IN ('qtech','mikrotik') AND firmware_source_id IS NULL"))
        connection.execute(text("INSERT OR IGNORE INTO firmware_sources(name,vendor,source_type,base_url,allowed_domains,config,builtin_provider,enabled,draft,last_status,created_at,updated_at) VALUES ('Eltex Official','Eltex','builtin','https://eltex.ru/product/kommutator_dostupa_mes2428p/','eltex-co.ru,eltex-co.com,eltex.ru,api.prod.eltex-co.ru','{}','eltex',1,0,'Требуется проверка',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT OR IGNORE INTO firmware_sources(name,vendor,source_type,base_url,allowed_domains,config,builtin_provider,enabled,draft,last_status,created_at,updated_at) VALUES ('D-Link Official','D-Link','builtin','https://ftp.dlink.ru/pub/Switch/','ftp.dlink.ru','{}','d-link',1,0,'Требуется проверка',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("UPDATE firmware_sources SET base_url='https://eltex.ru/product/kommutator_dostupa_mes2428p/' WHERE builtin_provider='eltex'"))
        connection.execute(text("UPDATE firmware_sources SET base_url='https://ftp.dlink.ru/pub/Switch/',allowed_domains='ftp.dlink.ru' WHERE builtin_provider='d-link'"))
        connection.execute(text("UPDATE equipment_models SET series='MES24xx',firmware_provider='eltex',firmware_page_url='https://eltex.ru/product/kommutator_dostupa_mes2428p/',firmware_source_id=(SELECT id FROM firmware_sources WHERE builtin_provider='eltex'),latest_check_status=CASE WHEN latest_check_status IN ('Прошивка не найдена','Ошибка проверки производителя') THEN 'Требуется проверка' ELSE latest_check_status END WHERE normalized_name='MES2428P' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='eltex')"))
        connection.execute(text("UPDATE equipment_models SET series='DGS-1100',hardware_revision_required=1,firmware_provider='d-link',firmware_page_url='https://ftp.dlink.ru/pub/Switch/',firmware_source_id=(SELECT id FROM firmware_sources WHERE builtin_provider='d-link'),parsing_parameters='{\"provider_revision\":\"REVA\"}',latest_check_status=CASE WHEN latest_check_status IN ('Прошивка не найдена','Ошибка проверки производителя') THEN 'Требуется проверка' ELSE latest_check_status END WHERE normalized_name='DGS-1100-08V2' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='d-link')"))
        connection.execute(text("UPDATE devices SET installed_version_source=version_source WHERE version_source IN ('snmp','manual')"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_devices_ip ON devices(ip_address)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_devices_catalog_model_id ON devices(catalog_model_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_devices_folder_id ON devices(folder_id)"))
        for name, slug, model in (("QTECH","qtech","QSW-4610-28T-AC"),("Eltex","eltex","MES2428P"),("D-Link","d-link","DGS-1100-08V2")):
            connection.execute(text("INSERT OR IGNORE INTO equipment_vendors(name,slug,enabled) VALUES (:name,:slug,1)"),{"name":name,"slug":slug})
            vendor_id=connection.execute(text("SELECT id FROM equipment_vendors WHERE slug=:slug"),{"slug":slug}).scalar_one()
            connection.execute(text("INSERT INTO equipment_models(vendor_id,name,normalized_name,enabled,snmp_profile,model_requires_clarification,hardware_revision_required,installed_version_method,version_comparator,latest_check_status,created_at,updated_at) VALUES (:vendor_id,:name,:normalized,1,NULL,0,0,'manual','numeric','Источник не настроен',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) ON CONFLICT(vendor_id,normalized_name) DO NOTHING"),{"vendor_id":vendor_id,"name":model,"normalized":model.upper()})
        connection.execute(text("UPDATE equipment_models SET firmware_provider='qtech', firmware_page_url='https://ftp.qtech.ru/Switch/Access/QSW-4610/Firmware/QSW-4610-28T-AC/' WHERE normalized_name='QSW-4610-28T-AC' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='qtech')"))
        qtech_id=connection.execute(text("SELECT id FROM equipment_vendors WHERE slug='qtech'")).scalar_one()
        qtech_models=(
            ("QSW-3750-10","QSW-3750",None,None),
            ("QSW-3750-28","QSW-3750",None,None),
            ("QSW-4530-56","QSW-4530","https://ftp.qtech.ru/Switch/Access/QSW-4530/Firmware/",'{"version_rule":"numeric-8.x"}'),
            ("QSW-4610","QSW-4610","https://ftp.qtech.ru/Switch/Access/QSW-4610/Firmware/",'{"version_rule":"numeric-8.x"}'),
            ("QSW-4700-52","QSW-4700","https://ftp.qtech.ru/Switch/Access/QSW-4700/Firmware/",'{"version_rule":"os12","comparison_enabled":false}'),
            ("QSW-6910-28","QSW-6910","https://ftp.qtech.ru/Switch/Aggregation/QSW-6910/Firmware/",'{"version_rule":"os12","comparison_enabled":false}'),
        )
        for model_name,series,url,parameters in qtech_models:
            connection.execute(text("INSERT OR IGNORE INTO equipment_models(vendor_id,name,normalized_name,series,model_requires_clarification,enabled,snmp_profile,firmware_provider,firmware_page_url,parsing_parameters,latest_check_status,created_at,updated_at) VALUES (:vendor_id,:name,:normalized,:series,1,1,NULL,:provider,:url,:parameters,'Требуется уточнить модель',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"vendor_id":qtech_id,"name":model_name,"normalized":model_name.upper(),"series":series,"provider":"qtech" if url else None,"url":url,"parameters":parameters})
        connection.execute(text("UPDATE equipment_models SET series='QSW-4610', model_requires_clarification=0 WHERE vendor_id=:vendor_id AND normalized_name='QSW-4610-28T-AC'"),{"vendor_id":qtech_id})
        corrections=(
            ("QSW-4700-52","QSW-4700-52TX","QSW-4700","https://ftp.qtech.ru/Switch/Access/QSW-4700/Firmware/",'{"version_rule":"os12","comparison_enabled":false}'),
            ("QSW-4530-56","QSW-4530-54TX","QSW-4530","https://ftp.qtech.ru/Switch/Access/QSW-4530/Firmware/",'{"version_rule":"numeric-8.x"}'),
            ("QSW-3750-10","QSW-3750-10T-AC-R","QSW-3750","https://ftp.qtech.ru/Switch/Access/QSW-3750-R/Firmware/QSW-3750-10T-AC-R/",'{"version_rule":"numeric-8.x"}'),
            ("QSW-4610","QSW-4610-10T-POE-AC","QSW-4610","https://ftp.qtech.ru/Switch/Access/QSW-4610/Firmware/QSW-4610-10T-POE-AC/",'{"version_rule":"numeric-8.x"}'),
        )
        for old_name,new_name,series,url,parameters in corrections:
            old_id=connection.execute(text("SELECT id FROM equipment_models WHERE vendor_id=:vendor AND normalized_name=:name"),{"vendor":qtech_id,"name":old_name}).scalar()
            target_id=connection.execute(text("SELECT id FROM equipment_models WHERE vendor_id=:vendor AND normalized_name=:name"),{"vendor":qtech_id,"name":new_name}).scalar()
            if old_id and not target_id:
                connection.execute(text("UPDATE equipment_models SET name=:new,normalized_name=:new,series=:series,model_requires_clarification=0,firmware_provider='qtech',firmware_page_url=:url,parsing_parameters=:parameters WHERE id=:id"),{"new":new_name,"series":series,"url":url,"parameters":parameters,"id":old_id})
            elif old_id and target_id and old_id!=target_id:
                connection.execute(text("UPDATE devices SET catalog_model_id=:target,model=:new WHERE catalog_model_id=:old"),{"target":target_id,"new":new_name,"old":old_id})
                connection.execute(text("DELETE FROM equipment_models WHERE id=:old"),{"old":old_id})
            connection.execute(text("UPDATE equipment_models SET model_requires_clarification=0,series=:series,firmware_provider='qtech',firmware_page_url=:url,parsing_parameters=:parameters WHERE vendor_id=:vendor AND normalized_name=:new"),{"series":series,"url":url,"parameters":parameters,"vendor":qtech_id,"new":new_name})
        final_corrections=(
            ("QSW-3750-28","QSW-3750-28T-AC-R","QSW-3750","https://ftp.qtech.ru/Switch/Access/QSW-3750-R/Firmware/QSW-3750-28T-AC-R/",'{"version_rule":"numeric-8.x"}'),
            ("QSW-6910-28","QSW-6910-26F","QSW-6910","https://ftp.qtech.ru/Switch/Aggregation/QSW-6910/Firmware/",'{"version_rule":"os12","comparison_enabled":false}'),
        )
        for old_name,new_name,series,url,parameters in final_corrections:
            old_id=connection.execute(text("SELECT id FROM equipment_models WHERE vendor_id=:vendor AND normalized_name=:name"),{"vendor":qtech_id,"name":old_name}).scalar()
            target_id=connection.execute(text("SELECT id FROM equipment_models WHERE vendor_id=:vendor AND normalized_name=:name"),{"vendor":qtech_id,"name":new_name}).scalar()
            if old_id and not target_id:
                connection.execute(text("UPDATE equipment_models SET name=:new,normalized_name=:new,series=:series,model_requires_clarification=0,firmware_provider='qtech',firmware_page_url=:url,parsing_parameters=:parameters WHERE id=:id"),{"new":new_name,"series":series,"url":url,"parameters":parameters,"id":old_id})
            elif old_id and target_id and old_id!=target_id:
                connection.execute(text("UPDATE devices SET catalog_model_id=:target,model=:new WHERE catalog_model_id=:old"),{"target":target_id,"new":new_name,"old":old_id})
                connection.execute(text("DELETE FROM equipment_models WHERE id=:old"),{"old":old_id})
            connection.execute(text("UPDATE equipment_models SET model_requires_clarification=0,series=:series,firmware_provider='qtech',firmware_page_url=:url,parsing_parameters=:parameters WHERE vendor_id=:vendor AND normalized_name=:new"),{"series":series,"url":url,"parameters":parameters,"vendor":qtech_id,"new":new_name})

        exact_qtech_models=("QSW-3750-10T-AC-R","QSW-3750-28T-AC-R","QSW-4530-54TX","QSW-4610-10T-POE-AC","QSW-4610-28T-AC","QSW-4700-52TX","QSW-6910-26F")
        exact_models_parameter=bindparam("exact_models",expanding=True)
        model_cleanup=text("UPDATE equipment_models SET model_requires_clarification=0,latest_check_status=CASE WHEN latest_check_status='Требуется уточнить модель' THEN 'Не проверялся' ELSE latest_check_status END,latest_check_error=CASE WHEN latest_check_status='Требуется уточнить модель' THEN NULL ELSE latest_check_error END,latest_checked_at=CASE WHEN latest_check_status='Требуется уточнить модель' THEN NULL ELSE latest_checked_at END WHERE vendor_id=:vendor AND normalized_name IN :exact_models").bindparams(exact_models_parameter)
        device_cleanup=text("UPDATE devices SET status='Требуется проверка' WHERE status='Требуется уточнить модель' AND catalog_model_id IN (SELECT id FROM equipment_models WHERE vendor_id=:vendor AND normalized_name IN :exact_models)").bindparams(exact_models_parameter)
        parameters={"vendor":qtech_id,"exact_models":exact_qtech_models}
        connection.execute(model_cleanup,parameters)
        connection.execute(device_cleanup,parameters)
        connection.execute(text("UPDATE equipment_models SET installed_version_method='snmp',version_oid='1.3.6.1.4.1.27514.1.1.10.2.1.1.2.0',installed_version_pattern=NULL WHERE vendor_id=:vendor AND normalized_name='QSW-4700-52TX'"),{"vendor":qtech_id})
        connection.execute(text("INSERT OR IGNORE INTO equipment_vendors(name,slug,enabled) VALUES ('MikroTik','mikrotik',1)"))
        mikrotik_id=connection.execute(text("SELECT id FROM equipment_vendors WHERE slug='mikrotik'")).scalar_one()
        for model_name in ("RB4011iGS+RM","RB4011iGS+5HacQ2HnD-IN"):
            connection.execute(text("INSERT OR IGNORE INTO equipment_models(vendor_id,name,normalized_name,series,model_requires_clarification,os_family,architecture,update_channel,enabled,snmp_profile,latest_check_status,created_at,updated_at) VALUES (:vendor,:name,:normalized,'RB4011',0,'routeros','arm','long-term',1,NULL,'Источник не настроен',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"vendor":mikrotik_id,"name":model_name,"normalized":model_name.upper()})
        connection.execute(text("UPDATE equipment_models SET update_channel='long-term',firmware_provider='mikrotik', firmware_page_url='https://mikrotik.com/download/routeros?architecture=arm&channel=longTerm', parsing_parameters='{\"channel\":\"longTerm\"}' WHERE vendor_id=:vendor AND normalized_name IN ('RB4011IGS+RM','RB4011IGS+5HACQ2HND-IN')"),{"vendor":mikrotik_id})

        for provider,official_name in (("qtech","QTECH Official"),("mikrotik","MikroTik Official")):
            canonical=connection.execute(text("SELECT MIN(id) FROM firmware_sources WHERE builtin_provider=:provider"),{"provider":provider}).scalar()
            connection.execute(text("UPDATE equipment_models SET firmware_source_id=:canonical WHERE firmware_source_id IN (SELECT id FROM firmware_sources WHERE builtin_provider=:provider)"),{"canonical":canonical,"provider":provider})
            connection.execute(text("DELETE FROM firmware_sources WHERE builtin_provider=:provider AND id!=:canonical"),{"provider":provider,"canonical":canonical})
            connection.execute(text("UPDATE firmware_sources SET name=:name WHERE id=:canonical"),{"name":official_name,"canonical":canonical})
        connection.execute(text("UPDATE firmware_sources SET base_url='https://eltex.ru/',allowed_domains='eltex.ru,www.eltex.ru,eltex-co.ru,www.eltex-co.ru,eltex-co.com,www.eltex-co.com,api.prod.eltex-co.ru,docs.eltex-co.ru' WHERE builtin_provider='eltex'"))
        connection.execute(text("UPDATE firmware_sources SET base_url='https://ftp.dlink.ru/pub/Switch/',allowed_domains='dlink.com,support.dlink.com,dlink.ru,www.dlink.ru,support.d-link.ru,ftp.dlink.ru' WHERE builtin_provider='d-link'"))
        connection.execute(text("INSERT OR IGNORE INTO firmware_sources(name,vendor,source_type,base_url,allowed_domains,config,builtin_provider,enabled,draft,last_status,created_at,updated_at) VALUES ('Zyxel Official','Zyxel','builtin','https://www.zyxel.com/','zyxel.com,www.zyxel.com,download.zyxel.com,community.zyxel.com','{}','zyxel',1,0,'Требуется проверка',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))

        vendor_models={
            "eltex":(
                ("MES2300B-48","Eltex MES2300B-48","Коммутатор доступа","MES2300B","MES2300B-48","https://eltex.ru/product/kommutator_dostupa_mes2300b-48/","supported"),
                ("MES3400-24","Eltex MES3400-24","Коммутатор агрегации","MES3400","MES14xx/MES24xx/MES3400-xx/MES37xx","https://eltex.ru/product/kommutator_agregatsii_mes3400-24/","supported"),
                ("MES2308R","Eltex MES2308R","Коммутатор доступа","MES23xx","MES23xx/MES33xx/MES35xx/MES5324","https://eltex.ru/product/mes2308r/","eol"),
                ("MES2428P","Eltex MES2428P","Коммутатор доступа PoE","MES24xx","MES14xx/MES24xx/MES3400-xx/MES37xx","https://eltex.ru/product/kommutator_dostupa_mes2428p/","supported"),
            ),
            "d-link":(
                ("DGS-1100-08V2","D-Link DGS-1100-08V2","Smart Managed Switch","DGS-1100","DGS-1100-08V2","https://ftp.dlink.ru/pub/Switch/DGS-1100-08V2/","supported"),
                ("DGS-1100-08","D-Link DGS-1100-08","Smart Managed Switch","DGS-1100","DGS-1100-08","https://ftp.dlink.ru/pub/Switch/DGS-1100-08/","supported"),
                ("DGS-1100-05","D-Link DGS-1100-05","Smart Managed Switch","DGS-1100","DGS-1100-05","https://ftp.dlink.ru/pub/Switch/DGS-1100-05/","supported"),
            ),
            "zyxel":(
                ("GS1900-8","Zyxel GS1900-8","GbE Smart Managed Switch","GS1900 Series","AAHH","https://www.zyxel.com/global/en/products/switch/8-10-16-24-48-port-gbe-smart-managed-switch-gs1900-series","supported"),
            ),
        }
        for slug,items in vendor_models.items():
            vendor_name={"eltex":"Eltex","d-link":"D-Link","zyxel":"Zyxel"}[slug]
            connection.execute(text("INSERT OR IGNORE INTO equipment_vendors(name,slug,enabled) VALUES (:name,:slug,1)"),{"name":vendor_name,"slug":slug})
            vendor_id=connection.execute(text("SELECT id FROM equipment_vendors WHERE slug=:slug"),{"slug":slug}).scalar_one()
            provider=slug;source_id=connection.execute(text("SELECT id FROM firmware_sources WHERE builtin_provider=:provider"),{"provider":provider}).scalar_one()
            for name,display_name,device_type,family,group,url,support in items:
                connection.execute(text("INSERT OR IGNORE INTO equipment_models(vendor_id,name,normalized_name,enabled,snmp_profile,model_requires_clarification,hardware_revision_required,installed_version_method,version_comparator,latest_check_status,created_at,updated_at) VALUES (:vendor,:name,:normalized,1,NULL,0,:revision_required,'manual',:comparator,'Не проверялся',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"vendor":vendor_id,"name":name,"normalized":name.upper(),"revision_required":1 if slug=='d-link' else 0,"comparator":"zyxel" if slug=='zyxel' else "eltex" if slug=='eltex' else "dlink"})
                connection.execute(text("UPDATE equipment_models SET display_name=:display_name,device_type=:device_type,series=:family,firmware_family=:family,compatibility_group=:group_name,product_page_url=:url,firmware_page_url=:url,firmware_source_id=:source,firmware_provider=:provider,hardware_revision_required=:revision_required,version_comparator=:comparator,support_status=:support,enabled=1 WHERE vendor_id=:vendor AND normalized_name=:normalized"),{"display_name":display_name,"device_type":device_type,"family":family,"group_name":group,"url":url,"source":source_id,"provider":provider,"revision_required":1 if slug=='d-link' else 0,"comparator":"zyxel" if slug=='zyxel' else "eltex" if slug=='eltex' else "dlink","support":support,"vendor":vendor_id,"normalized":name.upper()})

        connection.execute(text("UPDATE equipment_models SET firmware_page_url='https://www.zyxel.com/global/en/support/download?model=gs1900-8',firmware_filename_pattern='GS1900-8.*AAHH',version_pattern='V\\d+\\.\\d+\\(AAHH\\.\\d+\\)C\\d+',download_rule='exact_model_and_firmware_code' WHERE normalized_name='GS1900-8' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='zyxel')"))
        connection.execute(text("UPDATE equipment_models SET firmware_filename_pattern='exact_model_or_compatibility_list',version_pattern='\\d+(?:\\.\\d+){2,3}(?: R\\d+)?',download_rule='product_page_compatibility' WHERE vendor_id=(SELECT id FROM equipment_vendors WHERE slug='eltex')"))
        connection.execute(text("UPDATE equipment_models SET installed_version_method='snmp',version_oid='1.3.6.1.4.1.2076.81.1.3.0',installed_version_pattern=NULL WHERE normalized_name='MES2428P' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='eltex')"))
        connection.execute(text("UPDATE equipment_models SET firmware_filename_pattern='exact_model_and_revision',version_pattern='V?\\d+\\.\\d+\\.(?:\\d+|B\\d+)',download_rule='hardware_revision_directory' WHERE vendor_id=(SELECT id FROM equipment_vendors WHERE slug='d-link')"))

        dlink_revisions={
            "DGS-1100-08V2":(("A","REVA","https://ftp.dlink.ru/pub/Switch/DGS-1100-08V2/Firmware/"),),
            "DGS-1100-08":(("A","REVA","https://ftp.dlink.ru/pub/Switch/DGS-1100-08/Firmware/"),("B","REVB","https://ftp.dlink.ru/pub/Switch/DGS-1100-08/Firmware/")),
            "DGS-1100-05":(("A","REVA","https://ftp.dlink.ru/pub/Switch/DGS-1100-05/Firmware/"),("B","REVB","https://ftp.dlink.ru/pub/Switch/DGS-1100-05/Firmware/")),
        }
        for model_name,revisions in dlink_revisions.items():
            model_id=connection.execute(text("SELECT id FROM equipment_models WHERE normalized_name=:name AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='d-link')"),{"name":model_name}).scalar_one()
            for display,provider,path in revisions:
                connection.execute(text("INSERT OR IGNORE INTO model_hardware_revisions(equipment_model_id,display_revision,provider_revision,firmware_path,enabled) VALUES (:model,:display,:provider,:path,1)"),{"model":model_id,"display":display,"provider":provider,"path":path})
                connection.execute(text("UPDATE model_hardware_revisions SET provider_revision=:provider,firmware_path=:path,enabled=1 WHERE equipment_model_id=:model AND display_revision=:display"),{"model":model_id,"display":display,"provider":provider,"path":path})
