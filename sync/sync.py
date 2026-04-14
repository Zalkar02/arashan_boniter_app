import os
import json
import requests
import datetime
from api_config import build_api_url
from db.models import (
    Sheep, User, Color, Owner, Application, Lamb,
    Boniter, Photo, init_db
)
from services.auth_service import load_tokens, refresh_access_token
from sqlalchemy.orm import Session
from sqlalchemy import Date, DateTime
from state_paths import APP_STATE_HOME, ensure_state_dir

BASE_URL = build_api_url("/api_v2/sync").rstrip("/")
TOKEN_REFRESH_URL = build_api_url("/api/token/refresh/")

HEADERS = {
    "Content-Type": "application/json"
}

LAST_SYNC_FILE = os.path.join(APP_STATE_HOME, "last_sync.txt")
CONFLICT_POLICY = "server-wins"  # варианты: server-wins | client-wins | manual
CONFLICT_LOG = os.path.join(APP_STATE_HOME, "sync_conflicts.jsonl")
SYNC_BATCH_SIZE = int(os.getenv("SYNC_BATCH_SIZE", "100"))
UPLOAD_MODELS = [Color, User, Sheep, Lamb, Application, Owner]
DOWNLOAD_MODELS = [Color, User, Sheep, Lamb, Application, Owner]
MODEL_NAMES = {
    Sheep: "sheep",
    Lamb: "lamb",
    Application: "application",
    Color: "color",
    Owner: "owner",
    User: "user",
}
MODEL_BY_SYNC_NAME = {value: key for key, value in MODEL_NAMES.items()}
MODEL_LABELS = {
    "color": "Окрасы",
    "user": "Владельцы",
    "sheep": "Овцы",
    "lamb": "Ягнята",
    "application": "Бонитировки",
    "owner": "Связи владельцев",
    "deleted": "Удаления",
}
FK_FIELD_MAP = {
    Sheep: {
        "color_id": ("color", Color),
        "owner_id": ("owner", User),
        "boniter": ("boniter", Boniter),
    },
    Application: {
        "sheep_id": ("sheep", Sheep),
        "boniter": ("boniter", Boniter),
    },
    Lamb: {
        "sheep_id": ("sheep", Sheep),
    },
    Owner: {
        "sheep_id": ("sheep", Sheep),
        "owner_id": ("owner", User),
    },
}


def _get_headers():
    access = load_tokens().get("access")
    if not access:
        raise RuntimeError("No access token found. Log in to the application first.")
    headers = dict(HEADERS)
    headers["Authorization"] = f"Bearer {access}"
    return headers


def _request_with_auth(method, url, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.update(_get_headers())
    response = requests.request(method, url, headers=headers, **kwargs)
    if not _should_refresh_token(response):
        return response

    try:
        access = refresh_access_token(TOKEN_REFRESH_URL)
    except Exception as exc:
        raise RuntimeError(f"Failed to refresh sync token: {exc}") from exc

    headers = dict(kwargs.pop("headers", {}) or {})
    headers.update(HEADERS)
    headers["Authorization"] = f"Bearer {access}"
    return requests.request(method, url, headers=headers, **kwargs)


def _should_refresh_token(response):
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False

    try:
        payload = response.json()
    except Exception:
        return False
    return payload.get("code") == "token_not_valid"


def _iter_chunks(items, chunk_size: int):
    size = max(1, chunk_size)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _unique_by_id(items):
    unique = []
    seen = set()
    for item in items:
        item_id = getattr(item, "id", None)
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
    return unique


def _sheep_parents_ready_for_sync(sheep, pending_ids: set[int]) -> bool:
    for parent in getattr(sheep, "parents", []):
        parent_remote_id = getattr(parent, "remote_id", None)
        if parent_remote_id:
            continue
        if getattr(parent, "id", None) in pending_ids:
            return False
        return False
    return True


def _iter_upload_batches(session: Session, model, objects):
    if model is not Sheep:
        yield from _iter_chunks(objects, SYNC_BATCH_SIZE)
        return

    pending = list(objects)
    while pending:
        pending_ids = {obj.id for obj in pending}
        ready = [obj for obj in pending if _sheep_parents_ready_for_sync(obj, pending_ids)]
        if not ready:
            break

        for chunk in _iter_chunks(ready, SYNC_BATCH_SIZE):
            yield chunk
        ready_ids = {obj.id for obj in ready}
        pending = [obj for obj in pending if obj.id not in ready_ids]


class SyncCancelled(Exception):
    pass


def _check_stop(should_stop=None):
    if should_stop and should_stop():
        raise SyncCancelled()


def _emit_progress(progress_cb=None, stage="", model_name="", current=0, total=0, message=""):
    if progress_cb:
        progress_cb(stage, model_name, current, total, message)

def get_last_sync_time():
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE, "r") as f:
            return datetime.datetime.fromisoformat(f.read().strip())
    return datetime.datetime(2000, 1, 1)

