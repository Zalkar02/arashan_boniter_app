import datetime
from services.owner_search_service import _norm, _digits, _display_region, _display_area


RECENT_DAYS = 30
SQLITE_SAFE_IN_LIMIT = 900


def _chunked(values, size=SQLITE_SAFE_IN_LIMIT):
    values = list(values or [])
    if not values:
        return []
    return [values[index:index + size] for index in range(0, len(values), size)]


def _load_current_owner_map(session, owner_model, sheep_ids=None):
    current_owner_map = {}
    chunks = _chunked(sheep_ids)
    if not chunks:
        return _build_current_owner_map(session, owner_model, sheep_ids=None)

    for sheep_id_chunk in chunks:
        current_owner_map.update(
            _build_current_owner_map(session, owner_model, sheep_ids=sheep_id_chunk)
        )
    return current_owner_map


def _load_rows_by_ids(session, model, id_attr, ids, *filters):
    rows = []
    for id_chunk in _chunked(ids):
        query = session.query(model).filter(id_attr.in_(id_chunk))
        for filter_clause in filters:
            query = query.filter(filter_clause)
        rows.extend(query.all())
    return rows


def _build_current_owner_map(session, owner_model, sheep_ids=None):
    current_owner_map = {}
    query = session.query(owner_model)
    if sheep_ids:
        query = query.filter(owner_model.sheep_id.in_(sheep_ids))
    owner_rows = query.order_by(
        owner_model.owner_bool.desc(),
        owner_model.date1.desc().nullslast(),
        owner_model.id.desc(),
    ).all()
    for owner_row in owner_rows:
        sheep_id = getattr(owner_row, "sheep_id", None)
        owner = getattr(owner_row, "owner", None)
        if sheep_id is None or owner is None or sheep_id in current_owner_map or bool(getattr(owner, "is_deleted", False)):
            continue
        current_owner_map[sheep_id] = owner
    return current_owner_map


def _resolve_sheep_owner(sheep, current_owner_map):
    owner = getattr(sheep, "owner", None)
    if owner is not None:
        return owner
    return current_owner_map.get(getattr(sheep, "id", None))


def build_owner_history_summary(session, application_model, sheep_model, owner_model, user_model):
    """Сводка по всем хозяйствам. Только колоночные запросы, без ORM-объектов."""
    recent_since = datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)

    users = {}
    for uid, name, phone, city, area, region, is_deleted in session.query(
        user_model.id, user_model.name, user_model.phone, user_model.city,
        user_model.area, user_model.region, user_model.is_deleted,
    ).all():
        users[uid] = (name, phone, city, area, region, bool(is_deleted))

    sheep_rows = session.query(
        sheep_model.id, sheep_model.owner_id, sheep_model.date_filling,
    ).filter(sheep_model.is_deleted.is_(False)).all()

    current_owner = {}
    owner_rows = session.query(
        owner_model.sheep_id, owner_model.owner_id,
    ).order_by(
        owner_model.owner_bool.desc(),
        owner_model.date1.desc().nullslast(),
        owner_model.id.desc(),
    ).all()
    for sheep_id, uid in owner_rows:
        if sheep_id is None or sheep_id in current_owner:
            continue
        user = users.get(uid)
        if user is None or user[5]:
            continue
        current_owner[sheep_id] = uid

    latest_app = {}
    for sheep_id, app_date, app_id, is_paid in session.query(
        application_model.sheep_id, application_model.date,
        application_model.id, application_model.is_paid,
    ).filter(application_model.is_deleted.is_(False)).all():
        if sheep_id is None:
            continue
        key = (app_date or datetime.date.min, app_id or 0)
        prev = latest_app.get(sheep_id)
        if prev is None or key > prev[0]:
            latest_app[sheep_id] = (key, app_date, bool(is_paid))

    buckets = {}
    for sheep_id, direct_owner_id, sheep_date in sheep_rows:
        if direct_owner_id is not None and direct_owner_id in users:
            owner_id = direct_owner_id
        else:
            owner_id = current_owner.get(sheep_id)
        if owner_id is None or users[owner_id][5]:
            continue

        latest = latest_app.get(sheep_id)
        app_date = latest[1] if latest else None
        activity = sheep_date
        if app_date and (sheep_date is None or app_date > sheep_date):
            activity = app_date

        bucket = buckets.get(owner_id)
        if bucket is None:
            name, phone, city, area, region, _ = users[owner_id]
            name = str(name or "")
            phone = str(phone or "")
            city = str(city or "")
            area = str(area or "")
            region = str(region or "")
            bucket = buckets[owner_id] = {
                "owner_id": owner_id,
                "name": name,
                "phone": phone,
                "location": city or area or region,
                "total_sheep": 0,
                "sheep_with_applications": 0,
                "sheep_without_applications": 0,
                "recent_sheep": 0,
                "unpaid_sheep": 0,
                "latest_activity": None,
                "search_text": _norm(" ".join([
                    name, phone, city, area, region,
                    _display_region(region), _display_area(area),
                ])),
                "search_digits": _digits(phone),
            }

        bucket["total_sheep"] += 1
        if latest is not None:
            bucket["sheep_with_applications"] += 1
            if not latest[2]:
                bucket["unpaid_sheep"] += 1
        else:
            bucket["sheep_without_applications"] += 1
        if activity and activity >= recent_since:
            bucket["recent_sheep"] += 1
        if activity and (bucket["latest_activity"] is None or activity > bucket["latest_activity"]):
            bucket["latest_activity"] = activity

    return sorted(
        buckets.values(),
        key=lambda row: (row["latest_activity"] or datetime.date.min, row["owner_id"] or 0),
        reverse=True,
    )


