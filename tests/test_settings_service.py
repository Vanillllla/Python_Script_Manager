from sqlalchemy import select

from pysm.domain.models import AppSettingRecord


def test_database_initialization_bootstraps_language_setting(database) -> None:
    with database.session() as session:
        keys = {record.key for record in session.scalars(select(AppSettingRecord)).all()}
    assert "language" in keys


def test_settings_update_persists_language(settings_service) -> None:
    settings = settings_service.update_settings(language="ru")
    assert settings.language == "ru"
    reloaded = settings_service.get_settings()
    assert reloaded.language == "ru"
