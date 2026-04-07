import json
import os

import requests

from auth_state import AuthState
from state_paths import TOKENS_PATH, USER_PATH, ensure_state_dir


def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return {}
    try:
        with open(TOKENS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_tokens(access: str, refresh: str):
    ensure_state_dir()
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump({"access": access, "refresh": refresh}, f)


def load_user():
    if not os.path.exists(USER_PATH):
        return None
    try:
        with open(USER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_user(user: dict):
    ensure_state_dir()
    with open(USER_PATH, "w", encoding="utf-8") as f:
        json.dump(user, f, ensure_ascii=False)


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
            if os.path.exists(path):
                os.remove(path)
        except Exception:
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
