"""SMTP configuration and bounded, non-blocking notification delivery."""

import json
import logging
import re
import smtplib
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr
from threading import BoundedSemaphore

from sqlalchemy.orm import Session

from .models import ApplicationSetting
from .security import decrypt_secret, encrypt_secret

log = logging.getLogger(__name__)
CONFIG_KEY = "smtp_config"
PASSWORD_KEY = "smtp_password_encrypted"
EVENT_TYPES = ("new_firmware", "device_error", "source_error", "auto_check_result")
DEFAULT_CONFIG = {
    "enabled": False, "host": "", "port": 587, "encryption": "starttls",
    "username": "", "sender_email": "", "sender_name": "Firmware Monitor",
    "recipients": [], "event_types": list(EVENT_TYPES), "reminder_count": 0,
}
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="firmware-mail")
_pending = BoundedSemaphore(20)
_email_pattern = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


class MailDeliveryError(Exception):
    """A safe message suitable for the settings UI."""


def _setting(db: Session, key: str) -> str | None:
    item = db.get(ApplicationSetting, key)
    return item.value if item else None


def _put_setting(db: Session, key: str, value: str) -> None:
    item = db.get(ApplicationSetting, key)
    if item:
        item.value = value
    else:
        db.add(ApplicationSetting(key=key, value=value))


def load_smtp_config(db: Session) -> dict:
    saved = json.loads(_setting(db, CONFIG_KEY) or "{}")
    return {**DEFAULT_CONFIG, **saved}


def public_smtp_config(db: Session) -> dict:
    return {**load_smtp_config(db), "password_saved": bool(_setting(db, PASSWORD_KEY))}


