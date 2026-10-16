"""Run identical tasks through real model adapters, agent loop, and MCP tools."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from coding_assistant.agent import BasicAgentLoop
from coding_assistant.config import load_mcp_config
from coding_assistant.contracts import ModelProvider, Payload
from coding_assistant.execution import PolicyMCPClient
from coding_assistant.mcp import MCPClient

from .tasks import TASKS, Task
from .checkpoint import RETRYABLE, atomic_json, latest_runs, outcome, output_lock, validate_resume

ROOT = Path(__file__).resolve().parents[2]


def grade(task: Task, workspace: Path) -> dict[str, object]:
    """Run evaluator-owned checks outside the model's writable workspace."""
    source_path = workspace / "solution.py"
    if not source_path.is_file():
        return {"passed": False, "detail": "solution.py is missing"}
    code = (
        "import runpy\nfrom pathlib import Path\n"
        f"source = Path({str(source_path)!r}).read_text(encoding='utf-8')\n"
        f"s = runpy.run_path({str(source_path)!r})\n" + task.checks
    )
    # Do not pass provider credentials to generated code.
    env = {k: v for k, v in os.environ.items() if not any(
        marker in k.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")
    )}
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-B", "-c", code], cwd=workspace,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, env=env,
        )
        return {
            "passed": result.returncode == 0,
            "detail": (result.stdout + result.stderr)[-6000:],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "detail": "Correctness checks exceeded 15 seconds"}


def assess(task: Task, events: Sequence[Payload], checks: dict[str, object]) -> dict[str, object]:
    results = [event for event in events if event.get("type") == "tool_result"]
    successful_tools = [str(e.get("name")) for e in results if not e.get("is_error")]
    # read_file/read_multiple_files are equally valid ways to inspect existing code.
    read = any(name in successful_tools for name in (
        "filesystem.read_text_file", "filesystem.read_file", "filesystem.read_multiple_files"
    ))
    edited = any(name in successful_tools for name in (
        "filesystem.write_file", "filesystem.edit_file"
    ))
    missing = [name for name in task.required_tools if not any(
        tool.startswith(name) for tool in successful_tools
    )]
    completion: Payload = next((e for e in reversed(events) if e.get("type") == "completed"), {})
    errors = [str(e.get("content")) for e in events if e.get("type") == "error"]
    passed = bool(checks["passed"] and read and edited and not missing
                  and completion.get("reason") == "answered" and not errors)
    return {
        "passed": passed, "checks": checks, "read_existing_code": read,
        "outcome": outcome(events, passed=passed, checks_passed=bool(checks["passed"]),
                           completion=str(completion.get("reason", "missing"))),
        "edited_file": edited, "missing_required_tools": missing,
        "completion_reason": completion.get("reason", "missing"),
        "iterations": completion.get("iterations"), "errors": errors,
        "tool_calls": sum(e.get("type") == "tool_call" for e in events),
        "tool_errors": sum(bool(e.get("is_error")) for e in results),
        "tool_sequence": [str(e.get("name")) for e in events if e.get("type") == "tool_call"],
    }


