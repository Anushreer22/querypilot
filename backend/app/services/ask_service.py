"""Core orchestration service for natural language to SQL translation, validation, single repair, and audit logging."""

import asyncio
import logging
import time

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.ask import (
    AskResponse,
    AskResultPayload,
    ClarificationResponse,
)
from app.services.llm.base import (
    LLMInvalidResponse,
    LLMRateLimit,
    LLMTimeout,
    LLMUnavailable,
)
from app.services.llm.factory import get_llm_client
from app.services.query_executor import (
    QueryExecutionError,
    QueryTimeoutError,
    execute_readonly_query,
    log_query_history,
)
from app.services.schema_context import get_schema_context
from app.services.sql_generator import (
    GeneratedSQLResponse,
    build_repair_user_prompt,
    build_system_prompt,
    build_user_prompt,
    generate_sql_response,
)
from app.services.sql_validator import validate_sql

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window in-memory IP rate limiter."""

    def __init__(self, limit_per_minute: int = 10) -> None:
        self.limit_per_minute = limit_per_minute
        self._history: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> bool:
        """Return True if the client is within the rate limit, otherwise False."""
        now = time.monotonic()
        cutoff = now - 60.0

        async with self._lock:
            timestamps = self._history.get(client_ip, [])
            # Purge timestamps older than 60 seconds
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= self.limit_per_minute:
                self._history[client_ip] = valid_timestamps
                return False

            valid_timestamps.append(now)
            self._history[client_ip] = valid_timestamps
            return True

    def reset(self) -> None:
        """Clear rate limit history (for testing)."""
        self._history.clear()


rate_limiter = InMemoryRateLimiter(limit_per_minute=settings.rate_limit_ask_per_minute)


async def ask_question(question: str, client_ip: str = "127.0.0.1") -> AskResponse:
    """Process a natural language question through the prompt-and-repair flow.

    Steps:
    1. Check in-memory client rate limit.
    2. Build compact schema context and call LLM for structured JSON.
    3. If question is ambiguous (needs_clarification), return clarification without running SQL.
    4. Validate generated SQL with Phase 3 AST validator.
    5. Execute sanitized SQL in read-only transaction.
    6. If validation or execution encounters a fixable error, execute exactly ONE repair attempt.
    7. Log every interaction outcome to query_history ledger.
    """
    clean_question = question.strip()
    if not clean_question:
        raise HTTPException(status_code=400, detail="Question cannot be empty or whitespace only")

    # 1. Rate limiting check
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {settings.rate_limit_ask_per_minute} requests per minute.",
        )

    llm = get_llm_client()

    # 2. Build schema context
    schema_context = await get_schema_context()
    system_prompt = build_system_prompt(schema_context)
    user_prompt = build_user_prompt(clean_question)

    # 3. Call LLM for initial query generation
    llm_start = time.perf_counter()
    try:
        gen_response: GeneratedSQLResponse = await generate_sql_response(
            llm=llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        llm_latency_ms = int((time.perf_counter() - llm_start) * 1000.0)
    except LLMTimeout as exc:
        await log_query_history(
            sql_text="",
            status="timeout",
            source="ask",
            question=clean_question,
            error_message="LLM generation timed out",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
        )
        raise HTTPException(status_code=504, detail="LLM request timed out") from exc
    except LLMRateLimit as exc:
        await log_query_history(
            sql_text="",
            status="llm_failure",
            source="ask",
            question=clean_question,
            error_message="LLM provider rate limit exceeded",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
        )
        raise HTTPException(
            status_code=503,
            detail="LLM provider rate limit exceeded; please try again later",
        ) from exc
    except (LLMUnavailable, LLMInvalidResponse) as exc:
        await log_query_history(
            sql_text="",
            status="llm_failure",
            source="ask",
            question=clean_question,
            error_message=exc.message[:2000],
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
        )
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc.message}") from exc

    # 4. Handle Clarification Flow (No SQL executed)
    if gen_response.needs_clarification:
        clarification_msg = (
            gen_response.clarification_question
            or gen_response.explanation
            or "Could you please clarify your request?"
        )
        await log_query_history(
            sql_text="",
            status="clarification",
            source="ask",
            question=clean_question,
            explanation=gen_response.explanation,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        return AskResponse(
            question=clean_question,
            sql=None,
            explanation=gen_response.explanation,
            assumptions=gen_response.assumptions,
            results=None,
            repaired=False,
            clarification=ClarificationResponse(clarification_question=clarification_msg),
            status="clarification",
        )

    # 5. Validate initial SQL with Phase 3 AST validator
    initial_sql = gen_response.sql
    validation = validate_sql(initial_sql)
    fixable_error: str | None = None

    if not validation.ok:
        fixable_error = validation.reason or "Validation rejected query"
    else:
        # Initial execution attempt
        sanitized_sql = validation.sanitized_sql
        try:
            exec_res = await execute_readonly_query(sanitized_sql=sanitized_sql)
            # Success on initial attempt
            await log_query_history(
                sql_text=sanitized_sql,
                status="success",
                source="ask",
                question=clean_question,
                explanation=gen_response.explanation,
                duration_ms=exec_res.duration_ms,
                row_count=exec_res.row_count,
                repaired=False,
                llm_provider=settings.llm_provider,
                llm_model=settings.llm_model,
                llm_latency_ms=llm_latency_ms,
            )
            return AskResponse(
                question=clean_question,
                sql=sanitized_sql,
                explanation=gen_response.explanation,
                assumptions=gen_response.assumptions,
                results=AskResultPayload(
                    columns=exec_res.columns,
                    rows=exec_res.rows,
                    row_count=exec_res.row_count,
                    duration_ms=exec_res.duration_ms,
                    truncated=exec_res.truncated,
                ),
                repaired=False,
                clarification=None,
                status="success",
            )
        except QueryTimeoutError as exc:
            # Never repair timeouts
            await log_query_history(
                sql_text=sanitized_sql,
                status="timeout",
                source="ask",
                question=clean_question,
                explanation=gen_response.explanation,
                duration_ms=exc.duration_ms,
                error_message=exc.message,
                llm_provider=settings.llm_provider,
                llm_model=settings.llm_model,
                llm_latency_ms=llm_latency_ms,
            )
            raise HTTPException(status_code=504, detail=exc.message) from exc
        except QueryExecutionError as exc:
            # Check if this is a permission error (never repair permission errors)
            if exc.sqlstate in ("42501", "25006"):
                await log_query_history(
                    sql_text=sanitized_sql,
                    status="error",
                    source="ask",
                    question=clean_question,
                    explanation=gen_response.explanation,
                    duration_ms=exc.duration_ms,
                    error_message=exc.message,
                    llm_provider=settings.llm_provider,
                    llm_model=settings.llm_model,
                    llm_latency_ms=llm_latency_ms,
                )
                raise HTTPException(status_code=422, detail=f"Permission error: {exc.message}") from exc
            fixable_error = exc.message

    # 6. Single Repair Attempt
    logger.info("Triggering single repair attempt for question '%s' due to: %s", clean_question[:50], fixable_error)
    repair_user_prompt = build_repair_user_prompt(
        question=clean_question,
        previous_sql=initial_sql,
        error_message=fixable_error or "Unknown SQL error",
    )

    try:
        repair_gen: GeneratedSQLResponse = await generate_sql_response(
            llm=llm,
            system_prompt=system_prompt,
            user_prompt=repair_user_prompt,
        )
    except Exception as exc:
        await log_query_history(
            sql_text=initial_sql,
            status="error",
            source="ask",
            question=clean_question,
            explanation=gen_response.explanation,
            repaired=True,
            repair_sql=initial_sql,
            error_message=f"Repair generation failed: {exc}",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        raise HTTPException(
            status_code=422,
            detail=f"SQL repair generation failed: {exc}",
        ) from exc

    repaired_sql = repair_gen.sql
    repair_val = validate_sql(repaired_sql)

    if not repair_val.ok:
        await log_query_history(
            sql_text=repaired_sql,
            status="rejected",
            source="ask",
            question=clean_question,
            explanation=repair_gen.explanation,
            repaired=True,
            repair_sql=initial_sql,
            error_message=repair_val.reason,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Repaired SQL validation failed: {repair_val.reason}",
        )

    # Execute repaired SQL
    sanitized_repaired_sql = repair_val.sanitized_sql
    try:
        exec_repaired = await execute_readonly_query(sanitized_sql=sanitized_repaired_sql)
        await log_query_history(
            sql_text=sanitized_repaired_sql,
            status="success",
            source="ask",
            question=clean_question,
            explanation=repair_gen.explanation,
            duration_ms=exec_repaired.duration_ms,
            row_count=exec_repaired.row_count,
            repaired=True,
            repair_sql=initial_sql,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        return AskResponse(
            question=clean_question,
            sql=sanitized_repaired_sql,
            explanation=repair_gen.explanation,
            assumptions=repair_gen.assumptions,
            results=AskResultPayload(
                columns=exec_repaired.columns,
                rows=exec_repaired.rows,
                row_count=exec_repaired.row_count,
                duration_ms=exec_repaired.duration_ms,
                truncated=exec_repaired.truncated,
            ),
            repaired=True,
            clarification=None,
            status="success",
        )
    except QueryTimeoutError as exc:
        await log_query_history(
            sql_text=sanitized_repaired_sql,
            status="timeout",
            source="ask",
            question=clean_question,
            explanation=repair_gen.explanation,
            duration_ms=exc.duration_ms,
            repaired=True,
            repair_sql=initial_sql,
            error_message=exc.message,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        raise HTTPException(status_code=504, detail=exc.message) from exc
    except QueryExecutionError as exc:
        await log_query_history(
            sql_text=sanitized_repaired_sql,
            status="error",
            source="ask",
            question=clean_question,
            explanation=repair_gen.explanation,
            duration_ms=exc.duration_ms,
            repaired=True,
            repair_sql=initial_sql,
            error_message=exc.message,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_latency_ms=llm_latency_ms,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Repaired SQL query execution failed: {exc.message}",
        ) from exc
