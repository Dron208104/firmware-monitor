import asyncio
import ipaddress
import re

from .config import settings


_LATENCY = re.compile(r"time[=<]([0-9]+(?:[.,][0-9]+)?)\s*ms", re.IGNORECASE)


async def ping_address(address: str) -> tuple[bool, str]:
    """Perform one bounded ICMP echo check without invoking a shell."""
    target = str(ipaddress.ip_address(address))
    timeout = max(1, min(int(settings.ping_timeout_seconds), 10))
    try:
        process = await asyncio.create_subprocess_exec(
            "ping", "-n", "-c", "1", "-W", str(timeout), target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout + 2)
    except FileNotFoundError:
        return False, "Утилита ping недоступна на сервере"
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return False, f"Нет ответа по ICMP за {timeout} сек."

    output = stdout.decode("utf-8", errors="replace")
    if process.returncode == 0:
        latency = _LATENCY.search(output)
        return True, f"Ответ получен, задержка {latency.group(1).replace(',', '.')} мс" if latency else "Ответ получен"
    return False, f"Нет ответа по ICMP за {timeout} сек."
