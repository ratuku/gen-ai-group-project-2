"""Evaluation integrity checks; fake responses are never model-comparison evidence."""

import asyncio
import argparse
import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from coding_assistant.contracts import Payload
from evaluations.model_comparison.run import ROOT, assess, evaluate, grade, run_task
from evaluations.model_comparison.checkpoint import latest_runs, output_lock, validate_resume
from evaluations.model_comparison.tasks import TASKS


def test_original_bug_and_stubs_fail_checks(tmp_path: Path) -> None:
    for task in TASKS:
        (tmp_path / "solution.py").write_text(task.source, encoding="utf-8")
        result = grade(task, tmp_path)
        # Refactor starts behaviorally correct, but has no shared helper.
        assert result["passed"] is False, (task.name, result)


@pytest.mark.parametrize("index,source", [
    (0, "def average(values):\n    if not values: raise ValueError('empty')\n    return sum(values)/len(values)\n"),
    (1, "import re\ndef unique_words(text):\n    return list(dict.fromkeys(w.lower() for w in re.findall('[a-z]+', text, flags=re.ASCII | re.IGNORECASE)))\n"),
    (2, "def total(rows, region):\n    return sum(r['amount'] for r in rows if r['region'] == region)\n"
        "def summarize_sales(rows):\n    return {k: total(rows, k) for k in dict.fromkeys(['north', 'south'] + [r['region'] for r in rows])}\n"),
    (3, "from pathlib import Path\ndef write_greeting(path, name):\n    return Path(path).write_text(f'Hello, {name}!\\n', encoding='utf-8')\n"),
])
def test_reference_solutions_pass(tmp_path: Path, index: int, source: str) -> None:
    (tmp_path / "solution.py").write_text(source, encoding="utf-8")
    result = grade(TASKS[index], tmp_path)
    assert result["passed"], result


def test_claimed_completion_is_not_task_success() -> None:
    events: list[Payload] = [{"type": "text", "content": "Done"},
                             {"type": "completed", "reason": "answered"}]
    assert not assess(TASKS[0], events, {"passed": True})["passed"]


def test_success_requires_retrieval_and_normal_completion() -> None:
    events: list[Payload] = [
        {"type": "tool_result", "name": "filesystem.read_text_file", "is_error": False},
        {"type": "tool_result", "name": "filesystem.write_file", "is_error": False},
        {"type": "completed", "reason": "answered"},
    ]
    assert assess(TASKS[0], events, {"passed": True})["passed"]
    assert not assess(TASKS[3], events, {"passed": True})["passed"]
    events[-1] = {"type": "completed", "reason": "iteration_limit"}
    assert not assess(TASKS[0], events, {"passed": True})["passed"]


