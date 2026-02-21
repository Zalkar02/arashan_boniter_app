import os
import json
import requests
import datetime
from requests.auth import HTTPBasicAuth
from db.models import (
    Sheep, User, Color, Owner, Application,
    Boniter, Photo, init_db
)
from sqlalchemy.orm import Session
from sqlalchemy import Date, DateTime

BASE_URL = "http://0.0.0.0:8000/api_v2/sync"
AUTH = HTTPBasicAuth("Zalkar", "zuko9856")
HEADERS = {
    "Content-Type": "application/json"
}

LAST_SYNC_FILE = "last_sync.txt"
CONFLICT_POLICY = "server-wins"  # варианты: server-wins | client-wins | manual
CONFLICT_LOG = "sync_conflicts.jsonl"
MODELS = [Sheep, Application, Color, Owner, User,]
MODEL_NAMES = {
    Sheep: "sheep",
    Application: "application",
    Color: "color",
    Owner: "owner",
    User: "user",
}

def get_last_sync_time():
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE, "r") as f:
            return datetime.datetime.fromisoformat(f.read().strip())
    return datetime.datetime(2000, 1, 1)

def update_last_sync_time():
    with open(LAST_SYNC_FILE, "w") as f:
        f.write(datetime.datetime.utcnow().isoformat())

def serialize(obj):
    data = {}
    for column in obj.__table__.columns:
        data[column.name] = getattr(obj, column.name)

    for k, v in data.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            data[k] = v.isoformat()

    return data

def _normalize_item(model, item: dict):
    valid_keys = {column.name for column in model.__table__.columns}
    clean_item = {k: v for k, v in item.items() if k in valid_keys}

    # Преобразование дат из строк в объекты Python
    for column in model.__table__.columns:
        if column.name in clean_item and isinstance(clean_item[column.name], str):
            if isinstance(column.type, Date):
                clean_item[column.name] = datetime.date.fromisoformat(clean_item[column.name])
            elif isinstance(column.type, DateTime):
                clean_item[column.name] = datetime.datetime.fromisoformat(clean_item[column.name])

    # remote_id берем из id сервера
    if "remote_id" in valid_keys and "id" in item:
        clean_item["remote_id"] = item.get("id")

    # отметим как синхронизированное
    clean_item["synced"] = True
    return clean_item

def _log_conflict(model_name: str, local_id: int, server_data: dict, local_data: dict):
    try:
        row = {
            "ts": datetime.datetime.utcnow().isoformat(),
            "model": model_name,
            "local_id": local_id,
            "server": server_data,
            "local": local_data,
        }
        with open(CONFLICT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _handle_conflict(session: Session, model, model_name: str, local_id: int, server_data: dict):
    local = None
    if local_id:
        local = session.query(model).filter_by(id=local_id).first()
    if local is None and server_data.get("id") is not None:
        local = session.query(model).filter_by(remote_id=server_data.get("id")).first()

    if local is None:
        return

    _log_conflict(model_name, local_id, server_data, serialize(local))

    if CONFLICT_POLICY == "server-wins":
        clean_item = _normalize_item(model, server_data)
        for k, v in clean_item.items():
            setattr(local, k, v)
        session.commit()
    elif CONFLICT_POLICY == "client-wins":
        # пока нет серверного "force" — оставляем локальные данные и пометим как несинхр.
        local.synced = False
        session.commit()
    else:
        # manual: только логируем, не трогаем
        pass

def sync_to_server(session: Session):
    ok = True
    for model in MODELS:
        model_name = MODEL_NAMES[model]
        unsynced = session.query(model).filter_by(synced=False).all()
        if not unsynced:
            continue

        payload = []
        for obj in unsynced:
            data = serialize(obj)
            # локальный id не отправляем, но шлём как local_id для маппинга
            local_id = data.pop("id", None)
            data["local_id"] = local_id
            # если есть remote_id — отправляем как id для update на сервере
            if data.get("remote_id"):
                data["id"] = data["remote_id"]
            else:
                data.pop("remote_id", None)
                data.pop("id", None)
            payload.append(data)

        url = f"{BASE_URL}/{MODEL_NAMES[model]}/post/"
        r = requests.post(url, headers=HEADERS, auth=AUTH, json=payload)

        if r.status_code == 200:
            # если сервер вернул mapping id, пробуем применить
            try:
                resp = r.json()
            except Exception:
                resp = None

            if isinstance(resp, list):
                # ожидаем элементы вида {"remote_id": X, "local_id": Y} или {"id": X, "local_id": Y}
                by_local = {item.get("local_id"): item for item in resp if isinstance(item, dict)}
                for obj in unsynced:
                    item = by_local.get(obj.id)
                    if item:
                        if item.get("status") == "conflict" and item.get("server"):
                            _handle_conflict(session, model, model_name, obj.id, item["server"])
                            continue
                        obj.remote_id = item.get("remote_id") or item.get("id") or obj.remote_id

            for obj in unsynced:
                obj.synced = True
            session.commit()
        else:
            ok = False
            print(f"Error syncing {model.__name__}: {r.status_code} {r.text}")
    return ok

def sync_from_server(session: Session):
    ok = True
    last_sync = get_last_sync_time()
    for model in MODELS:
        name = MODEL_NAMES[model]
        url = f"{BASE_URL}/{name}/?updated_after={last_sync.isoformat()}"
        r = requests.get(url, headers=HEADERS, auth=AUTH)
        if r.status_code != 200:
            ok = False
            print(f"Error fetching {name}: {r.status_code} {r.text}")
            continue

        for item in r.json():
            remote_id = item.get("id")

            clean_item = _normalize_item(model, item)

            local = session.query(model).filter_by(remote_id=remote_id).first()
            if local:
                for k, v in clean_item.items():
                    setattr(local, k, v)
            else:
                try:
                    new = model(**clean_item)
                    session.add(new)
                except Exception as e:
                    ok = False
                    print(f"Ошибка при вставке {model.__name__} ({remote_id}): {e}")
        session.commit()
    return ok

def run_sync():
    session = init_db()
    ok_up = sync_to_server(session)
    ok_down = sync_from_server(session)
    if ok_up and ok_down:
        update_last_sync_time()

if __name__ == "__main__":
    run_sync()
