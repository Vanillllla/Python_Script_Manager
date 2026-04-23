from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pysm.domain.messages import MessageSpec


class Base(DeclarativeBase):
    pass


class ScriptRecord(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    script_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    cwd: Mapped[str] = mapped_column(String(2048), nullable=False)
    interpreter_env_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id"), nullable=True
    )
    autostart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    desired_state: Mapped[str] = mapped_column(String(32), default="stopped", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    environment: Mapped["EnvironmentRecord | None"] = relationship()


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="stopped")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pause_state: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    terminal_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TerminalSessionRecord(Base):
    __tablename__ = "terminal_sessions"

    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    pty_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    cols: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    last_output_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class InterpreterRecord(Base):
    __tablename__ = "interpreters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    arch: Mapped[str] = mapped_column(String(64), nullable=False)
    python_exe: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    source_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnvironmentRecord(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_interpreter_id: Mapped[int] = mapped_column(
        ForeignKey("interpreters.id"), nullable=False
    )
    env_path: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    python_exe: Mapped[str] = mapped_column(String(2048), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    base_interpreter: Mapped["InterpreterRecord"] = relationship()


class ModuleSnapshotRecord(Base):
    __tablename__ = "module_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id"), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSettingRecord(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


@dataclass(slots=True)
class DependencyReport:
    imports: list[str]
    missing_modules: list[str]
    installed_modules: list[str]


@dataclass(slots=True)
class StartScriptResult:
    status: str
    message: MessageSpec
    missing_modules: list[str] = field(default_factory=list)
    run_id: int | None = None
    pid: int | None = None


@dataclass(slots=True)
class ActionResult:
    status: str
    message: MessageSpec


@dataclass(slots=True)
class TerminalSnapshot:
    sequence: int
    content: str
    backend: str
    is_running: bool
    pid: int | None
    exit_code: int | None


@dataclass(slots=True)
class LoadSnapshot:
    cpu_percent: float
    memory_percent: float
    processes: list[dict[str, Any]]

