import datetime
from sqlalchemy import case, func, or_
from services.owner_search_service import _norm


RECENT_DAYS = 30


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


def get_owner_history_rows(session, application_model, sheep_model, owner_model, raw_query: str):
    query = (raw_query or "").strip()
    query_norm = _norm(query) if query else ""
    recent_since = datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)
    sheep_query = session.query(sheep_model).filter_by(is_deleted=False)
    if query:
        like = f"%{query}%"
        sheep_query = sheep_query.filter(
            or_(
                sheep_model.id_n.ilike(like),
                sheep_model.nick.ilike(like),
            )
        )
    sheep_rows = sheep_query.order_by(sheep_model.date_filling.desc().nullslast(), sheep_model.id.desc()).all()
    sheep_ids = [sheep.id for sheep in sheep_rows]
    current_owner_map = _build_current_owner_map(session, owner_model, sheep_ids=sheep_ids)
    application_stats = (
        session.query(
            application_model.sheep_id.label("sheep_id"),
            func.count(application_model.id).label("applications_count"),
            func.max(application_model.date).label("latest_date"),
            func.max(case((application_model.is_paid.is_(False), 1), else_=0)).label("has_unpaid"),
        )
        .filter_by(is_deleted=False)
        .filter(application_model.sheep_id.isnot(None))
        .group_by(application_model.sheep_id)
        .all()
    )
    app_stats_by_sheep_id = {row.sheep_id: row for row in application_stats}

    owners = {}
    for sheep in sheep_rows:
        owner = _resolve_sheep_owner(sheep, current_owner_map)
        if owner is None:
            continue

        owner_id = getattr(owner, "id", None)
        if owner_id is None or bool(getattr(owner, "is_deleted", False)):
            continue

        app_stats = app_stats_by_sheep_id.get(sheep.id)
        bucket = owners.setdefault(
            owner_id,
            {
                "owner": owner,
                "total_sheep": 0,
                "sheep_with_applications": 0,
                "sheep_without_applications": 0,
                "recent_sheep": 0,
                "unpaid_sheep": 0,
                "latest_activity": None,
            },
        )

        bucket["total_sheep"] += 1
        if app_stats and app_stats.applications_count:
            bucket["sheep_with_applications"] += 1
        else:
            bucket["sheep_without_applications"] += 1

        if sheep.date_filling and sheep.date_filling >= recent_since:
            bucket["recent_sheep"] += 1

        if app_stats and app_stats.has_unpaid:
            bucket["unpaid_sheep"] += 1

        latest_activity = bucket["latest_activity"]
        sheep_activity = sheep.date_filling
        if sheep_activity and (latest_activity is None or sheep_activity > latest_activity):
            bucket["latest_activity"] = sheep_activity

        app_activity = getattr(app_stats, "latest_date", None)
        latest_activity = bucket["latest_activity"]
        if app_activity and (latest_activity is None or app_activity > latest_activity):
            bucket["latest_activity"] = app_activity

    filtered = []
    for bucket in owners.values():
        owner = bucket["owner"]
        haystack = " ".join(
            [
                str(getattr(owner, "name", "") or ""),
                str(getattr(owner, "phone", "") or ""),
                str(getattr(owner, "city", "") or ""),
                str(getattr(owner, "area", "") or ""),
                str(getattr(owner, "region", "") or ""),
            ]
        )
        haystack_norm = _norm(haystack)
        if query and query_norm not in haystack_norm:
            continue
        filtered.append(bucket)

    filtered.sort(
        key=lambda row: (
            row["latest_activity"] or datetime.date.min,
            row["owner"].id or 0,
        ),
        reverse=True,
    )
    return filtered


def format_owner_history_row(row: dict):
    owner = row["owner"]
    location = (
        str(getattr(owner, "city", "") or "")
        or str(getattr(owner, "area", "") or "")
        or str(getattr(owner, "region", "") or "")
    )
    return [
        str(getattr(owner, "name", "") or ""),
        str(getattr(owner, "phone", "") or ""),
        location,
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
            session.query(sheep_model)
            .filter(sheep_model.is_deleted.is_(False), sheep_model.id.in_(missing_linked_ids))
            .all()
        )

    sheep_rows.sort(
        key=lambda sheep: (
            getattr(sheep, "date_filling", None) or datetime.date.min,
            getattr(sheep, "id", 0) or 0,
        ),
        reverse=True,
    )

    sheep_ids = [sheep.id for sheep in sheep_rows]
    current_owner_map = _build_current_owner_map(session, owner_model, sheep_ids=sheep_ids)
    applications = (
        session.query(application_model)
        .filter(application_model.is_deleted.is_(False), application_model.sheep_id.in_(sheep_ids))
        .all()
        if sheep_ids else []
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
        sheep_paid = bool(getattr(sheep, "is_paid", False))
        record_type = _get_record_type(sheep, latest_application)

        rows.append(
            {
                "sheep": sheep,
                "applications": owner_apps,
                "latest_application": latest_application,
                "has_applications": has_applications,
                "record_type": record_type,
                "sync_status": "Синхронизировано" if sheep_synced else "Не синхронизировано",
                "payment_status": _get_payment_status(sheep_paid),
                "passport_status": "Доступен" if sheep_paid else "Недоступен",
                "can_pay": sheep_synced and not sheep_paid,
                "can_print": sheep_paid,
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
    return [
        row["record_type"],
        str(getattr(sheep, "id_n", "") or ""),
        str(getattr(sheep, "nick", "") or ""),
        sheep.date_filling.strftime("%d.%m.%Y") if getattr(sheep, "date_filling", None) else "",
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


def _get_payment_status(sheep_paid: bool):
    if sheep_paid:
        return "Оплачено"
    return "Не оплачено"
