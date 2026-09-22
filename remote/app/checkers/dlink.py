def matches(vendor: str, model: str, revision: str | None = None) -> bool:
    return vendor.upper() == "D-LINK" and model.upper() == "DGS-1100-08V2" and bool(revision)

