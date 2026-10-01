import asyncio
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.availability import ping_address


class FakeProcess:
    def __init__(self, returncode=0, output=b""):
        self.returncode = returncode
        self.output = output

    async def communicate(self):
        return self.output, b""

    def kill(self):
        self.returncode = -9


def test_ping_reports_latency_and_uses_no_shell(monkeypatch):
    captured = []

    async def create(*args, **kwargs):
        captured.extend(args)
        return FakeProcess(output=b"64 bytes from 192.0.2.1: time=1.25 ms")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    ok, message = asyncio.run(ping_address("192.0.2.1"))
    assert ok is True
    assert message == "Ответ получен, задержка 1.25 мс"
    assert captured[-1] == "192.0.2.1"


def test_ping_rejects_non_ip_input_before_process_start(monkeypatch):
    called = False

    async def create(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    with pytest.raises(ValueError):
        asyncio.run(ping_address("127.0.0.1; whoami"))
    assert called is False
