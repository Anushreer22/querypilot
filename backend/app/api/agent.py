"""API endpoints for autonomous database agent."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.agent.loop import AgentLoop
from app.core.config import settings
from app.db.models import AgentRun
from app.db.session import AppAsyncSessionLocal
from app.schemas.agent import (
    AgentActionItem,
    AgentAskRequest,
    AgentAskResponse,
    AgentRunDetailResponse,
    AgentRunSummary,
)
from app.services.ask_service import InMemoryRateLimiter

router = APIRouter(prefix="/api/agent", tags=["Agent"])

agent_rate_limiter = InMemoryRateLimiter(limit_per_minute=settings.rate_limit_agent_per_minute)


async def check_agent_rate_limit(request: Request) -> None:
    """Enforce per-client-IP rate limits for agent requests."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not await agent_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for agent queries. Please wait before submitting additional questions.",
        )


@router.post(
    "/ask",
    response_model=AgentAskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_agent_rate_limit)],
)
async def ask_agent(
    payload: AgentAskRequest,
) -> JSONResponse:
    """Execute autonomous agent reasoning and tool-calling loop."""
    loop = AgentLoop()
    response = await loop.run(payload.question)

    status_code = status.HTTP_200_OK
    if response.status in ("completed", "clarification"):
        status_code = status.HTTP_200_OK
    elif response.status in ("step_limit_exceeded", "repeated_failure"):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif response.status == "timeout":
        status_code = status.HTTP_504_GATEWAY_TIMEOUT
    elif response.status == "llm_failure":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif response.status == "error":
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
async def get_agent_run(run_id: str) -> AgentRunDetailResponse:
    """Fetch full execution details of an agent run including all tool actions."""
    async with AppAsyncSessionLocal() as session:
        stmt = select(AgentRun).options(selectinload(AgentRun.actions)).where(AgentRun.id == run_id)
        result = await session.execute(stmt)
        run_record = result.scalar_one_or_none()

        if not run_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent run '{run_id}' not found.",
            )

        summary = AgentRunSummary(
            id=run_record.id,
            question=run_record.question,
            status=run_record.status,
            final_answer=run_record.final_answer,
            step_count=run_record.step_count,
            total_duration_ms=float(run_record.total_duration_ms),
            llm_provider=run_record.llm_provider,
            llm_model=run_record.llm_model,
            created_at=run_record.created_at,
        )

        actions = [
            AgentActionItem(
                step=a.step_number,
                tool=a.tool_name,
                arguments=a.arguments,
                status=a.status,
                duration_ms=float(a.duration_ms),
                summary=a.result_summary,
            )
            for a in run_record.actions
        ]

        return AgentRunDetailResponse(run=summary, actions=actions)


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_agent_runs(
    limit: int = Query(default=20, ge=1, le=100, description="Max runs to return"),
) -> list[AgentRunSummary]:
    """List recent agent runs."""
    async with AppAsyncSessionLocal() as session:
        stmt = select(AgentRun).order_by(desc(AgentRun.created_at)).limit(limit)
        result = await session.execute(stmt)
        records = result.scalars().all()

        return [
            AgentRunSummary(
                id=r.id,
                question=r.question,
                status=r.status,
                final_answer=r.final_answer,
                step_count=r.step_count,
                total_duration_ms=float(r.total_duration_ms),
                llm_provider=r.llm_provider,
                llm_model=r.llm_model,
                created_at=r.created_at,
            )
            for r in records
        ]