def filter_owner_history(rows, raw_query: str):
    query = (raw_query or "").strip()
    if not query:
        return list(rows)
    words = _norm(query).split()
    query_digits = _digits(query)
    use_digits = len(query_digits) >= 3
    result = []
    for row in rows:
        text = row["search_text"]
        if words and all(word in text for word in words):
            result.append(row)
        elif use_digits and query_digits in row["search_digits"]:
            result.append(row)
    return result


def get_owner_history_rows(session, application_model, sheep_model, owner_model, raw_query: str, user_model=None):
    if user_model is None:
        user_model = owner_model.owner.property.mapper.class_
    rows = build_owner_history_summary(session, application_model, sheep_model, owner_model, user_model)
    return filter_owner_history(rows, raw_query)


def format_owner_history_row(row: dict):
    return [
        row["name"],
        row["phone"],
        row["location"],
        str(row["total_sheep"]),
        str(row["sheep_with_applications"]),
        str(row["sheep_without_applications"]),
        str(row["recent_sheep"]),
        str(row["unpaid_sheep"]),
    ]


def get_owner_detail_rows(session, user_model, sheep_model, application_model, owner_model, owner_id: int):
    owner = session.query(user_model).filter_by(id=owner_id, is_deleted=False).first()
    if owner is None:
        return None

    direct_sheep = session.query(sheep_model).filter_by(owner_id=owner_id, is_deleted=False).all()
    linked_sheep_ids = {
        sheep_id
        for (sheep_id,) in session.query(owner_model.sheep_id).filter(owner_model.owner_id == owner_id).all()
        if sheep_id is not None
    }

    sheep_rows = list(direct_sheep)
    direct_ids = {row.id for row in direct_sheep}
    missing_linked_ids = [sheep_id for sheep_id in linked_sheep_ids if sheep_id not in direct_ids]
    if missing_linked_ids:
        sheep_rows.extend(
            _load_rows_by_ids(
                session,
                sheep_model,
                sheep_model.id,
                missing_linked_ids,
                sheep_model.is_deleted.is_(False),
            )
        )

    sheep_rows.sort(
        key=lambda sheep: (
            getattr(sheep, "date_filling", None) or datetime.date.min,
            getattr(sheep, "id", 0) or 0,
        ),
        reverse=True,
    )

    sheep_ids = [sheep.id for sheep in sheep_rows]
    current_owner_map = _load_current_owner_map(session, owner_model, sheep_ids=sheep_ids)
    applications = _load_rows_by_ids(
        session,
        application_model,
        application_model.sheep_id,
        sheep_ids,
        application_model.is_deleted.is_(False),
    )

    app_by_sheep_id = {}
    for application in applications:
        if application.sheep_id is None:
            continue
        app_by_sheep_id.setdefault(application.sheep_id, []).append(application)

    rows = []
    for sheep in sheep_rows:
        sheep_owner = _resolve_sheep_owner(sheep, current_owner_map)
        if getattr(sheep_owner, "id", None) != owner_id:
            continue
        owner_apps = app_by_sheep_id.get(sheep.id, [])
        has_applications = bool(owner_apps)
        latest_application = _get_latest_application(owner_apps)
        sheep_synced = bool(getattr(sheep, "synced", False))
        apps_synced = all(bool(getattr(app, "synced", False)) for app in owner_apps) if owner_apps else True
        row_synced = sheep_synced and apps_synced
        sheep_paid = bool(getattr(sheep, "is_paid", False))
        latest_paid = bool(getattr(latest_application, "is_paid", False)) if latest_application else False
        fully_paid = sheep_paid and (latest_application is None or latest_paid)
        has_unpaid_application = latest_application is not None and not latest_paid
        record_type = _get_record_type(sheep, latest_application)
        activity_date = _get_row_activity_date(sheep, latest_application)
        display_date = _get_row_display_date(sheep, latest_application)

        rows.append(
            {
                "sheep": sheep,
                "applications": owner_apps,
                "latest_application": latest_application,
                "activity_date": activity_date,
                "display_date": display_date,
                "has_applications": has_applications,
                "record_type": record_type,
                "sync_status": "Синхронизировано" if row_synced else "Не синхронизировано",
                "is_synced": row_synced,
                "payment_status": _get_payment_status(sheep_paid, has_unpaid_application),
                "passport_status": "Доступен" if fully_paid else "Недоступен",
                "can_pay": row_synced and (not sheep_paid or has_unpaid_application),
                "can_print": fully_paid,
                "is_unpaid": not fully_paid,
            }
        )

    return {
        "owner": owner,
        "owner_name": str(getattr(owner, "name", "") or ""),
        "phone": str(getattr(owner, "phone", "") or ""),
        "location": (
            str(getattr(owner, "city", "") or "")
            or str(getattr(owner, "area", "") or "")
            or str(getattr(owner, "region", "") or "")
        ),
        "rows": rows,
    }


