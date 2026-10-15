"""Unit tests verifying secret, credential, prompt, and row redaction in structured logging."""

import json
import logging

from app.core.logging import JSONFormatter, RedactionFilter, redact_sensitive_text


def test_redact_api_keys() -> None:
    text_openai = "Connecting with key sk-proj-1234567890abcdef1234567890 to API"
    assert "sk-proj" not in redact_sensitive_text(text_openai)
    assert "[REDACTED_API_KEY]" in redact_sensitive_text(text_openai)

    text_bearer = "Authorization: Bearer ya29.a0AfH6SMD_very_secret_token_12345"
    assert "ya29" not in redact_sensitive_text(text_bearer)
    assert "Bearer [REDACTED_TOKEN]" in redact_sensitive_text(text_bearer)


def test_redact_database_passwords() -> None:
    db_url = "postgresql+psycopg://app_rw:super_secret_password_123@127.0.0.1:5436/querypilot_app"
    redacted = redact_sensitive_text(db_url)
    assert "super_secret_password_123" not in redacted
    assert "postgresql+psycopg://app_rw:***@127.0.0.1:5436/querypilot_app" == redacted


def test_redact_system_prompts_and_tool_outputs() -> None:
    prompt_payload = "<system_instructions>You are a database engineer. Secret prompt text.</system_instructions>"
    redacted = redact_sensitive_text(prompt_payload)
    assert "Secret prompt text" not in redacted
    assert "[REDACTED_SYSTEM_PROMPT]" in redacted

    tool_payload = '<tool_output name="execute_readonly_query">Sensitive data</tool_output>'
    redacted_tool = redact_sensitive_text(tool_payload)
    assert "Sensitive data" not in redacted_tool
    assert "[REDACTED_TOOL_OUTPUT]" in redacted_tool


def test_redact_raw_database_rows() -> None:
    log_data = "{'query': 'SELECT * FROM users', 'rows': [{'id': 1, 'email': 'alice@example.com', 'ssn': '123-45'}]}"
    redacted = redact_sensitive_text(log_data)
    assert "alice@example.com" not in redacted
    assert "'rows': [REDACTED_ROWS]" in redacted


def test_json_formatter_and_filter_integration() -> None:
    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)

    log_filter = RedactionFilter()
    formatter = JSONFormatter()

    record = logger.makeRecord(
        name="test_redaction_logger",
        level=logging.INFO,
        fn="test_file.py",
        lno=42,
        msg="User attempted query with sk-abcdef1234567890 and postgresql://app_rw:secret123@localhost/db",
        args=(),
        exc_info=None,
    )

    log_filter.filter(record)
    formatted_output = formatter.format(record)
    parsed = json.loads(formatted_output)

    assert parsed["level"] == "INFO"
    assert "sk-abcdef" not in parsed["message"]
    assert "secret123" not in parsed["message"]
    assert "[REDACTED_API_KEY]" in parsed["message"]
    assert "***" in parsed["message"]
