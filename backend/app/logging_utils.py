from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    _reserved = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        for key, value in record.__dict__.items():
            if key in self._reserved:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> Path:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = Path(os.getenv("QA_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "qa_execution.log"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "format": "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
                    "datefmt": "%H:%M:%S",
                },
                "json": {"()": "app.logging_utils.JsonFormatter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": level,
                    "formatter": "console",
                    "stream": "ext://sys.stdout",
                },
                "qa_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": level,
                    "formatter": "json",
                    "filename": str(log_file),
                    "maxBytes": 20 * 1024 * 1024,
                    "backupCount": 10,
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "uvicorn.access": {"level": "INFO"},
            },
            "root": {
                "level": level,
                "handlers": ["console", "qa_file"],
            },
        }
    )

    return log_file
