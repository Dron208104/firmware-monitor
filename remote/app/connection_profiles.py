"""Validation and secret handling for SNMP connection profiles."""

import json

from .models import ConnectionProfile
from .security import decrypt_secret, encrypt_secret


def profile_secrets(profile: ConnectionProfile | None) -> dict[str, str]:
    if not profile or not profile.secret_encrypted:
        return {}
    try:
        value = decrypt_secret(profile.secret_encrypted)
    except Exception as exc:
        raise RuntimeError("Секрет профиля недоступен") from exc
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        decoded = value
    if isinstance(decoded, dict):
        return {key: str(item) for key, item in decoded.items() if key in {"community", "auth_password", "privacy_password"} and item}
    return {"auth_password" if profile.snmp_version == "3" else "community": value}


def profile_payload(profile: ConnectionProfile) -> dict:
    secrets = profile_secrets(profile)
    return {
        "id": profile.id,
        "name": profile.name,
        "snmp_version": profile.snmp_version,
        "username": profile.username if profile.snmp_version == "3" else None,
        "security_level": profile.security_level or "noAuthNoPriv",
        "auth_protocol": profile.auth_protocol,
        "privacy_protocol": profile.privacy_protocol,
        "port": profile.port or 161,
        "timeout_seconds": profile.timeout_seconds,
        "retries": profile.retries,
        "enabled": profile.enabled,
        "secret_saved": bool(secrets.get("community") or secrets.get("auth_password")),
        "privacy_secret_saved": bool(secrets.get("privacy_password")),
    }


def apply_profile_data(profile: ConnectionProfile, data: dict) -> None:
    name = str(data.get("name", "")).strip()
    version = str(data.get("snmp_version", "2c"))
    if not name or len(name) > 120:
        raise ValueError("Укажите название профиля до 120 символов")
    if version not in {"1", "2c", "3"}:
        raise ValueError("Выберите версию SNMP")
    try:
        port = int(data.get("port", 161))
        timeout = int(data.get("timeout_seconds", 5))
        retries = int(data.get("retries", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Укажите корректные порт, тайм-аут и количество повторов") from exc
    if not 1 <= port <= 65535 or not 1 <= timeout <= 60 or not 0 <= retries <= 10:
        raise ValueError("Порт, тайм-аут или количество повторов вне допустимого диапазона")
    previous = profile_secrets(profile) if profile.id is not None and profile.snmp_version == version else {}
    secrets: dict[str, str] = {}
    username = None
    level = None
    auth_protocol = None
    privacy_protocol = None
    if version in {"1", "2c"}:
        community = str(data.get("community", "")).strip() or previous.get("community", "")
        if not community:
            raise ValueError("Укажите Community string")
        secrets["community"] = community
    else:
        username = str(data.get("username", "")).strip()
        if not username:
            raise ValueError("Укажите имя пользователя SNMPv3")
        level = str(data.get("security_level", "noAuthNoPriv"))
        if level not in {"noAuthNoPriv", "authNoPriv", "authPriv"}:
            raise ValueError("Выберите уровень безопасности SNMPv3")
        if level in {"authNoPriv", "authPriv"}:
            auth_protocol = str(data.get("auth_protocol", ""))
            if auth_protocol not in {"MD5", "SHA"}:
                raise ValueError("Выберите протокол аутентификации MD5 или SHA")
            auth_password = str(data.get("auth_password", "")) or previous.get("auth_password", "")
            if not auth_password:
                raise ValueError("Укажите пароль аутентификации")
            secrets["auth_password"] = auth_password
        if level == "authPriv":
            privacy_protocol = str(data.get("privacy_protocol", ""))
            if privacy_protocol not in {"DES", "AES"}:
                raise ValueError("Выберите протокол шифрования DES или AES")
            privacy_password = str(data.get("privacy_password", "")) or previous.get("privacy_password", "")
            if not privacy_password:
                raise ValueError("Укажите пароль шифрования")
            secrets["privacy_password"] = privacy_password
    profile.name = name
    profile.method = "snmp"
    profile.snmp_version = version
    profile.username = username
    profile.security_level = level
    profile.auth_protocol = auth_protocol
    profile.privacy_protocol = privacy_protocol
    profile.port = port
    profile.timeout_seconds = timeout
    profile.retries = retries
    try:
        profile.secret_encrypted = encrypt_secret(json.dumps(secrets, ensure_ascii=False)) if secrets else None
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Шифрование секретов не настроено") from exc
