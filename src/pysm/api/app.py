from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pysm.api.schemas import (
    ActionResponse,
    EnvironmentInstallRequest,
    EnvironmentMutationResponse,
    EnvironmentResponse,
    EnvironmentSelectionRequest,
    EnvironmentSelectionResponse,
    HealthResponse,
    InterpreterCreateRequest,
    InterpreterMutationResponse,
    InterpreterResponse,
    InterpretersResponse,
    ManagerAutostartRequest,
    RemovalResponse,
    ScriptAutostartRequest,
    ScriptCreateRequest,
    ScriptCreatedResponse,
    ScriptResponse,
    ScriptsDeleteRequest,
    ScriptStartRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    StartScriptResponse,
    SystemLoadResponse,
    TerminalInputRequest,
    TerminalSnapshotResponse,
)
from pysm.domain.exceptions import PysmError
from pysm.domain.models import ActionResult, StartScriptResult, TerminalSnapshot
from pysm.services.context import ServiceContainer, build_container
from pysm.services.manager import clear_pid, read_pid

try:
    import psutil
except ImportError:  # pragma: no cover - optional in local dev before install
    psutil = None


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    services = container or build_container()
    templates = Jinja2Templates(directory=str(_templates_dir()))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = services
        app.state.monitor_task = asyncio.create_task(_monitor_processes(services))
        services.runtime.ensure_autostart_scripts()
        try:
            yield
        finally:
            app.state.monitor_task.cancel()
            clear_pid(services.paths)

    app = FastAPI(title="Python Script Manager", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_static_dir())), name="static")

    def render(template_name: str, request: Request, **context: Any) -> HTMLResponse:
        settings = services.settings.get_settings()
        locale = _request_locale(request, services)
        translator = lambda key, **params: services.i18n.translate(key, locale, **params)
        response = templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "request": request,
                "settings": settings,
                "locale": locale,
                "supported_locales": services.i18n.catalog_subset(
                    locale,
                    ["common.locale.en", "common.locale.ru"],
                ),
                "frontend_messages": services.i18n.build_frontend_messages(locale),
                "status_label": lambda status: services.i18n.status_label(str(status), locale),
                "tm": lambda message: services.i18n.translate_message(message, locale),
                "locale_name": lambda code: services.i18n.locale_name(code, locale),
                "bool_label": lambda enabled: translator(
                    "common.states.enabled" if enabled else "common.states.disabled"
                ),
                "t": translator,
                **context,
            },
        )
        response.set_cookie("pysm_lang", locale, samesite="lax")
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return render(
            "dashboard.html",
            request,
            scripts=services.runtime.list_scripts(),
            load=_system_load(),
            health=_health_payload(services),
        )

    @app.get("/scripts", response_class=HTMLResponse)
    async def scripts_page(request: Request) -> HTMLResponse:
        return render("scripts.html", request, scripts=services.runtime.list_scripts())

    @app.get("/scripts/{script_id}", response_class=HTMLResponse)
    async def script_detail(request: Request, script_id: int) -> HTMLResponse:
        script = services.runtime.get_script(script_id)
        return render("script_detail.html", request, script=script)

    @app.get("/interpreters", response_class=HTMLResponse)
    async def interpreters_page(request: Request) -> HTMLResponse:
        return render(
            "interpreters.html",
            request,
            interpreters=services.interpreters.list_interpreters(),
            environments=services.interpreters.list_environments(),
            scripts=services.runtime.list_scripts(),
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return render("settings.html", request, health=_health_payload(services))

    @app.get("/api/health", response_model=HealthResponse)
    async def api_health() -> HealthResponse:
        return HealthResponse.model_validate(_health_payload(services))

    @app.get("/api/scripts", response_model=list[ScriptResponse])
    async def api_scripts(request: Request) -> list[ScriptResponse]:
        locale = _request_locale(request, services)
        return [_script_payload(item, locale, services) for item in services.runtime.list_scripts()]

    @app.post("/api/scripts", response_model=ScriptCreatedResponse)
    async def api_add_script(request: Request, payload: ScriptCreateRequest) -> ScriptCreatedResponse:
        locale = _request_locale(request, services)
        record = services.runtime.add_script(
            script_path=payload.script_path,
            interpreter_env_id=payload.interpreter_env_id,
            autostart=payload.autostart,
        )
        return ScriptCreatedResponse(
            status="created",
            message=services.i18n.translate("scripts.added", locale),
            message_key="scripts.added",
            message_params={},
            id=record.id,
            name=record.name,
        )

    @app.delete("/api/scripts", response_model=RemovalResponse)
    async def api_remove_scripts(
        request: Request, payload: ScriptsDeleteRequest
    ) -> RemovalResponse:
        locale = _request_locale(request, services)
        removed = services.runtime.remove_scripts(payload.script_ids)
        return RemovalResponse(
            status="ok",
            message=services.i18n.translate("scripts.removed", locale, count=removed),
            message_key="scripts.removed",
            message_params={"count": removed},
            removed=removed,
        )

    @app.post("/api/scripts/{script_id}/start", response_model=StartScriptResponse)
    async def api_start_script(
        request: Request, script_id: int, payload: ScriptStartRequest
    ) -> StartScriptResponse:
        locale = _request_locale(request, services)
        result = services.runtime.start_script(script_id, install_missing=payload.install_missing)
        return _start_result_payload(result, locale, services)

    @app.post("/api/scripts/{script_id}/stop", response_model=ActionResponse)
    async def api_stop_script(request: Request, script_id: int) -> ActionResponse:
        locale = _request_locale(request, services)
        result = services.runtime.stop_script(script_id)
        return _action_payload(result, locale, services)

    @app.post("/api/scripts/{script_id}/pause", response_model=ActionResponse)
    async def api_pause_script(request: Request, script_id: int) -> ActionResponse:
        locale = _request_locale(request, services)
        result = services.runtime.pause_script(script_id)
        return _action_payload(result, locale, services)

    @app.post("/api/scripts/{script_id}/resume", response_model=ActionResponse)
    async def api_resume_script(request: Request, script_id: int) -> ActionResponse:
        locale = _request_locale(request, services)
        result = services.runtime.resume_script(script_id)
        return _action_payload(result, locale, services)

    @app.get("/api/scripts/{script_id}/console", response_model=TerminalSnapshotResponse)
    async def api_console(script_id: int) -> TerminalSnapshotResponse:
        snapshot = services.runtime.terminal_snapshot(script_id)
        return TerminalSnapshotResponse.model_validate(asdict(snapshot))

    @app.websocket("/api/scripts/{script_id}/terminal")
    async def api_terminal(websocket: WebSocket, script_id: int) -> None:
        locale = _websocket_locale(websocket, services)
        await websocket.accept()
        sequence = 0
        try:
            snapshot = services.runtime.terminal_snapshot(script_id)
            sequence = snapshot.sequence
            await websocket.send_json(
                {"type": "snapshot", **TerminalSnapshotResponse.model_validate(asdict(snapshot)).model_dump()}
            )
            if not snapshot.is_running:
                await websocket.close()
                return
            while True:
                for chunk_sequence, chunk_text in services.runtime.terminal_chunks_since(
                    script_id, sequence
                ):
                    sequence = chunk_sequence
                    await websocket.send_json(
                        {"type": "chunk", "sequence": sequence, "content": chunk_text}
                    )
                latest_snapshot = services.runtime.terminal_snapshot(script_id)
                if not latest_snapshot.is_running:
                    await websocket.close()
                    return
                await asyncio.sleep(0.15)
        except WebSocketDisconnect:
            return
        except PysmError as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": exc.code,
                    "message_key": exc.message.key,
                    "message": services.i18n.translate_message(exc.message, locale),
                }
            )
            await websocket.close()
        except Exception:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": services.i18n.translate("frontend.terminal.error", locale),
                }
            )
            await websocket.close()

    @app.post("/api/scripts/{script_id}/terminal/input", response_model=ActionResponse)
    async def api_terminal_input(
        request: Request, script_id: int, payload: TerminalInputRequest
    ) -> ActionResponse:
        locale = _request_locale(request, services)
        services.runtime.write_terminal_input(script_id, payload.data)
        return ActionResponse(
            status="ok",
            message=services.i18n.translate("api.status.ok", locale),
            message_key="api.status.ok",
            message_params={},
        )

    @app.get("/api/interpreters", response_model=InterpretersResponse)
    async def api_interpreters() -> InterpretersResponse:
        return InterpretersResponse(
            interpreters=[
                InterpreterResponse.model_validate(_interpreter_payload(item))
                for item in services.interpreters.list_interpreters()
            ],
            environments=[
                EnvironmentResponse.model_validate(_environment_payload(item))
                for item in services.interpreters.list_environments()
            ],
        )

    @app.post("/api/interpreters", response_model=InterpreterMutationResponse)
    async def api_add_interpreter(
        request: Request, payload: InterpreterCreateRequest
    ) -> InterpreterMutationResponse:
        locale = _request_locale(request, services)
        record = services.interpreters.add_interpreter(
            python_exe=payload.python_exe,
            label=payload.label,
        )
        return InterpreterMutationResponse(
            status="created",
            message=services.i18n.translate("interpreters.added", locale),
            message_key="interpreters.added",
            message_params={},
            interpreter=InterpreterResponse.model_validate(_interpreter_payload(record)),
        )

    @app.post("/api/interpreters/install", response_model=EnvironmentMutationResponse)
    async def api_install_environment(
        request: Request, payload: EnvironmentInstallRequest
    ) -> EnvironmentMutationResponse:
        locale = _request_locale(request, services)
        record = services.interpreters.install_environment(
            base_interpreter_id=payload.base_interpreter_id,
            name=payload.name,
        )
        return EnvironmentMutationResponse(
            status="created",
            message=services.i18n.translate("interpreters.environment_created", locale),
            message_key="interpreters.environment_created",
            message_params={},
            environment=EnvironmentResponse.model_validate(_environment_payload(record)),
        )

    @app.post("/api/interpreters/select", response_model=EnvironmentSelectionResponse)
    async def api_select_environment(
        request: Request, payload: EnvironmentSelectionRequest
    ) -> EnvironmentSelectionResponse:
        locale = _request_locale(request, services)
        record = services.interpreters.assign_environment_to_script(
            script_id=payload.script_id,
            environment_id=payload.environment_id,
        )
        return EnvironmentSelectionResponse(
            status="ok",
            message=services.i18n.translate("interpreters.environment_assigned", locale),
            message_key="interpreters.environment_assigned",
            message_params={},
            script_id=record.id,
            environment_id=record.interpreter_env_id or payload.environment_id,
        )

    @app.get("/api/interpreters/{environment_id}/modules")
    async def api_modules(environment_id: int) -> list[dict[str, str]]:
        return services.interpreters.list_modules(environment_id)

    @app.get("/api/load", response_model=SystemLoadResponse)
    async def api_load() -> SystemLoadResponse:
        return SystemLoadResponse.model_validate(_system_load())

    @app.get("/api/settings", response_model=SettingsResponse)
    async def api_settings() -> SettingsResponse:
        return SettingsResponse.model_validate(services.settings.get_settings().to_mapping())

    @app.put("/api/settings", response_model=SettingsResponse)
    async def api_update_settings(
        request: Request, response: Response, payload: SettingsUpdateRequest
    ) -> SettingsResponse:
        updated = services.settings.update_settings(**payload.model_dump(exclude_none=True))
        locale = _request_locale(request, services, settings_language=updated.language)
        response.set_cookie("pysm_lang", locale, samesite="lax")
        return SettingsResponse.model_validate(updated.to_mapping())

    @app.post("/api/autostart/manager", response_model=ActionResponse)
    async def api_manager_autostart(
        request: Request, payload: ManagerAutostartRequest
    ) -> ActionResponse:
        locale = _request_locale(request, services)
        if payload.enabled:
            services.autostart.enable_manager_autostart()
        else:
            services.autostart.disable_manager_autostart()
        services.settings.update_settings(manager_autostart=payload.enabled)
        key = (
            "autostart.manager.enabled"
            if payload.enabled
            else "autostart.manager.disabled"
        )
        return ActionResponse(
            status="enabled" if payload.enabled else "disabled",
            message=services.i18n.translate(key, locale),
            message_key=key,
            message_params={},
        )

    @app.post("/api/autostart/scripts", response_model=ActionResponse)
    async def api_script_autostart(
        request: Request, payload: ScriptAutostartRequest
    ) -> ActionResponse:
        locale = _request_locale(request, services)
        result = services.runtime.set_script_autostart(
            payload.script_id, payload.enabled
        )
        return _action_payload(result, locale, services)

    @app.exception_handler(PysmError)
    async def pysm_error_handler(request: Request, exc: PysmError) -> JSONResponse:
        locale = _request_locale(request, services)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "detail": services.i18n.translate_message(exc.message, locale),
                "message_key": exc.message.key,
                "message_params": exc.message.params,
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


