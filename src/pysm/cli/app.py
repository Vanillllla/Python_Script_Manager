from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Literal

import typer
import uvicorn

from pysm.api.app import create_app
from pysm.config import AppPaths
from pysm.i18n import LocalizationService
from pysm.infra.database import Database
from pysm.services.context import build_container
from pysm.services.manager import manager_is_running, spawn_detached_manager, wait_for_manager
from pysm.services.settings import SettingsService


Language = Literal["en", "ru"]
I18N = LocalizationService()


def create_cli_app(locale: str) -> typer.Typer:
    t = lambda key, **params: I18N.translate(key, locale, **params)

    app = typer.Typer(
        no_args_is_help=True,
        add_completion=False,
        help=t("cli.app.help"),
    )
    scripts_app = typer.Typer(no_args_is_help=True, help=t("cli.commands.scripts.help"))
    interpreters_app = typer.Typer(
        no_args_is_help=True,
        help=t("cli.commands.interpreters.help"),
    )
    load_app = typer.Typer(no_args_is_help=True, help=t("cli.commands.load.help"))
    settings_app = typer.Typer(no_args_is_help=True, help=t("cli.commands.settings.help"))
    autostart_app = typer.Typer(no_args_is_help=True, help=t("cli.autostart.help"))
    autostart_manager_app = typer.Typer(
        no_args_is_help=True,
        help=t("cli.autostart.manager.help"),
    )
    autostart_scripts_app = typer.Typer(
        no_args_is_help=True,
        help=t("cli.autostart.scripts.help"),
    )

    app.add_typer(scripts_app, name="scripts")
    app.add_typer(interpreters_app, name="interpreters")
    app.add_typer(load_app, name="load")
    app.add_typer(settings_app, name="settings")
    app.add_typer(autostart_app, name="autostart")
    autostart_app.add_typer(autostart_manager_app, name="manager")
    autostart_app.add_typer(autostart_scripts_app, name="scripts")

    @app.callback()
    def app_callback(
        lang: Language | None = typer.Option(None, "--lang", help=t("cli.global.lang"))
    ) -> None:
        return None

    @app.command(help=t("cli.serve.help"))
    def serve(
        foreground: bool = typer.Option(False, "--foreground", help=t("cli.options.foreground")),
        open_browser: bool = typer.Option(
            True,
            "--open-browser/--no-open-browser",
            help=t("cli.options.open_browser"),
        ),
    ) -> None:
        container = build_container()
        settings = container.settings.get_settings()
        url = f"http://{settings.host}:{settings.port}"
        if foreground:
            _run_manager_foreground()
            return
        if manager_is_running(settings):
            typer.echo(t("cli.messages.manager_already_running", url=url))
            if open_browser:
                webbrowser.open(url)
            raise typer.Exit()
        pid = spawn_detached_manager(container.paths, settings)
        if not wait_for_manager(settings):
            _fail(t("cli.messages.manager_start_timeout"))
        typer.echo(t("cli.messages.manager_started", pid=pid, url=url))
        if open_browser and settings.auto_open_browser:
            webbrowser.open(url)

    @app.command(help=t("cli.status.help"))
    def status() -> None:
        payload = _request("GET", "/api/health", ensure_running=False, locale=locale)
        _echo_health(payload, locale)

    @scripts_app.command("add", help=t("cli.scripts.add"))
    def scripts_add(
        script_path: str = typer.Option(..., "--script-path", help=t("cli.options.script_path")),
        autostart: bool = typer.Option(
            False,
            "--autostart/--no-autostart",
            help=t("cli.options.autostart"),
        ),
    ) -> None:
        payload = _request(
            "POST",
            "/api/scripts",
            {"script_path": script_path, "autostart": autostart},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))
        typer.echo(f"{t('common.labels.id')}: {payload['id']}")

    @scripts_app.command("list", help=t("cli.scripts.list"))
    def scripts_list() -> None:
        payload = _request("GET", "/api/scripts", locale=locale)
        _echo_scripts(payload, locale)

    @scripts_app.command("remove", help=t("cli.scripts.remove"))
    def scripts_remove(
        script_id: list[int] = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request("DELETE", "/api/scripts", {"script_ids": script_id}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @scripts_app.command("start", help=t("cli.scripts.start"))
    def scripts_start(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id")),
        install_missing: bool = typer.Option(
            False,
            "--install-missing",
            help=t("cli.options.install_missing"),
        ),
    ) -> None:
        payload = _request(
            "POST",
            f"/api/scripts/{script_id}/start",
            {"install_missing": install_missing},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))
        if payload.get("pid") is not None:
            typer.echo(f"{t('common.labels.pid')}: {payload['pid']}")
        if payload.get("missing_modules"):
            typer.echo(", ".join(payload["missing_modules"]))

    @scripts_app.command("stop", help=t("cli.scripts.stop"))
    def scripts_stop(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request("POST", f"/api/scripts/{script_id}/stop", {}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @scripts_app.command("pause", help=t("cli.scripts.pause"))
    def scripts_pause(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request("POST", f"/api/scripts/{script_id}/pause", {}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @scripts_app.command("resume", help=t("cli.scripts.resume"))
    def scripts_resume(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request("POST", f"/api/scripts/{script_id}/resume", {}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @scripts_app.command("console", help=t("cli.scripts.console"))
    def scripts_console(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        settings = _load_settings()
        url = f"http://{settings.host}:{settings.port}/scripts/{script_id}"
        _ensure_manager_running(locale)
        opened = webbrowser.open(url)
        typer.echo(url if opened else t("cli.messages.open_in_browser", url=url))

    @interpreters_app.command("list", help=t("cli.interpreters.list"))
    def interpreters_list() -> None:
        payload = _request("GET", "/api/interpreters", locale=locale)
        _echo_interpreters(payload, locale)

    @interpreters_app.command("add", help=t("cli.interpreters.add"))
    def interpreters_add(
        python_exe: str = typer.Option(..., "--python-exe", help=t("cli.options.python_exe")),
        label: str | None = typer.Option(None, "--label", help=t("cli.options.label")),
    ) -> None:
        payload = _request(
            "POST",
            "/api/interpreters",
            {"python_exe": python_exe, "label": label},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))
        typer.echo(f"{t('common.labels.path')}: {payload['interpreter']['python_exe']}")

    @interpreters_app.command("install", help=t("cli.interpreters.install"))
    def interpreters_install(
        base_interpreter_id: int = typer.Option(
            ...,
            "--base-interpreter-id",
            help=t("cli.options.base_interpreter_id"),
        ),
        name: str | None = typer.Option(None, "--name", help=t("cli.options.name")),
    ) -> None:
        payload = _request(
            "POST",
            "/api/interpreters/install",
            {"base_interpreter_id": base_interpreter_id, "name": name},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))
        typer.echo(f"{t('common.labels.path')}: {payload['environment']['python_exe']}")

    @interpreters_app.command("select", help=t("cli.interpreters.select"))
    def interpreters_select(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id")),
        environment_id: int = typer.Option(
            ...,
            "--environment-id",
            help=t("cli.options.environment_id"),
        ),
    ) -> None:
        payload = _request(
            "POST",
            "/api/interpreters/select",
            {"script_id": script_id, "environment_id": environment_id},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))

    @interpreters_app.command("modules", help=t("cli.interpreters.modules"))
    def interpreters_modules(
        environment_id: int = typer.Option(
            ...,
            "--environment-id",
            help=t("cli.options.environment_id"),
        )
    ) -> None:
        payload = _request("GET", f"/api/interpreters/{environment_id}/modules", locale=locale)
        for item in payload:
            typer.echo(f"{item['name']}=={item['version']}")

    @load_app.command("list", help=t("cli.load.list"))
    def load_list() -> None:
        payload = _request("GET", "/api/load", locale=locale)
        _echo_load(payload, locale)

    @settings_app.command("change-port", help=t("cli.settings.change_port"))
    def settings_change_port(
        port: int = typer.Option(..., "--port", help=t("cli.options.port"))
    ) -> None:
        _request("PUT", "/api/settings", {"port": port}, locale=locale)
        typer.echo(t("settings.saved"))
        typer.echo(t("cli.messages.restart_required"))

    @settings_app.command("change-language", help=t("cli.settings.change_language"))
    def settings_change_language(
        language: Language = typer.Option(..., "--language", help=t("cli.options.language"))
    ) -> None:
        _request("PUT", "/api/settings", {"language": language}, locale=locale)
        typer.echo(I18N.translate("settings.language_changed", language))

    @autostart_manager_app.command("enable", help=t("cli.autostart.manager.enable"))
    def autostart_manager_enable() -> None:
        payload = _request("POST", "/api/autostart/manager", {"enabled": True}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @autostart_manager_app.command("disable", help=t("cli.autostart.manager.disable"))
    def autostart_manager_disable() -> None:
        payload = _request("POST", "/api/autostart/manager", {"enabled": False}, locale=locale)
        typer.echo(_response_message(payload, locale))

    @autostart_scripts_app.command("enable", help=t("cli.autostart.scripts.enable"))
    def autostart_scripts_enable(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request(
            "POST",
            "/api/autostart/scripts",
            {"script_id": script_id, "enabled": True},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))

    @autostart_scripts_app.command("disable", help=t("cli.autostart.scripts.disable"))
    def autostart_scripts_disable(
        script_id: int = typer.Option(..., "--script-id", help=t("cli.options.script_id"))
    ) -> None:
        payload = _request(
            "POST",
            "/api/autostart/scripts",
            {"script_id": script_id, "enabled": False},
            locale=locale,
        )
        typer.echo(_response_message(payload, locale))

    @app.command(hidden=True, name="_run-manager")
    def run_manager_hidden() -> None:
        _run_manager_foreground()

    return app


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
    *,
    ensure_running: bool = True,
    locale: str,
) -> Any:
    settings = _load_settings()
    if ensure_running:
        _ensure_manager_running(locale)
    url = _with_lang(f"http://{settings.host}:{settings.port}{path}", locale)
    data = None
    headers = {"Accept-Language": locale}
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
        message = detail or str(exc)
        try:
            payload = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            message = _response_message(payload, locale)
        _fail(message)
    except urllib.error.URLError:
        if ensure_running:
            _fail(I18N.translate("cli.messages.manager_unreachable", locale, url=url))
        _fail(I18N.translate("cli.messages.manager_not_running", locale))


def _ensure_manager_running(locale: str) -> None:
    container = build_container()
    settings = container.settings.get_settings()
    if manager_is_running(settings):
        return
    spawn_detached_manager(container.paths, settings)
    if not wait_for_manager(settings):
        _fail(I18N.translate("cli.messages.manager_start_timeout", locale))


def _load_settings():
    paths = AppPaths.create()
    database = Database(paths)
    database.initialize()
    return SettingsService(database, paths).get_settings()


def _with_lang(url: str, locale: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urllib.parse.urlencode({'lang': locale})}"


def _response_message(payload: Any, locale: str) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    key = payload.get("message_key")
    if key:
        params = payload.get("message_params") or {}
        if isinstance(params, dict):
            return I18N.translate(str(key), locale, **params)
    if payload.get("last_error_key"):
        params = payload.get("last_error_params") or {}
        if isinstance(params, dict):
            return I18N.translate(str(payload["last_error_key"]), locale, **params)
    return str(payload.get("detail") or payload.get("message") or payload.get("status") or payload)


def _echo_health(payload: dict[str, Any], locale: str) -> None:
    typer.echo(f"{I18N.translate('common.labels.status', locale)}: {I18N.translate('common.status.' + payload['status'], locale)}")
    typer.echo(f"{I18N.translate('common.labels.host', locale)}: {payload['host']}")
    typer.echo(f"{I18N.translate('common.labels.port', locale)}: {payload['port']}")
    typer.echo(f"{I18N.translate('common.labels.pid', locale)}: {payload.get('pid') or I18N.translate('common.values.na', locale)}")
    typer.echo(f"{I18N.translate('common.labels.running_scripts', locale)}: {payload['running_scripts']}")


def _echo_scripts(payload: list[dict[str, Any]], locale: str) -> None:
    if not payload:
        typer.echo(I18N.translate("web.scripts.empty", locale))
        return
    for index, script in enumerate(payload, start=1):
        if index > 1:
            typer.echo("")
        typer.echo(f"[{script['id']}] {script['name']}")
        typer.echo(f"{I18N.translate('common.labels.status', locale)}: {I18N.translate('common.status.' + script['status'], locale)}")
        typer.echo(f"{I18N.translate('common.labels.path', locale)}: {script['script_path']}")
        typer.echo(f"{I18N.translate('common.labels.pid', locale)}: {script.get('pid') or I18N.translate('common.values.na', locale)}")
        typer.echo(f"{I18N.translate('common.labels.autostart', locale)}: {I18N.translate('common.states.enabled' if script['autostart'] else 'common.states.disabled', locale)}")
        if script.get("last_error_key"):
            typer.echo(
                f"{I18N.translate('common.labels.last_error', locale)}: "
                f"{I18N.translate(script['last_error_key'], locale, **(script.get('last_error_params') or {}))}"
            )


def _echo_interpreters(payload: dict[str, Any], locale: str) -> None:
    typer.echo(I18N.translate("web.interpreters.system_interpreters", locale))
    for item in payload.get("interpreters", []):
        typer.echo(
            f"[{item['id']}] {item['label']} | {item['version']} / {item['arch']} | {item['python_exe']}"
        )
    typer.echo("")
    typer.echo(I18N.translate("web.interpreters.managed_environments", locale))
    for item in payload.get("environments", []):
        typer.echo(f"[{item['id']}] {item['display_name']} | {item['python_exe']}")


def _echo_load(payload: dict[str, Any], locale: str) -> None:
    typer.echo(
        f"{I18N.translate('common.labels.cpu', locale)}: "
        f"{payload.get('cpu_percent') if payload.get('cpu_percent') is not None else I18N.translate('common.values.na', locale)}"
    )
    typer.echo(
        f"{I18N.translate('common.labels.memory', locale)}: "
        f"{payload.get('memory_percent') if payload.get('memory_percent') is not None else I18N.translate('common.values.na', locale)}"
    )
    processes = payload.get("processes") or []
    if not processes:
        return
    typer.echo("")
    typer.echo(I18N.translate("common.labels.scripts", locale) + ":")
    for process in processes:
        typer.echo(
            f"[{process.get('script_id')}] {process.get('name')} "
            f"| {I18N.translate('common.labels.pid', locale)}: {process.get('pid')} "
            f"| {I18N.translate('common.labels.cpu', locale)}: {process.get('cpu_percent')} "
            f"| {I18N.translate('common.labels.memory', locale)}: {process.get('memory_percent')}"
        )


def _fail(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)


def normalize_legacy_args(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    passthrough, stripped = _extract_passthrough_options(argv)
    normalized = _normalize_legacy_args_inner(stripped)
    return passthrough + normalized


def _normalize_legacy_args_inner(argv: list[str]) -> list[str]:
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


def _extract_passthrough_options(argv: list[str]) -> tuple[list[str], list[str]]:
    passthrough: list[str] = []
    stripped: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--lang" and index + 1 < len(argv):
            passthrough.extend([item, argv[index + 1]])
            index += 2
            continue
        if item.startswith("--lang="):
            passthrough.append(item)
            index += 1
            continue
        stripped.append(item)
        index += 1
    return passthrough, stripped


def _extract_lang(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--lang="):
            return item.split("=", 1)[1]
    return None


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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    lang_override = _extract_lang(raw_args)
    settings = _load_settings()
    locale = I18N.resolve_cli_locale(
        lang_override,
        environment=os.environ,
        settings_locale=settings.language,
    )
    args = normalize_legacy_args(raw_args)
    app = create_cli_app(locale)
    app(args=args, prog_name="pysm")


if __name__ == "__main__":
    main()
