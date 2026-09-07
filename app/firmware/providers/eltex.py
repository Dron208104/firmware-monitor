from datetime import datetime, timezone
from .base import FirmwareProvider, FirmwareResult
class EltexFirmwareProvider(FirmwareProvider):
    allowed_domains=("eltex-co.ru",)
    async def fetch(self,vendor,model):
        return FirmwareResult(vendor.name,model.name,None,None,model.firmware_page_url,None,None,None,datetime.now(timezone.utc),"Источник не настроен","Адаптер Eltex ожидает подтверждённые URL и правила парсинга")
