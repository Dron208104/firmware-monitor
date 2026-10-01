from pathlib import Path


ROOT = Path(__file__).parents[1]
THEME_CSS = (ROOT / "app/static/theme.css").read_text(encoding="utf-8")
THEME_JS = (ROOT / "app/static/theme.js").read_text(encoding="utf-8")
THEME_INIT = (ROOT / "app/static/theme-init.js").read_text(encoding="utf-8")


def test_theme_switch_is_temporarily_hidden_and_dark_theme_is_forced():
    assert '.theme-toggle{display:none!important}' in THEME_CSS
    assert 'localStorage.removeItem("firmware-theme")' in THEME_INIT
    assert 'root.dataset.theme = "dark"' in THEME_JS


def test_light_theme_has_readable_text_and_component_surfaces():
    assert '--text:#1b2027' in THEME_CSS
    assert 'html[data-theme="light"] th{background:#f5f7f9;color:#5f6976}' in THEME_CSS
    assert 'html[data-theme="light"] td{color:#303842}' in THEME_CSS
    assert 'html[data-theme="light"] .device strong' in THEME_CSS
    assert 'html[data-theme="light"] .modal-card' in THEME_CSS
    assert 'html[data-theme="light"] .settings-card' in THEME_CSS
    assert 'html[data-theme="light"] .action-menu' in THEME_CSS


def test_all_page_shells_load_current_theme_assets():
    for name in ("base.html", "login.html", "change_password.html"):
        html = (ROOT / "app/templates" / name).read_text(encoding="utf-8")
        assert '/static/theme-init.js?v=3' in html
        assert '/static/theme.css?v=3' in html
        assert '/static/theme.js?v=3' in html
