from pathlib import Path

JS=(Path(__file__).parents[1]/"app"/"static"/"app.js").read_text(encoding="utf-8")
CSS=(Path(__file__).parents[1]/"app"/"static"/"style.css").read_text(encoding="utf-8")

def test_firmware_actions_depend_on_backend_urls():
    assert "if(device.download_url)" in JS
    assert "if(device.changelog_url)" in JS
    assert "link.href=device.download_url" in JS
    assert "link.href=device.changelog_url" in JS
    assert "WEB" not in JS and "'DL'" not in JS and "'LOG'" not in JS

def test_external_actions_are_safe_and_accessible():
    assert "noopener noreferrer" in JS
    assert "aria-label" in JS
    assert "Скачать прошивку ${device.available_version}" in JS
    assert "Посмотреть изменения в версии ${device.available_version}" in JS

def test_rare_actions_are_in_more_menu_and_narrow_layout_exists():
    assert "action-more" in JS and "Страница производителя" in JS and "Удалить устройство" in JS
    assert "@media(max-width:1180px)" in CSS
    assert ".firmware-download span,.row-actions .firmware-changelog span{display:none}" in CSS

def test_check_button_has_busy_state():
    assert "button.disabled=true" in JS and "button.disabled=false" in JS
    assert "Проверяем сайт производителя…" in JS
