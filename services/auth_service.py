import json
import os
import tempfile

import requests

from auth_state import AuthState
from state_paths import TOKENS_PATH, USER_PATH, ensure_state_dir


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path, data):
    ensure_state_dir()
    directory = os.path.dirname(path) or "."
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def load_tokens():
    return _load_json(TOKENS_PATH)


def save_tokens(access: str, refresh: str):
    _save_json(TOKENS_PATH, {"access": access, "refresh": refresh})


def load_user():
    return _load_json(USER_PATH) or None


def save_user(user: dict):
    _save_json(USER_PATH, user)


def login_user(token_url: str, me_url: str, username: str, password: str, timeout: int = 10):
    response = requests.post(
        token_url,
        json={"username": username, "password": password},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError("Неверный логин или пароль")

    data = response.json()
    access = data.get("access")
    refresh = data.get("refresh")
    if not access or not refresh:
        raise RuntimeError("Не удалось получить токены")

    AuthState.access = access
    AuthState.refresh = refresh
    save_tokens(access, refresh)
    fetch_current_user(me_url, access, timeout=timeout)
    return {
        "access": access,
        "refresh": refresh,
        "user": AuthState.user,
    }


def restore_authenticated_session(refresh_url: str, me_url: str, timeout: int = 10):
    tokens = load_tokens()
    refresh = tokens.get("refresh")
    if not refresh:
        return None

    access = refresh_access_token(refresh_url, refresh=refresh, timeout=timeout)
    user = fetch_current_user(me_url, access, timeout=timeout)
    return {
        "access": access,
        "refresh": AuthState.refresh,
        "user": user,
    }


def clear_session():
    AuthState.user = None
    AuthState.access = None
    AuthState.refresh = None

    for path in (TOKENS_PATH, USER_PATH):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def refresh_access_token(refresh_url: str, refresh: str | None = None, timeout: int = 10):
    refresh_token = refresh or AuthState.refresh or load_tokens().get("refresh")
    if not refresh_token:
        raise RuntimeError(
            "No refresh token found. Log in to the application first."
        )

    response = requests.post(refresh_url, json={"refresh": refresh_token}, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to refresh token: {response.status_code} {response.text}"
        )

    data = response.json()
    access = data.get("access")
    if not access:
        raise RuntimeError("Token refresh succeeded but access token is missing in the response.")

    new_refresh = data.get("refresh") or refresh_token
    AuthState.access = access
    AuthState.refresh = new_refresh
    save_tokens(access, new_refresh)
    return access


def fetch_current_user(me_url: str, access: str, timeout: int = 10):
    response = requests.get(
        me_url,
        headers={"Authorization": f"Bearer {access}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        return None

    user = response.json()
    AuthState.user = user
    save_user(user)
    return user
