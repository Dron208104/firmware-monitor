from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
import ipaddress, socket

@dataclass
class FirmwareResult:
    vendor: str
    model: str
    latest_version: str | None
    release_date: datetime | None
    firmware_page_url: str | None
    download_url: str | None
    checksum: str | None
    release_notes: str | None
    checked_at: datetime
    status: str
    error: str | None = None
    changelog_url: str | None = None
    size_bytes: int | None = None

class FirmwareProvider:
    allowed_domains: tuple[str,...] = ()
    async def fetch(self, vendor, model) -> FirmwareResult:
        raise NotImplementedError
    def validate_source(self, url: str) -> None:
        parsed=urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname: raise ValueError("Допустим только HTTPS URL источника")
        host=parsed.hostname.lower()
        if not any(host==domain or host.endswith("."+domain) for domain in self.allowed_domains): raise ValueError("Домен не входит в список официальных источников")
        for item in socket.getaddrinfo(host,parsed.port or (443 if parsed.scheme=="https" else 80)):
            if not ipaddress.ip_address(item[4][0]).is_global: raise ValueError("Источник разрешается в служебный или частный адрес")
