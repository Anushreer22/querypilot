"""Structured JSON logging with contextvars and security redaction filter."""

import contextvars
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# Context variables for distributed tracing across requests and agent runs
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
run_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
step_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar("step", default=None)

# Secret and sensitive data redaction regex patterns
REDACTION_PATTERNS = [
    # API keys (OpenAI, Gemini, general bearer tokens)
    (re.compile(r"sk-[a-zA-Z0-9_\-]{10,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (
        re.compile(
            r"(api[_-]?key|secret|password|auth_token)\s*[:=]\s*['\"]?([^'\"\s,\}\]]+)['\"]?",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
    # Database connection strings with credentials
    (
        re.compile(r"(postgres(?:ql)?(?:\+[a-z0-9]+)?://[^:]+:)([^@]+)(@)", re.IGNORECASE),
        r"\1***\3",
    ),
    # Prompt text and system instruction blocks
    (
        re.compile(r"<system_instructions>.*?</system_instructions>", re.DOTALL | re.IGNORECASE),
        "[REDACTED_SYSTEM_PROMPT]",
    ),
    (
        re.compile(r"<tool_output[^>]*>.*?</tool_output>", re.DOTALL | re.IGNORECASE),
        "[REDACTED_TOOL_OUTPUT]",
    ),
    # Full prompt parameters
    (
        re.compile(
            r"('full_prompt'|\"full_prompt\"|'prompt'|\"prompt\")\s*:\s*['\"].*?['\"](?=[,\s\}])",
            re.DOTALL | re.IGNORECASE,
        ),
        r"\1: '[REDACTED_PROMPT]'",
    ),
    # Result rows
    (
        re.compile(r"('rows'|\"rows\")\s*:\s*\[.*?\](?=[,\s\}])", re.DOTALL | re.IGNORECASE),
        r"\1: [REDACTED_ROWS]",
    ),
]


def redact_sensitive_text(text: str) -> str:
    """Scrub sensitive credentials, passwords, prompts, and database rows from string."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials and payloads from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive_text(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    redact_sensitive_text(a) if isinstance(a, str) else a for a in record.args
                )
        return True


class JSONFormatter(logging.Formatter):
    """Formatter outputting single-line structured JSON logs with tracing metadata."""

    def format(self, record: logging.LogRecord) -> str:
        # Base structured fields
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "run_id": run_id_ctx.get(),
            "step": step_ctx.get(),
        }

        # Add optional route metrics if set on the record
        if hasattr(record, "route"):
            log_entry["route"] = record.route
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        if hasattr(record, "latency_ms"):
            log_entry["latency_ms"] = record.latency_ms

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure root logger to use JSON formatting and redaction filter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RedactionFilter())
    root_logger.addHandler(handler)
