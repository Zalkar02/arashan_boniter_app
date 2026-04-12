import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class UpdateError(RuntimeError):
    pass


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git command failed").strip()
        raise UpdateError(message)
    return (result.stdout or "").strip()


def _python_bin() -> str:
    candidates = [
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / "env" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "python3"


def _run_python(*args: str) -> str:
    result = subprocess.run(
        [_python_bin(), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "python command failed").strip()
        raise UpdateError(message)
    return (result.stdout or "").strip()


def check_for_updates():
    current_branch = _run_git("branch", "--show-current")
    dirty = bool(_run_git("status", "--porcelain"))
    _run_git("fetch", "origin", "main")
    local_head = _run_git("rev-parse", "HEAD")
    remote_head = _run_git("rev-parse", "origin/main")
    behind = int(_run_git("rev-list", "--count", "HEAD..origin/main") or "0")
    ahead = int(_run_git("rev-list", "--count", "origin/main..HEAD") or "0")
    return {
        "branch": current_branch,
        "dirty": dirty,
        "local_head": local_head,
        "remote_head": remote_head,
        "behind": behind,
        "ahead": ahead,
        "has_updates": behind > 0,
    }


def pull_updates():
    status = check_for_updates()
    if status["dirty"]:
        raise UpdateError("Есть локальные изменения. Сначала закоммитьте или уберите их.")
    output = _run_git("pull", "origin", "main")
    migrate_output = _run_python("migrate_local_db.py")
    refreshed = check_for_updates()
    return {
        "output": output,
        "migrate_output": migrate_output,
        "before": status,
        "after": refreshed,
    }
