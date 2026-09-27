"""Project runner (Stage 7).

Tests the discovery and preflight logic without spawning servers. The process
lifecycle — start, report, clean shutdown — was verified by running
`python runner.py` for real; see docs/STAGE_7_COMPLETION.md.
"""

from __future__ import annotations

import io
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Configuration discovery
# --------------------------------------------------------------------------
def test_reads_a_value_from_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_PORT=9001\nAPI_HOST=0.0.0.0\n", encoding="utf-8")

    assert runner.read_env_value("API_PORT", env) == "9001"
    assert runner.read_env_value("API_HOST", env) == "0.0.0.0"


def test_ignores_commented_and_missing_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# API_PORT=1234\nOTHER=x\n", encoding="utf-8")

    assert runner.read_env_value("API_PORT", env) is None
    assert runner.read_env_value("NOT_THERE", env) is None


def test_strips_quotes_from_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text('API_HOST="127.0.0.1"\n', encoding="utf-8")
    assert runner.read_env_value("API_HOST", env) == "127.0.0.1"


def test_missing_env_file_falls_back_to_defaults(tmp_path):
    missing = tmp_path / "nope.env"

    assert runner.read_env_value("API_PORT", missing) is None
    assert runner.backend_port(missing) == runner.DEFAULT_BACKEND_PORT
    assert runner.backend_host(missing) == runner.DEFAULT_BACKEND_HOST


