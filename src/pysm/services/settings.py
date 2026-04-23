from __future__ import annotations

import json

from sqlalchemy import select

from pysm.config import AppPaths, AppSettings
from pysm.domain.exceptions import PysmError
from pysm.domain.models import AppSettingRecord
from pysm.infra.database import Database


class SettingsService:
    def __init__(self, database: Database, paths: AppPaths) -> None:
        self.database = database
        self.paths = paths

    def get_settings(self) -> AppSettings:
        with self.database.session() as session:
            records = session.scalars(select(AppSettingRecord)).all()
            mapping = {record.key: json.loads(record.value) for record in records}
        return AppSettings.from_mapping(mapping, root=self.paths.root)

    def update_settings(self, **changes: object) -> AppSettings:
        if "language" in changes:
            language = str(changes["language"]).strip().lower()
            if language not in {"en", "ru"}:
                raise PysmError(
                    code="settings.invalid_language",
                    message_key="errors.settings.invalid_language",
                    params={"language": str(changes["language"])},
                )
            changes["language"] = language
        settings = self.get_settings().to_mapping()
        settings.update(changes)
        with self.database.session() as session:
            for key, value in settings.items():
                record = session.get(AppSettingRecord, key)
                if record is None:
                    record = AppSettingRecord(key=key, value=json.dumps(value))
                    session.add(record)
                else:
                    record.value = json.dumps(value)
            session.commit()
        return self.get_settings()

