from pathlib import Path

from mcp import Client
import pytest

from coding_assistant.execution.check_server import OUTPUT_LIMIT, create_server, run_python


def test_python_check_returns_real_exit_status_and_hides_environment_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "must-not-be-forwarded")
    (tmp_path / "check.py").write_text("import os\nassert 'TEST_API_KEY' not in os.environ\nprint('checked')\n", encoding="utf-8")
    result = run_python(tmp_path, "check.py")
    assert result["passed"] is True
    assert result["returncode"] == 0
    assert "checked" in str(result["output"])
    (tmp_path / "fail.py").write_text("raise ValueError('intentional failure')\n", encoding="utf-8")
    failed = run_python(tmp_path, "fail.py")
    assert failed["passed"] is False
    assert "intentional failure" in str(failed["output"])


def test_check_timeout_and_output_limit(tmp_path: Path) -> None:
    (tmp_path / "slow.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    assert run_python(tmp_path, "slow.py", timeout_seconds=1)["timed_out"] is True
    (tmp_path / "loud.py").write_text("print('x' * 20000)\n", encoding="utf-8")
    result = run_python(tmp_path, "loud.py")
    assert result["output_truncated"] is True
    assert len(str(result["output"])) <= OUTPUT_LIMIT


def test_check_rejects_outside_paths_and_non_python_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("raise RuntimeError('must not run')", encoding="utf-8")
    for path in (str(outside), "../outside.py"):
        with pytest.raises(ValueError, match="inside"):
            run_python(workspace, path)
    (workspace / "text.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Python"):
        run_python(workspace, "text.txt")
    with pytest.raises(ValueError, match="1 to 60"):
        run_python(workspace, "text.txt", timeout_seconds=61)


@pytest.mark.asyncio
async def test_check_runs_pytest_through_real_mcp(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text("def test_addition():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    async with Client(create_server(tmp_path)) as client:
        tools = await client.list_tools()
        assert any(tool.name == "run_python_check" for tool in tools.tools)
        result = await client.call_tool("run_python_check", {"path": "test_sample.py", "mode": "pytest"})
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["passed"] is True
    assert "1 passed" in result.structured_content["output"]
