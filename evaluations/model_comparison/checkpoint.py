"""Atomic batch checkpoints and conservative resume compatibility checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import json
import os
import sys
from pathlib import Path
from typing import BinaryIO


RETRYABLE = {"provider_blocked"}
COMPATIBILITY = (
    "schema_version", "python", "models", "repeats", "scope", "config_sha256", "max_iterations",
    "timeout_seconds", "tasks", "task_definition_sha256", "production_source_sha256",
    "harness_source_sha256", "sampling", "execution_mode",
)


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def output_lock(output: Path) -> Iterator[None]:
    """OS releases this lock on interruption/crash, so resume needs no cleanup."""
    with (output / ".run.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        _lock(handle, unlock=False)
        try:
            yield
        finally:
            handle.seek(0)
            _lock(handle, unlock=True)


def _lock(handle: BinaryIO, *, unlock: bool) -> None:
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)


def validate_resume(saved: dict[str, object], current: dict[str, object]) -> None:
    changed = [field for field in COMPATIBILITY if field not in saved or saved[field] != current[field]]
    if changed:
        raise ValueError("Resume settings or code changed: " + ", ".join(changed) + ". Use a new output directory.")


def latest_runs(runs: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    latest: dict[tuple[str, str, int], dict[str, object]] = {}
    for run in runs:
        key = (str(run["model"]), str(run["task"]), int(str(run["repeat"])))
        latest[key] = run
    return list(latest.values())


def outcome(events: Sequence[Mapping[str, object]], *, passed: bool, checks_passed: bool,
            completion: str) -> str:
    if passed:
        return "passed"
    codes = {event.get("error_code") for event in events if event.get("type") == "error"}
    if codes & {"provider_daily_limit", "provider_rate_limit", "provider_unavailable", "provider_quota"}:
        return "provider_blocked"
    if "code_validation_failed" in codes or (completion == "answered" and not checks_passed):
        return "coding_failure"
    return "assistant_failure"
