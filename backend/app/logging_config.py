"""
AuraGrade — Structured Logging Configuration
=============================================
Replaces all print() statements with proper structured logging.
Supports JSON output in production, human-readable in development.
Includes request correlation IDs for distributed tracing.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

# Context variable for request correlation
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production environments."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request correlation ID if available
        req_id = request_id_var.get()
        if req_id:
            log_entry["request_id"] = req_id

        # Add exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        # Add extra fields
        for key in ("status_code", "method", "path", "duration_ms", "user_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable colored formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET

        # Build prefix
        req_id = request_id_var.get()
        req_prefix = f"[{req_id[:8]}] " if req_id else ""

        timestamp = datetime.now().strftime("%H:%M:%S")
        return (
            f"{color}{timestamp} {record.levelname:8s}{reset} "
            f"{req_prefix}{record.name}: {record.getMessage()}"
        )


def setup_logging(log_level: str = "INFO", is_production: bool = False) -> None:
    """Configure the root logger and all AuraGrade loggers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove any existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Set formatter based on environment
    if is_production:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter())

    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def generate_request_id() -> str:
    """Generate a unique request correlation ID."""
    return str(uuid.uuid4())


# Convenience logger factory
def get_logger(name: str) -> logging.Logger:
    """Get a named logger for the AuraGrade application."""
    return logging.getLogger(f"auragrade.{name}")
