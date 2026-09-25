"""Read an installed firmware version with one bounded SNMP GET request."""

import json
import re

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine,
    UdpTransportTarget, UsmUserData, get_cmd, usmAesCfb128Protocol,
    usmDESPrivProtocol, usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol,
    usmNoAuthProtocol, usmNoPrivProtocol,
)

from .connection_profiles import profile_secrets
from .security import decrypt_secret

DEFAULT_VERSION_OID = "1.3.6.1.2.1.1.1.0"
_OID = re.compile(r"^\.?\d+(?:\.\d+)+$")
_CLEAN_VERSION = re.compile(r"^[vV]?\d[0-9A-Za-z._()+-]*(?:\s+[Rr]\d+)?$")
_LABELLED_VERSION = re.compile(r"(?i)(?:firmware|software|routeros|sw\s*version|version|ver\.?|fw)[\s:=/_-]*([vV]?\d[0-9A-Za-z._()+-]*(?:\s+[Rr]\d+)?)")
_VERSION_TOKEN = re.compile(r"(?<![A-Za-z0-9])[vV]?\d+(?:\.\d+)+[0-9A-Za-z._()+-]*(?:\s+[Rr]\d+)?(?![A-Za-z0-9])")


class SnmpPollingError(Exception):
    """A sanitized polling error suitable for the interface and history."""


def validate_version_settings(oid: str | None, pattern: str | None) -> tuple[str | None, str | None]:
    normalized_oid = (oid or "").strip() or None
    normalized_pattern = (pattern or "").strip() or None
    if normalized_oid and (len(normalized_oid) > 255 or not _OID.fullmatch(normalized_oid)):
        raise ValueError("Укажите корректный числовой OID версии")
    if normalized_pattern:
        if len(normalized_pattern) > 500:
            raise ValueError("Шаблон версии не должен превышать 500 символов")
        try:
            re.compile(normalized_pattern)
        except re.error as exc:
            raise ValueError("Укажите корректное регулярное выражение версии") from exc
    return normalized_oid, normalized_pattern


def _device_secrets(device) -> dict[str, str]:
    if device.profile:
        return profile_secrets(device.profile)
    if not device.credentials_encrypted:
        return {}
    try:
        value = json.loads(decrypt_secret(device.credentials_encrypted))
    except Exception as exc:
        raise SnmpPollingError("Не удалось прочитать учётные данные SNMP") from exc
    return {key: str(item) for key, item in value.items() if key in {"community", "auth_password", "privacy_password"} and item}


def extract_version(raw_value: str, pattern: str | None = None) -> str:
    value = " ".join(str(raw_value).replace("\x00", " ").split())
    if not value or len(value) > 2048:
        raise SnmpPollingError("SNMP вернул пустое или слишком длинное значение")
    if pattern:
        if len(pattern) > 500:
            raise SnmpPollingError("Шаблон версии слишком длинный")
        try:
            match = re.search(pattern, value, re.IGNORECASE)
        except re.error as exc:
            raise SnmpPollingError("Некорректный шаблон извлечения версии") from exc
        if not match:
            raise SnmpPollingError("Версия не соответствует шаблону модели")
        version = match.group(1) if match.lastindex else match.group(0)
    elif _CLEAN_VERSION.fullmatch(value):
        version = value
    else:
        labelled = _LABELLED_VERSION.search(value)
        if labelled:
            version = labelled.group(1)
        else:
            candidates = list(dict.fromkeys(item.group(0) for item in _VERSION_TOKEN.finditer(value)))
            if len(candidates) != 1:
                raise SnmpPollingError("Не удалось однозначно выделить версию из ответа SNMP")
            version = candidates[0]
    version = version.strip().strip("\"'.,;:")
    if not version or len(version) > 120 or any(ord(char) < 32 for char in version):
        raise SnmpPollingError("Получено некорректное значение версии")
    return version


def _auth_data(device, secrets: dict[str, str]):
    profile = device.profile
    version = (profile.snmp_version if profile else device.snmp_version) or "2c"
    if version in {"1", "2c"}:
        community = secrets.get("community")
        if not community:
            raise SnmpPollingError("Не указан Community string")
        return CommunityData(community, mpModel=0 if version == "1" else 1)
    username = (profile.username if profile else device.snmpv3_username) or ""
    level = (profile.security_level if profile else device.security_level) or "noAuthNoPriv"
    if not username:
        raise SnmpPollingError("Не указан пользователь SNMPv3")
    auth_protocol, priv_protocol, auth_key, priv_key = usmNoAuthProtocol, usmNoPrivProtocol, None, None
    if level in {"authNoPriv", "authPriv"}:
        auth_key = secrets.get("auth_password")
        if not auth_key:
            raise SnmpPollingError("Не указан пароль аутентификации SNMPv3")
        configured_auth = profile.auth_protocol if profile else device.auth_protocol
        auth_protocol = {"MD5": usmHMACMD5AuthProtocol, "SHA": usmHMACSHAAuthProtocol}.get(configured_auth)
        if auth_protocol is None:
            raise SnmpPollingError("Не поддерживается протокол аутентификации SNMPv3")
    if level == "authPriv":
        priv_key = secrets.get("privacy_password")
        if not priv_key:
            raise SnmpPollingError("Не указан пароль шифрования SNMPv3")
        configured_priv = profile.privacy_protocol if profile else device.privacy_protocol
        priv_protocol = {"AES": usmAesCfb128Protocol, "DES": usmDESPrivProtocol}.get(configured_priv)
        if priv_protocol is None:
            raise SnmpPollingError("Не поддерживается протокол шифрования SNMPv3")
    return UsmUserData(username, auth_key, priv_key, authProtocol=auth_protocol, privProtocol=priv_protocol)


async def read_installed_version(device) -> str:
    model = device.catalog_model
    oid = (model.version_oid if model else None) or DEFAULT_VERSION_OID
    if len(oid) > 255 or not _OID.fullmatch(oid):
        raise SnmpPollingError("Для модели указан некорректный OID версии")
    profile = device.profile
    port = (profile.port if profile else device.snmp_port or device.management_port) or 161
    timeout = profile.timeout_seconds if profile else 5
    retries = profile.retries if profile else 1
    engine = SnmpEngine()
    try:
        target = await UdpTransportTarget.create((device.ip_address, int(port)), timeout=float(timeout), retries=int(retries))
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            engine, _auth_data(device, _device_secrets(device)), target, ContextData(),
            ObjectType(ObjectIdentity(oid)), lookupMib=False,
        )
    except SnmpPollingError:
        raise
    except Exception as exc:
        raise SnmpPollingError("Не удалось выполнить SNMP-запрос") from exc
    finally:
        engine.close_dispatcher()
    if error_indication:
        raise SnmpPollingError("Устройство не ответило на SNMP-запрос")
    if error_status:
        raise SnmpPollingError("Устройство отклонило запрос OID версии")
    if not var_binds:
        raise SnmpPollingError("SNMP не вернул значение версии")
    return extract_version(var_binds[0][1].prettyPrint(), model.installed_version_pattern if model else None)


async def test_snmp(device, profile=None) -> tuple[bool, str]:
    try:
        version = await read_installed_version(device)
    except SnmpPollingError as exc:
        return False, str(exc)
    return True, f"Подключение успешно. Установленная версия: {version}"
