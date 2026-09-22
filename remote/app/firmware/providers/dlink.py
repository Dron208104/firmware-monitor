from datetime import datetime, timezone
from time import monotonic
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen
import asyncio
import ssl
import time
import re

from bs4 import BeautifulSoup

from ...config import settings
from ...versioning import normalize_dlink_version
from .base import FirmwareProvider, FirmwareResult


class DlinkFirmwareProvider(FirmwareProvider):
    allowed_domains=("dlink.com","support.dlink.com","dlink.ru","support.d-link.ru","ftp.dlink.ru")

    @staticmethod
    def _directory(html:str,url:str,name:str):
        wanted=name.strip("/").upper()
        for link in BeautifulSoup(html,"html.parser").find_all("a",href=True):
            path=unquote(urlparse(link["href"]).path).rstrip("/")
            if path.split("/")[-1].upper()==wanted:return urljoin(url,link["href"])
        return None

    @classmethod
    def parse(cls,html:str,url:str,revision:str="REVA",model_name:str="DGS-1100-08V2"):
        soup=BeautifulSoup(html,"html.parser");firmware=[];notes={};model=model_name.upper()
        model_pattern=re.compile(rf"(?<![A-Z0-9]){re.escape(model)}(?![A-Z0-9])",re.I)
        for link in soup.find_all("a",href=True):
            name=unquote(link["href"].split("/")[-1].strip()) or link.get_text(strip=True);upper=name.upper()
            shared=((model in {"DGS-1100-05","DGS-1100-08"} and "DGS-1100-05_08" in upper) or
                    (model=="DGS-1100-08V2" and "DGS-1100-05V2_08V2" in upper))
            if not model_pattern.search(upper) and not shared:continue
            revision_letter=revision.upper().replace("REV","")[:1]
            named_revision=re.search(r"(?:^|[_-])REV([A-Z])(?:[_-])",upper)
            if named_revision and named_revision.group(1)!=revision_letter:continue
            file_revision=re.search(r"(?:^|[-_])([AB])1(?:[-_])",upper)
            if file_revision and file_revision.group(1)!=revision_letter:continue
            version_matches=list(re.finditer(r"(?:^|[_-])V?(\d+)[._](\d+)[._](B?\d+)",upper))
            if not version_matches:continue
            version_match=version_matches[-1]
            tail=version_match.group(3);version=f"{version_match.group(1)}.{version_match.group(2)}.{tail}"
            if not normalize_dlink_version(version):continue
            href=urljoin(url,link["href"])
            if upper.endswith((".BIN",".HEX",".IMG",".ZIP",".RAR")):firmware.append((version,href,name))
            elif "RELEASE" in upper and upper.endswith(".PDF"):notes[version]=href
        if not firmware:return None
        version,download,filename=max(firmware,key=lambda x:normalize_dlink_version(x[0])[1])
        return version,download,notes.get(version),filename

    def _get_sync(self,url):
        self.validate_source(url)
        request=Request(url,headers={"User-Agent":"Firmware Monitor/1.0"})
        context=ssl.create_default_context()
        context.maximum_version=ssl.TLSVersion.TLSv1_2
        # ftp.dlink.ru still negotiates a legacy TLS 1.2 cipher suite.
        # Keep certificate and hostname verification enabled while lowering
        # only the OpenSSL cipher security level for this allowlisted host.
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        last_error=None
        for attempt in range(3):
            try:
                with urlopen(request,timeout=settings.request_timeout_seconds,context=context) as response:
                    final_url=response.geturl();self.validate_source(final_url)
                    content=response.read(settings.max_response_bytes+1)
                    if len(content)>settings.max_response_bytes:raise ValueError("Ответ официального источника слишком велик")
                    return content.decode(response.headers.get_content_charset() or "utf-8",errors="replace"),final_url,response.status
            except (OSError,ConnectionError) as exc:
                last_error=exc
                if attempt<2:time.sleep(.35*(attempt+1))
        raise last_error

    async def fetch(self,vendor,model):
        start=monotonic();revision="REVA"
        try:
            selected=next((item for item in model.hardware_revisions if item.enabled),None)
            if not selected:raise LookupError("Аппаратная ревизия не настроена")
            revision=selected.provider_revision
            html,response_url,status_code=await asyncio.to_thread(self._get_sync,selected.firmware_path)
        except LookupError as exc:
            checked=datetime.now(timezone.utc);return FirmwareResult(vendor.name,model.name,None,None,model.firmware_page_url,None,None,None,checked,"Прошивка не найдена",str(exc),source_status="firmware_not_found",provider_revision=revision,response_time_ms=int((monotonic()-start)*1000))
        except Exception as exc:raise RuntimeError("Официальный источник D-Link недоступен") from exc
        found=self.parse(html,response_url,revision,model.name);checked=datetime.now(timezone.utc);elapsed=int((monotonic()-start)*1000)
        if not found:return FirmwareResult(vendor.name,model.name,None,None,response_url,None,None,None,checked,"Прошивка не найдена",f"Для {model.name} прошивка не найдена",source_status="firmware_not_found",provider_revision=revision,http_status=status_code,response_time_ms=elapsed)
        version,download,changelog,filename=found;self.validate_source(download)
        if changelog:self.validate_source(changelog)
        return FirmwareResult(vendor.name,model.name,version,None,response_url,download,None,None,checked,"Прошивка найдена",None,changelog,None,filename,"ok",revision,status_code,elapsed)
