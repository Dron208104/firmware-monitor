from .qtech import QtechFirmwareProvider
from .eltex import EltexFirmwareProvider
from .dlink import DlinkFirmwareProvider

PROVIDERS = {"qtech": QtechFirmwareProvider, "eltex": EltexFirmwareProvider, "d-link": DlinkFirmwareProvider}

def provider_for(slug: str):
    provider = PROVIDERS.get(slug)
    return provider() if provider else None
