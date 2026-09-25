from datetime import datetime, timezone
from time import monotonic
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup
from ...versioning import normalize_eltex_version
from .base import FirmwareProvider, FirmwareResult, fetch_limited

class EltexFirmwareProvider(FirmwareProvider):
    allowed_domains=("eltex-co.ru","eltex-co.com","eltex.ru","api.prod.eltex-co.ru")

    @staticmethod
    def parse(html:str,url:str,model_name:str="MES2428P"):
        soup=BeautifulSoup(html,"html.parser"); candidates=[]; notes={}
        if not re.search(rf"(?<![A-Z0-9-]){re.escape(model_name)}(?![A-Z0-9-])",soup.get_text(" ",strip=True),re.I):return None
        family_pattern={"MES2428P":r"MES(?:2400|24XX)","MES3400-24":r"MES(?:2400|24XX|3400)","MES2308R":r"MES(?:2300|23XX)","MES2300B-48":r"MES2300B"}.get(model_name.upper(),re.escape(model_name))
        for link in soup.find_all("a",href=True):
            label=link.get_text(" ",strip=True) or link["href"].split("/")[-1];asset_name=link["href"].split("/")[-1]
            context=label+" "+link["href"]
            version=re.search(r"(?<!\d)(\d+(?:\.\d+){2,3})(?!\d)",context)
            if not version or not normalize_eltex_version(version.group(1)): continue
            suffix=re.search(r"\bR(\d+)\b",context,re.I);display=version.group(1)+(f" R{suffix.group(1)}" if suffix else "")
            href=urljoin(url,link["href"]); lower=(label+" "+asset_name).lower()
            if any(x in lower for x in ("changelog","release","изменен")) or lower.endswith(".pdf"): notes[display]=href
            elif asset_name.lower().endswith((".bin",".tar.gz",".img",".zip")) and "mib" not in lower and ("версия по" in lower or re.search(family_pattern,context,re.I)): candidates.append((display,href,asset_name))
        if not candidates:return None
        version,download,filename=max(candidates,key=lambda x:normalize_eltex_version(x[0])[1])
        return version,download,notes.get(version),filename

    async def fetch(self,vendor,model):
        url=model.firmware_page_url;self.validate_source(url);start=monotonic()
        try:
            content,response_url,status_code,encoding=await fetch_limited(url,self.validate_source)
        except Exception as exc: raise RuntimeError("Официальный источник Eltex недоступен") from exc
        found=self.parse(content.decode(encoding,errors="replace"),response_url,model.name);checked=datetime.now(timezone.utc);elapsed=int((monotonic()-start)*1000)
        if not found:return FirmwareResult(vendor.name,model.name,None,None,response_url,None,None,None,checked,"Прошивка не найдена",f"Для модели {model.name} прошивка не найдена",source_status="firmware_not_found",http_status=status_code,response_time_ms=elapsed)
        version,download,changelog,filename=found
        if download:self.validate_source(download)
        if changelog:self.validate_source(changelog)
        source_status="ok" if download else "download_page_only";status="Прошивка найдена" if download else "Только страница загрузки"
        return FirmwareResult(vendor.name,model.name,version,None,response_url,download,None,None,checked,status,None if download else "Версия найдена, но ссылка скачивания недоступна",changelog,None,filename,source_status,None,status_code,elapsed)
