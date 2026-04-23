from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pysm.api.app import create_app


def test_api_load_includes_running_script_processes(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "load_probe.py"
    script.write_text("import time\nprint('load-test', flush=True)\ntime.sleep(5)\n", encoding="utf-8")
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    started = container.runtime.start_script(record.id)
    assert started.status == "started"

    try:
        client = TestClient(create_app(container))
        response = client.get("/api/load")
        assert response.status_code == 200
        payload = response.json()
        process = next(
            (item for item in payload["processes"] if item["script_id"] == record.id),
            None,
        )
        assert process is not None
        assert process["pid"] == started.pid
    finally:
        if record.id in container.runtime.active_sessions:
            container.runtime.stop_script(record.id)
