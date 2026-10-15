"""Unit tests verifying evaluation harness execution, cost guard, and metrics persistence."""

import json
from pathlib import Path

import pytest

from scripts.run_eval import run_evaluation


@pytest.mark.asyncio
async def test_eval_cost_guard_aborts_when_limit_exceeded() -> None:
    """Evaluation runner must abort immediately if estimated calls exceed max_calls threshold."""
    # 30 questions * 2 = 60 calls; setting max_calls = 10 should trigger cost guard
    exit_code = await run_evaluation(
        real_llm=False,
        max_calls=10,
    )
    assert exit_code == 1


@pytest.mark.asyncio
async def test_eval_offline_pipeline_execution(tmp_path: Path) -> None:
    """Evaluation runner executes cleanly in offline FakeLLM mode and writes valid reports."""
    out_md = tmp_path / "EVAL_RESULTS.md"
    out_json = tmp_path / "eval_results.json"

    exit_code = await run_evaluation(
        real_llm=False,
        output_md=out_md,
        output_json=out_json,
        max_calls=100,
    )
    assert exit_code == 0
    assert out_md.exists()
    assert out_json.exists()

    import asyncio

    content = await asyncio.to_thread(out_json.read_text, encoding="utf-8")
    data = json.loads(content)

    assert "simple_mode" in data
    assert "agent_mode" in data
    assert data["simple_mode"]["execution_accuracy"] >= 85.0
    assert data["simple_mode"]["clarification_precision"] == 100.0
    assert data["simple_mode"]["safe_refusal_rate"] == 100.0
    assert data["agent_mode"]["execution_accuracy"] >= 85.0
    assert data["agent_mode"]["safe_refusal_rate"] == 100.0
