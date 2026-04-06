from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "request": request,
                "settings": services.settings.get_settings(),
                **context,
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        scripts = services.runtime.list_scripts()
        return render(
            "dashboard.html",
            request,
            scripts=scripts,
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

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        return _health_payload(services)

    @app.get("/api/scripts")
    async def api_scripts() -> list[dict[str, Any]]:
        return services.runtime.list_scripts()

    @app.post("/api/scripts")
    async def api_add_script(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        record = services.runtime.add_script(
            script_path=str(payload["script_path"]),
            interpreter_env_id=_optional_int(payload.get("interpreter_env_id")),
            autostart=bool(payload.get("autostart", False)),
        )
        return {"id": record.id, "name": record.name}

    @app.delete("/api/scripts")
    async def api_remove_scripts(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        removed = services.runtime.remove_scripts([int(item) for item in payload.get("script_ids", [])])
        return {"removed": removed}

    @app.post("/api/scripts/{script_id}/start")
    async def api_start_script(script_id: int, request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        result = services.runtime.start_script(
            script_id, install_missing=bool(payload.get("install_missing", False))
        )
        return asdict(result)

    @app.post("/api/scripts/{script_id}/stop")
    async def api_stop_script(script_id: int) -> dict[str, Any]:
        services.runtime.stop_script(script_id)
        return {"status": "stopped"}

    @app.post("/api/scripts/{script_id}/pause")
    async def api_pause_script(script_id: int) -> dict[str, Any]:
        services.runtime.pause_script(script_id)
        return {"status": "paused"}

    @app.post("/api/scripts/{script_id}/resume")
    async def api_resume_script(script_id: int) -> dict[str, Any]:
        services.runtime.resume_script(script_id)
        return {"status": "running"}

    @app.get("/api/scripts/{script_id}/console")
    async def api_console(script_id: int) -> dict[str, Any]:
        snapshot = services.runtime.terminal_snapshot(script_id)
        return asdict(snapshot)

    @app.websocket("/api/scripts/{script_id}/terminal")
    async def api_terminal(websocket: WebSocket, script_id: int) -> None:
        await websocket.accept()
        sequence = 0
        try:
            snapshot = services.runtime.terminal_snapshot(script_id)
            sequence = snapshot.sequence
            await websocket.send_json({"type": "snapshot", **asdict(snapshot)})
            while True:
                for chunk_sequence, chunk_text in services.runtime.terminal_chunks_since(script_id, sequence):
                    sequence = chunk_sequence
                    await websocket.send_json(
                        {"type": "chunk", "sequence": sequence, "content": chunk_text}
                    )
                await asyncio.sleep(0.15)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()

    @app.post("/api/scripts/{script_id}/terminal/input")
    async def api_terminal_input(script_id: int, request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        data = str(payload.get("data", ""))
        services.runtime.write_terminal_input(script_id, data)
        return {"status": "ok"}

    @app.get("/api/interpreters")
    async def api_interpreters() -> dict[str, Any]:
        return {
            "interpreters": [_interpreter_payload(item) for item in services.interpreters.list_interpreters()],
            "environments": [_environment_payload(item) for item in services.interpreters.list_environments()],
        }

    @app.post("/api/interpreters")
    async def api_add_interpreter(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        record = services.interpreters.add_interpreter(
            python_exe=str(payload["python_exe"]),
            label=str(payload["label"]) if payload.get("label") else None,
        )
        return _interpreter_payload(record)

    @app.post("/api/interpreters/install")
    async def api_install_environment(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        record = services.interpreters.install_environment(
            base_interpreter_id=int(payload["base_interpreter_id"]),
            name=str(payload["name"]) if payload.get("name") else None,
        )
        return _environment_payload(record)

    @app.post("/api/interpreters/select")
    async def api_select_environment(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        record = services.interpreters.assign_environment_to_script(
            script_id=int(payload["script_id"]),
            environment_id=int(payload["environment_id"]),
        )
        return {"script_id": record.id, "environment_id": record.interpreter_env_id}

    @app.get("/api/interpreters/{environment_id}/modules")
    async def api_modules(environment_id: int) -> list[dict[str, str]]:
        return services.interpreters.list_modules(environment_id)

    @app.get("/api/load")
    async def api_load() -> dict[str, Any]:
        return _system_load()

    @app.get("/api/settings")
    async def api_settings() -> dict[str, Any]:
        return services.settings.get_settings().to_mapping()

    @app.put("/api/settings")
    async def api_update_settings(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        return services.settings.update_settings(**payload).to_mapping()

    @app.post("/api/autostart/manager")
    async def api_manager_autostart(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        enabled = bool(payload.get("enabled", False))
        if enabled:
            services.autostart.enable_manager_autostart()
        else:
            services.autostart.disable_manager_autostart()
        services.settings.update_settings(manager_autostart=enabled)
        return {"enabled": enabled}

    @app.post("/api/autostart/scripts")
    async def api_script_autostart(request: Request) -> dict[str, Any]:
        payload = await _payload(request)
        script_id = int(payload["script_id"])
        enabled = bool(payload.get("enabled", False))
        services.runtime.set_script_autostart(script_id, enabled)
        return {"script_id": script_id, "enabled": enabled}

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


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return await request.json()
    if content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith(
        "multipart/form-data"
    ):
        form = await request.form()
        return dict(form)
    try:
        return await request.json()
    except json.JSONDecodeError:
        return {}


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


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)