def update_last_sync_time():
    ensure_state_dir()
    with open(LAST_SYNC_FILE, "w") as f:
        f.write(datetime.datetime.utcnow().isoformat())

def serialize(obj):
    data = {}
    for column in obj.__table__.columns:
        data[column.name] = getattr(obj, column.name)

    if isinstance(obj, Sheep):
        data["parent"] = [
            parent.remote_id
            for parent in getattr(obj, "parents", [])
            if getattr(parent, "remote_id", None)
        ]

    for k, v in data.items():
        if isinstance(v, datetime.datetime) and v.tzinfo is None:
            v = v.replace(tzinfo=datetime.timezone.utc)
            data[k] = v
        if isinstance(v, (datetime.date, datetime.datetime)):
            data[k] = v.isoformat()

    return data


def _prepare_outgoing_payload(session: Session, model, data: dict):
    outgoing = dict(data)
    outgoing.pop("created_by_user_id", None)

    if model is User:
        password = outgoing.get("password")
        if not password:
            outgoing.pop("password", None)
        outgoing.pop("name_norm", None)
    elif model in (Sheep, Application):
        outgoing.pop("payment_reference", None)
        outgoing.pop("payment_token", None)
        outgoing.pop("is_printed", None)
        outgoing.pop("nick_norm", None)

    fk_map = FK_FIELD_MAP.get(model, {})
    for local_key, (remote_key, related_model) in fk_map.items():
        local_fk_value = outgoing.pop(local_key, None)
        if not local_fk_value:
            continue

        related = session.query(related_model).filter_by(id=local_fk_value).first()
        related_remote_id = getattr(related, "remote_id", None) if related is not None else None
        if related_remote_id:
            outgoing[remote_key] = related_remote_id

    if model is Sheep:
        outgoing["parent"] = data.get("parent", [])

    return outgoing


def _is_object_ready_for_sync(session: Session, model, obj) -> bool:
    fk_map = FK_FIELD_MAP.get(model, {})
    for local_key, (_, related_model) in fk_map.items():
        local_fk_value = getattr(obj, local_key, None)
        if not local_fk_value:
            continue
        related = session.query(related_model).filter_by(id=local_fk_value).first()
        if related is None:
            return False
        related_remote_id = getattr(related, "remote_id", None)
        if not related_remote_id:
            return False
    return True


def _get_owner_scope_objects(session: Session, owner_id: int):
    sheep_rows = session.query(Sheep).filter_by(owner_id=owner_id).all()
    owner_links = session.query(Owner).filter_by(owner_id=owner_id).all()
    linked_sheep_ids = {row.sheep_id for row in owner_links if getattr(row, "sheep_id", None)}
    if linked_sheep_ids:
        linked_sheep = session.query(Sheep).filter(Sheep.id.in_(linked_sheep_ids)).all()
        sheep_rows.extend(linked_sheep)
    sheep_rows = _unique_by_id(sheep_rows)

    sheep_ids = [row.id for row in sheep_rows]
    applications = session.query(Application).filter(Application.sheep_id.in_(sheep_ids)).all() if sheep_ids else []
    lambs = session.query(Lamb).filter(Lamb.sheep_id.in_(sheep_ids)).all() if sheep_ids else []
    color_ids = {row.color_id for row in sheep_rows if getattr(row, "color_id", None)}
    colors = session.query(Color).filter(Color.id.in_(color_ids)).all() if color_ids else []
    owner_user = session.query(User).filter_by(id=owner_id).first()

    scoped = {
        Color: colors,
        User: [owner_user] if owner_user is not None else [],
        Sheep: sheep_rows,
        Lamb: lambs,
        Application: applications,
        Owner: owner_links,
    }
    return scoped

