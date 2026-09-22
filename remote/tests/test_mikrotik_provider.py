from app.firmware.providers.mikrotik import MikrotikFirmwareProvider
from app.firmware.providers.qtech import QtechFirmwareProvider
from app.versioning import compare_manual, normalize_qtech_os12


def test_mikrotik_long_term_version_and_arm_package_are_parsed():
    html = '''<div wire:snapshot="{&quot;channel&quot;:&quot;longTerm&quot;,&quot;version&quot;:&quot;7.23.7&quot;}">
    <a href="https://download.mikrotik.com/routeros/7.23.7/routeros-7.23.7-arm.npk">RouterOS</a></div>'''
    assert MikrotikFirmwareProvider.parse(html, "arm") == (
        "7.23.7",
        "https://download.mikrotik.com/routeros/7.23.7/routeros-7.23.7-arm.npk",
    )


def test_mikrotik_ignores_stable_and_builds_only_long_term_package():
    html = '&quot;channel&quot;:&quot;stable&quot;,&quot;version&quot;:&quot;7.24.4&quot; &quot;channel&quot;:&quot;longTerm&quot;,&quot;version&quot;:&quot;7.23.7&quot;'
    assert MikrotikFirmwareProvider.parse(html, "arm") == (
        "7.23.7",
        "https://download.mikrotik.com/routeros/7.23.7/routeros-7.23.7-arm.npk",
    )


def test_mikrotik_rejects_page_without_long_term_channel():
    assert MikrotikFirmwareProvider.parse('"channel":"stable","version":"7.24.4"', "arm") is None


def test_qtech_os12_version_is_parsed():
    html = '''<table><tr><td><a href="QSW-6910_OS12.6(3)B0703S2_12231813_install.bin">QSW-6910_OS12.6(3)B0703S2_12231813_install.bin</a></td><td>2025-11-19 12:25</td><td>97M</td></tr>
    <tr><td><a href="QSW-6910_OS12.6(3)B0703S2_12231813_install.bin_changelog.txt">QSW-6910_OS12.6(3)B0703S2_12231813_install.bin_changelog.txt</a></td><td>2026-02-27 13:25</td></tr></table>'''
    result = QtechFirmwareProvider.parse(html, "https://ftp.qtech.ru/Switch/Aggregation/QSW-6910/Firmware/", "os12")
    assert result[0] == "12.6(3)B0703S2"
    assert result[1].endswith("_install.bin")
    assert result[2].endswith("_changelog.txt")


def test_qtech_os12_normalization_and_comparison():
    assert compare_manual("12.6(3)B0703S2", "12.6(3)B0703S2") == "Актуально"
    assert compare_manual(" 12.6(3)b0703s2 ", "12.6(3)B0703S2") == "Актуально"
    assert compare_manual("12.6(2)B0703S2", "12.6(3)B0703S2") == "Есть обновление"
    assert compare_manual("12.6(3)B0702S9", "12.6(3)B0703S2") == "Есть обновление"
    assert compare_manual("12.6(3)B0703S1", "12.6(3)B0703S2") == "Есть обновление"
    assert normalize_qtech_os12("12.6(3)B0703") == (12, 6, 3, 703, 0)
    assert compare_manual("повреждено", "12.6(3)B0703S2") == "Версия не определена"
    assert compare_manual("", "12.6(3)B0703S2") == "Версия не определена"
