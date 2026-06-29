import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(name: str = "opencode_session_web") -> logging.Logger:
    logger = logging.getLogger(name)
    if getattr(logger, "_opencode_session_web_configured", False):
        return logger

    level_name = os.environ.get("OPENCODE_WEB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = Path(os.environ.get("OPENCODE_WEB_LOG_DIR", Path.home() / ".opencode-session-web" / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=int(os.environ.get("OPENCODE_WEB_LOG_MAX_BYTES", str(5 * 1024 * 1024))),
        backupCount=int(os.environ.get("OPENCODE_WEB_LOG_BACKUPS", "5")),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    logger.setLevel(level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger._opencode_session_web_configured = True
    return logger
