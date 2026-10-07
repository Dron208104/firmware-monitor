from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_source_urls_are_safe_external_links():
    with TestClient(app) as client:
        response = client.get("/settings?tab=sources")

        assert response.status_code == 200
        assert 'class="source-url"' in response.text
        assert 'target="_blank"' in response.text
        assert 'rel="noopener noreferrer"' in response.text
        assert 'aria-label="Открыть сайт производителя' in response.text


def test_source_check_returns_updated_row_data():
    with TestClient(app) as client:
        client.get("/")
        sources = client.get("/api/firmware-sources").json()
        source_id = sources[0]["id"]
        response = client.post(
            f"/api/firmware-sources/{source_id}/test",
            json={"csrf": client.cookies.get("csrf")},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"]["last_status"] == "Конфигурация допустима"
        assert payload["source"]["last_checked_at"]


def test_equipment_model_links_use_product_or_firmware_page_and_are_never_empty():
    with TestClient(app) as client:
        response = client.get("/settings?tab=equipment")

        assert response.status_code == 200
        assert 'href=""' not in response.text
        assert 'aria-label="Открыть официальную страницу модели QSW-4610-28T-AC"' in response.text
        assert 'https://ftp.qtech.ru/Switch/Access/QSW-4610/' in response.text


def test_source_action_menu_is_viewport_positioned_on_narrow_screens():
    root = Path(__file__).parents[1]
    css = (root / "app/static/settings.css").read_text(encoding="utf-8")
    js = (root / "app/static/settings.js").read_text(encoding="utf-8")
    assert "width:min(210px,calc(100vw - 16px))" in css
    assert ".profile-actions summary{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px" in css
    assert ".settings-page .profile-actions summary.icon-action{border-color:#2a4059;background:#121d2b;color:#8fa8c2" in css
    assert '/static/settings.css?v=11' in (root / "app/templates/profiles.html").read_text(encoding="utf-8")
    assert "placeProfileMenu" in js
    assert "Math.min(rect.right-width,innerWidth-width-edge)" in js
