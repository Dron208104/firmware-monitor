from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from urllib.parse import urljoin
import ipaddress, socket
import httpx

from ...config import settings

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
    filename: str | None = None
    source_status: str | None = None
    provider_revision: str | None = None
    http_status: int | None = None
    response_time_ms: int | None = None
    display_version: str | None = None
    normalized_version: str | None = None
    product_page_url: str | None = None
    source_url: str | None = None
    error_code: str | None = None
    is_cached: bool = False
    compatibility_confirmed: bool = True
    hardware_revision: str | None = None

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

async def fetch_limited(url:str,validate,max_redirects:int=3):
    timeout=httpx.Timeout(settings.request_timeout_seconds,connect=min(5,settings.request_timeout_seconds))
    redirects=0
    async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,headers={"User-Agent":"Firmware Monitor/1.0"}) as client:
        while True:
            validate(url)
            async with client.stream("GET",url) as response:
                if response.status_code in {301,302,303,307,308}:
                    location=response.headers.get("location")
                    if not location or redirects>=max_redirects:raise ValueError("Небезопасное или слишком длинное перенаправление")
                    target=urljoin(url,location);validate(target);url=target;redirects+=1;continue
                response.raise_for_status();chunks=[];total=0
                async for chunk in response.aiter_bytes():
                    total+=len(chunk)
                    if total>settings.max_response_bytes:raise ValueError("Ответ официального источника слишком велик")
                    chunks.append(chunk)
                return b"".join(chunks),url,response.status_code,response.encoding or "utf-8"
