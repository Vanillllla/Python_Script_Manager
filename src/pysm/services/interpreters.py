from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy import delete, select

from pysm.config import AppPaths
from pysm.domain.exceptions import PysmError
from pysm.domain.models import (
    EnvironmentRecord,
    InterpreterRecord,
    ModuleSnapshotRecord,
    ScriptRecord,
)
from pysm.infra.database import Database


LOGGER = logging.getLogger(__name__)
PY_LIST_PATTERN = re.compile(r"-V:(?P<tag>[\w\.-]+)")


class InterpreterService:
    def __init__(self, database: Database, paths: AppPaths) -> None:
        self.database = database
        self.paths = paths
        (self.paths.runtimes_dir / "envs").mkdir(parents=True, exist_ok=True)

    def discover_system_interpreters(self) -> list[InterpreterRecord]:
        discovered: list[dict[str, str]] = []
        current = self._probe_python(sys.executable)
        if current:
            discovered.append(current)
        launcher = shutil.which("py")
        if launcher:
            output = subprocess.run(
                [launcher, "--list"], capture_output=True, text=True, check=False
            ).stdout
            for match in PY_LIST_PATTERN.finditer(output):
                tag = match.group("tag")
                probed = self._probe_python_via_launcher(tag)
                if probed:
                    discovered.append(probed)
        unique: dict[str, dict[str, str]] = {item["python_exe"]: item for item in discovered}
        with self.database.session() as session:
            for item in unique.values():
                record = session.scalar(
                    select(InterpreterRecord).where(
                        InterpreterRecord.python_exe == item["python_exe"]
                    )
                )
                if record is None:
                    session.add(
                        InterpreterRecord(
                            label=item["label"],
                            kind="system",
                            version=item["version"],
                            arch=item["arch"],
                            python_exe=item["python_exe"],
                            source_path=item["python_exe"],
                            status="available",
                        )
                    )
            session.commit()
            return session.scalars(select(InterpreterRecord).order_by(InterpreterRecord.id)).all()

    def add_interpreter(self, python_exe: str, label: str | None = None) -> InterpreterRecord:
        probed = self._probe_python(python_exe)
        if not probed:
            raise PysmError(
                code="interpreter.probe_failed",
                message_key="errors.interpreter.probe_failed",
                params={"python_exe": python_exe},
            )
        with self.database.session() as session:
            record = session.scalar(
                select(InterpreterRecord).where(InterpreterRecord.python_exe == probed["python_exe"])
            )
            if record is None:
                record = InterpreterRecord(
                    label=label or probed["label"],
                    kind="system",
                    version=probed["version"],
                    arch=probed["arch"],
                    python_exe=probed["python_exe"],
                    source_path=probed["python_exe"],
                    status="available",
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def list_interpreters(self) -> list[InterpreterRecord]:
        with self.database.session() as session:
            return session.scalars(select(InterpreterRecord).order_by(InterpreterRecord.id)).all()

    def list_environments(self) -> list[EnvironmentRecord]:
        with self.database.session() as session:
            return session.scalars(select(EnvironmentRecord).order_by(EnvironmentRecord.id)).all()

    def install_environment(self, base_interpreter_id: int, name: str | None = None) -> EnvironmentRecord:
        with self.database.session() as session:
            base = session.get(InterpreterRecord, base_interpreter_id)
            if base is None:
                raise PysmError(
                    code="interpreter.unknown",
                    message_key="errors.interpreter.unknown",
                    params={"interpreter_id": base_interpreter_id},
                    status_code=404,
                )
            env_name = _slugify(name or f"{base.label}-{base.version}")
            env_path = self.paths.runtimes_dir / "envs" / env_name
            python_exe = env_path / "Scripts" / "python.exe"
            if not python_exe.exists():
                env_path.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [base.python_exe, "-m", "venv", str(env_path)],
                    check=True,
                    text=True,
                )
            record = session.scalar(
                select(EnvironmentRecord).where(EnvironmentRecord.env_path == str(env_path))
            )
            if record is None:
                record = EnvironmentRecord(
                    base_interpreter_id=base.id,
                    env_path=str(env_path),
                    python_exe=str(python_exe),
                    display_name=name or env_name,
                    status="ready",
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def ensure_default_environment(self) -> EnvironmentRecord:
        environments = self.list_environments()
        if environments:
            return environments[0]
        interpreters = self.discover_system_interpreters()
        if not interpreters:
            raise PysmError(
                code="environment.no_interpreters",
                message_key="errors.environment.no_interpreters",
                status_code=404,
            )
        return self.install_environment(interpreters[0].id, name="default")

    def assign_environment_to_script(self, script_id: int, environment_id: int) -> ScriptRecord:
        with self.database.session() as session:
            script = session.get(ScriptRecord, script_id)
            environment = session.get(EnvironmentRecord, environment_id)
            if script is None or environment is None:
                raise PysmError(
                    code="interpreter.script_or_environment_unknown",
                    message_key="errors.interpreter.script_or_environment_unknown",
                    status_code=404,
                )
            script.interpreter_env_id = environment.id
            session.commit()
            session.refresh(script)
            return script

    def list_modules(self, environment_id: int) -> list[dict[str, str]]:
        with self.database.session() as session:
            environment = session.get(EnvironmentRecord, environment_id)
            if environment is None:
                raise PysmError(
                    code="environment.unknown",
                    message_key="errors.environment.unknown",
                    params={"environment_id": environment_id},
                    status_code=404,
                )
            result = subprocess.run(
                [environment.python_exe, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise PysmError(
                    code="runtime.pip_list_failed",
                    message_key="errors.runtime.pip_list_failed",
                )
            packages = json.loads(result.stdout or "[]")
            session.execute(
                delete(ModuleSnapshotRecord).where(
                    ModuleSnapshotRecord.environment_id == environment.id
                )
            )
            for package in packages:
                session.add(
                    ModuleSnapshotRecord(
                        environment_id=environment.id,
                        package_name=package["name"],
                        version=package["version"],
                    )
                )
            session.commit()
            return packages

    def install_modules(self, environment_id: int, packages: list[str]) -> None:
        if not packages:
            return
        with self.database.session() as session:
            environment = session.get(EnvironmentRecord, environment_id)
            if environment is None:
                raise PysmError(
                    code="environment.unknown",
                    message_key="errors.environment.unknown",
                    params={"environment_id": environment_id},
                    status_code=404,
                )
            result = subprocess.run(
                [environment.python_exe, "-m", "pip", "install", *packages],
                check=False,
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                raise PysmError(
                    code="runtime.pip_install_failed",
                    message_key="errors.runtime.pip_install_failed",
                )

    def get_environment(self, environment_id: int | None) -> EnvironmentRecord | None:
        if environment_id is None:
            return None
        with self.database.session() as session:
            return session.get(EnvironmentRecord, environment_id)

    def _probe_python_via_launcher(self, tag: str) -> dict[str, str] | None:
        launcher = shutil.which("py")
        if not launcher:
            return None
        command = [
            launcher,
            f"-{tag}",
            "-c",
            "import json, platform, sys; print(json.dumps({'python_exe': sys.executable, "
            "'version': platform.python_version(), 'arch': platform.machine()}))",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout.strip())
        return {
            "python_exe": payload["python_exe"],
            "version": payload["version"],
            "arch": payload["arch"],
            "label": f"Python {payload['version']}",
        }

    def _probe_python(self, python_exe: str) -> dict[str, str] | None:
        path = Path(python_exe).expanduser()
        if not path.exists():
            return None
        result = subprocess.run(
            [
                str(path),
                "-c",
                "import json, platform, sys; print(json.dumps({'python_exe': sys.executable, "
                "'version': platform.python_version(), 'arch': platform.machine()}))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout.strip())
        return {
            "python_exe": str(Path(payload["python_exe"]).resolve()),
            "version": payload["version"],
            "arch": payload["arch"],
            "label": f"Python {payload['version']}",
        }


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "environment"

