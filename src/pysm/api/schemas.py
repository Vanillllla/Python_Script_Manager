from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionResponse(BaseModel):
    status: str
    message: str
    message_key: str
    message_params: dict[str, Any] = Field(default_factory=dict)


class ScriptCreatedResponse(ActionResponse):
    id: int
    name: str


class RemovalResponse(ActionResponse):
    removed: int


class ScriptStartRequest(BaseModel):
    install_missing: bool = False


class ScriptCreateRequest(BaseModel):
    script_path: str
    interpreter_env_id: int | None = None
    autostart: bool = False


class ScriptsDeleteRequest(BaseModel):
    script_ids: list[int] = Field(default_factory=list)


class StartScriptResponse(ActionResponse):
    missing_modules: list[str] = Field(default_factory=list)
    run_id: int | None = None
    pid: int | None = None


class ScriptResponse(BaseModel):
    id: int
    name: str
    script_path: str
    cwd: str
    interpreter_env_id: int | None = None
    autostart: bool
    desired_state: str
    last_error: str | None = None
    last_error_key: str | None = None
    last_error_params: dict[str, Any] = Field(default_factory=dict)
    status: str
    status_label: str
    pause_state: str
    pid: int | None = None
    exit_code: int | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None


class TerminalSnapshotResponse(BaseModel):
    sequence: int
    content: str
    backend: str
    is_running: bool
    pid: int | None = None
    exit_code: int | None = None


class TerminalInputRequest(BaseModel):
    data: str = ""


class InterpreterResponse(BaseModel):
    id: int
    label: str
    kind: str
    version: str
    arch: str
    python_exe: str
    source_path: str | None = None
    status: str


class InterpreterCreateRequest(BaseModel):
    python_exe: str
    label: str | None = None


class InterpreterMutationResponse(ActionResponse):
    interpreter: InterpreterResponse


class EnvironmentResponse(BaseModel):
    id: int
    base_interpreter_id: int
    env_path: str
    python_exe: str
    display_name: str
    status: str


class EnvironmentInstallRequest(BaseModel):
    base_interpreter_id: int
    name: str | None = None


class EnvironmentMutationResponse(ActionResponse):
    environment: EnvironmentResponse


class EnvironmentSelectionRequest(BaseModel):
    script_id: int
    environment_id: int


class EnvironmentSelectionResponse(ActionResponse):
    script_id: int
    environment_id: int


class InterpretersResponse(BaseModel):
    interpreters: list[InterpreterResponse]
    environments: list[EnvironmentResponse]


class SystemLoadResponse(BaseModel):
    cpu_percent: float | None = None
    memory_percent: float | None = None
    processes: list[dict[str, Any]] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    host: str
    port: int
    auto_open_browser: bool
    manager_autostart: bool
    install_root: str | None = None
    terminal_buffer_bytes: int
    language: Literal["en", "ru"]


class SettingsUpdateRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    auto_open_browser: bool | None = None
    manager_autostart: bool | None = None
    install_root: str | None = None
    terminal_buffer_bytes: int | None = None
    language: Literal["en", "ru"] | None = None


class HealthResponse(BaseModel):
    status: str
    host: str
    port: int
    pid: int | None = None
    running_scripts: int


class ManagerAutostartRequest(BaseModel):
    enabled: bool = False


class ScriptAutostartRequest(BaseModel):
    script_id: int
    enabled: bool = False