async def run_task(
    task: Task, provider: ModelProvider, workspace: Path, *, config_path: Path,
    filesystem_only: bool, timeout: float, max_iterations: int,
) -> dict[str, object]:
    workspace.mkdir(parents=True)
    (workspace / "solution.py").write_text(task.source, encoding="utf-8")
    prompt = (
        f"Your coding workspace is {workspace}. Use absolute paths for filesystem "
        "tools. Modify files to complete the task, then explain your changes. "
        "Only this workspace is available for file operations.\n\n" + task.prompt
    )
    config = load_mcp_config(config_path, workspace_root=workspace)
    servers = tuple(s for s in config.servers if not filesystem_only or s.name == "filesystem")
    if not any(s.name == "filesystem" for s in servers):
        raise ValueError("Evaluation requires the filesystem MCP server")
    events: list[Payload] = []
    tools: Sequence[Payload] = ()
    started = time.perf_counter()
    # Keep transport entry/exit in the same task (MCP uses nested async contexts).
    async with MCPClient(servers) as client:
        try:
            async with asyncio.timeout(timeout) as active_timeout:
                await client.connect_all()
                tools = await client.list_tools()
                policy = PolicyMCPClient(client, mode="auto")
                agent = BasicAgentLoop(provider, policy, max_iterations=max_iterations)
                async for event in agent.run(prompt):
                    events.append({**event, "elapsed_seconds": round(time.perf_counter() - started, 3)})
                    if event.get("type") == "status":
                        print(f"  {event.get('content', '')}", flush=True)
                        wait = event.get("wait_seconds", 0)
                        deadline = active_timeout.when()
                        if isinstance(wait, (int, float)) and math.isfinite(wait) and 0 < wait <= 60 and deadline is not None:
                            # Explicit provider retry waits are not coding
                            # time. The full wall time still appears in evidence.
                            active_timeout.reschedule(deadline + wait)
        except TimeoutError:
            events.append({"type": "error", "content": f"Task exceeded {timeout:g} seconds"})
        except Exception as error:
            events.append({"type": "error", "content": f"{type(error).__name__}: {error}"})
    elapsed = time.perf_counter() - started
    checks = grade(task, workspace)
    return {
        "task": task.name, "prompt": prompt,
        "initial_source_sha256": hashlib.sha256(task.source.encode()).hexdigest(),
        "elapsed_seconds": round(elapsed, 3),
        "discovered_tools": [dict(tool) for tool in tools],
        "events": events, **assess(task, events, checks),
        "final_source_sha256": hashlib.sha256((workspace / "solution.py").read_bytes()).hexdigest()
        if (workspace / "solution.py").is_file() else None,
    }


