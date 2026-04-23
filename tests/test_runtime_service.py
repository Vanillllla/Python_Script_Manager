from __future__ import annotations

import time
from pathlib import Path

from pysm.domain.models import DependencyReport, ScriptRecord


def test_runtime_prevents_duplicate_start(container, registered_environment, tmp_path: Path) -> None:
    script = tmp_path / "sleepy.py"
    script.write_text(
        "import time\nprint('ready', flush=True)\ntime.sleep(5)\n",
        encoding="utf-8",
    )
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    first = container.runtime.start_script(record.id)
    second = container.runtime.start_script(record.id)
    assert first.status == "started"
    assert second.status == "already_running"
    stop_result = container.runtime.stop_script(record.id)
    assert stop_result.status == "stopped"


def test_runtime_retains_terminal_snapshot_after_exit(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "hello.py"
    script.write_text("print('hello from pysm', flush=True)\n", encoding="utf-8")
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    result = container.runtime.start_script(record.id)
    assert result.status == "started"
    deadline = time.time() + 10
    while time.time() < deadline:
        container.runtime.sync_active_processes()
        snapshot = container.runtime.terminal_snapshot(record.id)
        if not snapshot.is_running:
            break
        time.sleep(0.1)
    final_snapshot = container.runtime.terminal_snapshot(record.id)
    assert final_snapshot.is_running is False
    assert "hello from pysm" in final_snapshot.content


def test_runtime_reports_missing_dependencies(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "missing_dep.py"
    script.write_text("import definitely_missing_package_xyz\n", encoding="utf-8")
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    result = container.runtime.start_script(record.id, install_missing=False)
    assert result.status == "missing_modules"
    assert result.missing_modules == ["definitely_missing_package_xyz"]


def test_runtime_installs_missing_dependencies_when_requested(
    container, registered_environment, tmp_path: Path, monkeypatch
) -> None:
    script = tmp_path / "install_then_run.py"
    script.write_text("print('installed path ok', flush=True)\n", encoding="utf-8")
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)

    monkeypatch.setattr(
        container.dependencies,
        "build_report",
        lambda *_args, **_kwargs: DependencyReport(
            imports=["colorama"],
            missing_modules=["colorama"],
            installed_modules=[],
        ),
    )
    called = {}

    def fake_install(environment_id: int, packages: list[str]) -> None:
        called["environment_id"] = environment_id
        called["packages"] = packages

    monkeypatch.setattr(container.interpreters, "install_modules", fake_install)

    result = container.runtime.start_script(record.id, install_missing=True)
    assert result.status == "started"
    assert called == {"environment_id": registered_environment.id, "packages": ["colorama"]}
    container.runtime.stop_script(record.id)


def test_runtime_ensure_autostart_scripts_starts_flagged_scripts(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "autostart.py"
    script.write_text("import time\nprint('autostart ready', flush=True)\ntime.sleep(5)\n", encoding="utf-8")
    record = container.runtime.add_script(
        str(script),
        interpreter_env_id=registered_environment.id,
        autostart=True,
    )

    container.runtime.ensure_autostart_scripts()
    time.sleep(0.5)
    scripts = container.runtime.list_scripts()
    current = next(item for item in scripts if item["id"] == record.id)
    assert current["status"] == "running"
    container.runtime.stop_script(record.id)


def test_runtime_remove_script_stops_active_process(
    container, registered_environment, tmp_path: Path
) -> None:
    script = tmp_path / "remove_me.py"
    script.write_text("import time\nprint('alive', flush=True)\ntime.sleep(5)\n", encoding="utf-8")
    record = container.runtime.add_script(str(script), interpreter_env_id=registered_environment.id)
    started = container.runtime.start_script(record.id)
    assert started.status == "started"

    removed = container.runtime.remove_scripts([record.id])
    assert removed == 1
    assert record.id not in container.runtime.active_sessions

    with container.database.session() as session:
        assert session.get(ScriptRecord, record.id) is None
