from datetime import datetime, timezone
import re
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from ...config import settings
from ...versioning import normalized
from .base import FirmwareProvider, FirmwareResult
class QtechFirmwareProvider(FirmwareProvider):
    allowed_domains=("ftp.qtech.ru",)

    @staticmethod
    def parse(html:str,url:str):
        soup=BeautifulSoup(html,"html.parser"); candidates=[]; changelogs={}
        for link in soup.find_all("a",href=True):
            name=link.get_text(strip=True); href=urljoin(url,link["href"])
            version=re.search(r"(?<!\d)(\d+(?:\.\d+){2,})(?!\d)",name)
            if not version: continue
            if name.lower().endswith("changelog.txt"): changelogs[version.group(1)]=href; continue
            if not name.lower().endswith((".img",".bin")): continue
            row=link.find_parent("tr"); text=row.get_text(" ",strip=True) if row else (link.parent.get_text(" ",strip=True) if link.parent else "")
            stamp=re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})",text)
            changed=datetime.strptime(" ".join(stamp.groups()),"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) if stamp else None
            size_match=re.search(r"\b(\d+(?:\.\d+)?)\s*([KMG])?\b\s*$",text,re.I); size=None
            if size_match:
                factor={None:1,"K":1024,"M":1024**2,"G":1024**3}[size_match.group(2).upper() if size_match.group(2) else None]; size=int(float(size_match.group(1))*factor)
            candidates.append((version.group(1),href,changed,size))
        if not candidates: return None
        version,download,changed,size=max(candidates,key=lambda item:normalized(item[0]))
        return version,download,changelogs.get(version),changed,size

    async def fetch(self,vendor,model):
        url=model.firmware_page_url; self.validate_source(url); redirects=0
        timeout=httpx.Timeout(settings.request_timeout_seconds,connect=min(5,settings.request_timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,headers={"User-Agent":"Firmware Monitor/1.0"}) as client:
            while True:
                async with client.stream("GET",url) as response:
                    if response.status_code in {301,302,303,307,308}:
                        if redirects>=3 or not response.headers.get("location"): raise ValueError("Небезопасное или слишком длинное перенаправление")
                        url=urljoin(url,response.headers["location"]); self.validate_source(url); redirects+=1; continue
                    response.raise_for_status(); chunks=[]; total=0
                    async for chunk in response.aiter_bytes():
                        total+=len(chunk)
                        if total>settings.max_response_bytes: raise ValueError("Ответ официального источника слишком велик")
                        chunks.append(chunk)
                    html=b"".join(chunks).decode(response.encoding or "utf-8",errors="replace"); break
        found=self.parse(html,url); checked=datetime.now(timezone.utc)
        if not found: return FirmwareResult(vendor.name,model.name,None,None,url,None,None,None,checked,"Ошибка проверки производителя","В каталоге не найдены подтверждённые файлы прошивки")
        version,download,changelog,changed,size=found
        self.validate_source(download)
        if changelog: self.validate_source(changelog)
        return FirmwareResult(vendor.name,model.name,version,changed,url,download,None,None,checked,"Проверка завершена",None,changelog,size)
