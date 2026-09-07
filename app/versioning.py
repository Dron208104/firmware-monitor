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
    pattern = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")
    left, right = pattern.fullmatch(installed.strip()), pattern.fullmatch(available.strip())
    if not left or not right: return "Версия не определена"
    a=[int(x) for x in left.group(1).split(".")]; b=[int(x) for x in right.group(1).split(".")]
    length=max(len(a),len(b)); a.extend([0]*(length-len(a))); b.extend([0]*(length-len(b)))
    if a==b: return "Актуально"
    if a<b: return "Есть обновление"
    return "Требуется проверка"
