from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from pysm.config import AppPaths


def configure_logging(paths: AppPaths) -> None:
    log_file = paths.logs_dir / "pysm.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