async def _monitor_processes(container: ServiceContainer) -> None:
    while True:
        container.runtime.sync_active_processes()
        await asyncio.sleep(1.0)


def _templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "web" / "templates"


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "web" / "static"


def _system_load() -> dict[str, Any]:
    if psutil is None:
        return {"cpu_percent": None, "memory_percent": None, "processes": []}
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.0),
        "memory_percent": psutil.virtual_memory().percent,
        "processes": [],
    }


def _health_payload(services: ServiceContainer) -> dict[str, Any]:
    settings = services.settings.get_settings()
    return {
        "status": "ok",
        "host": settings.host,
        "port": settings.port,
        "pid": read_pid(services.paths),
        "running_scripts": len(services.runtime.active_sessions),
    }


def _request_locale(
    request: Request,
    services: ServiceContainer,
    *,
    settings_language: str | None = None,
) -> str:
    language = settings_language or services.settings.get_settings().language
    return services.i18n.resolve_web_locale(
        settings_locale=language,
        query_locale=request.query_params.get("lang"),
        cookie_locale=request.cookies.get("pysm_lang"),
        accept_language=request.headers.get("accept-language"),
        environment=os.environ,
    )


def _websocket_locale(websocket: WebSocket, services: ServiceContainer) -> str:
    settings = services.settings.get_settings()
    return services.i18n.resolve_web_locale(
        settings_locale=settings.language,
        query_locale=websocket.query_params.get("lang"),
        cookie_locale=websocket.cookies.get("pysm_lang"),
        accept_language=websocket.headers.get("accept-language"),
        environment=os.environ,
    )


