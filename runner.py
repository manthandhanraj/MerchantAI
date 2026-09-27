#!/usr/bin/env python
"""Start the whole MerchantAI application with one command.

    python runner.py

Launches the FastAPI backend and the Vite frontend together, streams both logs
to this terminal with a prefix, and stops both cleanly on Ctrl+C.

Design notes:

* **Standard library only.** No new dependency is introduced just to start the app.
* **Nothing is installed.** Missing dependencies are reported with the exact
  command to fix them; the runner never installs anything on your behalf.
* **Nothing is hard-coded.** Paths are derived from this file's location, ports
  are read from `.env` and `vite.config.js`, and the interpreter is discovered.
* **No duplicate servers.** A port already in use means that service is already
  running, so the runner leaves it alone and monitors it until Ctrl+C.
* **Errors are surfaced.** If either process exits unexpectedly, the runner
  reports the exit code and shuts the other one down rather than hanging.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

BACKEND_APP = "backend.app.main:app"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173

IS_WINDOWS = os.name == "nt"

# Seconds to wait for a child to exit after being asked politely.
SHUTDOWN_GRACE_SECONDS = 10


# --------------------------------------------------------------------------
# Environment discovery
# --------------------------------------------------------------------------
def read_env_value(name: str, env_path: Path | None = None) -> str | None:
    """Read one key from `.env` without needing python-dotenv.

    The runner starts before the backend's own settings layer is available, so
    it parses the file directly rather than importing the app.
    """
    path = env_path or (PROJECT_ROOT / ".env")
    if not path.exists():
        return None

    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*(.*?)\s*$")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = pattern.match(line)
            if match:
                return match.group(1).strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def backend_port(env_path: Path | None = None) -> int:
    value = read_env_value("API_PORT", env_path)
    try:
        return int(value) if value else DEFAULT_BACKEND_PORT
    except ValueError:
        return DEFAULT_BACKEND_PORT


def backend_host(env_path: Path | None = None) -> str:
    return read_env_value("API_HOST", env_path) or DEFAULT_BACKEND_HOST


def frontend_port(config_path: Path | None = None) -> int:
    """Read the dev-server port out of vite.config.js rather than repeating it."""
    path = config_path or (PROJECT_ROOT / "frontend" / "vite.config.js")
    if not path.exists():
        return DEFAULT_FRONTEND_PORT
    try:
        match = re.search(r"port:\s*(\d{2,5})", path.read_text(encoding="utf-8"))
    except OSError:
        return DEFAULT_FRONTEND_PORT
    return int(match.group(1)) if match else DEFAULT_FRONTEND_PORT


def python_executable() -> str:
    """Prefer the project's virtualenv interpreter over whatever launched us.

    `python runner.py` is commonly run with the system interpreter while the
    dependencies live in `.venv`, so this is what makes the obvious command work.
    """
    candidates = (
        PROJECT_ROOT / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python"),
        PROJECT_ROOT / "venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def npm_executable() -> str | None:
    """`shutil.which` resolves npm.cmd on Windows, which Popen needs."""
    return shutil.which("npm")


def port_in_use(port: int) -> bool:
    """Whether anything is already listening on this port, on either stack.

    Both loopback families are probed: Node binds `[::1]` by default, so an
    IPv4-only check reports a busy Vite port as free and the runner starts a
    duplicate that silently hops to another port.
    """
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.6)
                if probe.connect_ex((address, port)) == 0:
                    return True
        except OSError:
            # That family is unavailable on this machine; try the other.
            continue
    return False


def unavailable_external_service(services: list[tuple[str, int]]) -> str | None:
    """Return the first externally started service that is no longer listening."""
    for label, port in services:
        if not port_in_use(port):
            return label
    return None


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
def preflight() -> list[str]:
    """Check everything needed to start, returning human-readable problems.

    Returns an empty list when the project is ready. Nothing is installed or
    modified here.
    """
    problems: list[str] = []

    if not (PROJECT_ROOT / "backend" / "app" / "main.py").exists():
        problems.append(
            "backend/app/main.py not found. Run this from the project root:\n"
            "    python runner.py"
        )
    if not (PROJECT_ROOT / "frontend" / "package.json").exists():
        problems.append("frontend/package.json not found. Is the frontend directory intact?")

    interpreter = python_executable()
    # numpy and pandas are imported too: they ship compiled DLLs, and one that
    # Windows refuses to load would otherwise only surface as the backend
    # crashing mid-start, taking the whole app down with it.
    check = subprocess.run(
        [interpreter, "-c", "import fastapi, uvicorn, numpy, pandas"],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=str(PROJECT_ROOT),
    )
    if check.returncode != 0:
        problems.append(describe_import_failure(check.stderr or "", interpreter))

    if not (PROJECT_ROOT / "frontend" / "node_modules").exists():
        problems.append(
            "Frontend dependencies are missing. Install them with:\n"
            "    cd frontend && npm install"
        )

    if npm_executable() is None:
        problems.append("npm was not found on PATH. Install Node.js 18+ and reopen the terminal.")

    return problems


# What Windows says when Smart App Control / App Control for Business refuses
# to load an unsigned DLL, such as a compiled module inside a Python package.
APPLICATION_CONTROL_BLOCK = "Application Control policy has blocked"


def describe_import_failure(stderr: str, interpreter: str | None = None) -> str:
    """Turn a failed dependency import into the problem and its fix."""
    reinstall = f'    "{interpreter or python_executable()}" -m pip install -r requirements.txt'
    if APPLICATION_CONTROL_BLOCK in stderr:
        module = re.search(r"while importing (\S+?):", stderr)
        which = f" ({module.group(1)})" if module else ""
        return (
            f"Windows Smart App Control blocked a file inside an installed Python package{which}.\n"
            "    It only lets unsigned files run once Microsoft has seen them widely, so it\n"
            "    tends to block brand-new package releases. requirements.txt pins versions\n"
            "    that Windows allows; reinstall them with:\n"
            f"{reinstall}"
        )
    return f"Backend dependencies are missing. Install them with:\n{reinstall}"


def dataset_present() -> bool:
    return (PROJECT_ROOT / "data" / "raw" / "merchant_sales.csv").exists()


# --------------------------------------------------------------------------
# Process handling
# --------------------------------------------------------------------------
def spawn(command: list[str], cwd: Path) -> subprocess.Popen:
    """Start a child process in its own group so the whole tree can be stopped."""
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    preexec = None if IS_WINDOWS else os.setsid

    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        preexec_fn=preexec,
    )


def echo(text: str) -> None:
    """Write a child's output even when this console cannot encode all of it.

    Vite prints "➜", which a cp1252 stdout (Windows, output piped) cannot
    encode. Unhandled, that error kills the pump thread, and a child whose pipe
    is no longer drained blocks on its next write once the buffer fills.
    """
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.write(text.encode(encoding, errors="replace").decode(encoding))
    sys.stdout.flush()


def stream_output(process: subprocess.Popen, label: str, watch=None) -> threading.Thread:
    """Echo a child's output with a prefix so two logs stay readable as one.

    `watch` is called with each line, so the caller can pick facts out of the
    stream — the frontend's real port, for instance.
    """

    def pump() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            echo(f"[{label}] {line}")
            if watch is not None:
                watch(line)

    thread = threading.Thread(target=pump, name=f"{label}-output", daemon=True)
    thread.start()
    return thread


# Vite prints "Local:   http://localhost:5173/" once it has bound a port, and it
# silently moves to the next free one when the configured port is taken. The
# runner reads the real port back rather than advertising a URL that may be wrong.
_VITE_URL = re.compile(r"Local:.*?http://localhost:(\d+)", re.IGNORECASE)


def watch_frontend_port(expected: int):
    """Return a line-watcher that reports the port Vite actually used."""
    reported = False

    def watch(line: str) -> None:
        nonlocal reported
        if reported:
            return
        # Strip ANSI colour codes before matching; Vite colours its banner.
        match = _VITE_URL.search(re.sub(r"\x1b\[[0-9;]*m", "", line))
        if not match:
            return
        reported = True
        actual = int(match.group(1))
        if actual != expected:
            print(
                f"\n  Note: port {expected} was taken, so the frontend is on "
                f"http://localhost:{actual}\n  Open that instead.\n"
            )

    return watch


def collect_blocked_imports(lines: list[str]):
    """Return a line-watcher that keeps any "blocked by Application Control" line.

    Some DLLs (uvicorn's, for instance) load only once the server starts, after
    preflight has passed, so the runner also listens for the block at runtime.
    """

    def watch(line: str) -> None:
        if APPLICATION_CONTROL_BLOCK in line:
            lines.append(line)

    return watch


def stop(process: subprocess.Popen, label: str) -> None:
    """Stop a child and everything it spawned.

    npm launches node as a child, so terminating npm alone would orphan the dev
    server. Windows needs taskkill /T; POSIX uses the process group.
    """
    if process.poll() is not None:
        return

    print(f"  stopping {label}…")
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  could not stop {label} cleanly: {exc}")

    try:
        process.wait(timeout=SHUTDOWN_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"  {label} did not exit in time; killing it")
        process.kill()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
# Set by the signal handlers below; the monitor loop watches it.
_stop_requested = threading.Event()


def _request_stop(signum, _frame) -> None:
    _stop_requested.set()


def install_signal_handlers() -> None:
    """Route every stop signal through one flag so cleanup always runs.

    Windows needs SIGBREAK handled explicitly: Python's default action for
    Ctrl+Break terminates the process outright, skipping the cleanup that stops
    the children — which leaves orphaned servers holding the ports.
    """
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        handler = getattr(signal, name, None)
        if handler is not None:
            try:
                signal.signal(handler, _request_stop)
            except (ValueError, OSError):
                # Not available on this platform or not on the main thread.
                continue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the MerchantAI backend and frontend together."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run the preflight checks and exit without starting anything.",
    )
    args = parser.parse_args(argv)

    print("MerchantAI")
    print("=" * 60)

    problems = preflight()
    if problems:
        print("\nCannot start. Fix the following:\n")
        for problem in problems:
            print(f"  - {problem}\n")
        return 1

    if not dataset_present():
        print(
            "\n  Note: data/raw/merchant_sales.csv is missing. The app will start, but\n"
            "  data endpoints will return 503 until you run:\n"
            "      python data/generate_dataset.py\n"
        )

    if args.check:
        print("\nPreflight passed. Everything needed to start is in place.")
        return 0

    # ``main`` is also exercised repeatedly by tests and may be called more
    # than once by an embedding process. Do not inherit an earlier stop signal.
    _stop_requested.clear()

    host = backend_host()
    api_port = backend_port()
    web_port = frontend_port()

    backend_running = port_in_use(api_port)
    frontend_running = port_in_use(web_port)

    processes: list[tuple[str, subprocess.Popen]] = []
    external_services: list[tuple[str, int]] = []
    blocked_imports: list[str] = []

    if backend_running or frontend_running:
        # A hard kill (Windows TerminateProcess) cannot be intercepted, so a
        # previous run that was force-stopped can leave a server holding a port.
        print(
            "\n  A service is already listening. If that is a leftover from a run that\n"
            "  was force-stopped rather than Ctrl+C'd, free the port and start again:\n"
            f"      npx kill-port {api_port} {web_port}\n"
        )

    if backend_running:
        print(f"  Backend   already running on port {api_port}, leaving it alone")
        external_services.append(("backend", api_port))
    else:
        backend = spawn(
            [python_executable(), "-m", "uvicorn", BACKEND_APP, "--host", host, "--port", str(api_port)],
            cwd=PROJECT_ROOT,
        )
        stream_output(backend, "backend", watch=collect_blocked_imports(blocked_imports))
        processes.append(("backend", backend))

    if frontend_running:
        print(f"  Frontend  already running on port {web_port}, leaving it alone")
        external_services.append(("frontend", web_port))
    else:
        frontend = spawn([npm_executable(), "run", "dev"], cwd=PROJECT_ROOT / "frontend")
        stream_output(frontend, "frontend", watch=watch_frontend_port(web_port))
        processes.append(("frontend", frontend))

    if not processes:
        print("\nBoth services are already running. Monitoring them until Ctrl+C.")

    print()
    print(f"  Frontend  http://localhost:{web_port}      <- open this")
    print(f"  Backend   http://{host}:{api_port}")
    print(f"  API docs  http://{host}:{api_port}/docs")
    print()
    print("  The AI assistant answers from the merchant's own data.")
    print("  A language model is used only if LLM_ENABLED=true and a key is set.")
    print()
    if external_services:
        print("  Press Ctrl+C to stop this monitor.")
        print("  Services started outside this runner will be left running.")
    else:
        print("  Press Ctrl+C to stop both.")
    print("=" * 60)
    print()

    install_signal_handlers()

    exit_code = 0
    try:
        # Watch both children. If either exits on its own, something is wrong:
        # say which one and with what code, then bring the other down too.
        while not _stop_requested.is_set():
            unavailable = unavailable_external_service(external_services)
            if unavailable is not None:
                print(f"\n{unavailable} is no longer listening.")
                print("Shutting down any service started by this runner.")
                exit_code = 1
                _stop_requested.set()
                break

            for label, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"\n{label} exited unexpectedly with code {code}.")
                    print("Its output is above. Shutting down the rest.")
                    if blocked_imports:
                        print("\n  " + describe_import_failure("".join(blocked_imports)))
                    exit_code = code or 1
                    _stop_requested.set()
                    break
            _stop_requested.wait(0.5)

        if exit_code == 0:
            action = "Stopping MerchantAI…" if processes else "Stopping MerchantAI monitor…"
            print(f"\n\n{action}")
    except KeyboardInterrupt:
        # Belt and braces: an interrupt that arrives before the handler is
        # installed still lands here.
        print("\n\nStopping MerchantAI…")
    finally:
        for label, process in processes:
            stop(process, label)
        if external_services:
            print("  monitor stopped; externally started services were left running")
        else:
            print("  all processes stopped")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
