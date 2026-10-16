"""Local MCP tool for bounded Python scripts and pytest in the workspace.

This is a trusted-code runner, not an operating-system sandbox. The CLI's
confirmation policy applies before this server is called, including auto mode.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import Any, Literal

from mcp.server import MCPServer

OUTPUT_LIMIT = 16000


def run_python(root: Path, path: str, mode: Literal["script", "pytest"] = "script",
               timeout_seconds: int = 30) -> dict[str, object]:
    root = root.resolve(strict=True)
    target = (root / path).resolve(strict=True)
    if not target.is_relative_to(root):
        raise ValueError("The check target must be inside the configured workspace")
    if mode not in ("script", "pytest"):
        raise ValueError("mode must be script or pytest")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be an integer from 1 to 60")
    if mode == "script" and (not target.is_file() or target.suffix.lower() != ".py"):
        raise ValueError("script mode requires a Python .py file")
    if mode == "pytest" and not (target.is_dir() or target.suffix.lower() == ".py"):
        raise ValueError("pytest mode requires a directory or Python .py file")
    command = ([sys.executable, "-I", str(target)] if mode == "script" else
               [sys.executable, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--", str(target)])
    env = {key: value for key, value in os.environ.items() if not any(
        word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PYTHONPATH", "PYTHONSTARTUP")
    )}
    timed_out = False
    # Redirect to a temporary file to avoid retaining unbounded output in memory.
    with tempfile.TemporaryFile() as stream:
        process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != "nt",
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if sys.platform == "win32":
                system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                subprocess.run([str(system_root / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        stream.seek(0)
        output = stream.read(OUTPUT_LIMIT + 1)
    return {"command": command, "returncode": process.returncode, "timed_out": timed_out,
            "output": output[:OUTPUT_LIMIT].decode("utf-8", errors="replace"),
            "output_truncated": len(output) > OUTPUT_LIMIT,
            "passed": process.returncode == 0 and not timed_out}


def create_server(root: Path) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer("workspace-checks")

    @server.tool()
    async def run_python_check(path: str, mode: Literal["script", "pytest"] = "script",
                               timeout_seconds: int = 30) -> dict[str, object]:
        """Run a trusted workspace Python script or pytest target, with no shell.
        path must resolve inside the workspace. mode='script' runs a .py file;
        mode='pytest' runs a test file/directory. timeout_seconds is 1-60.
        Returns exit status, combined output (up to 16000 bytes), timeout and pass flags.
        This executes code with the user's permissions; it is not an OS sandbox.
        A successful exit only establishes what the script/tests actually checked.
        """
        return await asyncio.to_thread(run_python, root, path, mode, timeout_seconds)

    return server


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    options = parser.parse_args(arguments)
    if not options.workspace.is_dir():
        parser.error("workspace must be an existing directory")
    create_server(options.workspace.resolve()).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
