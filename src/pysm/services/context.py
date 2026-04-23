from __future__ import annotations

from dataclasses import dataclass

from pysm.config import AppPaths
from pysm.i18n import LocalizationService
from pysm.infra.database import Database
from pysm.infra.logging import configure_logging
from pysm.services.autostart import AutostartService
from pysm.services.dependencies import DependencyService
from pysm.services.interpreters import InterpreterService
from pysm.services.runtime import RuntimeService
from pysm.services.settings import SettingsService


@dataclass(slots=True)
class ServiceContainer:
    paths: AppPaths
    database: Database
    i18n: LocalizationService
    settings: SettingsService
    dependencies: DependencyService
    interpreters: InterpreterService
    runtime: RuntimeService
    autostart: AutostartService


def build_container() -> ServiceContainer:
    paths = AppPaths.create()
    configure_logging(paths)
    database = Database(paths)
    database.initialize()
    i18n_service = LocalizationService()
    settings_service = SettingsService(database, paths)
    dependency_service = DependencyService()
    interpreter_service = InterpreterService(database, paths)
    interpreter_service.discover_system_interpreters()
    runtime_service = RuntimeService(
        database=database,
        paths=paths,
        settings_service=settings_service,
        interpreter_service=interpreter_service,
        dependency_service=dependency_service,
    )
    autostart_service = AutostartService()
    return ServiceContainer(
        paths=paths,
        database=database,
        i18n=i18n_service,
        settings=settings_service,
        dependencies=dependency_service,
        interpreters=interpreter_service,
        runtime=runtime_service,
        autostart=autostart_service,
    )

