import os
import shutil
import sys


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    APP_STATE_HOME = os.path.join(os.path.expanduser("~"), ".local", "share", "arashan-boniter")
else:
    APP_STATE_HOME = PROJECT_ROOT

STATE_DIR = os.path.join(APP_STATE_HOME, ".app_state")
TOKENS_PATH = os.path.join(STATE_DIR, "tokens.json")
USER_PATH = os.path.join(STATE_DIR, "user.json")
DB_PATH = os.path.join(APP_STATE_HOME, "sheep_local.db")
LEGACY_DB_PATH = os.path.join(PROJECT_ROOT, "sheep_local.db")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(APP_STATE_HOME, exist_ok=True)


def ensure_db_path():
    ensure_state_dir()
    if DB_PATH != LEGACY_DB_PATH and not os.path.exists(DB_PATH) and os.path.exists(LEGACY_DB_PATH):
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)
    return DB_PATH
