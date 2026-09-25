import ipaddress, secrets, socket
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from .config import settings

def _fernet():
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY не настроен")
    return Fernet(settings.encryption_key.encode())
def validate_encryption_configuration() -> None:
    if not settings.encryption_key or settings.encryption_key == "replace-with-generated-fernet-key":
        raise RuntimeError("ENCRYPTION_KEY не настроен")
    try:
        Fernet(settings.encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("ENCRYPTION_KEY имеет некорректный формат") from exc
def encrypt_secret(value: str) -> str: return _fernet().encrypt(value.encode()).decode()
def decrypt_secret(value: str) -> str: return _fernet().decrypt(value.encode()).decode()
def csrf_token() -> str: return secrets.token_urlsafe(32)

def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Разрешены только HTTP/HTTPS URL без учётных данных")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise ValueError("Имя узла не разрешается") from exc
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if not ip.is_global:
            raise ValueError("URL указывает на локальный или служебный адрес")
    return url

def validate_firmware_source_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "ftp", "ftps"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Разрешены только HTTP, HTTPS, FTP и FTPS без учётных данных")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port)}
    except socket.gaierror as exc:
        raise ValueError("Имя узла не разрешается") from exc
    if any(not ipaddress.ip_address(raw).is_global for raw in addresses):
        raise ValueError("Источник указывает на локальный или служебный адрес")
    return url
