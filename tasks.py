#!/usr/bin/env python3
"""Cross-platform task runner (Windows / macOS / Linux, no `make` required).

    python tasks.py            list tasks
    python tasks.py setup      first-time setup
    python tasks.py dev        run the API
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
COMPOSE_FILE = ROOT / "deployment" / "compose" / "docker-compose.dev.yml"

# minio-init is a one-shot container, so it is excluded from `--wait`.
INFRA_SERVICES = ("postgres", "redis", "minio", "mailpit")
IS_WINDOWS = os.name == "nt"


def _uv() -> list[str]:
    exe = shutil.which("uv")
    return [exe] if exe else [sys.executable, "-m", "uv"]


def run(cmd: Sequence[str], cwd: Path = ROOT, check: bool = True) -> int:
    print(f"\n$ {' '.join(str(part) for part in cmd)}", flush=True)
    code = subprocess.run(list(cmd), cwd=cwd).returncode
    if check and code != 0:
        sys.exit(code)
    return code


def uv_run(*args: str, cwd: Path = BACKEND, check: bool = True) -> int:
    return run([*_uv(), "run", *args], cwd=cwd, check=check)


def manage(*args: str, check: bool = True) -> int:
    return uv_run("python", "manage.py", *args, check=check)


def compose(*args: str, check: bool = True) -> int:
    return run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], check=check)


# --------------------------------------------------------------------------- tasks
def setup(_: list[str]) -> None:
    """Install dependencies, create backend/.env, install git hooks."""
    run([*_uv(), "sync"], cwd=BACKEND)
    env_file = BACKEND / ".env"
    if not env_file.exists():
        shutil.copyfile(BACKEND / ".env.example", env_file)
        print(f"created {env_file.relative_to(ROOT)} from .env.example")
    uv_run("pre-commit", "install", check=False)
    print("\nNext: python tasks.py infra-up && python tasks.py migrate && python tasks.py dev")


def infra_up(_: list[str]) -> None:
    """Start PostgreSQL, Redis, MinIO and Mailpit."""
    compose("up", "-d", "--wait", *INFRA_SERVICES)
    compose("up", "-d", "minio-init", check=False)
    compose("ps")


def infra_down(_: list[str]) -> None:
    """Stop the dev containers (data volumes are kept)."""
    compose("down")


def infra_reset(args: list[str]) -> None:
    """Delete dev containers AND their data volumes. Requires --yes."""
    if "--yes" not in args:
        sys.exit("Refusing to destroy dev data. Re-run: python tasks.py infra-reset --yes")
    compose("down", "-v")


def infra_logs(args: list[str]) -> None:
    """Tail container logs."""
    compose("logs", "-f", *args)


def migrate(args: list[str]) -> None:
    """Apply database migrations."""
    manage("migrate", *args)


def makemigrations(args: list[str]) -> None:
    """Create new migrations."""
    manage("makemigrations", *args)


def superuser(args: list[str]) -> None:
    """Create a Django-admin superuser (internal debugging only)."""
    manage("createsuperuser", *args)


def dev(args: list[str]) -> None:
    """Run the development API server."""
    manage("runserver", *(args or ["127.0.0.1:8000"]))


def worker(args: list[str]) -> None:
    """Run a Celery worker consuming every queue."""
    queues = "default,critical,bulk,notifications,integrations"
    pool = ["-P", "solo"] if IS_WINDOWS else []
    uv_run("celery", "-A", "config", "worker", "-l", "info", "-Q", queues, *pool, *args)


def beat(args: list[str]) -> None:
    """Run the Celery beat scheduler."""
    uv_run("celery", "-A", "config", "beat", "-l", "info", *args)


def shell(args: list[str]) -> None:
    """Open a Django shell."""
    manage("shell", *args)


def test(args: list[str]) -> None:
    """Run the backend test suite."""
    uv_run("pytest", *(args or ["-q"]))


def lint(_: list[str]) -> None:
    """Run every static check exactly as CI does."""
    failures: list[str] = []
    checks: list[tuple[str, list[str]]] = [
        ("ruff check", ["ruff", "check", "."]),
        ("ruff format", ["ruff", "format", "--check", "."]),
        ("import-linter", ["lint-imports"]),
        ("mypy", ["mypy", "."]),
        ("migrations", ["python", "manage.py", "makemigrations", "--check", "--dry-run"]),
    ]
    for name, cmd in checks:
        if uv_run(*cmd, check=False) != 0:
            failures.append(name)
    if failures:
        sys.exit(f"\nFAILED: {', '.join(failures)}")
    print("\nAll checks passed.")


def fmt(_: list[str]) -> None:
    """Auto-format and auto-fix."""
    uv_run("ruff", "format", ".")
    uv_run("ruff", "check", "--fix", ".")


def openapi(_: list[str]) -> None:
    """Write the OpenAPI schema (source for the generated frontend client)."""
    target = BACKEND / "openapi" / "schema.yaml"
    target.parent.mkdir(exist_ok=True)
    manage("spectacular", "--validate", "--fail-on-warn", "--file", str(target))
    print(f"wrote {target.relative_to(ROOT)}")


def ci(_: list[str]) -> None:
    """Everything CI runs: static checks plus tests."""
    lint([])
    test([])


TASKS: dict[str, Callable[[list[str]], None]] = {
    "setup": setup,
    "infra-up": infra_up,
    "infra-down": infra_down,
    "infra-reset": infra_reset,
    "infra-logs": infra_logs,
    "migrate": migrate,
    "makemigrations": makemigrations,
    "superuser": superuser,
    "dev": dev,
    "worker": worker,
    "beat": beat,
    "shell": shell,
    "test": test,
    "lint": lint,
    "fmt": fmt,
    "openapi": openapi,
    "ci": ci,
}


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help", "help"):
        width = max(len(name) for name in TASKS)
        print(__doc__)
        print("Tasks:")
        for name, func in TASKS.items():
            summary = (func.__doc__ or "").splitlines()[0]
            print(f"  {name.ljust(width)}  {summary}")
        return
    task = argv[0]
    if task not in TASKS:
        sys.exit(f"Unknown task: {task}\nRun `python tasks.py` to list tasks.")
    TASKS[task](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
