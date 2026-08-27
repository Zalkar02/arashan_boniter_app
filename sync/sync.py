import os
import json
import requests
import datetime
import uuid
from api_config import build_api_url
from db.models import (
    Sheep, User, Color, Owner, Application, Lamb,
    Boniter, Photo, SyncMetadata, init_db
)
from services.auth_service import load_tokens, refresh_access_token
from sqlalchemy.orm import Session
from sqlalchemy import Date, DateTime
from state_paths import APP_STATE_HOME, ensure_state_dir

BASE_URL = build_api_url("/api_v2/sync").rstrip("/")
TOKEN_REFRESH_URL = build_api_url("/api/token/refresh/")
SYNC_CURSOR_URL = f"{BASE_URL}/cursor/"

HEADERS = {
    "Content-Type": "application/json"
}

LAST_SYNC_FILE = os.path.join(APP_STATE_HOME, "last_sync.txt")
CONFLICT_POLICY = "server-wins"  # варианты: server-wins | client-wins | manual
CONFLICT_LOG = os.path.join(APP_STATE_HOME, "sync_conflicts.jsonl")
SYNC_BATCH_SIZE = int(os.getenv("SYNC_BATCH_SIZE", "100"))
SYNC_REQUEST_TIMEOUT = float(os.getenv("SYNC_REQUEST_TIMEOUT", "30"))
SYNC_CLIENT_KEY = "sync_client_id"
UPLOAD_MODELS = [Color, User, Sheep, Lamb, Application, Owner]
DOWNLOAD_MODELS = [Color, User, Sheep, Lamb, Application, Owner]
MODEL_NAMES = {
    Sheep: "sheep",
    Lamb: "lamb",
    Application: "application",
    Color: "color",
    Boniter: "boniter",
    Owner: "owner",
    User: "user",
}
MODEL_BY_SYNC_NAME = {value: key for key, value in MODEL_NAMES.items()}
MODEL_LABELS = {
    "color": "Окрасы",
    "boniter": "Бонитёры",
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
DEPENDENCY_LABELS = {
    Color: "окрас",
    User: "владелец",
    Sheep: "овца",
    Boniter: "бонитёр",
}


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def get_sync_client_id(session: Session):
    row = session.query(SyncMetadata).filter_by(key=SYNC_CLIENT_KEY).first()
    if row is None:
        row = SyncMetadata(key=SYNC_CLIENT_KEY, value=str(uuid.uuid4()))
        session.add(row)
        session.commit()
    try:
        return str(uuid.UUID(row.value))
    except (TypeError, ValueError, AttributeError):
        row.value = str(uuid.uuid4())
        session.commit()
        return row.value


def get_server_sync_cursor():
    response = _request_with_auth("GET", SYNC_CURSOR_URL)
    if response.status_code != 200:
        raise RuntimeError(
            f"Не удалось получить курсор синхронизации: {response.status_code} {response.text}"
        )
    try:
        raw_cursor = response.json().get("cursor")
        cursor = datetime.datetime.fromisoformat(str(raw_cursor).replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SyncProtocolError("Сервер вернул некорректный курсор синхронизации.") from exc
    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=datetime.timezone.utc)
    return cursor


def _get_headers():
    access = load_tokens().get("access")
    if not access:
        raise RuntimeError("No access token found. Log in to the application first.")
    headers = dict(HEADERS)
    headers["Authorization"] = f"Bearer {access}"
    return headers


def _request_with_auth(method, url, **kwargs):
    kwargs.setdefault("timeout", SYNC_REQUEST_TIMEOUT)
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


class SyncProtocolError(RuntimeError):
    pass


def _check_stop(should_stop=None):
    if should_stop and should_stop():
        raise SyncCancelled()


def _emit_progress(progress_cb=None, stage="", model_name="", current=0, total=0, message=""):
    if progress_cb:
        progress_cb(stage, model_name, current, total, message)

def get_last_sync_time():
    if os.path.exists(LAST_SYNC_FILE):
        try:
            with open(LAST_SYNC_FILE, "r", encoding="utf-8") as f:
                value = datetime.datetime.fromisoformat(f.read().strip().replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=datetime.timezone.utc)
                return value
        except (OSError, TypeError, ValueError):
            pass
    return datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


def update_last_sync_time(value=None):
    ensure_state_dir()
    timestamp = value or _utcnow()
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        f.write(timestamp.isoformat())

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
    return not _get_missing_dependencies(session, model, obj)


def _get_missing_dependencies(session: Session, model, obj):
    missing = []
    fk_map = FK_FIELD_MAP.get(model, {})
    for local_key, (_, related_model) in fk_map.items():
        local_fk_value = getattr(obj, local_key, None)
        if not local_fk_value:
            continue
        related = session.query(related_model).filter_by(id=local_fk_value).first()
        if related is None:
            reason = "локальная запись отсутствует"
        elif not getattr(related, "remote_id", None):
            reason = "ещё не синхронизирован"
        else:
            continue
        label = DEPENDENCY_LABELS.get(related_model, related_model.__name__)
        missing.append(f"{label} {local_fk_value} ({reason})")
    return missing


def _format_blocked_dependencies(session: Session, model, objects):
    details = []
    for obj in objects[:5]:
        reasons = _get_missing_dependencies(session, model, obj)
        local_id = getattr(obj, "id", "?")
        details.append(f"локальная запись #{local_id}: {', '.join(reasons)}")
    suffix = "" if len(objects) <= 5 else f"; ещё {len(objects) - 5}"
    return "; ".join(details) + suffix


def _get_owner_scope_objects(session: Session, owner_id: int):
    sheep_rows = session.query(Sheep).filter(
        Sheep.owner_id == owner_id,
        (Sheep.is_deleted.is_(False)) | (Sheep.synced.is_(False)),
    ).all()
    direct_owner_links = session.query(Owner).filter_by(owner_id=owner_id).all()
    linked_sheep_ids = {row.sheep_id for row in direct_owner_links if getattr(row, "sheep_id", None)}
    if linked_sheep_ids:
        linked_sheep = session.query(Sheep).filter(
            Sheep.id.in_(linked_sheep_ids),
            (Sheep.is_deleted.is_(False)) | (Sheep.synced.is_(False)),
        ).all()
        sheep_rows.extend(linked_sheep)
    sheep_rows = _unique_by_id(sheep_rows)

    sheep_ids = [row.id for row in sheep_rows]
    owner_links = session.query(Owner).filter(Owner.sheep_id.in_(sheep_ids)).all() if sheep_ids else []
    applications = session.query(Application).filter(Application.sheep_id.in_(sheep_ids)).all() if sheep_ids else []
    lambs = session.query(Lamb).filter(Lamb.sheep_id.in_(sheep_ids)).all() if sheep_ids else []
    color_ids = {row.color_id for row in sheep_rows if getattr(row, "color_id", None)}
    colors = session.query(Color).filter(Color.id.in_(color_ids)).all() if color_ids else []
    user_ids = {owner_id}
    user_ids.update(
        row.owner_id for row in owner_links
        if getattr(row, "owner_id", None) is not None
    )
    owner_users = session.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []

    scoped = {
        Color: colors,
        User: owner_users,
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


def _load_missing_sheep_parents(session: Session, pending_items, progress_cb=None, should_stop=None):
    """Download parents omitted from the incremental sheep response, including ancestors."""
    pending_by_remote_id = {
        remote_id: item for remote_id, item in pending_items if remote_id is not None
    }
    requested_ids = set()

    while True:
        _check_stop(should_stop)
        referenced_ids = {
            parent_remote_id
            for item in pending_by_remote_id.values()
            if isinstance(item.get("parent"), list)
            for parent_remote_id in item["parent"]
        }
        existing_ids = (
            {
                row[0]
                for row in session.query(Sheep.remote_id).filter(
                    Sheep.remote_id.in_(referenced_ids)
                ).all()
            }
            if referenced_ids else set()
        )
        missing_ids = referenced_ids - existing_ids
        if not missing_ids:
            break

        new_ids = missing_ids - requested_ids
        if not new_ids:
            missing_text = ", ".join(str(value) for value in sorted(missing_ids)[:20])
            raise RuntimeError(
                "Сервер не вернул отсутствующих родителей овец. "
                f"ID: {missing_text}"
            )

        for chunk in _iter_chunks(sorted(new_ids), SYNC_BATCH_SIZE):
            _check_stop(should_stop)
            response = _request_with_auth(
                "GET",
                f"{BASE_URL}/sheep/",
                params={"ids": ",".join(str(value) for value in chunk)},
            )
            if response.status_code != 200:
                details = response.text.strip() or "без описания"
                raise RuntimeError(
                    f"Ошибка загрузки родителей овец: HTTP {response.status_code}: {details}"
                )

            payload = response.json()
            items, _ = _extract_response_items(payload)
            received_ids = set()
            for item in items:
                remote_id = item.get("id")
                if remote_id is None:
                    continue
                received_ids.add(remote_id)
                clean_item = _normalize_item(session, Sheep, item)
                local = session.query(Sheep).filter_by(remote_id=remote_id).first()
                if local is not None:
                    if not bool(local.synced):
                        _log_conflict("sheep", local.id, item, serialize(local))
                        raise RuntimeError(
                            f"Конфликт овцы: локальная запись {local.id} ещё не отправлена"
                        )
                    for key, value in clean_item.items():
                        setattr(local, key, value)
                else:
                    session.add(Sheep(**clean_item))
                if "parent" in item:
                    pending_by_remote_id[remote_id] = item
            session.commit()
            requested_ids.update(chunk)

            not_returned = set(chunk) - received_ids
            if not_returned:
                missing_text = ", ".join(str(value) for value in sorted(not_returned)[:20])
                raise RuntimeError(
                    "На сервере не найдены родители овец с ID: " + missing_text
                )

        _emit_progress(
            progress_cb,
            "download",
            "sheep",
            len(requested_ids),
            len(requested_ids),
            f"Догружены родители овец: {len(requested_ids)}",
        )

    for remote_id, item in pending_by_remote_id.items():
        local_sheep = session.query(Sheep).filter_by(remote_id=remote_id).first()
        if local_sheep is None:
            continue
        parent_ids = _extract_sheep_parent_ids(session, item)
        if parent_ids is None:
            raise RuntimeError(f"Не удалось связать родителей овцы #{remote_id}")
        local_sheep.parents = (
            session.query(Sheep).filter(Sheep.id.in_(parent_ids)).all()
            if parent_ids else []
        )
    session.commit()

def _log_conflict(model_name: str, local_id: int, server_data: dict, local_data: dict):
    try:
        ensure_state_dir()
        row = {
            "ts": _utcnow().isoformat(),
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
        return False

    _log_conflict(model_name, local_id, server_data, serialize(local))

    if CONFLICT_POLICY == "server-wins":
        clean_item = _normalize_item(session, model, server_data)
        for k, v in clean_item.items():
            setattr(local, k, v)
        return True
    elif CONFLICT_POLICY == "client-wins":
        # пока нет серверного "force" — оставляем локальные данные и пометим как несинхр.
        local.synced = False
        return False
    else:
        # manual: только логируем, не трогаем
        return False


def _extract_response_items(payload):
    if isinstance(payload, list):
        return payload, False
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            next_url = payload.get("next")
            return results, bool(next_url)
    raise SyncProtocolError("Сервер вернул некорректный формат списка синхронизации.")


def sync_reference_data(session: Session, progress_cb=None, should_stop=None):
    """Refresh server-owned dictionaries required to upload local records."""
    for model in (Color, Boniter):
        _check_stop(should_stop)
        model_name = MODEL_NAMES[model]
        response = _request_with_auth(
            "GET",
            f"{BASE_URL}/{model_name}/",
            params={"full": "1"},
        )
        if response.status_code != 200:
            details = response.text.strip() or "без описания"
            raise RuntimeError(
                f"Ошибка загрузки {MODEL_LABELS[model_name]}: "
                f"HTTP {response.status_code}: {details}"
            )

        payload = response.json()
        items, _ = _extract_response_items(payload)
        for item in items:
            remote_id = item.get("id")
            if remote_id is None:
                continue
            clean_item = _normalize_item(session, model, item)
            local = session.query(model).filter_by(remote_id=remote_id).first()
            if local is None:
                local = model(**clean_item)
                session.add(local)
            else:
                for key, value in clean_item.items():
                    setattr(local, key, value)
        session.commit()
        _emit_progress(
            progress_cb,
            "download",
            model_name,
            len(items),
            len(items),
            f"{MODEL_LABELS[model_name]}: {len(items)} / {len(items)}",
        )

    # Older databases stored the server boniter ID directly in FK columns even
    # though no local Boniter rows existed. Convert those dangling values now.
    for model in (Sheep, Application):
        for obj in session.query(model).filter(model.boniter.isnot(None)).all():
            if session.query(Boniter).filter_by(id=obj.boniter).first() is not None:
                continue
            related = session.query(Boniter).filter_by(remote_id=obj.boniter).first()
            if related is not None:
                obj.boniter = related.id
    session.commit()
    return True


def _extract_upload_results(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    raise SyncProtocolError("Сервер вернул некорректный ответ на отправку данных.")


def _coerce_local_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _apply_upload_results(session: Session, model, model_name: str, chunk, payload):
    results = _extract_upload_results(payload)
    expected = {obj.id: obj for obj in chunk}
    by_local = {}
    for item in results:
        if not isinstance(item, dict):
            raise SyncProtocolError("Ответ сервера содержит некорректное подтверждение записи.")
        local_id = _coerce_local_id(item.get("local_id"))
        if local_id in by_local:
            raise SyncProtocolError(f"Сервер дважды подтвердил локальную запись {local_id}.")
        if local_id in expected:
            by_local[local_id] = item

    missing_ids = sorted(set(expected) - set(by_local))
    if missing_ids:
        raise SyncProtocolError(
            "Сервер не подтвердил локальные записи: "
            + ", ".join(str(value) for value in missing_ids)
        )

    unresolved_ids = []
    for local_id, obj in expected.items():
        item = by_local[local_id]
        status = str(item.get("status") or "").lower()
        if status in {"error", "failed", "invalid"}:
            detail = item.get("detail") or item.get("error") or status
            raise SyncProtocolError(f"Сервер отклонил запись {local_id}: {detail}")

        if status == "conflict":
            server_data = item.get("server")
            if not isinstance(server_data, dict):
                raise SyncProtocolError(
                    f"Сервер сообщил конфликт для записи {local_id} без серверных данных."
                )
            if not _handle_conflict(session, model, model_name, local_id, server_data):
                unresolved_ids.append(local_id)
            continue

        remote_id = item.get("remote_id") or item.get("id") or obj.remote_id
        if not remote_id:
            raise SyncProtocolError(
                f"Сервер не вернул remote_id для локальной записи {local_id}."
            )
        obj.remote_id = remote_id
        if model is User:
            obj.password = None
        obj.synced = True

    session.commit()
    return set(expected) - set(unresolved_ids), unresolved_ids


def _apply_deleted_records(
    session: Session,
    last_sync: datetime.datetime,
    sync_until=None,
    progress_cb=None,
    should_stop=None,
):
    processed = 0
    total_count = 0
    url = f"{BASE_URL}/deleted-records/"
    params = {
        "deleted_after": last_sync.isoformat(),
        "limit": SYNC_BATCH_SIZE,
    }
    if sync_until is not None:
        params["deleted_before"] = sync_until.isoformat()
    while True:
        _check_stop(should_stop)
        r = _request_with_auth("GET", url, params=params)
        if r.status_code != 200:
            raise RuntimeError(
                f"Ошибка загрузки удалений: HTTP {r.status_code}: {r.text}"
            )

        payload = r.json()
        items, has_next = _extract_response_items(payload)
        if isinstance(payload, dict):
            total_count = payload.get("count") or total_count
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
            if hasattr(local, "synced") and not bool(local.synced):
                _log_conflict(
                    item.get("model_name") or model.__name__.lower(),
                    local.id,
                    item,
                    serialize(local),
                )
                raise RuntimeError(
                    f"Конфликт удаления {item.get('model_name')} #{remote_id}: "
                    "локальная запись ещё не отправлена."
                )
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

        if isinstance(payload, dict):
            next_url = payload.get("next")
            if not next_url:
                break
            url = next_url
            params = None
        elif len(items) < SYNC_BATCH_SIZE:
            break
        else:
            params["offset"] = processed

    return True


def _build_upload_payload(session: Session, model, objects, client_id: str):
    payload = []
    for obj in objects:
        data = _prepare_outgoing_payload(session, model, serialize(obj))
        local_id = data.pop("id", None)
        data["local_id"] = local_id
        data["client_id"] = client_id
        if data.get("remote_id"):
            data["id"] = data["remote_id"]
        else:
            data.pop("remote_id", None)
            data.pop("id", None)
        payload.append(data)
    return payload


def _sync_models_to_server(
    session: Session,
    candidates_by_model=None,
    progress_cb=None,
    should_stop=None,
    client_id=None,
):
    client_id = client_id or get_sync_client_id(session)
    for model in UPLOAD_MODELS:
        _check_stop(should_stop)
        model_name = MODEL_NAMES[model]
        label = MODEL_LABELS.get(model_name, model_name)
        if candidates_by_model is None:
            candidates = session.query(model).filter_by(synced=False).all()
        else:
            candidates = [
                obj for obj in candidates_by_model.get(model, [])
                if not bool(getattr(obj, "synced", False))
            ]
        if hasattr(model, "created_by_guest"):
            candidates = [obj for obj in candidates if not getattr(obj, "created_by_guest", False)]
        ready = [obj for obj in candidates if _is_object_ready_for_sync(session, model, obj)]
        ready_ids = {id(obj) for obj in ready}
        blocked = [obj for obj in candidates if id(obj) not in ready_ids]

        if not ready:
            message = f"{label}: 0 / 0"
            if blocked:
                message = f"Ожидание зависимостей для {len(blocked)} записей"
            _emit_progress(progress_cb, "upload", model_name, 0, 0, message)
            if blocked:
                details = _format_blocked_dependencies(session, model, blocked)
                raise RuntimeError(f"{label}: не готовы зависимости. {details}")
            continue

        url = f"{BASE_URL}/{model_name}/post/"
        processed = 0
        total = len(ready)
        processed_ids = set()
        for chunk in _iter_upload_batches(session, model, ready):
            _check_stop(should_stop)
            response = _request_with_auth(
                "POST",
                url,
                json=_build_upload_payload(session, model, chunk, client_id),
            )
            if response.status_code != 200:
                details = response.text.strip() or "без описания"
                raise RuntimeError(
                    f"Ошибка отправки {label}: "
                    f"HTTP {response.status_code}: {details}"
                )

            try:
                acknowledged_ids, unresolved_ids = _apply_upload_results(
                    session, model, model_name, chunk, response.json()
                )
            except Exception as exc:
                session.rollback()
                raise RuntimeError(f"Ошибка подтверждения {label}: {exc}") from exc

            processed_ids.update(acknowledged_ids)
            processed += len(acknowledged_ids)
            _emit_progress(
                progress_cb,
                "upload",
                model_name,
                processed,
                total,
                f"{label}: {processed} / {total}",
            )
            if unresolved_ids:
                unresolved = ", ".join(str(value) for value in unresolved_ids)
                raise RuntimeError(f"Не разрешены конфликты {label}: {unresolved}")

        if model is Sheep:
            remaining = [obj for obj in ready if obj.id not in processed_ids]
            if remaining:
                _emit_progress(
                    progress_cb,
                    "upload",
                    model_name,
                    processed,
                    total,
                    f"Ожидание родителей для {len(remaining)} овец",
                )
                raise RuntimeError(
                    f"Для {len(remaining)} овец сначала нужно синхронизировать родителей."
                )
        if blocked:
            _emit_progress(
                progress_cb,
                "upload",
                model_name,
                processed,
                total + len(blocked),
                f"Ожидание зависимостей для {len(blocked)} записей",
            )
            details = _format_blocked_dependencies(session, model, blocked)
            raise RuntimeError(f"{label}: не готовы зависимости. {details}")
    return True


def sync_to_server(session: Session, progress_cb=None, should_stop=None, client_id=None):
    return _sync_models_to_server(
        session,
        progress_cb=progress_cb,
        should_stop=should_stop,
        client_id=client_id,
    )


def sync_owner_to_server(session: Session, owner_id: int, progress_cb=None, should_stop=None, client_id=None):
    return _sync_models_to_server(
        session,
        candidates_by_model=_get_owner_scope_objects(session, owner_id),
        progress_cb=progress_cb,
        should_stop=should_stop,
        client_id=client_id,
    )


def sync_from_server(session: Session, sync_until=None, progress_cb=None, should_stop=None):
    last_sync = get_last_sync_time()
    _apply_deleted_records(
        session,
        last_sync,
        sync_until=sync_until,
        progress_cb=progress_cb,
        should_stop=should_stop,
    )
    for model in DOWNLOAD_MODELS:
        _check_stop(should_stop)
        name = MODEL_NAMES[model]
        processed = 0
        total_count = 0
        pending_sheep_parents = []
        url = f"{BASE_URL}/{name}/"
        if model is Color:
            # Colors are a small reference table required before sheep FK mapping.
            # Always refresh the complete list so a stale watermark cannot omit it.
            params = {"full": "1"}
        else:
            params = {
                "updated_after": last_sync.isoformat(),
                "limit": SYNC_BATCH_SIZE,
            }
            if sync_until is not None:
                params["updated_before"] = sync_until.isoformat()
        while True:
            _check_stop(should_stop)
            r = _request_with_auth("GET", url, params=params)
            if r.status_code != 200:
                details = r.text.strip() or "без описания"
                raise RuntimeError(
                    f"Ошибка загрузки {MODEL_LABELS.get(name, name)}: "
                    f"HTTP {r.status_code}: {details}"
                )

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
                if local is None and model is User:
                    username = clean_item.get("username")
                    if username:
                        local = session.query(User).filter_by(username=username).first()
                if local:
                    if hasattr(local, "synced") and not bool(local.synced):
                        _log_conflict(name, local.id, item, serialize(local))
                        raise RuntimeError(
                            f"Конфликт {MODEL_LABELS.get(name, name)}: "
                            f"локальная запись {local.id} ещё не отправлена, "
                            "поэтому данные сервера не применены"
                        )
                    for k, v in clean_item.items():
                        if k == "id":
                            continue
                        setattr(local, k, v)
                    if model is User and not getattr(local, "remote_id", None):
                        local.remote_id = remote_id
                else:
                    try:
                        clean_item.pop("id", None)
                        new = model(**clean_item)
                        session.add(new)
                    except Exception as e:
                        session.rollback()
                        raise RuntimeError(
                            f"Ошибка сохранения {MODEL_LABELS.get(name, name)} "
                            f"(серверный ID {remote_id}): {e}"
                        ) from e
                if model is Sheep and "parent" in item:
                    pending_sheep_parents.append((remote_id, item))
            session.commit()

            if model is Sheep and pending_sheep_parents:
                unresolved_parents = []
                for remote_id, item in pending_sheep_parents:
                    local_sheep = session.query(Sheep).filter_by(remote_id=remote_id).first()
                    if local_sheep is None:
                        continue
                    parent_ids = _extract_sheep_parent_ids(session, item)
                    if parent_ids is None:
                        unresolved_parents.append((remote_id, item))
                        continue
                    local_sheep.parents = session.query(Sheep).filter(Sheep.id.in_(parent_ids)).all() if parent_ids else []
                session.commit()
                pending_sheep_parents = unresolved_parents
            processed += len(items)
            _emit_progress(
                progress_cb,
                "download",
                name,
                processed,
                total_count or processed,
                f"{MODEL_LABELS.get(name, name)}: {processed} / {total_count or processed}",
            )

            if isinstance(payload, dict):
                next_url = payload.get("next")
                if not next_url:
                    break
                url = next_url
                params = None
            elif len(items) < SYNC_BATCH_SIZE:
                break
            else:
                params["offset"] = processed
        if model is Sheep and pending_sheep_parents:
            _emit_progress(
                progress_cb,
                "download",
                name,
                processed,
                total_count or processed,
                f"Догружаются родители для {len(pending_sheep_parents)} овец",
            )
            _load_missing_sheep_parents(
                session,
                pending_sheep_parents,
                progress_cb=progress_cb,
                should_stop=should_stop,
            )
    return True

def _run_sync_workflow(owner_id=None, progress_cb=None, should_stop=None):
    session = init_db()
    try:
        sync_until = get_server_sync_cursor()
        client_id = get_sync_client_id(session)
        _emit_progress(progress_cb, "download", "", 0, 0, "Загрузка справочников...")
        sync_reference_data(session, progress_cb=progress_cb, should_stop=should_stop)
        upload_message = (
            "Отправка локальных данных..."
            if owner_id is None else "Отправка данных хозяйства..."
        )
        _emit_progress(progress_cb, "upload", "", 0, 0, upload_message)
        upload_kwargs = {
            "progress_cb": progress_cb,
            "should_stop": should_stop,
            "client_id": client_id,
        }
        if owner_id is None:
            sync_to_server(session, **upload_kwargs)
        else:
            sync_owner_to_server(session, owner_id, **upload_kwargs)

        _check_stop(should_stop)
        download_message = (
            "Загрузка данных с сервера..."
            if owner_id is None else "Загрузка обновлений с сервера..."
        )
        _emit_progress(progress_cb, "download", "", 0, 0, download_message)
        sync_from_server(
            session,
            sync_until=sync_until,
            progress_cb=progress_cb,
            should_stop=should_stop,
        )
        update_last_sync_time(sync_until)
        return True
    finally:
        session.close()


def run_sync(progress_cb=None, should_stop=None):
    return _run_sync_workflow(progress_cb=progress_cb, should_stop=should_stop)


def run_owner_sync(owner_id: int, progress_cb=None, should_stop=None):
    return _run_sync_workflow(
        owner_id=owner_id,
        progress_cb=progress_cb,
        should_stop=should_stop,
    )

if __name__ == "__main__":
    run_sync()