def write_report(output: Path, runs: list[dict[str, object]], planned: int | None = None) -> None:
    latest = latest_runs(runs)
    passed = sum(bool(run["passed"]) for run in latest)
    lines = [
        "# Coding task test results", "",
        "Supporting test record; PROJECT_REPORT.pdf at the repository root is the submission report. Review explanations and grounding manually.", "",
        f"Overall completion: **{passed}/{len(latest)} attempted task/model slots**"
        + (f"; **{passed}/{planned} planned slots**." if planned is not None else "."), "",
        f"All-attempt completion: **{sum(bool(run['passed']) for run in runs)}/{len(runs)}**. "
        "Retries remain below and in results.json; they are never erased.", "",
        "| Latest outcome | Slots |", "|---|---:|",
        *[f"| {category} | {sum(run.get('outcome') == category for run in latest)} |"
          for category in ("passed", "coding_failure", "assistant_failure", "provider_blocked")], "",
        "Provider-blocked attempts remain unsuccessful in the overall completion count. An incomplete",
        "saved implementation is not proof of a model logic error; inspect checks and terminal cause together.", "",
        "| Model | Task | Repeat | Attempt | Outcome | Pass | Checks | Calls | Tool errors | Seconds | Completion |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        checks = run["checks"]
        assert isinstance(checks, dict)
        lines.append(
            f"| {run['model']} | {run['task']} | {run['repeat']} | {run.get('attempt', 1)} | {run.get('outcome', 'legacy')} | {run['passed']} "
            f"| {checks['passed']} | {run['tool_calls']} | {run['tool_errors']} "
            f"| {run['elapsed_seconds']} | {run['completion_reason']} |"
        )
    lines += ["", "## Failure evidence", ""]
    for run in runs:
        if not run["passed"]:
            lines += [f"### {run['model']} / {run['task']} / repeat {run['repeat']}",
                      "", "```json", json.dumps({k: run[k] for k in (
                          "checks", "errors", "missing_required_tools", "read_existing_code",
                          "edited_file", "completion_reason", "tool_sequence",
                      )}, indent=2, ensure_ascii=False), "```", ""]
    lines += [
        "## Interpretation and limits", "",
        "Compare pass counts, tool sequences, recoveries, edits, and final explanations in results.json.",
        "Task success requires correctness checks, a successful filesystem read and edit, required",
        "integration calls, and a normal agent completion. Tool errors may be recovered from.",
        "A successful retrieval call does not establish relevance or correct source grounding.",
        "Small synthetic tasks do not establish general coding quality. Refactor checks verify",
        "behavior and helper presence; inspect the final source to assess design quality.",
        "Elapsed time includes discovery, retries, and tool work; excludes grading; it is not token throughput.",
        "Explicit quota waits are excluded from the active task deadline. Service-side changes can affect results.",
        "No token cost, local-provider comparison, or advanced-RAG benefit is measured here.",
        "Filesystem-only runs omit external and custom-RAG integration; see metadata.json for scope.",
        "",
    ]
    (output / "TEST_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


async def evaluate(args: argparse.Namespace) -> int:
    key_name = "OPENAI_API_KEY" if getattr(args, "provider", "groq") == "openai" else "GROQ_API_KEY"
    key = args.api_key_file.read_text(encoding="utf-8").strip() if args.api_key_file else os.environ.get(key_name, "").strip()
    if not key:
        raise ValueError(f"Configure {key_name} before running live evaluation")
    if len(set(model.strip() for model in args.models)) != 2 or not all(model.strip() for model in args.models):
        raise ValueError("Choose two distinct, nonempty model IDs")
    # Catch missing/invalid configuration before creating an output checkpoint.
    load_mcp_config(args.config, workspace_root=ROOT)
    output = args.output.resolve()
    if args.resume:
        if not output.is_dir():
            raise ValueError("--resume requires an existing evaluation directory")
    else:
        output.mkdir(parents=True, exist_ok=False)
    with output_lock(output):
        return await _evaluate_locked(args, output)


async def _evaluate_locked(args: argparse.Namespace, output: Path) -> int:
    from coding_assistant.providers.groq import GroqProvider, MAX_RATE_LIMIT_RETRIES, MAX_RATE_LIMIT_WAIT_SECONDS
    from coding_assistant.providers.openai import OpenAIProvider

    provider_name = getattr(args, "provider", "groq")
    key_name = "OPENAI_API_KEY" if provider_name == "openai" else "GROQ_API_KEY"
    key = os.environ.get(key_name, "").strip()
    if args.api_key_file:
        key = args.api_key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"Configure {key_name} or --api-key-file before running live evaluation")
    models = [model.strip() for model in args.models]
    if len(set(models)) != 2 or not all(models):
        raise ValueError("Choose two distinct, nonempty model IDs")
    tasks = [task for task in TASKS if not args.filesystem_only or not task.required_tools]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    metadata = {
        "schema_version": 2,
        "started_utc": datetime.now(timezone.utc).isoformat(), "git_revision": revision,
        "python": platform.python_version(), "platform": platform.platform(),
        "working_tree_status": dirty,
        "models": models, "provider": provider_name, "repeats": args.repeats,
        "scope": "filesystem-only" if args.filesystem_only else "all-configured-servers",
        "config_path": str(args.config.resolve()),
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "max_iterations": args.max_iterations, "timeout_seconds": args.timeout,
        "sampling": "Groq temperature=0; GPT-OSS reasoning=low; max_completion_tokens=2048",
        "request_context_budget_bytes": 18000, "provider_max_attempts": 5,
        "provider_max_rate_limit_retries": MAX_RATE_LIMIT_RETRIES,
        "provider_max_rate_limit_wait_seconds": MAX_RATE_LIMIT_WAIT_SECONDS,
        "deadline_policy": "active work; explicit retry waits excluded",
        "code_validation": "saved Python syntax through policy-controlled filesystem reads; hidden grading checks remain separate",
        "execution_mode": "auto",
        "tasks": [task.name for task in tasks],
        "task_definition_sha256": hashlib.sha256(Path(__file__).with_name("tasks.py").read_bytes()).hexdigest(),
        "production_source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in (ROOT / "src", ROOT / "rag_server")
            for path in sorted(directory.rglob("*.py"))
        },
        "harness_source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(__file__).parent.glob("*.py"))
        },
    }
    if provider_name == "openai":
        metadata.update({"sampling": "OpenAI Chat Completions; SDK-default temperature; max_completion_tokens=4096; parallel_tool_calls=false; store=false",
                         "request_context_budget_bytes": 30000, "provider_max_attempts": 3,
                         "provider_max_rate_limit_retries": 2, "provider_max_rate_limit_wait_seconds": 60})
    runs: list[dict[str, object]] = []
    if args.resume:
        saved = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        validate_resume(saved, metadata)
        result_path = output / "results.json"
        runs = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
        # Verify retained fixtures before trusting completed slots.
        for run in runs:
            source = output / str(run["workspace"]) / "solution.py"
            digest = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
            if digest != run.get("final_source_sha256"):
                raise ValueError("Saved evaluation source changed; start a new output directory")
    else:
        atomic_json(output / "metadata.json", metadata)
        atomic_json(output / "results.json", runs)
        dependencies = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True,
        ).stdout
        (output / "dependencies.txt").write_text(dependencies, encoding="utf-8")
    planned = len(tasks) * len(models) * args.repeats
    for repeat in range(1, args.repeats + 1):
        # Alternate model order each repeat to reduce systematic order effects.
        for task in tasks:
            order = list(enumerate(models))
            if repeat % 2 == 0:
                order.reverse()
            for index, model in order:
                prior = [run for run in runs if run["model"] == model and run["task"] == task.name and run["repeat"] == repeat]
                if prior and prior[-1].get("outcome") not in RETRYABLE:
                    print(f"Keeping completed {model} / {task.name} / repeat {repeat}", flush=True)
                    continue
                print(f"Running {model} / {task.name} / repeat {repeat}", flush=True)
                attempt = len(prior) + 1
                base = output / "workspaces" / f"model-{index + 1}"
                workspace = base / f"{task.name}-{repeat}-attempt-{attempt}"
                # Preserve an interrupted, unscored workspace too.
                while workspace.exists():
                    attempt += 1
                    workspace = base / f"{task.name}-{repeat}-attempt-{attempt}"
                result = await run_task(
                    task, (OpenAIProvider(model, api_key=key) if provider_name == "openai" else GroqProvider(model, api_key=key)), workspace,
                    config_path=args.config, filesystem_only=args.filesystem_only,
                    timeout=args.timeout, max_iterations=args.max_iterations,
                )
                runs.append({"model": model, "repeat": repeat, "attempt": attempt,
                             "workspace": workspace.relative_to(output).as_posix(), **result})
                # Redact the key even if an upstream error unexpectedly echoes it.
                serialized = json.dumps(runs, indent=2, ensure_ascii=False).replace(key, "[REDACTED]")
                safe_runs = json.loads(serialized)
                atomic_json(output / "results.json", safe_runs)
                write_report(output, safe_runs, planned)
                print(f"  outcome={result['outcome']}; passed={result['passed']}; calls={result['tool_calls']}", flush=True)
                if result["outcome"] == "provider_blocked":
                    atomic_json(output / "state.json", {"status": "paused_provider_capacity", "planned": planned,
                                "attempted_slots": len(latest_runs(runs)), "resume": True})
                    print("Paused: provider capacity is unavailable. Results are saved. Later rerun the same command with --resume.", flush=True)
                    return 3
    final = latest_runs(runs)
    write_report(output, json.loads(json.dumps(runs).replace(key, "[REDACTED]")), planned)
    atomic_json(output / "state.json", {"status": "complete", "planned": planned, "attempted_slots": len(final)})
    return 0 if len(final) == planned and all(run["passed"] for run in final) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("groq", "openai"), default="groq")
    parser.add_argument("--models", nargs=2, required=True, metavar=("MODEL_A", "MODEL_B"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/mcp.json")
    parser.add_argument("--output", type=Path, required=True, help="New directory, or the same directory with --resume")
    parser.add_argument("--resume", action="store_true", help="Keep completed slots; retry provider-blocked slots in fresh workspaces")
    parser.add_argument("--api-key-file", type=Path, help="Local file containing only the Groq API key")
    parser.add_argument("--filesystem-only", action="store_true")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.max_iterations < 1 or not 0 < args.timeout < float("inf"):
        parser.error("repeats, max-iterations, and timeout must be positive and finite")
    try:
        return asyncio.run(evaluate(args))
    except (ValueError, OSError) as error:
        # Do not print arbitrary file/SDK exceptions that may include credentials.
        # Compatibility errors contain only field names and are safe to explain.
        detail = str(error) if isinstance(error, ValueError) and str(error).startswith(("Resume settings", "Saved evaluation", "--resume")) else "Check access, paths, arguments, and whether another runner holds the output lock."
        print(f"Evaluation setup failed ({type(error).__name__}): {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
