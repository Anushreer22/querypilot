"""Query execution and history endpoints."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.db.models import QueryHistory
from app.db.session import AppAsyncSessionLocal
from app.schemas.query import (
    ExecuteQueryRequest,
    ExecuteQueryResponse,
    QueryHistoryItem,
    QueryHistoryResponse,
)
from app.services.query_executor import (
    QueryExecutionError,
    QueryTimeoutError,
    execute_readonly_query,
    log_query_history,
)
from app.services.sql_validator import validate_sql

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post(
    "/execute",
    response_model=ExecuteQueryResponse,
    summary="Validate and execute a read-only SQL query",
    responses={
        422: {"description": "SQL validation failed or security violation"},
        400: {"description": "PostgreSQL query execution error"},
        504: {"description": "Query execution timed out"},
    },
)
async def execute_query(payload: ExecuteQueryRequest) -> ExecuteQueryResponse:
    """Validate, sanitize, and execute an ad-hoc SQL query against sample_shop.

    Enforces AST security constraints, clamps limits, executes in a read-only
    transaction with statement timeouts, and logs all attempts into the audit ledger.
    """
    # 1. AST-based SQL validation & sanitization
    validation = validate_sql(payload.sql)
    if not validation.ok:
        await log_query_history(
            sql_text=payload.sql,
            status="rejected",
            source=payload.source,
            duration_ms=0.0,
            row_count=0,
            error_message=validation.reason,
        )
        raise HTTPException(
            status_code=422,
            detail=validation.reason or "SQL validation failed",
        )

    # 2. Execute ONLY the sanitized SQL
    sanitized_sql = validation.sanitized_sql
    if not sanitized_sql:
        raise HTTPException(
            status_code=422,
            detail="Sanitized SQL could not be generated",
        )

    try:
        exec_result = await execute_readonly_query(
            sanitized_sql=sanitized_sql,
            timeout_ms=payload.timeout_ms,
        )
    except QueryTimeoutError as exc:
        await log_query_history(
            sql_text=sanitized_sql,
            status="timeout",
            source=payload.source,
            duration_ms=exc.duration_ms,
            error_message=exc.message,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except QueryExecutionError as exc:
        await log_query_history(
            sql_text=sanitized_sql,
            status="error",
            source=payload.source,
            duration_ms=exc.duration_ms,
            error_message=exc.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc

    # 3. Log successful execution
    await log_query_history(
        sql_text=sanitized_sql,
        status="success",
        source=payload.source,
        duration_ms=exec_result.duration_ms,
        row_count=exec_result.row_count,
    )

    return ExecuteQueryResponse(
        columns=exec_result.columns,
        rows=exec_result.rows,
        row_count=exec_result.row_count,
        duration_ms=exec_result.duration_ms,
        limit_injected=validation.limit_injected,
        truncated=exec_result.truncated,
        sanitized_sql=sanitized_sql,
    )


@router.get(
    "/history",
    response_model=QueryHistoryResponse,
    summary="Fetch query execution audit history",
)
async def get_query_history(
    limit: int = Query(50, ge=1, le=200, description="Max history items to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> QueryHistoryResponse:
    """Retrieve paginated query audit logs ordered by creation timestamp descending."""
    async with AppAsyncSessionLocal() as session:
        # Count total records
        count_stmt = select(func.count(QueryHistory.id))
        total_count = (await session.execute(count_stmt)).scalar() or 0

        # Fetch records
        stmt = (
            select(QueryHistory)
            .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
            .offset(offset)
            .limit(limit)
        )
        results = (await session.execute(stmt)).scalars().all()

        items = [QueryHistoryItem.model_validate(row) for row in results]
        return QueryHistoryResponse(items=items, total=total_count)