class RepairProvider:
    """Harness plumbing only: edit via real filesystem MCP, then finish."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        assert any(tool["name"] == "filesystem.write_file" for tool in tools)
        count = sum(message["role"] == "tool" for message in messages)
        if count == 0:
            yield {"type": "tool_call", "name": "filesystem.read_text_file",
                   "arguments": {"path": str(self.workspace / "solution.py")}}
        elif count == 1:
            yield {"type": "tool_call", "name": "filesystem.write_file", "arguments": {
                "path": str(self.workspace / "solution.py"),
                "content": "def average(values):\n    if not values: raise ValueError('empty')\n    return sum(values)/len(values)\n",
            }}
        else:
            yield {"type": "text", "content": "Fixed average."}


@pytest.mark.asyncio
async def test_runner_uses_real_mcp_and_retains_trace(tmp_path: Path) -> None:
    workspace = tmp_path / "coding workspace"
    result = await run_task(
        TASKS[0], RepairProvider(workspace), workspace,
        config_path=ROOT / "config/mcp.json", filesystem_only=True,
        timeout=30, max_iterations=4,
    )
    assert result["passed"], result
    assert result["tool_calls"] == 3
    assert result["tool_sequence"] == ["filesystem.read_text_file", "filesystem.write_file", "filesystem.read_text_file"]
    assert result["events"]


class WaitingProvider:
    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        yield {"type": "status", "content": "waiting"}
        await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_timeout_retains_failure_and_closes_real_transport(tmp_path: Path) -> None:
    result = await run_task(
        TASKS[0], WaitingProvider(), tmp_path / "timeout",
        config_path=ROOT / "config/mcp.json", filesystem_only=True,
        timeout=2, max_iterations=4,
    )
    assert not result["passed"]
    assert "Task exceeded" in str(result["errors"])


class SyntaxRepairProvider:
    def __init__(self, workspace: Path, *, repair: bool) -> None:
        self.workspace, self.repair, self.turn = workspace, repair, 0

    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        self.turn += 1
        if self.turn == 1:
            yield {"type": "tool_call", "name": "filesystem.read_text_file",
                   "arguments": {"path": str(self.workspace / "solution.py")}}
        elif self.turn == 2 or (self.turn == 3 and self.repair):
            if self.turn == 3:
                assert "IndentationError" in str(messages[-1])
            source = ("def average(values):\nreturn 0\n" if self.turn == 2 else
                      "def average(values):\n    if not values: raise ValueError('empty')\n    return sum(values)/len(values)\n")
            yield {"type": "tool_call", "name": "filesystem.write_file",
                   "arguments": {"path": str(self.workspace / "solution.py"), "content": source}}
        else:
            yield {"type": "text", "content": "Finished"}


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.asyncio
async def test_saved_syntax_feedback_repairs_or_blocks_completion(tmp_path: Path, repair: bool) -> None:
    workspace = tmp_path / "syntax"
    result = await run_task(TASKS[0], SyntaxRepairProvider(workspace, repair=repair), workspace,
                            config_path=ROOT / "config/mcp.json", filesystem_only=True,
                            timeout=30, max_iterations=5)
    assert result["passed"] is repair
    assert result["outcome"] == ("passed" if repair else "coding_failure")
    assert result["completion_reason"] == ("answered" if repair else "validation_failed")


def test_provider_limit_survives_assessment_without_hiding_failed_checks() -> None:
    result = assess(TASKS[0], [{"type": "error", "error_code": "provider_daily_limit",
                               "content": "Daily allowance"}], {"passed": False})
    assert result["outcome"] == "provider_blocked"
    assert result["passed"] is False
    assert result["checks"] == {"passed": False}


@pytest.mark.asyncio
async def test_pause_resume_preserves_attempts_and_skips_completed_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import evaluations.model_comparison.run as runner
    monkeypatch.setenv("GROQ_API_KEY", "checkpoint-test-key")
    args = argparse.Namespace(models=["model-a", "model-b"], output=tmp_path / "batch",
                              config=ROOT / "config/mcp.json", api_key_file=None, filesystem_only=True,
                              repeats=1, max_iterations=8, timeout=180, resume=False, tokens_per_minute=7000)
    calls: list[tuple[str, str]] = []
    blocked_once = False

    async def fake_task(task: object, provider: object, workspace: Path, **kwargs: object) -> dict[str, object]:
        nonlocal blocked_once
        name, model = str(getattr(task, "name")), str(getattr(provider, "model"))
        calls.append((name, model))
        workspace.mkdir(parents=True)
        (workspace / "solution.py").write_bytes(b"pass\n")
        blocked = len(calls) == 2 and not blocked_once
        blocked_once = blocked_once or blocked
        # A genuine coding failure is completed work and must not be retried.
        passed = not blocked and len(calls) != 1
        return {"task": name, "passed": passed, "outcome": "provider_blocked" if blocked else "passed" if passed else "coding_failure",
                "checks": {"passed": passed}, "errors": [], "events": [], "tool_calls": 2, "tool_errors": 0,
                "elapsed_seconds": 1, "completion_reason": "error" if blocked else "answered",
                "missing_required_tools": [], "read_existing_code": True, "edited_file": True, "tool_sequence": [],
                "final_source_sha256": hashlib.sha256(b"pass\n").hexdigest()}

    monkeypatch.setattr(runner, "run_task", fake_task)
    assert await evaluate(args) == 3
    first = (args.output / "results.json").read_bytes()
    assert len(calls) == 2
    args.resume = True
    assert await evaluate(args) == 1  # The genuine coding failure is retained.
    assert calls.count(("bugfix", "model-a")) == 1
    assert calls.count(("bugfix", "model-b")) == 2
    runs = json.loads((args.output / "results.json").read_text())
    assert runs[:2] == json.loads(first)
    assert len(runs) == 7 and len(latest_runs(runs)) == 6
    assert len({run["workspace"] for run in runs}) == 7
    assert "checkpoint-test-key" not in (args.output / "results.json").read_text()
    report = (args.output / "REPORT.md").read_text()
    assert "5/6 planned slots" in report and "provider_blocked" in report
    assert "5/7" in report
    # Completed resume makes no more model/task calls.
    assert await evaluate(args) == 1 and len(calls) == 7
    args.tokens_per_minute = 6000
    with pytest.raises(ValueError, match="pacing_tokens_per_minute"):
        await evaluate(args)
    assert len(calls) == 7
    args.tokens_per_minute = 7000
    (args.output / runs[0]["workspace"] / "solution.py").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="Saved evaluation source changed"):
        await evaluate(args)
    assert len(calls) == 7


@pytest.mark.asyncio
async def test_resume_preserves_interrupted_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import evaluations.model_comparison.run as runner
    monkeypatch.setenv("GROQ_API_KEY", "checkpoint-test-key")
    args = argparse.Namespace(models=["a", "b"], output=tmp_path / "interrupted",
                              config=ROOT / "config/mcp.json", api_key_file=None, filesystem_only=True,
                              repeats=1, max_iterations=8, timeout=180, resume=False, tokens_per_minute=7000)
    workspaces: list[Path] = []

    async def interrupted(task: object, provider: object, workspace: Path, **kwargs: object) -> dict[str, object]:
        workspaces.append(workspace)
        workspace.mkdir(parents=True)
        (workspace / "solution.py").write_bytes(b"# partial saved work\n")
        raise asyncio.CancelledError

    monkeypatch.setattr(runner, "run_task", interrupted)
    with pytest.raises(asyncio.CancelledError):
        await evaluate(args)
    args.resume = True
    with pytest.raises(asyncio.CancelledError):
        await evaluate(args)
    assert workspaces[0] != workspaces[1]
    assert all((path / "solution.py").read_bytes() == b"# partial saved work\n" for path in workspaces)
    assert json.loads((args.output / "results.json").read_text()) == []


class PacedProvider:
    async def stream(self, messages: Sequence[Payload], tools: Sequence[Payload]) -> AsyncIterator[Payload]:
        yield {"type": "status", "content": "Test pacing wait", "wait_seconds": 2.5}
        await asyncio.sleep(2.5)
        yield {"type": "text", "content": "No edit"}


@pytest.mark.asyncio
async def test_explicit_pacing_wait_is_not_counted_as_task_timeout(tmp_path: Path) -> None:
    result = await run_task(TASKS[0], PacedProvider(), tmp_path / "paced",
                            config_path=ROOT / "config/mcp.json", filesystem_only=True,
                            timeout=2, max_iterations=4)
    assert result["completion_reason"] == "answered"
    assert float(str(result["elapsed_seconds"])) >= 2.5
    assert not result["passed"]  # Waiting never substitutes for doing the task.


def test_output_lock_prevents_two_runners(tmp_path: Path) -> None:
    with output_lock(tmp_path):
        with pytest.raises(OSError):
            with output_lock(tmp_path):
                pytest.fail("Concurrent runner acquired lock")
    with output_lock(tmp_path):
        pass


def test_resume_rejects_old_metadata() -> None:
    with pytest.raises(ValueError, match="Use a new output directory"):
        validate_resume({}, {})
