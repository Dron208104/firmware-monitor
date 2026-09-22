from datetime import datetime, timezone
from html import unescape
import re
import httpx
from ...config import settings
from .base import FirmwareProvider, FirmwareResult


class MikrotikFirmwareProvider(FirmwareProvider):
    allowed_domains = ("mikrotik.com", "download.mikrotik.com")

    @staticmethod
    def parse(html: str, architecture: str = "arm"):
        decoded = unescape(html)
        long_term = re.search(r'"channel"\s*:\s*"longTerm"\s*,\s*"version"\s*:\s*"([0-9]+(?:\.[0-9]+)+)"', decoded)
        if not long_term:
            return None
        version = long_term.group(1)
        expected = f"https://download.mikrotik.com/routeros/{version}/routeros-{version}-{architecture}.npk"
        return version, expected

    async def fetch(self, vendor, model):
        url = model.firmware_page_url
        self.validate_source(url)
        architecture = (model.architecture or "arm").lower()
        timeout = httpx.Timeout(settings.request_timeout_seconds, connect=min(5, settings.request_timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": "Firmware Monitor/1.0"}) as client:
            response = await client.get(url)
            response.raise_for_status()
            if len(response.content) > settings.max_response_bytes:
                raise ValueError("Ответ официального источника слишком велик")
        found = self.parse(response.text, architecture)
        checked = datetime.now(timezone.utc)
        if not found:
            return FirmwareResult(vendor.name, model.name, None, None, url, None, None, None, checked, "Ошибка проверки производителя", "На официальной странице не найдена long-term версия RouterOS")
        version, download = found
        self.validate_source(download)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": "Firmware Monitor/1.0"}) as client:
            package = await client.head(download)
            package.raise_for_status()
        changelog = "https://mikrotik.com/download/changelogs?channelFilter=longTerm"
        self.validate_source(changelog)
        return FirmwareResult(vendor.name, model.name, version, None, url, download, None, None, checked, "Прошивка найдена", None, changelog, None)
