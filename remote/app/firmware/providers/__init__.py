from .qtech import QtechFirmwareProvider
from .eltex import EltexFirmwareProvider
from .dlink import DlinkFirmwareProvider
from .mikrotik import MikrotikFirmwareProvider
from .zyxel import ZyxelFirmwareProvider

PROVIDERS = {"qtech": QtechFirmwareProvider, "eltex": EltexFirmwareProvider, "d-link": DlinkFirmwareProvider, "mikrotik": MikrotikFirmwareProvider, "zyxel": ZyxelFirmwareProvider}

def provider_for(slug: str):
    provider = PROVIDERS.get(slug)
    return provider() if provider else None
