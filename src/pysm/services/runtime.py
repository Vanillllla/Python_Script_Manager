from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import desc, select

from pysm.config import AppPaths
from pysm.domain.models import (
    RunRecord,
    ScriptRecord,
    StartScriptResult,
    TerminalSessionRecord,
    TerminalSnapshot,
)
from pysm.infra.database import Database
from pysm.services.dependencies import DependencyService
from pysm.services.interpreters import InterpreterService
from pysm.services.settings import SettingsService
from pysm.windows.pty import ManagedTerminalProcess, process_metrics


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ActiveSession:
    run_id: int
    process: ManagedTerminalProcess
    script_id: int
    log_file: Path


class RuntimeService:
    def __init__(
        self,
        database: Database,
        paths: AppPaths,
        settings_service: SettingsService,
        interpreter_service: InterpreterService,
        dependency_service: DependencyService,
    ) -> None:
        self.database = database
        self.paths = paths
        self.settings_service = settings_service
        self.interpreter_service = interpreter_service
        self.dependency_service = dependency_service
        self.active_sessions: dict[int, ActiveSession] = {}

    def add_script(
        self,
        script_path: str,
        interpreter_env_id: int | None = None,
        autostart: bool = False,
    ) -> ScriptRecord:
        path = Path(script_path).expanduser().resolve()
        if path.suffix.lower() != ".py" or not path.exists():
            raise ValueError("script_path must point to an existing .py file")
        with self.database.session() as session:
            record = ScriptRecord(
                name=path.stem,
                script_path=str(path),
                cwd=str(path.parent),
                interpreter_env_id=interpreter_env_id,
                autostart=autostart,
                desired_state="stopped",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def remove_scripts(self, script_ids: list[int]) -> int:
        removed = 0
        with self.database.session() as session:
            for script_id in script_ids:
                self.stop_script(script_id)
                record = session.get(ScriptRecord, script_id)
                if record is None:
                    continue
                session.delete(record)
                removed += 1
            session.commit()
        return removed

    def list_scripts(self) -> list[dict[str, object]]:
        self.sync_active_processes()
        with self.database.session() as session:
            scripts = session.scalars(select(ScriptRecord).order_by(ScriptRecord.id)).all()
            output: list[dict[str, object]] = []
            for script in scripts:
                latest_run = session.scalar(
                    select(RunRecord)
                    .where(RunRecord.script_id == script.id)
                    .order_by(desc(RunRecord.id))
                    .limit(1)
                )
                active = self.active_sessions.get(script.id)
                metrics = process_metrics(active.process.pid if active else latest_run.pid if latest_run else None)
                output.append(
                    {
                        "id": script.id,
                        "name": script.name,
                        "script_path": script.script_path,
                        "cwd": script.cwd,
                        "interpreter_env_id": script.interpreter_env_id,
                        "autostart": script.autostart,
                        "desired_state": script.desired_state,
                        "last_error": script.last_error,
                        "status": latest_run.status if latest_run else "stopped",
                        "pause_state": latest_run.pause_state if latest_run else "stopped",
                        "pid": latest_run.pid if latest_run else None,
                        "exit_code": latest_run.exit_code if latest_run else None,
                        "cpu_percent": metrics["cpu_percent"],
                        "memory_percent": metrics["memory_percent"],
                    }
                )
            return output

    def get_script(self, script_id: int) -> dict[str, object]:
        scripts = {item["id"]: item for item in self.list_scripts()}
        script = scripts.get(script_id)
        if script is None:
            raise ValueError(f"Unknown script id {script_id}")
        return script

    def start_script(self, script_id: int, install_missing: bool = False) -> StartScriptResult:
        self.sync_active_processes()
        if script_id in self.active_sessions and self.active_sessions[script_id].process.is_alive():
            active = self.active_sessions[script_id]
            return StartScriptResult(
                status="already_running",
                message="Script is already running",
                missing_modules=[],
                run_id=active.run_id,
                pid=active.process.pid,
            )
        with self.database.session() as session:
            script = session.get(ScriptRecord, script_id)
            if script is None:
                raise ValueError(f"Unknown script id {script_id}")
            environment = self.interpreter_service.get_environment(script.interpreter_env_id)
            if environment is None:
                environment = self.interpreter_service.ensure_default_environment()
                script.interpreter_env_id = environment.id
            report = self.dependency_service.build_report(
                Path(script.script_path), Path(environment.python_exe)
            )
            if report.missing_modules and not install_missing:
                script.last_error = (
                    "Missing modules: " + ", ".join(report.missing_modules) + ". Install them first."
                )
                session.commit()
                return StartScriptResult(
                    status="missing_modules",
                    message=script.last_error,
                    missing_modules=report.missing_modules,
                )
            if report.missing_modules:
                self.interpreter_service.install_modules(environment.id, report.missing_modules)
            settings = self.settings_service.get_settings()
            log_file = self.paths.logs_dir / f"script-{script.id}-{datetime.now():%Y%m%d-%H%M%S}.log"
            process = ManagedTerminalProcess(
                command=[environment.python_exe, "-u", script.script_path],
                cwd=Path(script.cwd),
                env=_child_environment(self.paths.root),
                log_file=log_file,
                buffer_bytes=settings.terminal_buffer_bytes,
            )
            process.start()
            run = RunRecord(
                script_id=script.id,
                pid=process.pid,
                status="running",
                started_at=datetime.utcnow(),
                pause_state="running",
                terminal_backend=process.backend,
            )
            session.add(run)
            session.flush()
            session.add(
                TerminalSessionRecord(
                    run_id=run.id,
                    pty_backend=process.backend,
                    cols=120,
                    rows=30,
                    last_output_seq=0,
                )
            )
            script.desired_state = "running"
            script.last_error = None
            session.commit()
            self.active_sessions[script.id] = ActiveSession(
                run_id=run.id,
                process=process,
                script_id=script.id,
                log_file=log_file,
            )
            return StartScriptResult(
                status="started",
                message="Script started",
                missing_modules=[],
                run_id=run.id,
                pid=process.pid,
            )

    def stop_script(self, script_id: int) -> None:
        active = self.active_sessions.get(script_id)
        if active:
            active.process.terminate()
        with self.database.session() as session:
            script = session.get(ScriptRecord, script_id)
            if script is None:
                return
            latest_run = session.scalar(
                select(RunRecord)
                .where(RunRecord.script_id == script_id)
                .order_by(desc(RunRecord.id))
                .limit(1)
            )
            if latest_run:
                latest_run.status = "stopped"
                latest_run.ended_at = datetime.utcnow()
                latest_run.exit_code = latest_run.exit_code if latest_run.exit_code is not None else 0
            script.desired_state = "stopped"
            session.commit()
        self.active_sessions.pop(script_id, None)

    def pause_script(self, script_id: int) -> None:
        active = self._require_active(script_id)
        active.process.suspend()
        with self.database.session() as session:
            latest_run = session.scalar(
                select(RunRecord)
                .where(RunRecord.script_id == script_id)
                .order_by(desc(RunRecord.id))
                .limit(1)
            )
            if latest_run:
                latest_run.status = "paused"
                latest_run.pause_state = "paused"
                session.commit()

    def resume_script(self, script_id: int) -> None:
        active = self._require_active(script_id)
        active.process.resume()
        with self.database.session() as session:
            latest_run = session.scalar(
                select(RunRecord)
                .where(RunRecord.script_id == script_id)
                .order_by(desc(RunRecord.id))
                .limit(1)
            )
            if latest_run:
                latest_run.status = "running"
                latest_run.pause_state = "running"
                session.commit()

    def set_script_autostart(self, script_id: int, enabled: bool) -> None:
        with self.database.session() as session:
            script = session.get(ScriptRecord, script_id)
            if script is None:
                raise ValueError(f"Unknown script id {script_id}")
            script.autostart = enabled
            session.commit()

    def ensure_autostart_scripts(self) -> None:
        with self.database.session() as session:
            scripts = session.scalars(select(ScriptRecord).where(ScriptRecord.autostart.is_(True))).all()
        for script in scripts:
            if script.id not in self.active_sessions:
                try:
                    self.start_script(script.id)
                except Exception as exc:  # pragma: no cover - boot-time resilience
                    LOGGER.warning("Unable to autostart script %s: %s", script.id, exc)

    def terminal_snapshot(self, script_id: int) -> TerminalSnapshot:
        active = self._require_active(script_id)
        sequence, content = active.process.buffer.snapshot()
        return TerminalSnapshot(
            sequence=sequence,
            content=content,
            backend=active.process.backend,
            is_running=active.process.is_alive(),
            pid=active.process.pid,
            exit_code=active.process.exit_code,
        )

    def terminal_chunks_since(self, script_id: int, sequence: int) -> list[tuple[int, str]]:
        active = self._require_active(script_id)
        return active.process.buffer.chunks_since(sequence)

    def write_terminal_input(self, script_id: int, data: str) -> None:
        active = self._require_active(script_id)
        active.process.write(data)

    def sync_active_processes(self) -> None:
        stale: list[int] = []
        with self.database.session() as session:
            for script_id, active in self.active_sessions.items():
                if active.process.is_alive():
                    continue
                stale.append(script_id)
                latest_run = session.get(RunRecord, active.run_id)
                if latest_run:
                    latest_run.status = "exited"
                    latest_run.pause_state = "stopped"
                    latest_run.ended_at = datetime.utcnow()
                    latest_run.exit_code = active.process.exit_code
                script = session.get(ScriptRecord, script_id)
                if script:
                    script.desired_state = "stopped"
            if stale:
                session.commit()
        for script_id in stale:
            self.active_sessions.pop(script_id, None)

    def _require_active(self, script_id: int) -> ActiveSession:
        self.sync_active_processes()
        active = self.active_sessions.get(script_id)
        if active is None or not active.process.is_alive():
            raise ValueError(f"Script {script_id} is not running")
        return active


def _child_environment(app_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYSM_HOME", str(app_root))
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYSM_CONSOLE_BACKEND", "pipes")
    return env
