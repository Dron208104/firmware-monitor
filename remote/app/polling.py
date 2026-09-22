from .snmp import test_snmp
from .ssh_poll import test_ssh

async def test_connection(device):
    if device.acquisition_method == "manual": return True, "Ручной режим не требует подключения"
    if not device.profile: return False, "Не выбран профиль подключения"
    # Реальный опрос выполняется только по явной кнопке пользователя.
    if device.acquisition_method == "ssh": return await test_ssh(device, device.profile)
    return await test_snmp(device, device.profile)
