from types import SimpleNamespace
import asyncio

import pytest

from app import snmp


@pytest.mark.parametrize(("raw", "pattern", "expected"), (
    ("12.6(3)B0703S2", None, "12.6(3)B0703S2"),
    ("QTECH QSW-4700 Software Version 12.6(3)B0703S2, Build 2026", None, "12.6(3)B0703S2"),
    ("MES2428P 10.3.2.2", None, "10.3.2.2"),
    ("Zyxel firmware: V2.90(AAHH.2)C0", None, "V2.90(AAHH.2)C0"),
    ("release=custom-7.2", r"release=([A-Za-z0-9.-]+)", "custom-7.2"),
))
def test_extract_version_keeps_only_version(raw, pattern, expected):
    assert snmp.extract_version(raw, pattern) == expected


def test_extract_version_rejects_ambiguous_and_nonmatching_values():
    with pytest.raises(snmp.SnmpPollingError, match="однозначно"):
        snmp.extract_version("versions 1.2.3 and 2.3.4")
    with pytest.raises(snmp.SnmpPollingError, match="не соответствует"):
        snmp.extract_version("Firmware release unknown", r"Version ([0-9.]+)")


def test_read_installed_version_uses_single_configured_oid(monkeypatch):
    profile = SimpleNamespace(snmp_version="2c", port=1161, timeout_seconds=3, retries=2)
    model = SimpleNamespace(version_oid="1.3.6.1.4.1.999.1.0", installed_version_pattern=r"Version ([0-9.]+)")
    device = SimpleNamespace(profile=profile, catalog_model=model, ip_address="192.0.2.40")
    calls = []

    async def target(address, **options):
        calls.append((address, options))
        return "target"

    class Value:
        def prettyPrint(self):
            return "Switch OS Version 8.2.1.256 build 44"

    async def get(*args, **kwargs):
        calls.append((args, kwargs))
        return None, 0, 0, ((None, Value()),)

    monkeypatch.setattr(snmp, "profile_secrets", lambda _profile: {"community": "secret"})
    monkeypatch.setattr(snmp.UdpTransportTarget, "create", target)
    monkeypatch.setattr(snmp, "get_cmd", get)
    assert asyncio.run(snmp.read_installed_version(device)) == "8.2.1.256"
    assert calls[0] == (("192.0.2.40", 1161), {"timeout": 3.0, "retries": 2})
    assert len(calls) == 2
