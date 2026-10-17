"""Process-wide logging setup, driven by the LOG_LEVEL setting."""

import logging

from app.config import settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    level = logging.getLevelName(settings.log_level.upper())
    if not isinstance(level, int):  # unknown name -> getLevelName returns a string
        level = logging.INFO
    logging.basicConfig(level=level, format=FORMAT)


def want_traceback() -> bool:
    """Tracebacks carry internal file paths; only emit them when LOG_LEVEL=DEBUG."""
    return logging.getLogger().isEnabledFor(logging.DEBUG)
