from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from pysm.config import AppPaths, AppSettings
from pysm.domain.models import AppSettingRecord, Base


class Database:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.engine = create_engine(f"sqlite:///{paths.database_path}", future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
            future=True,
        )

    def initialize(self) -> None:
        with self.engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if not inspect(connection).has_table(table.name):
                    table.create(connection)
        with self.session() as session:
            existing = {
                record.key: record.value
                for record in session.scalars(select(AppSettingRecord)).all()
            }
            defaults = AppSettings(install_root=str(self.paths.root)).to_mapping()
            changed = False
            for key, value in defaults.items():
                if key not in existing:
                    session.add(AppSettingRecord(key=key, value=json.dumps(value)))
                    changed = True
            if changed:
                session.commit()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

