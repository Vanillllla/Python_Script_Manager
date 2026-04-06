from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import webbrowser
from typing import Any

import typer
import uvicorn

from pysm.api.app import create_app
from pysm.services.context import build_container
from pysm.services.manager import manager_is_running, spawn_detached_manager, wait_for_manager


app = typer.Typer(no_args_is_help=True, add_completion=False)
scripts_app = typer.Typer(no_args_is_help=True)
interpreters_app = typer.Typer(no_args_is_help=True)
load_app = typer.Typer(no_args_is_help=True)
settings_app = typer.Typer(no_args_is_help=True)
autostart_app = typer.Typer(no_args_is_help=True)
autostart_manager_app = typer.Typer(no_args_is_help=True)
autostart_scripts_app = typer.Typer(no_args_is_help=True)

app.add_typer(scripts_app, name="scripts")
app.add_typer(interpreters_app, name="interpreters")
app.add_typer(load_app, name="load")
app.add_typer(settings_app, name="settings")
app.add_typer(autostart_app, name="autostart")
autostart_app.add_typer(autostart_manager_app, name="manager")
autostart_app.add_typer(autostart_scripts_app, name="scripts")


@app.command()
def serve(
    foreground: bool = typer.Option(False, "--foreground", help="Run server in foreground"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser"),
) -> None:
    """Start the local web manager."""
    container = build_container()
    settings = container.settings.get_settings()
    if foreground:
        _run_manager_foreground()
        return
    if manager_is_running(settings):
        typer.echo(f"Manager is already running at http://{settings.host}:{settings.port}")
        if open_browser:
            webbrowser.open(f"http://{settings.host}:{settings.port}")
        raise typer.Exit()
    pid = spawn_detached_manager(container.paths, settings)
    if not wait_for_manager(settings):
        raise typer.BadParameter("Manager failed to start within timeout")
    typer.echo(f"Manager started in background (PID {pid}) at http://{settings.host}:{settings.port}")
    if open_browser and settings.auto_open_browser:
        webbrowser.open(f"http://{settings.host}:{settings.port}")


@app.command()
def status() -> None:
    """Show manager health."""
    payload = _request("GET", "/api/health", ensure_running=False)
    typer.echo(json.dumps(payload, indent=2))


@scripts_app.command("add")
def scripts_add(
    script_path: str = typer.Option(..., "--script-path"),
    autostart: bool = typer.Option(False, "--autostart/--no-autostart"),
) -> None:
    payload = _request("POST", "/api/scripts", {"script_path": script_path, "autostart": autostart})
    typer.echo(f"Added script {payload['name']} (id={payload['id']})")


@scripts_app.command("list")
def scripts_list() -> None:
    payload = _request("GET", "/api/scripts")
    typer.echo(json.dumps(payload, indent=2))


@scripts_app.command("remove")
def scripts_remove(script_id: list[int] = typer.Option(..., "--script-id")) -> None:
    payload = _request("DELETE", "/api/scripts", {"script_ids": script_id})
    typer.echo(f"Removed {payload['removed']} script(s)")


@scripts_app.command("start")
def scripts_start(
    script_id: int = typer.Option(..., "--script-id"),
    install_missing: bool = typer.Option(False, "--install-missing"),
) -> None:
    payload = _request(
        "POST",
        f"/api/scripts/{script_id}/start",
        {"install_missing": install_missing},
    )
    typer.echo(json.dumps(payload, indent=2))


@scripts_app.command("stop")
def scripts_stop(script_id: int = typer.Option(..., "--script-id")) -> None:
    payload = _request("POST", f"/api/scripts/{script_id}/stop", {})
    typer.echo(payload["status"])


@scripts_app.command("pause")
def scripts_pause(script_id: int = typer.Option(..., "--script-id")) -> None:
    payload = _request("POST", f"/api/scripts/{script_id}/pause", {})
    typer.echo(payload["status"])


@scripts_app.command("resume")
def scripts_resume(script_id: int = typer.Option(..., "--script-id")) -> None:
    payload = _request("POST", f"/api/scripts/{script_id}/resume", {})
    typer.echo(payload["status"])


@scripts_app.command("console")
def scripts_console(script_id: int = typer.Option(..., "--script-id")) -> None:
    settings = build_container().settings.get_settings()
    url = f"http://{settings.host}:{settings.port}/scripts/{script_id}"
    _ensure_manager_running()
    opened = webbrowser.open(url)
    typer.echo(url if opened else f"Open in browser: {url}")


@interpreters_app.command("list")
def interpreters_list() -> None:
    payload = _request("GET", "/api/interpreters")
    typer.echo(json.dumps(payload, indent=2))


@interpreters_app.command("add")
def interpreters_add(
    python_exe: str = typer.Option(..., "--python-exe"),
    label: str | None = typer.Option(None, "--label"),
) -> None:
    payload = _request("POST", "/api/interpreters", {"python_exe": python_exe, "label": label})
    typer.echo(json.dumps(payload, indent=2))


@interpreters_app.command("install")
def interpreters_install(
    base_interpreter_id: int = typer.Option(..., "--base-interpreter-id"),
    name: str | None = typer.Option(None, "--name"),
) -> None:
    payload = _request(
        "POST",
        "/api/interpreters/install",
        {"base_interpreter_id": base_interpreter_id, "name": name},
    )
    typer.echo(json.dumps(payload, indent=2))


@interpreters_app.command("select")
def interpreters_select(
    script_id: int = typer.Option(..., "--script-id"),
    environment_id: int = typer.Option(..., "--environment-id"),
) -> None:
    payload = _request(
        "POST",
        "/api/interpreters/select",
        {"script_id": script_id, "environment_id": environment_id},
    )
    typer.echo(json.dumps(payload, indent=2))


@interpreters_app.command("modules")
def interpreters_modules(environment_id: int = typer.Option(..., "--environment-id")) -> None:
    payload = _request("GET", f"/api/interpreters/{environment_id}/modules")
    typer.echo(json.dumps(payload, indent=2))


@load_app.command("list")
def load_list() -> None:
    payload = _request("GET", "/api/load")
    typer.echo(json.dumps(payload, indent=2))


@settings_app.command("change-port")
def settings_change_port(port: int = typer.Option(..., "--port")) -> None:
    payload = _request("PUT", "/api/settings", {"port": port})
    typer.echo(json.dumps(payload, indent=2))
    typer.echo("Restart the manager for host/port changes to take effect.")


@autostart_manager_app.command("enable")
def autostart_manager_enable() -> None:
    payload = _request("POST", "/api/autostart/manager", {"enabled": True})
    typer.echo(json.dumps(payload, indent=2))


@autostart_manager_app.command("disable")
def autostart_manager_disable() -> None:
    payload = _request("POST", "/api/autostart/manager", {"enabled": False})
    typer.echo(json.dumps(payload, indent=2))


@autostart_scripts_app.command("enable")
def autostart_scripts_enable(script_id: int = typer.Option(..., "--script-id")) -> None:
    payload = _request("POST", "/api/autostart/scripts", {"script_id": script_id, "enabled": True})
    typer.echo(json.dumps(payload, indent=2))


@autostart_scripts_app.command("disable")
def autostart_scripts_disable(script_id: int = typer.Option(..., "--script-id")) -> None:
    payload = _request("POST", "/api/autostart/scripts", {"script_id": script_id, "enabled": False})
    typer.echo(json.dumps(payload, indent=2))


@app.command(hidden=True, name="_run-manager")
def run_manager_hidden() -> None:
    _run_manager_foreground()


def _run_manager_foreground() -> None:
    container = build_container()
    settings = container.settings.get_settings()
    uvicorn.run(
        create_app(container),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    ensure_running: bool = True,
) -> Any:
    container = build_container()
    settings = container.settings.get_settings()
    if ensure_running:
        _ensure_manager_running()
    url = f"http://{settings.host}:{settings.port}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise typer.BadParameter(detail or str(exc)) from exc
    except urllib.error.URLError as exc:
        if ensure_running:
            raise typer.BadParameter(f"Cannot reach manager at {url}") from exc
        raise typer.BadParameter("Manager is not running") from exc


def _ensure_manager_running() -> None:
    container = build_container()
    settings = container.settings.get_settings()
    if manager_is_running(settings):
        return
    spawn_detached_manager(container.paths, settings)
    if not wait_for_manager(settings):
        raise typer.BadParameter("Unable to start manager")


def normalize_legacy_args(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if "--add-script" in argv:
        script_path = _consume_option(argv, "--script-path")
        normalized = ["scripts", "add"]
        if script_path:
            normalized.extend(["--script-path", script_path])
        return normalized
    if "--remove-script" in argv:
        ids = _consume_values(argv, "--remove-script")
        normalized = ["scripts", "remove"]
        for item in ids:
            normalized.extend(["--script-id", item])
        return normalized
    if "--pause" in argv:
        return ["scripts", "pause", "--script-id", _consume_single(argv, "--pause")]
    if "--play" in argv:
        return ["scripts", "resume", "--script-id", _consume_single(argv, "--play")]
    if "--add-interpreter" in argv:
        return ["interpreters", "add", "--python-exe", _consume_single(argv, "--add-interpreter")]
    if "--select-interpreter" in argv:
        script_id = _consume_option(argv, "--script-id")
        environment_id = _consume_option(argv, "--environment-id")
        return [
            "interpreters",
            "select",
            "--script-id",
            script_id or "",
            "--environment-id",
            environment_id or "",
        ]
    if "--list-load" in argv:
        return ["load", "list"]
    if "--change-port" in argv:
        return ["settings", "change-port", "--port", _consume_single(argv, "--change-port")]
    return argv


def _consume_single(argv: list[str], name: str) -> str:
    values = _consume_values(argv, name)
    return values[0] if values else ""


def _consume_option(argv: list[str], name: str) -> str | None:
    if name not in argv:
        return None
    index = argv.index(name)
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def _consume_values(argv: list[str], name: str) -> list[str]:
    if name not in argv:
        return []
    index = argv.index(name) + 1
    values: list[str] = []
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return values


def main(argv: list[str] | None = None) -> None:
    args = normalize_legacy_args(list(sys.argv[1:] if argv is None else argv))
    app(args=args, prog_name="pysm")


if __name__ == "__main__":
    main()
