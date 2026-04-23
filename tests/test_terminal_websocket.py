from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from pysm.api.app import create_app


def test_terminal_websocket_streams_console_output(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "interactive.py"
    script.write_text(
        (
            "print('Interactive echo script started.', flush=True)\n"
            "value = input('> ')\n"
            "print(f'Echo: {value}', flush=True)\n"
        ),
        encoding="utf-8",
    )
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    start = container.runtime.start_script(record.id)
    assert start.status == "started"

    client = TestClient(create_app(container))
    with client.websocket_connect(f"/api/scripts/{record.id}/terminal") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        client.post(
            f"/api/scripts/{record.id}/terminal/input",
            json={"data": "hello websocket\n"},
        )
        deadline = time.time() + 10
        received = ""
        while time.time() < deadline:
            payload = websocket.receive_json()
            if payload["type"] == "chunk":
                received += payload["content"]
                if "Echo: hello websocket" in received:
                    break
        assert "Echo: hello websocket" in received