def _normalize_item(session: Session, model, item: dict):
    valid_keys = {column.name for column in model.__table__.columns}
    clean_item = {k: v for k, v in item.items() if k in valid_keys}

    fk_map = FK_FIELD_MAP.get(model, {})
    for local_key, (remote_key, related_model) in fk_map.items():
        if remote_key not in item:
            continue
        remote_fk_value = item.get(remote_key)
        if remote_fk_value in (None, ""):
            clean_item[local_key] = None
            continue
        related = session.query(related_model).filter_by(remote_id=remote_fk_value).first()
        if related is not None:
            clean_item[local_key] = related.id

    if model is User:
        clean_item.pop("password", None)

    # Преобразование дат из строк в объекты Python
    for column in model.__table__.columns:
        if column.name in clean_item and isinstance(clean_item[column.name], str):
            if isinstance(column.type, Date):
                clean_item[column.name] = datetime.date.fromisoformat(clean_item[column.name])
            elif isinstance(column.type, DateTime):
                clean_item[column.name] = datetime.datetime.fromisoformat(clean_item[column.name])

    # never override local primary key from server id
    clean_item.pop("id", None)

    # remote_id берем из id сервера
    if "remote_id" in valid_keys and "id" in item:
        clean_item["remote_id"] = item.get("id")

    # отметим как синхронизированное
    clean_item["synced"] = True
    return clean_item


def _extract_sheep_parent_ids(session: Session, item: dict):
    parent_remote_ids = item.get("parent")
    if not isinstance(parent_remote_ids, list):
        return None
    parent_ids = []
    for remote_id in parent_remote_ids:
        parent = session.query(Sheep).filter_by(remote_id=remote_id).first()
        if parent is None:
            return None
        parent_ids.append(parent.id)
    return parent_ids

def _log_conflict(model_name: str, local_id: int, server_data: dict, local_data: dict):
    try:
        ensure_state_dir()
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
        clean_item = _normalize_item(session, model, server_data)
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


def _extract_response_items(payload):
    if isinstance(payload, list):
        return payload, False
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            next_url = payload.get("next")
            return results, bool(next_url)
    return [], False


def _apply_deleted_records(session: Session, last_sync: datetime.datetime, progress_cb=None, should_stop=None):
    offset = 0
    processed = 0
    total_count = 0
    while True:
        _check_stop(should_stop)
        params = {
            "deleted_after": last_sync.isoformat(),
            "limit": SYNC_BATCH_SIZE,
            "offset": offset,
        }
        url = f"{BASE_URL}/deleted-records/"
        r = _request_with_auth("GET", url, params=params)
        if r.status_code != 200:
            print(f"Error fetching deleted records: {r.status_code} {r.text}")
            return False

        items, has_next = _extract_response_items(r.json())
        if isinstance(r.json(), dict):
            total_count = r.json().get("count") or total_count
        if not items:
            break

        for item in items:
            model = MODEL_BY_SYNC_NAME.get(item.get("model_name"))
            remote_id = item.get("remote_id")
            if model is None or remote_id is None:
                continue
            local = session.query(model).filter_by(remote_id=remote_id).first()
            if local is None or not hasattr(local, "is_deleted"):
                continue
            local.is_deleted = True
            if hasattr(local, "synced"):
                local.synced = True
        session.commit()
        processed += len(items)
        _emit_progress(
            progress_cb,
            "download",
            "deleted",
            processed,
            total_count or processed,
            f"Удаления: {processed} / {total_count or processed}",
        )

        if len(items) < SYNC_BATCH_SIZE and not has_next:
            break
        offset += len(items)

    return True

