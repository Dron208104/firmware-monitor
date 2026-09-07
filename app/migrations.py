from sqlalchemy import inspect, text

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
    "version_source": "VARCHAR(20) NOT NULL DEFAULT 'snmp'",
    "installed_version_source": "VARCHAR(20) NOT NULL DEFAULT 'snmp'",
}

MODEL_COLUMNS = {
    "firmware_page_url": "TEXT",
    "firmware_provider": "VARCHAR(40)",
    "model_aliases": "TEXT",
    "parsing_parameters": "TEXT",
    "latest_check_status": "VARCHAR(60) NOT NULL DEFAULT 'Источник не настроен'",
    "latest_checked_at": "DATETIME",
    "latest_check_error": "TEXT",
}
RELEASE_COLUMNS = {"changelog_url":"TEXT","file_size":"INTEGER"}

def migrate_sqlite(engine):
    if engine.dialect.name != "sqlite": return
    existing = {column["name"] for column in inspect(engine).get_columns("devices")}
    model_existing = {column["name"] for column in inspect(engine).get_columns("equipment_models")}
    release_existing = {column["name"] for column in inspect(engine).get_columns("firmware_releases")}
    with engine.begin() as connection:
        for name, definition in COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE devices ADD COLUMN {name} {definition}"))
        for name, definition in MODEL_COLUMNS.items():
            if name not in model_existing:
                connection.execute(text(f"ALTER TABLE equipment_models ADD COLUMN {name} {definition}"))
        for name, definition in RELEASE_COLUMNS.items():
            if name not in release_existing: connection.execute(text(f"ALTER TABLE firmware_releases ADD COLUMN {name} {definition}"))
        connection.execute(text("UPDATE devices SET installed_version_source=version_source WHERE version_source IN ('snmp','manual')"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_devices_ip ON devices(ip_address)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_devices_catalog_model_id ON devices(catalog_model_id)"))
        for name, slug, model in (("QTECH","qtech","QSW-4610-28T-AC"),("Eltex","eltex","MES2428P"),("D-Link","d-link","DGS-1100-08V2")):
            connection.execute(text("INSERT OR IGNORE INTO equipment_vendors(name,slug,enabled) VALUES (:name,:slug,1)"),{"name":name,"slug":slug})
            vendor_id=connection.execute(text("SELECT id FROM equipment_vendors WHERE slug=:slug"),{"slug":slug}).scalar_one()
            connection.execute(text("INSERT OR IGNORE INTO equipment_models(vendor_id,name,normalized_name,enabled,snmp_profile,latest_check_status,created_at,updated_at) VALUES (:vendor_id,:name,:normalized,1,NULL,'Источник не настроен',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"vendor_id":vendor_id,"name":model,"normalized":model.upper()})
        connection.execute(text("UPDATE equipment_models SET firmware_provider='qtech', firmware_page_url='https://ftp.qtech.ru/Switch/Access/QSW-4610/Firmware/QSW-4610-28T-AC/' WHERE normalized_name='QSW-4610-28T-AC' AND vendor_id=(SELECT id FROM equipment_vendors WHERE slug='qtech')"))
