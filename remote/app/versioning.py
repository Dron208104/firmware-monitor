import re
from packaging.version import Version, InvalidVersion

def normalized(value: str) -> Version:
    cleaned = re.sub(r"^[vV]", "", value.strip()).replace("_", ".")
    match = re.search(r"\d+(?:\.\d+)+(?:[-.]?[A-Za-z0-9]+)?", cleaned)
    if not match: raise InvalidVersion(value)
    return Version(match.group(0))

def compare(installed: str | None, available: str | None) -> str:
    if not installed: return "Версия не указана"
    if not available: return "Не удалось проверить источник"
    try: return "Доступно обновление" if normalized(available) > normalized(installed) else "Актуальная версия"
    except InvalidVersion: return "Не удалось проверить источник"

def compare_manual(installed: str, available: str) -> str:
    qtech_left, qtech_right = normalize_qtech_os12(installed), normalize_qtech_os12(available)
    if qtech_left or qtech_right:
        if not qtech_left or not qtech_right: return "Версия не определена"
        if qtech_left == qtech_right: return "Актуально"
        return "Есть обновление" if qtech_left < qtech_right else "Требуется проверка"
    pattern = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")
    left, right = pattern.fullmatch(installed.strip()), pattern.fullmatch(available.strip())
    if not left or not right: return "Версия не определена"
    a=[int(x) for x in left.group(1).split(".")]; b=[int(x) for x in right.group(1).split(".")]
    length=max(len(a),len(b)); a.extend([0]*(length-len(a))); b.extend([0]*(length-len(b)))
    if a==b: return "Актуально"
    if a<b: return "Есть обновление"
    return "Требуется проверка"

def _compare_keys(left, right) -> str:
    if left == right: return "Актуально"
    return "Есть обновление" if left < right else "Требуется проверка"

def compare_for_vendor(vendor: str | None, installed: str, available: str) -> str:
    """Compare versions using a vendor format without weakening model compatibility checks."""
    slug=(vendor or "").strip().lower()
    if slug=="eltex":
        left,right=normalize_eltex_version(installed),normalize_eltex_version(available)
        if left and right:return _compare_keys(left[1],right[1])
        return "Версия не определена"
    if slug=="zyxel":
        right=normalize_zyxel_version(available)
        left=normalize_zyxel_version(installed)
        if right and left:return _compare_keys(left[1],right[1])
        short=re.fullmatch(r"\s*[vV]?(\d+)(?:\.(\d+))?\s*",installed)
        if right and short:
            short_key=(int(short.group(1)),int(short.group(2) or 0),0,0)
            return _compare_keys(short_key,right[1])
        return "Версия не определена"
    return compare_manual(installed,available)

def normalize_qtech_os12(value: str | None) -> tuple[int,int,int,int,int] | None:
    if not value: return None
    match=re.fullmatch(r"\s*(\d+)\.(\d+)\((\d+)\)B(\d+)(?:S(\d+))?\s*",value,re.I)
    if not match: return None
    major,minor,revision,build,service=match.groups()
    return int(major),int(minor),int(revision),int(build),int(service or 0)

def normalize_eltex_version(value: str | None):
    if not value: return None
    match=re.fullmatch(r"\s*[vV]?(\d+(?:\.\d+){2,3})(?:\s+[rR](\d+))?\s*",value)
    return (value.strip(),tuple(int(x) for x in match.group(1).split('.'))+(int(match.group(2) or 0),),f"R{match.group(2)}" if match and match.group(2) else None) if match else None

def normalize_dlink_version(value: str | None):
    if not value: return None
    match=re.fullmatch(r"\s*[vV]?(\d+)\.(\d+)\.(?:(\d+)|[bB](\d+))\s*",value)
    if not match:return None
    major,minor,numeric,build=match.groups()
    return value.strip(),(int(major),int(minor),int(numeric or build))

def normalize_zyxel_version(value: str | None):
    if not value:return None
    match=re.fullmatch(r"\s*[vV]?(\d+)\.(\d+)\(AAHH\.(\d+)\)C(\d+)\s*",value,re.I)
    return (value.strip(),tuple(int(x) for x in match.groups())) if match else None