def _action_payload(
    result: ActionResult,
    locale: str,
    services: ServiceContainer,
) -> ActionResponse:
    return ActionResponse(
        status=result.status,
        message=services.i18n.translate_message(result.message, locale) or result.message.key,
        message_key=result.message.key,
        message_params=result.message.params,
    )


def _start_result_payload(
    result: StartScriptResult,
    locale: str,
    services: ServiceContainer,
) -> StartScriptResponse:
    return StartScriptResponse(
        status=result.status,
        message=services.i18n.translate_message(result.message, locale) or result.message.key,
        message_key=result.message.key,
        message_params=result.message.params,
        missing_modules=result.missing_modules,
        run_id=result.run_id,
        pid=result.pid,
    )


def _script_payload(
    item: dict[str, Any],
    locale: str,
    services: ServiceContainer,
) -> ScriptResponse:
    last_error = item.get("last_error")
    return ScriptResponse(
        id=int(item["id"]),
        name=str(item["name"]),
        script_path=str(item["script_path"]),
        cwd=str(item["cwd"]),
        interpreter_env_id=item.get("interpreter_env_id"),
        autostart=bool(item["autostart"]),
        desired_state=str(item["desired_state"]),
        last_error=services.i18n.translate_message(last_error, locale),
        last_error_key=last_error.key if last_error else None,
        last_error_params=last_error.params if last_error else {},
        status=str(item["status"]),
        status_label=services.i18n.status_label(str(item["status"]), locale),
        pause_state=str(item["pause_state"]),
        pid=item.get("pid"),
        exit_code=item.get("exit_code"),
        cpu_percent=item.get("cpu_percent"),
        memory_percent=item.get("memory_percent"),
    )


def _interpreter_payload(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "label": item.label,
        "kind": item.kind,
        "version": item.version,
        "arch": item.arch,
        "python_exe": item.python_exe,
        "source_path": item.source_path,
        "status": item.status,
    }


def _environment_payload(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "base_interpreter_id": item.base_interpreter_id,
        "env_path": item.env_path,
        "python_exe": item.python_exe,
        "display_name": item.display_name,
        "status": item.status,
    }
