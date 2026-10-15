"""FastAPI router for AI-powered SQL generation (/api/ask)."""

from fastapi import APIRouter, Request

from app.schemas.ask import AskRequest, AskResponse
from app.services.ask_service import ask_question

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post(
    "",
    response_model=AskResponse,
    summary="Generate and execute read-only SQL from a natural language question",
    responses={
        200: {"description": "Query executed successfully or clarification requested"},
        400: {"description": "Invalid question input"},
        422: {"description": "Model SQL failed validation or could not be repaired"},
        429: {"description": "Rate limit exceeded (max 10 requests per minute)"},
        502: {"description": "LLM service unavailable or invalid response"},
        503: {"description": "LLM rate limited"},
        504: {"description": "Database statement timeout or LLM timeout"},
    },
)
async def ask_endpoint(payload: AskRequest, request: Request) -> AskResponse:
    """Natural language to safe SQL generation with prompt-and-repair flow.

    Translates user questions into validated read-only PostgreSQL queries,
    runs them against sample_shop within strict transaction constraints,
    repairs fixable errors with a single repair attempt, and logs the complete audit trail.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    return await ask_question(question=payload.question, client_ip=client_ip)
