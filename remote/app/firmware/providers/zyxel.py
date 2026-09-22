from datetime import datetime, timezone
from time import monotonic
from urllib.parse import urljoin
import re

import httpx
from bs4 import BeautifulSoup

from ...config import settings
from ...versioning import normalize_zyxel_version
from .base import FirmwareProvider, FirmwareResult


class ZyxelFirmwareProvider(FirmwareProvider):
    allowed_domains=("zyxel.com","download.zyxel.com","community.zyxel.com")

    @staticmethod
    def parse(html:str,url:str,model_name:str="GS1900-8"):
        soup=BeautifulSoup(html,"html.parser");items=[];notes={}
        exact_model=re.compile(r"(?<![A-Z0-9-])GS1900-8(?!HP|[A-Z0-9-])",re.I)
        version_re=re.compile(r"V?\d+\.\d+\(AAHH\.\d+\)C\d+",re.I)
        for link in soup.find_all("a",href=True):
            context=" ".join((link.get_text(" ",strip=True),link["href"]))
            if not exact_model.search(context):continue
            match=version_re.search(context)
            if not match or not normalize_zyxel_version(match.group(0)):continue
            href=urljoin(url,link["href"]);lower=context.lower();version=match.group(0)
            if "release" in lower or "changelog" in lower or href.lower().endswith(".pdf"):notes[version]=href
            elif href.lower().endswith((".zip",".bin",".bix")):items.append((version,href,href.split("/")[-1]))
        if not items:return None
        version,download,filename=max(items,key=lambda x:normalize_zyxel_version(x[0])[1])
        return version,download,notes.get(version),filename

    async def fetch(self,vendor,model):
        url=model.firmware_page_url;self.validate_source(url);start=monotonic();timeout=httpx.Timeout(settings.request_timeout_seconds,connect=min(5,settings.request_timeout_seconds))
        try:
            async with httpx.AsyncClient(timeout=timeout,follow_redirects=True,max_redirects=3,headers={"User-Agent":"Firmware Monitor/1.0"}) as client:response=await client.get(url)
            self.validate_source(str(response.url));response.raise_for_status()
            if len(response.content)>settings.max_response_bytes:raise ValueError("Ответ официального источника слишком велик")
        except Exception as exc:raise RuntimeError("Официальный источник Zyxel недоступен") from exc
        found=self.parse(response.text,str(response.url),model.name);checked=datetime.now(timezone.utc);elapsed=int((monotonic()-start)*1000)
        if not found:return FirmwareResult(vendor.name,model.name,None,None,str(response.url),None,None,None,checked,"Совместимость не подтверждена","Файл GS1900-8 с кодом AAHH не найден",source_status="compatibility_unconfirmed",http_status=response.status_code,response_time_ms=elapsed)
        version,download,changelog,filename=found;self.validate_source(download)
        if changelog:self.validate_source(changelog)
        return FirmwareResult(vendor.name,model.name,version,None,str(response.url),download,None,None,checked,"Прошивка найдена",None,changelog,None,filename,"ok",None,response.status_code,elapsed)
