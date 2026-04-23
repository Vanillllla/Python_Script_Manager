from fastapi.testclient import TestClient

from pysm.api.app import create_app


def test_settings_page_renders_english(container) -> None:
    container.settings.update_settings(language="en")
    client = TestClient(create_app(container))
    response = client.get("/settings")
    assert response.status_code == 200
    assert "Settings" in response.text
    assert "Language" in response.text


def test_settings_page_renders_russian(container) -> None:
    container.settings.update_settings(language="ru")
    client = TestClient(create_app(container))
    response = client.get("/settings")
    assert response.status_code == 200
    assert "Настройки" in response.text
    assert "Язык" in response.text


def test_api_error_payload_is_localized(container) -> None:
    container.settings.update_settings(language="ru")
    client = TestClient(create_app(container))
    response = client.post("/api/scripts/999/stop")
    assert response.status_code == 404
    payload = response.json()
    assert payload["message_key"] == "errors.script.not_found"
    assert payload["detail"] == "Неизвестный ID скрипта: 999."
