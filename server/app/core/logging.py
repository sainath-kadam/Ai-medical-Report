"""Centralized logging configuration.

IMPORTANT (spec §31/§33): nothing that touches patient/report/clinical content should
ever be logged. Call sites pass structured `extra=` fields for identifiers (ids, status
codes, counts) — never free-text clinical content, passwords, or tokens. This module only
configures *how* logs are formatted/routed; enforcing *what* gets logged is a code-review
concern at each call site.
"""

import logging
import sys

from app.core.config import settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if not settings.is_production else logging.INFO
    fmt = (
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        if not settings.is_production
        else '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Quiet noisy third-party loggers down a notch so our own logs aren't drowned out.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
