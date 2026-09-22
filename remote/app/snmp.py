"""Безопасная точка расширения SNMP.

Опрос не запускается планировщиком до добавления подтверждённых vendor-specific OID.
"""
async def test_snmp(device, profile) -> tuple[bool, str]:
    if not profile:
        return False, "Не выбран SNMP-профиль"
    return False, "SNMP-интерфейс подготовлен; для модели требуется подтверждённый OID версии"

