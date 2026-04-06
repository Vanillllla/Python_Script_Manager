from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "PythonScriptManager"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1511
DEFAULT_TERMINAL_BUFFER = 1_048_576


def resolve_app_home() -> Path:
    explicit = os.environ.get("PYSM_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class AppPaths:
    root: Path
    data_dir: Path
    logs_dir: Path
    runtimes_dir: Path
    web_assets_dir: Path
    database_path: Path
    pid_file: Path

    @classmethod
    def create(cls) -> "AppPaths":
        root = resolve_app_home()
        data_dir = root / "data"
        logs_dir = root / "logs"
        runtimes_dir = root / "runtimes"
        web_assets_dir = root / "src" / "pysm" / "web"
        database_path = data_dir / "pysm.sqlite3"
        pid_file = data_dir / "manager.pid"
        for path in (data_dir, logs_dir, runtimes_dir):
            path.mkdir(parents=True, exist_ok=True)
        return cls(
            root=root,
            data_dir=data_dir,
            logs_dir=logs_dir,
            runtimes_dir=runtimes_dir,
            web_assets_dir=web_assets_dir,
            database_path=database_path,
            pid_file=pid_file,
        )


@dataclass(slots=True)
class AppSettings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    auto_open_browser: bool = True
    manager_autostart: bool = False
    install_root: str | None = None
    terminal_buffer_bytes: int = DEFAULT_TERMINAL_BUFFER

    @classmethod
    def from_mapping(cls, mapping: dict[str, object], root: Path) -> "AppSettings":
        install_root = mapping.get("install_root")
        return cls(
            host=str(mapping.get("host", DEFAULT_HOST)),
            port=int(mapping.get("port", DEFAULT_PORT)),
            auto_open_browser=_as_bool(mapping.get("auto_open_browser", True)),
            manager_autostart=_as_bool(mapping.get("manager_autostart", False)),
            install_root=str(install_root) if install_root else str(root),
            terminal_buffer_bytes=int(
                mapping.get("terminal_buffer_bytes", DEFAULT_TERMINAL_BUFFER)
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "auto_open_browser": self.auto_open_browser,
            "manager_autostart": self.manager_autostart,
            "install_root": self.install_root,
            "terminal_buffer_bytes": self.terminal_buffer_bytes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=True, sort_keys=True)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

