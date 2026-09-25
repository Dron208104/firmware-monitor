import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .security import validate_public_url
from .firmware.providers.base import fetch_limited
from .checkers.qtech import matches as qtech_matches
from .checkers.eltex import matches as eltex_matches
from .checkers.dlink import matches as dlink_matches

SUPPORTED = {("QTECH", "QSW-4610-28T-AC"), ("ELTEX", "MES2428P"), ("D-LINK", "DGS-1100-08V2")}

class SourceError(RuntimeError): pass

async def latest_firmware(vendor: str, model: str, revision: str | None, url: str | None):
    key = (vendor.upper(), model.upper())
    basic_dlink = key == ("D-LINK", "DGS-1100-08V2")
    if basic_dlink and not revision: raise SourceError("Для D-Link требуется аппаратная ревизия")
    if not any((qtech_matches(vendor, model, revision), eltex_matches(vendor, model, revision), dlink_matches(vendor, model, revision))): raise SourceError("Модель не поддерживается")
    if not url: raise SourceError("Не задана официальная страница прошивок")
    validate_public_url(url)
    try:
        content,final_url,_,encoding=await fetch_limited(url,validate_public_url)
        html=content.decode(encoding,errors="replace")
    except SourceError: raise
    except Exception as exc: raise SourceError(f"Источник недоступен: {type(exc).__name__}") from exc
    soup = BeautifulSoup(html, "html.parser")
    haystack = soup.get_text(" ", strip=True)
    candidates = re.findall(r"(?i)(?:firmware|прошивк|software|version|версия)[^\n]{0,80}?\b[vV]?([0-9]+(?:[._-][0-9A-Za-z]+){1,5})", haystack)
    links = [(a.get_text(" ", strip=True), urljoin(final_url, a.get("href"))) for a in soup.select("a[href]") if re.search(r"(?i)firmware|прошив|\.bin|\.img|\.zip", a.get_text(" ", strip=True)+a.get("href", ""))]
    if revision:
        revision_links = [x for x in links if revision.lower() in (x[0]+x[1]).lower()]
        if revision_links: links = revision_links
    if not candidates: raise SourceError("Формат официальной страницы не распознан")
    return candidates[0], (links[0][1] if links else final_url)
