import asyncio
from .security import decrypt_secret

def _connect(device, profile):
    from netmiko import ConnectHandler
    connection = ConnectHandler(
        device_type="autodetect", host=device.ip_address,
        username=profile.username, password=decrypt_secret(profile.secret_encrypted),
        port=profile.port or 22, timeout=8,
    )
    connection.disconnect()

async def test_ssh(device, profile) -> tuple[bool, str]:
    if not profile: return False, "Не выбран SSH-профиль"
    try:
        await asyncio.wait_for(asyncio.to_thread(_connect, device, profile), timeout=10)
        return True, "SSH-подключение успешно"
    except Exception as exc:
        return False, f"Устройство недоступно: {type(exc).__name__}"