def test_non_numeric_port_falls_back(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_PORT=not-a-number\n", encoding="utf-8")
    assert runner.backend_port(env) == runner.DEFAULT_BACKEND_PORT


def test_frontend_port_is_read_from_vite_config():
    """The port is read back from the real config rather than duplicated."""
    assert runner.frontend_port() == 5173


def test_frontend_port_falls_back_when_config_is_missing(tmp_path):
    assert runner.frontend_port(tmp_path / "nope.js") == runner.DEFAULT_FRONTEND_PORT


def test_frontend_port_parses_a_custom_config(tmp_path):
    config = tmp_path / "vite.config.js"
    config.write_text("export default { server: { port: 4321 } }", encoding="utf-8")
    assert runner.frontend_port(config) == 4321


# --------------------------------------------------------------------------
# Executable discovery
# --------------------------------------------------------------------------
def test_prefers_the_project_virtualenv_interpreter():
    """`python runner.py` is usually run with the system interpreter while the
    dependencies live in .venv — this is what makes that work."""
    interpreter = Path(runner.python_executable())

    assert interpreter.exists()
    if (PROJECT_ROOT / ".venv").exists():
        assert ".venv" in interpreter.parts


def test_falls_back_to_the_current_interpreter(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    assert runner.python_executable() == sys.executable


def test_npm_is_discoverable():
    """shutil.which resolves npm.cmd on Windows, which Popen needs."""
    assert runner.npm_executable() is not None


# --------------------------------------------------------------------------
# Port probing
# --------------------------------------------------------------------------
def test_detects_a_listening_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert runner.port_in_use(port) is True


def test_reports_a_free_port_as_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Socket closed, so nothing is listening there now.
    assert runner.port_in_use(port) is False


def test_detects_an_ipv6_only_listener():
    """Regression: Node binds [::1] by default. An IPv4-only probe reported a
    busy Vite port as free, so the runner started a duplicate that silently
    hopped to another port."""
    try:
        server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:  # pragma: no cover - IPv6 unavailable
        pytest.skip("IPv6 not available")

    with server:
        server.bind(("::1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert runner.port_in_use(port) is True


def test_external_service_monitor_reports_the_first_closed_port(monkeypatch):
    states = iter([True, False])
    monkeypatch.setattr(runner, "port_in_use", lambda _port: next(states))

    stopped = runner.unavailable_external_service(
        [("backend", 8000), ("frontend", 5173)]
    )

    assert stopped == "frontend"


def test_external_service_monitor_accepts_running_services(monkeypatch):
    monkeypatch.setattr(runner, "port_in_use", lambda _port: True)
    assert runner.unavailable_external_service(
        [("backend", 8000), ("frontend", 5173)]
    ) is None


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
def test_preflight_passes_on_this_repository():
    assert runner.preflight() == []


def test_preflight_reports_missing_frontend_dependencies(monkeypatch, tmp_path):
    """The runner explains how to fix it and never installs anything itself."""
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)

    problems = runner.preflight()
    assert any("npm install" in problem for problem in problems)


def test_preflight_reports_a_missing_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    problems = runner.preflight()
    assert any("backend/app/main.py not found" in problem for problem in problems)


BLOCKED_STDERR = (
    "Traceback (most recent call last):\n"
    '  File "pandas\\_libs\\tslibs\\__init__.py", line 82, in <module>\n'
    "ImportError: DLL load failed while importing vectorized: "
    "An Application Control policy has blocked this file.\n"
)


def _failing_import(stderr, seen=None):
    def fake_run(command, **kwargs):
        if seen is not None:
            seen.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=stderr)

    return fake_run


def test_preflight_imports_the_packages_that_ship_dlls(monkeypatch):
    """pandas and numpy carry compiled DLLs; checking only fastapi and uvicorn
    let a blocked pandas through, and the backend then died mid-start."""
    seen = []
    monkeypatch.setattr(runner.subprocess, "run", _failing_import("", seen))
    runner.preflight()
    code = seen[0][-1]
    assert "pandas" in code and "numpy" in code


def test_preflight_explains_a_windows_application_control_block(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", _failing_import(BLOCKED_STDERR))
    problems = runner.preflight()

    blocked = [p for p in problems if "Smart App Control" in p]
    assert len(blocked) == 1
    assert "(vectorized)" in blocked[0]
    assert "-m pip install -r requirements.txt" in blocked[0]
    assert not any("dependencies are missing" in p for p in problems)


def test_preflight_still_reports_plainly_missing_packages(monkeypatch):
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        _failing_import("ModuleNotFoundError: No module named 'pandas'\n"),
    )
    problems = runner.preflight()
    assert any("Backend dependencies are missing" in p for p in problems)
    assert not any("Smart App Control" in p for p in problems)


def test_a_block_during_startup_is_noticed_in_the_backend_log():
    lines = []
    watch = runner.collect_blocked_imports(lines)
    watch("INFO:     Waiting for application startup.\n")
    watch("ImportError: DLL load failed while importing vectorized: An Application Control policy has blocked this file.\n")

    assert len(lines) == 1
    assert "(vectorized)" in runner.describe_import_failure("".join(lines))


def test_check_flag_exits_zero_without_starting_anything(capsys):
    assert runner.main(["--check"]) == 0
    assert "Preflight passed" in capsys.readouterr().out


def test_dataset_presence_is_detected():
    assert runner.dataset_present() is True


# --------------------------------------------------------------------------
# Frontend port correction
# --------------------------------------------------------------------------
def test_reports_when_vite_moves_to_another_port(capsys):
    """Vite silently hops when its port is taken, so the runner reads the real
    port back rather than advertising one that does not work."""
    watch = runner.watch_frontend_port(5173)
    watch("  \x1b[32m➜\x1b[39m  Local:   http://localhost:5174/\n")

    output = capsys.readouterr().out
    assert "5174" in output
    assert "Open that instead" in output


def test_stays_quiet_when_vite_uses_the_expected_port(capsys):
    watch = runner.watch_frontend_port(5173)
    watch("  Local:   http://localhost:5173/\n")
    assert capsys.readouterr().out == ""


def test_reports_the_moved_port_only_once(capsys):
    watch = runner.watch_frontend_port(5173)
    watch("Local:   http://localhost:5174/\n")
    capsys.readouterr()
    watch("Local:   http://localhost:5174/\n")
    assert capsys.readouterr().out == ""


def test_output_the_console_cannot_encode_does_not_stop_the_pump(monkeypatch):
    """Vite prints "➜". On a cp1252 console that must not kill the thread that
    drains Vite's pipe, or Vite eventually blocks writing to it."""
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")  # strict, like Windows
    monkeypatch.setattr(sys, "stdout", console)

    lines = ["  ➜  Local:   http://localhost:5173/\n", "ready\n"]

    class FakeProcess:
        stdout = iter(lines)

    seen: list[str] = []
    runner.stream_output(FakeProcess(), "frontend", watch=seen.append).join(timeout=5)
    console.flush()

    # Every line still reached the port watcher and the console.
    assert seen == lines
    text = buffer.getvalue().decode("cp1252")
    assert "Local:   http://localhost:5173/" in text
    assert "[frontend] ready" in text


# --------------------------------------------------------------------------
# Portability
# --------------------------------------------------------------------------
def test_no_machine_specific_paths_are_hardcoded():
    source = (PROJECT_ROOT / "runner.py").read_text(encoding="utf-8")

    for pattern in ("C:\\\\Users", "/home/", "/Users/", "MANTHAN"):
        assert pattern not in source, f"runner.py hardcodes {pattern}"


def test_runner_introduces_no_new_dependencies():
    """Everything the runner imports ships with Python.

    Checked by parsing the imports rather than searching the text: the preflight
    check runs `python -c "import fastapi, uvicorn"` in a subprocess, and a
    substring search would wrongly flag that string.
    """
    import ast

    tree = ast.parse((PROJECT_ROOT / "runner.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported <= set(sys.stdlib_module_names), (
        f"runner.py imports non-stdlib modules: {imported - set(sys.stdlib_module_names)}"
    )


def test_signal_handlers_cover_windows_break():
    """Regression: Python's default SIGBREAK action terminates the process
    outright, skipping cleanup and orphaning both servers."""
    source = (PROJECT_ROOT / "runner.py").read_text(encoding="utf-8")
    assert "SIGBREAK" in source
    assert "SIGTERM" in source
    assert "SIGINT" in source
