def matches(vendor: str, model: str, revision: str | None = None) -> bool:
    return vendor.upper() == "ELTEX" and model.upper() == "MES2428P"

