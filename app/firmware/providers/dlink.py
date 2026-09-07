from datetime import datetime, timezone
from .base import FirmwareProvider, FirmwareResult
class DlinkFirmwareProvider(FirmwareProvider):
    allowed_domains=("dlink.ru","dlink.com")
    async def fetch(self,vendor,model):
        return FirmwareResult(vendor.name,model.name,None,None,model.firmware_page_url,None,None,None,datetime.now(timezone.utc),"Источник не настроен","Адаптер D-Link ожидает подтверждённые URL и правила парсинга")