def format_owner_sheep_row(row: dict):
    sheep = row["sheep"]
    gender = "Баран" if str(getattr(sheep, "gender", "") or "") == "B" else "Овца"
    dob = getattr(sheep, "dob", None)
    age = ""
    if dob:
        today = datetime.date.today()
        years = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            years -= 1
        age = f"{max(0, years)} г."
    return [
        row["record_type"],
        str(getattr(sheep, "id_n", "") or ""),
        str(getattr(sheep, "nick", "") or ""),
        gender,
        age,
        row["display_date"].strftime("%d.%m.%Y") if row.get("display_date") else "",
        "Да" if row["has_applications"] else "Нет",
        row["sync_status"],
        row["payment_status"],
        row["passport_status"],
    ]


def _get_latest_application(applications):
    if not applications:
        return None
    return max(
        applications,
        key=lambda app: (
            getattr(app, "date", None) or datetime.date.min,
            getattr(app, "id", 0) or 0,
        ),
    )


def _get_record_type(sheep, latest_application):
    if latest_application is None:
        return "Овца"
    sheep_date = getattr(sheep, "date_filling", None)
    app_date = getattr(latest_application, "date", None)
    if sheep_date and app_date and sheep_date == app_date:
        return "Овца + бон."
    if latest_application is not None:
        return "Бонитр."
    return "Овца"


def _get_row_display_date(sheep, latest_application):
    if latest_application is not None:
        return getattr(latest_application, "date", None) or getattr(sheep, "date_filling", None)
    return getattr(sheep, "date_filling", None)


def _get_row_activity_date(sheep, latest_application):
    sheep_date = getattr(sheep, "date_filling", None)
    app_date = getattr(latest_application, "date", None) if latest_application is not None else None
    if app_date and (sheep_date is None or app_date > sheep_date):
        return app_date
    return sheep_date


def _get_payment_status(sheep_paid: bool, has_unpaid_application: bool):
    if sheep_paid and not has_unpaid_application:
        return "Оплачено"
    if sheep_paid and has_unpaid_application:
        return "Не оплачено (повторка)"
    return "Не оплачено"
