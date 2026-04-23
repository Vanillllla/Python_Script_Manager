from pysm.i18n import LocalizationService


def test_web_locale_resolution_prefers_saved_setting() -> None:
    service = LocalizationService()
    locale = service.resolve_web_locale(
        settings_locale="ru",
        query_locale="en",
        cookie_locale="en",
        accept_language="en-US,en;q=0.9",
    )
    assert locale == "ru"


def test_cli_locale_resolution_prefers_explicit_override() -> None:
    service = LocalizationService()
    locale = service.resolve_cli_locale(
        "ru",
        environment={"PYSM_LANG": "en"},
        settings_locale="en",
    )
    assert locale == "ru"


def test_unsupported_locale_falls_back_to_english() -> None:
    service = LocalizationService()
    assert service.resolve_cli_locale("de", environment={}, settings_locale=None) == "en"


def test_translation_falls_back_to_english_catalog() -> None:
    service = LocalizationService()
    service.catalogs["en"]["tests.only_en"] = "English only"
    assert service.translate("tests.only_en", "ru") == "English only"


def test_missing_translation_key_returns_key() -> None:
    service = LocalizationService()
    assert service.translate("missing.catalog.key", "ru") == "missing.catalog.key"
