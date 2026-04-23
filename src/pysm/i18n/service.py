from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from pysm.domain.messages import MessageSpec


DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "ru")


class LocalizationService:
    def __init__(self) -> None:
        self.catalogs = {
            locale: _load_catalog(locale)
            for locale in SUPPORTED_LOCALES
        }

    def is_supported(self, locale: str | None) -> bool:
        return self.normalize_locale(locale) in SUPPORTED_LOCALES

    def normalize_locale(self, locale: str | None) -> str:
        if not locale:
            return DEFAULT_LOCALE
        normalized = locale.strip().replace("_", "-").lower()
        base = normalized.split("-", 1)[0]
        if base in SUPPORTED_LOCALES:
            return base
        return DEFAULT_LOCALE

    def resolve_cli_locale(
        self,
        explicit: str | None = None,
        *,
        environment: dict[str, str] | None = None,
        settings_locale: str | None = None,
    ) -> str:
        env = environment or os.environ
        if explicit:
            return self.normalize_locale(explicit)
        if env.get("PYSM_LANG"):
            return self.normalize_locale(env["PYSM_LANG"])
        if settings_locale:
            return self.normalize_locale(settings_locale)
        return DEFAULT_LOCALE

    def resolve_web_locale(
        self,
        *,
        settings_locale: str | None = None,
        query_locale: str | None = None,
        cookie_locale: str | None = None,
        accept_language: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> str:
        env = environment or os.environ
        if settings_locale:
            return self.normalize_locale(settings_locale)
        if query_locale:
            return self.normalize_locale(query_locale)
        if cookie_locale:
            return self.normalize_locale(cookie_locale)
        if accept_language:
            negotiated = self.negotiate_accept_language(accept_language)
            if negotiated:
                return negotiated
        if env.get("PYSM_LANG"):
            return self.normalize_locale(env["PYSM_LANG"])
        return DEFAULT_LOCALE

    def negotiate_accept_language(self, header: str) -> str | None:
        ranked: list[tuple[float, str]] = []
        for raw_part in header.split(","):
            part = raw_part.strip()
            if not part:
                continue
            locale, _, tail = part.partition(";")
            quality = 1.0
            if tail.startswith("q="):
                try:
                    quality = float(tail[2:])
                except ValueError:
                    quality = 0.0
            ranked.append((quality, locale))
        for _, locale in sorted(ranked, reverse=True):
            normalized = self.normalize_locale(locale)
            if normalized in SUPPORTED_LOCALES:
                return normalized
        return None

    def translate(self, key: str, locale: str | None = None, **params: Any) -> str:
        active_locale = self.normalize_locale(locale)
        template = self.catalogs.get(active_locale, {}).get(key)
        if template is None:
            template = self.catalogs[DEFAULT_LOCALE].get(key)
        if template is None:
            return key
        try:
            return template.format(**params)
        except Exception:
            return template

    def translate_message(self, message: MessageSpec | None, locale: str | None = None) -> str | None:
        if message is None:
            return None
        return self.translate(message.key, locale, **message.params)

    def build_frontend_messages(self, locale: str) -> dict[str, str]:
        keys = [
            "frontend.toast.saved",
            "frontend.toast.action_complete",
            "frontend.toast.autostart_updated",
            "frontend.terminal.connecting",
            "frontend.terminal.disconnected",
            "frontend.terminal.error",
            "frontend.modules.empty",
        ]
        return {key: self.translate(key, locale) for key in keys}

    def status_label(self, status: str, locale: str) -> str:
        key = f"common.status.{status}"
        return self.translate(key, locale)

    def locale_name(self, locale: str, display_locale: str | None = None) -> str:
        target_locale = display_locale or locale
        return self.translate(f"common.locale.{self.normalize_locale(locale)}", target_locale)

    def catalog_subset(self, locale: str, keys: Iterable[str]) -> dict[str, str]:
        return {key: self.translate(key, locale) for key in keys}


@lru_cache(maxsize=1)
def _catalog_dir() -> Path:
    return Path(__file__).resolve().parent / "catalogs"


@lru_cache(maxsize=None)
def _load_catalog(locale: str) -> dict[str, str]:
    path = _catalog_dir() / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8"))
