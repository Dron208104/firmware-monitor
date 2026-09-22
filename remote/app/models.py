from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now(): return datetime.now(timezone.utc)

class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sessions: Mapped[list["UserSession"]] = relationship(cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(160))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ConnectionProfile(Base):
    __tablename__ = "connection_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    method: Mapped[str] = mapped_column(String(20), default="snmp")
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    snmp_version: Mapped[str] = mapped_column(String(10), default="2c")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5)
    retries: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class FirmwareSource(Base):
    __tablename__ = "firmware_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    vendor: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(30))
    base_url: Mapped[str] = mapped_column(Text)
    allowed_domains: Mapped[str] = mapped_column(Text)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    builtin_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(60), default="Не проверялся")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class EquipmentVendor(Base):
    __tablename__ = "equipment_vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    models: Mapped[list["EquipmentModel"]] = relationship(back_populates="vendor", cascade="all, delete-orphan")

class EquipmentModel(Base):
    __tablename__ = "equipment_models"
    __table_args__ = (UniqueConstraint("vendor_id", "normalized_name", name="uq_model_vendor_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("equipment_vendors.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(120))
    series: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_requires_clarification: Mapped[bool] = mapped_column(Boolean, default=False)
    hardware_revision_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    os_family: Mapped[str | None] = mapped_column(String(40), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(40), nullable=True)
    update_channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    snmp_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_family: Mapped[str | None] = mapped_column(String(120), nullable=True)
    compatibility_group: Mapped[str | None] = mapped_column(String(180), nullable=True)
    firmware_filename_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    changelog_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_status: Mapped[str] = mapped_column(String(30), default="supported", server_default="supported")
    firmware_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    firmware_source_id: Mapped[int | None] = mapped_column(ForeignKey("firmware_sources.id"), nullable=True, index=True)
    device_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    installed_version_method: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    version_oid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installed_version_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_file_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_version_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_comparator: Mapped[str] = mapped_column(String(40), default="numeric", server_default="numeric")
    model_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsing_parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_check_status: Mapped[str] = mapped_column(String(60), default="Источник не настроен")
    latest_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    vendor: Mapped[EquipmentVendor] = relationship(back_populates="models")
    firmware_releases: Mapped[list["FirmwareRelease"]] = relationship(back_populates="model", cascade="all, delete-orphan")
    hardware_revisions: Mapped[list["ModelHardwareRevision"]] = relationship(back_populates="model", cascade="all, delete-orphan")

class ModelHardwareRevision(Base):
    __tablename__ = "model_hardware_revisions"
    __table_args__ = (UniqueConstraint("equipment_model_id", "display_revision", name="uq_model_hardware_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_model_id: Mapped[int] = mapped_column(ForeignKey("equipment_models.id"), index=True)
    display_revision: Mapped[str] = mapped_column(String(30))
    provider_revision: Mapped[str] = mapped_column(String(30))
    firmware_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model: Mapped[EquipmentModel] = relationship(back_populates="hardware_revisions")

class FirmwareRelease(Base):
    __tablename__ = "firmware_releases"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_firmware_model_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("equipment_models.id"), index=True)
    version: Mapped[str] = mapped_column(String(120))
    normalized_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    release_suffix: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider_revision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    release_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmware_page_url: Mapped[str] = mapped_column(Text)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    changelog_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    model: Mapped[EquipmentModel] = relationship(back_populates="firmware_releases")

class FirmwareSourceCheck(Base):
    __tablename__ = "firmware_source_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("equipment_models.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(60))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_version: Mapped[str | None] = mapped_column(String(120), nullable=True)

class FirmwareEvent(Base):
    __tablename__ = "firmware_events"
    __table_args__ = (UniqueConstraint("model_id", "version", "event_type", name="uq_firmware_event"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("equipment_models.id"), index=True)
    version: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(80), default="Найдена новая прошивка")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    notification_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(30), default="updates", server_default="updates")
    old_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    new_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", server_default="info")

class EquipmentFolder(Base):
    __tablename__ = "equipment_folders"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_folder_parent_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_folders.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    parent: Mapped["EquipmentFolder | None"] = relationship(remote_side="EquipmentFolder.id", back_populates="children")
    children: Mapped[list["EquipmentFolder"]] = relationship(back_populates="parent")

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    ip_address: Mapped[str] = mapped_column(String(45))
    management_port: Mapped[int] = mapped_column(Integer, default=161)
    vendor: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    catalog_model_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_models.id"), nullable=True, index=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    hardware_revision: Mapped[str | None] = mapped_column(String(60), nullable=True)
    installed_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    available_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acquisition_method: Mapped[str] = mapped_column(String(20), default="manual")
    version_source: Mapped[str] = mapped_column(String(20), default="snmp")
    installed_version_source: Mapped[str] = mapped_column(String(20), default="snmp")
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("connection_profiles.id"), nullable=True)
    official_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_check: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(60), default="Версия не указана")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    snmp_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    snmpv3_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    security_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    auth_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    privacy_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[ConnectionProfile | None] = relationship()
    checks: Mapped[list["CheckHistory"]] = relationship(cascade="all, delete-orphan")
    catalog_model: Mapped[EquipmentModel | None] = relationship()
    folder: Mapped[EquipmentFolder | None] = relationship()

class CheckHistory(Base):
    __tablename__ = "check_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    installed_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    available_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(60))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
