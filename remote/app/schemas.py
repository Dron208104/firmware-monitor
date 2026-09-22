from pydantic import BaseModel, ConfigDict, Field, field_validator

class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csrf: str
    name: str = Field(max_length=120)
    address: str = Field(max_length=45)
    vendor_id: int | None = None
    model_id: int | None = None
    custom_model: str | None = Field(default=None, max_length=120)
    version_source: str = "snmp"
    snmp_version: str = "2c"
    snmp_port: int = 161
    community: str | None = None
    description: str | None = None
    auto_check: bool = True
    snmpv3_username: str | None = None
    security_level: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    installed_version: str | None = Field(default=None, max_length=120)
    folder_id: int | None = None
    hardware_revision: str | None = Field(default=None, max_length=20)

    @field_validator("folder_id", mode="before")
    @classmethod
    def empty_folder_is_none(cls, value):
        return None if value == "" else value

class DeviceOut(BaseModel):
    id: int
    name: str
    address: str
    vendor: str
    model: str
    acquisition_method: str
    version_source: str
    management_port: int
    installed_version: str | None
    available_version: str | None
    description: str | None
    auto_check: bool
    status: str
    last_checked_at: str | None
    latest_checked_at: str | None = None
    latest_check_status: str | None = None
    download_url: str | None = None
    firmware_page_url: str | None = None
    changelog_url: str | None = None
    folder_id: int | None = None
    hardware_revision: str | None = None