def sync_to_server(session: Session, progress_cb=None, should_stop=None):
    ok = True
    for model in UPLOAD_MODELS:
        _check_stop(should_stop)
        model_name = MODEL_NAMES[model]
        unsynced = session.query(model).filter_by(synced=False).all()
        if hasattr(model, "created_by_guest"):
            unsynced = [obj for obj in unsynced if not getattr(obj, "created_by_guest", False)]
        unsynced = [obj for obj in unsynced if _is_object_ready_for_sync(session, model, obj)]
        if not unsynced:
            continue

        url = f"{BASE_URL}/{MODEL_NAMES[model]}/post/"
        processed = 0
        total = len(unsynced)
        processed_ids = set()
        for chunk in _iter_upload_batches(session, model, unsynced):
            _check_stop(should_stop)
            payload = []
            for obj in chunk:
                data = _prepare_outgoing_payload(session, model, serialize(obj))
                local_id = data.pop("id", None)
                data["local_id"] = local_id
                if data.get("remote_id"):
                    data["id"] = data["remote_id"]
                else:
                    data.pop("remote_id", None)
                    data.pop("id", None)
                payload.append(data)

            r = _request_with_auth("POST", url, json=payload)

            if r.status_code == 200:
                try:
                    resp = r.json()
                except Exception:
                    resp = None

                if isinstance(resp, list):
                    by_local = {item.get("local_id"): item for item in resp if isinstance(item, dict)}
                    for obj in chunk:
                        item = by_local.get(obj.id)
                        if item:
                            if item.get("status") == "conflict" and item.get("server"):
                                _handle_conflict(session, model, model_name, obj.id, item["server"])
                                continue
                            obj.remote_id = item.get("remote_id") or item.get("id") or obj.remote_id

                for obj in chunk:
                    if model is User:
                        obj.password = None
                    obj.synced = True
                    processed_ids.add(obj.id)
                session.commit()
                processed += len(chunk)
                _emit_progress(
                    progress_cb,
                    "upload",
                    model_name,
                    processed,
                    total,
                    f"{MODEL_LABELS.get(model_name, model_name)}: {processed} / {total}",
                )
            else:
                ok = False
                print(f"Error syncing {model.__name__}: {r.status_code} {r.text}")
                break

        if model is Sheep:
            remaining = [obj for obj in unsynced if obj.id not in processed_ids]
            if remaining:
                _emit_progress(
                    progress_cb,
                    "upload",
                    model_name,
                    processed,
                    total,
                    f"Ожидание родителей для {len(remaining)} овец",
                )
    return ok


def sync_owner_to_server(session: Session, owner_id: int, progress_cb=None, should_stop=None):
    ok = True
    scoped_objects = _get_owner_scope_objects(session, owner_id)
    for model in UPLOAD_MODELS:
        _check_stop(should_stop)
        model_name = MODEL_NAMES[model]
        unsynced = [
            obj for obj in scoped_objects.get(model, [])
            if not bool(getattr(obj, "synced", False))
        ]
        if hasattr(model, "created_by_guest"):
            unsynced = [obj for obj in unsynced if not getattr(obj, "created_by_guest", False)]
        unsynced = [obj for obj in unsynced if _is_object_ready_for_sync(session, model, obj)]
        if not unsynced:
            continue

        url = f"{BASE_URL}/{MODEL_NAMES[model]}/post/"
        processed = 0
        total = len(unsynced)
        processed_ids = set()
        for chunk in _iter_upload_batches(session, model, unsynced):
            _check_stop(should_stop)
            payload = []
            for obj in chunk:
                data = _prepare_outgoing_payload(session, model, serialize(obj))
                local_id = data.pop("id", None)
                data["local_id"] = local_id
                if data.get("remote_id"):
                    data["id"] = data["remote_id"]
                else:
                    data.pop("remote_id", None)
                    data.pop("id", None)
                payload.append(data)

            r = _request_with_auth("POST", url, json=payload)

            if r.status_code == 200:
                try:
                    resp = r.json()
                except Exception:
                    resp = None

                if isinstance(resp, list):
                    by_local = {item.get("local_id"): item for item in resp if isinstance(item, dict)}
                    for obj in chunk:
                        item = by_local.get(obj.id)
                        if item:
                            if item.get("status") == "conflict" and item.get("server"):
                                _handle_conflict(session, model, model_name, obj.id, item["server"])
                                continue
                            obj.remote_id = item.get("remote_id") or item.get("id") or obj.remote_id

                for obj in chunk:
                    if model is User:
                        obj.password = None
                    obj.synced = True
                    processed_ids.add(obj.id)
                session.commit()
                processed += len(chunk)
                _emit_progress(
                    progress_cb,
                    "upload",
                    model_name,
                    processed,
                    total,
                    f"{MODEL_LABELS.get(model_name, model_name)}: {processed} / {total}",
                )
            else:
                ok = False
                print(f"Error syncing {model.__name__}: {r.status_code} {r.text}")
                break

        if model is Sheep:
            remaining = [obj for obj in unsynced if obj.id not in processed_ids]
            if remaining:
                _emit_progress(
                    progress_cb,
                    "upload",
                    model_name,
                    processed,
                    total,
                    f"Ожидание родителей для {len(remaining)} овец",
                )
    return ok

