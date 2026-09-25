"""User-facing source state, separate from provider diagnostics."""


def source_status_view(source) -> tuple[str, str]:
    status = (source.last_status or "").strip().casefold()
    if not source.last_checked_at or status in {"", "не проверялся", "не проверен", "черновик", "требуется проверка"}:
        return "Не проверен", "off"
    if source.last_error or any(word in status for word in ("ошибка", "недоступ", "отключ", "error", "failed")):
        return "Ошибка проверки", "error"
    if status in {"доступны обновления", "найдены новые версии"}:
        return "Доступны обновления", "warn"
    if status in {"конфигурация допустима", "configuration valid", "config valid", "источник доступен"}:
        return "Источник доступен", "ok"
    if status in {"проверка выполнена", "прошивка найдена", "прошивка не найдена", "только страница загрузки"}:
        return "Проверка выполнена", "ok"
    return "Не проверен", "off"
