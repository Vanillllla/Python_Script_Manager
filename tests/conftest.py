from __future__ import annotations

import platform
import sys
from pathlib import Path

import pytest

from pysm.config import AppPaths
from pysm.domain.models import EnvironmentRecord, InterpreterRecord
from pysm.i18n import LocalizationService
from pysm.infra.database import Database
from pysm.services.autostart import AutostartService
from pysm.services.context import ServiceContainer
from pysm.services.dependencies import DependencyService
from pysm.services.interpreters import InterpreterService
from pysm.services.runtime import RuntimeService
from pysm.services.settings import SettingsService


@pytest.fixture()
def app_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppPaths:
    monkeypatch.setenv("PYSM_HOME", str(tmp_path))
    return AppPaths.create()


@pytest.fixture()
def database(app_paths: AppPaths) -> Database:
    database = Database(app_paths)
    database.initialize()
    return database


@pytest.fixture()
def settings_service(database: Database, app_paths: AppPaths) -> SettingsService:
    return SettingsService(database, app_paths)


@pytest.fixture()
def container(database: Database, app_paths: AppPaths) -> ServiceContainer:
    settings = SettingsService(database, app_paths)
    dependencies = DependencyService()
    interpreters = InterpreterService(database, app_paths)
    runtime = RuntimeService(database, app_paths, settings, interpreters, dependencies)
    return ServiceContainer(
        paths=app_paths,
        database=database,
        i18n=LocalizationService(),
        settings=settings,
        dependencies=dependencies,
        interpreters=interpreters,
        runtime=runtime,
        autostart=AutostartService(),
    )


@pytest.fixture()
def registered_environment(container: ServiceContainer) -> EnvironmentRecord:
    with container.database.session() as session:
        interpreter = InterpreterRecord(
            label=f"Python {platform.python_version()}",
            kind="system",
            version=platform.python_version(),
            arch=platform.machine(),
            python_exe=sys.executable,
            source_path=sys.executable,
            status="available",
        )
        session.add(interpreter)
        session.flush()
        environment = EnvironmentRecord(
            base_interpreter_id=interpreter.id,
            env_path=str(container.paths.runtimes_dir / "envs" / "test-env"),
            python_exe=sys.executable,
            display_name="test-env",
            status="ready",
        )
        session.add(environment)
        session.commit()
        session.refresh(environment)
        return environment
