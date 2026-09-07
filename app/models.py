from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now(): return datetime.now(timezone.utc)

class ConnectionProfile(Base):
    __tablename__ = "connection_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    method: Mapped[str] = mapped_column(String(20), default="snmp")
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    snmp_version: Mapped[str] = mapped_column(String(10), default="2c")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    normalized_name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    snmp_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsing_parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_check_status: Mapped[str] = mapped_column(String(60), default="Источник не настроен")
    latest_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    vendor: Mapped[EquipmentVendor] = relationship(back_populates="models")
    firmware_releases: Mapped[list["FirmwareRelease"]] = relationship(back_populates="model", cascade="all, delete-orphan")

class FirmwareRelease(Base):
    __tablename__ = "firmware_releases"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_firmware_model_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("equipment_models.id"), index=True)
    version: Mapped[str] = mapped_column(String(120))
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

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    ip_address: Mapped[str] = mapped_column(String(45))
    management_port: Mapped[int] = mapped_column(Integer, default=161)
    vendor: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    catalog_model_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_models.id"), nullable=True, index=True)
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

class CheckHistory(Base):
    __tablename__ = "check_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    installed_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    available_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(60))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
