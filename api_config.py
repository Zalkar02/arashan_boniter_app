import os
import sys
from pathlib import Path


def _load_env_file():
    candidates = []
    configured_path = os.getenv("ARASHAN_ENV_FILE")
    if configured_path:
        candidates.append(Path(configured_path).expanduser())
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")

    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            continue
        break


_load_env_file()


API_HOST = os.getenv("API_HOST", "https://arashan.zet.kg").rstrip("/")


def build_api_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{API_HOST}{normalized}"
