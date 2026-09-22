"""Почтовая интеграция первой версии намеренно выключена.

Будущая SMTP-конфигурация должна поступать только из переменных окружения.
"""
import logging
log = logging.getLogger(__name__)

def notifications_enabled() -> bool:
    return False

def send_update_notification(*_args, **_kwargs) -> None:
    log.info("Email notifications are not configured")

