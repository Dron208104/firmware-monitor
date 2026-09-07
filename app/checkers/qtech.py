def matches(vendor: str, model: str, revision: str | None = None) -> bool:
    return vendor.upper() == "QTECH" and model.upper() == "QSW-4610-28T-AC"

