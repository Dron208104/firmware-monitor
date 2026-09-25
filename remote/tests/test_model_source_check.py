from fastapi.testclient import TestClient

from app.main import app


def test_model_check_endpoint_and_button(monkeypatch):
    async def fake_check(db, model):
        model.latest_check_status = "Проверка завершена"
        db.commit()

    monkeypatch.setattr("app.main.check_model_source", fake_check)
    with TestClient(app) as client:
        client.get("/")
        vendor = next(v for v in client.get("/api/vendors").json() if v["slug"] == "qtech")
        model = client.get(f"/api/vendors/{vendor['id']}/models").json()[0]
        response = client.post(
            f"/api/models/{model['id']}/check-firmware",
            json={"csrf": client.cookies.get("csrf")},
        )

        assert response.status_code == 200
        assert response.json()["model"]["latest_check_status"] == "Проверка завершена"
        page = client.get("/settings?tab=equipment")
        assert f'data-check-model="{model["id"]}"' in page.text
        assert f"Проверить прошивку для модели {model['name']}" in page.text
        assert 'data-model-tooltip="Открыть источник"' in page.text
        assert 'data-model-tooltip="Проверить модель"' in page.text