def _email(value: str) -> str:
    address = value.strip()
    if len(address) > 254 or not _email_pattern.fullmatch(address):
        raise ValueError("Укажите корректные адреса электронной почты")
    local, domain = address.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _validate_smtp_target(host: str, port: int) -> None:
    if host.casefold()=="localhost":
        raise MailDeliveryError("SMTP-сервер указывает на запрещённый служебный адрес")
    try:
        addresses={item[4][0] for item in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise MailDeliveryError("Не удалось подключиться к SMTP-серверу") from exc
    for raw in addresses:
        ip=__import__("ipaddress").ip_address(raw)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise MailDeliveryError("SMTP-сервер указывает на запрещённый служебный адрес")


def normalize_smtp_config(data: dict, *, password_saved: bool = False) -> dict:
    config = {key: data.get(key, default) for key, default in DEFAULT_CONFIG.items()}
    if not isinstance(config["enabled"], bool):
        raise ValueError("Укажите состояние почтовых уведомлений")
    config["host"] = str(config["host"]).strip()
    config["username"] = str(config["username"]).strip()
    config["sender_name"] = str(config["sender_name"]).strip() or "Firmware Monitor"
    if any("\n" in config[key] or "\r" in config[key] for key in ("host", "username", "sender_name")):
        raise ValueError("Недопустимые символы в настройках SMTP")
    try:
        config["port"] = int(config["port"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Укажите порт от 1 до 65535") from exc
    if not 1 <= config["port"] <= 65535:
        raise ValueError("Укажите порт от 1 до 65535")
    try:
        config["reminder_count"] = int(config["reminder_count"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Укажите количество напоминаний от 0 до 10") from exc
    if not 0 <= config["reminder_count"] <= 10:
        raise ValueError("Укажите количество напоминаний от 0 до 10")
    if config["encryption"] not in {"none", "starttls", "ssl"}:
        raise ValueError("Выберите тип шифрования SMTP")
    raw_recipients = config["recipients"]
    if isinstance(raw_recipients, str):
        raw_recipients = re.split(r"[,;\n]+", raw_recipients)
    if not isinstance(raw_recipients, list):
        raise ValueError("Укажите адреса получателей")
    seen = set()
    recipients = []
    for value in raw_recipients:
        if not str(value).strip():
            continue
        address = _email(str(value))
        if address.casefold() not in seen:
            seen.add(address.casefold())
            recipients.append(address)
    config["recipients"] = recipients
    config["sender_email"] = str(config["sender_email"]).strip()
    if config["sender_email"]:
        config["sender_email"] = _email(config["sender_email"])
    kinds = config["event_types"]
    if not isinstance(kinds, list) or any(kind not in EVENT_TYPES for kind in kinds):
        raise ValueError("Выберите корректные типы уведомлений")
    config["event_types"] = list(dict.fromkeys(kinds))
    if config["enabled"]:
        if not config["host"]:
            raise ValueError("Укажите SMTP-сервер")
        if not config["sender_email"]:
            raise ValueError("Укажите адрес отправителя")
        if not recipients:
            raise ValueError("Укажите хотя бы одного получателя")
        if config["username"] and not password_saved:
            raise ValueError("Укажите пароль SMTP")
    return config


def save_smtp_config(db: Session, data: dict) -> dict:
    password = str(data.get("password") or "")
    config = normalize_smtp_config(data, password_saved=bool(password or _setting(db, PASSWORD_KEY)))
    if password:
        try:
            _put_setting(db, PASSWORD_KEY, encrypt_secret(password))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Шифрование секретов не настроено") from exc
    _put_setting(db, CONFIG_KEY, json.dumps(config, ensure_ascii=False))
    db.commit()
    return public_smtp_config(db)


def _send_email(config: dict, password: str, subject: str, body: str) -> None:
    _validate_smtp_target(config["host"],config["port"])
    message = EmailMessage()
    message["From"] = formataddr((config["sender_name"], config["sender_email"]))
    message["To"] = ", ".join(config["recipients"])
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if config["encryption"] == "ssl":
            client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=5, context=context)
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=5)
        with client:
            client.ehlo()
            if config["encryption"] == "starttls":
                client.starttls(context=context)
                client.ehlo()
            if config["username"]:
                client.login(config["username"], password)
            client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailDeliveryError("Ошибка авторизации SMTP") from exc
    except (socket.gaierror, ConnectionRefusedError) as exc:
        raise MailDeliveryError("Не удалось подключиться к SMTP-серверу") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise MailDeliveryError("Превышено время ожидания SMTP-сервера") from exc
    except ssl.SSLError as exc:
        raise MailDeliveryError("Ошибка защищённого соединения SMTP") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailDeliveryError("SMTP-сервер отклонил отправку") from exc


def send_test_email(db: Session) -> None:
    config = load_smtp_config(db)
    normalize_smtp_config(config, password_saved=bool(_setting(db, PASSWORD_KEY)))
    if not config["enabled"]:
        raise ValueError("Сначала включите и сохраните почтовые уведомления")
    try:
        password = decrypt_secret(_setting(db, PASSWORD_KEY)) if _setting(db, PASSWORD_KEY) else ""
    except Exception as exc:
        raise RuntimeError("Настройка почты недоступна") from exc
    _send_email(
        config,
        password,
        "Firmware Monitor — тестовое письмо",
        "Почтовые уведомления Firmware Monitor настроены успешно.\n\n"
        "Это тестовое сообщение подтверждает, что SMTP-сервер, отправитель и список получателей настроены правильно.",
    )


def send_test_email_from_store() -> None:
    from .db import SessionLocal

    with SessionLocal() as db:
        send_test_email(db)


def send_selected_notification(kind: str, subject: str, body: str) -> bool:
    from .db import SessionLocal

    with SessionLocal() as db:
        config = load_smtp_config(db)
        if not config["enabled"] or kind not in config["event_types"]:
            return False
        try:
            password = decrypt_secret(_setting(db, PASSWORD_KEY)) if _setting(db, PASSWORD_KEY) else ""
        except Exception as exc:
            raise RuntimeError("Настройка почты недоступна") from exc
    _send_email(config, password, subject, body)
    return True


def queue_notification(kind: str, subject: str, body: str) -> None:
    if not _pending.acquire(blocking=False):
        log.warning("Mail queue is full")
        return

    def deliver() -> None:
        try:
            send_selected_notification(kind, subject, body)
        except Exception:
            log.warning("Mail delivery failed for event type %s", kind)
        finally:
            _pending.release()

    _executor.submit(deliver)
