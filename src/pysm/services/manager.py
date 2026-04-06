from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from pysm.config import AppPaths, AppSettings


def manager_health_url(settings: AppSettings) -> str:
    return f"http://{settings.host}:{settings.port}/api/health"


def manager_is_running(settings: AppSettings, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(manager_health_url(settings), timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def spawn_detached_manager(paths: AppPaths, settings: AppSettings) -> int:
    command = [sys.executable, "-m", "pysm", "_run-manager"]
    if os.name == "nt":
        pid = _spawn_with_start_process(command, paths.root)
    else:
        env = dict(os.environ)
        env.setdefault("PYSM_HOME", str(paths.root))
        process = subprocess.Popen(
            command,
            cwd=str(paths.root),
            env=env,
            close_fds=True,
        )
        pid = process.pid
    paths.pid_file.write_text(json.dumps({"pid": pid}), encoding="utf-8")
    return pid


def wait_for_manager(settings: AppSettings, timeout_seconds: float = 15.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if manager_is_running(settings, timeout=1.0):
            return True
        time.sleep(0.25)
    return False


def read_pid(paths: AppPaths) -> int | None:
    if not paths.pid_file.exists():
        return None
    try:
        payload = json.loads(paths.pid_file.read_text(encoding="utf-8"))
        return int(payload["pid"])
    except (ValueError, OSError, KeyError, json.JSONDecodeError):
        return None


def clear_pid(paths: AppPaths) -> None:
    try:
        paths.pid_file.unlink(missing_ok=True)
    except OSError:
        pass


def _spawn_with_start_process(command: list[str], cwd: os.PathLike[str] | str) -> int:
    file_path = _ps_quote(command[0])
    arguments = ", ".join(_ps_quote(arg) for arg in command[1:])
    workdir = _ps_quote(str(cwd))
    script = (
        f"$p = Start-Process -FilePath {file_path} -ArgumentList {arguments} "
        f"-WorkingDirectory {workdir} -WindowStyle Hidden -PassThru; "
        "$p.Id"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip().splitlines()[-1])


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