def sync_from_server(session: Session, progress_cb=None, should_stop=None):
    ok = True
    last_sync = get_last_sync_time()
    if not _apply_deleted_records(session, last_sync, progress_cb=progress_cb, should_stop=should_stop):
        ok = False
    for model in DOWNLOAD_MODELS:
        _check_stop(should_stop)
        name = MODEL_NAMES[model]
        offset = 0
        processed = 0
        total_count = 0
        pending_sheep_parents = []
        while True:
            _check_stop(should_stop)
            params = {
                "updated_after": last_sync.isoformat(),
                "limit": SYNC_BATCH_SIZE,
                "offset": offset,
            }
            url = f"{BASE_URL}/{name}/"
            r = _request_with_auth("GET", url, params=params)
            if r.status_code != 200:
                ok = False
                print(f"Error fetching {name}: {r.status_code} {r.text}")
                break

            payload = r.json()
            items, has_next = _extract_response_items(payload)
            if isinstance(payload, dict):
                total_count = payload.get("count") or total_count
            if not items:
                break

            for item in items:
                remote_id = item.get("id")
                clean_item = _normalize_item(session, model, item)

                local = session.query(model).filter_by(remote_id=remote_id).first()
                if local:
                    for k, v in clean_item.items():
                        if k == "id":
                            continue
                        setattr(local, k, v)
                else:
                    try:
                        clean_item.pop("id", None)
                        new = model(**clean_item)
                        session.add(new)
                    except Exception as e:
                        ok = False
                        print(f"Ошибка при вставке {model.__name__} ({remote_id}): {e}")
                if model is Sheep and "parent" in item:
                    pending_sheep_parents.append((remote_id, item))
            session.commit()

            if model is Sheep and pending_sheep_parents:
                for remote_id, item in pending_sheep_parents:
                    local_sheep = session.query(Sheep).filter_by(remote_id=remote_id).first()
                    if local_sheep is None:
                        continue
                    parent_ids = _extract_sheep_parent_ids(session, item)
                    if parent_ids is None:
                        continue
                    local_sheep.parents = session.query(Sheep).filter(Sheep.id.in_(parent_ids)).all() if parent_ids else []
                session.commit()
                pending_sheep_parents.clear()
            processed += len(items)
            _emit_progress(
                progress_cb,
                "download",
                name,
                processed,
                total_count or processed,
                f"{MODEL_LABELS.get(name, name)}: {processed} / {total_count or processed}",
            )

            if len(items) < SYNC_BATCH_SIZE and not has_next:
                break
            offset += len(items)
    return ok

def run_sync(progress_cb=None, should_stop=None):
    session = init_db()
    _emit_progress(progress_cb, "upload", "", 0, 0, "Отправка локальных данных...")
    ok_up = sync_to_server(session, progress_cb=progress_cb, should_stop=should_stop)
    _check_stop(should_stop)
    _emit_progress(progress_cb, "download", "", 0, 0, "Загрузка данных с сервера...")
    ok_down = sync_from_server(session, progress_cb=progress_cb, should_stop=should_stop)
    if ok_up and ok_down:
        update_last_sync_time()


def run_owner_sync(owner_id: int, progress_cb=None, should_stop=None):
    session = init_db()
    _emit_progress(progress_cb, "upload", "", 0, 0, "Отправка данных хозяйства...")
    ok_up = sync_owner_to_server(session, owner_id, progress_cb=progress_cb, should_stop=should_stop)
    _check_stop(should_stop)
    _emit_progress(progress_cb, "download", "", 0, 0, "Загрузка обновлений с сервера...")
    ok_down = sync_from_server(session, progress_cb=progress_cb, should_stop=should_stop)
    if ok_up and ok_down:
        update_last_sync_time()
    return ok_up and ok_down

if __name__ == "__main__":
    run_sync()
