from sqlalchemy import func, or_


def get_owner_rows(session, user_model, sheep_model, owner_model, query_text: str = "", region: str = ""):
    rows = (
        session.query(
            user_model,
            func.count(func.distinct(sheep_model.id)).label("sheep_count"),
        )
        .outerjoin(owner_model, owner_model.owner_id == user_model.id)
        .outerjoin(sheep_model, sheep_model.id == owner_model.sheep_id)
        .filter(user_model.is_deleted == False)
        .group_by(user_model.id)
        .order_by(user_model.name.asc(), user_model.id.desc())
        .all()
    )

    query_text = (query_text or "").strip().casefold()
    region = (region or "").strip()
    result = []
    for user, sheep_count in rows:
        if region and (user.region or "") != region:
            continue
        haystack = " ".join(
            [
                str(user.name or ""),
                str(user.username or ""),
                str(user.phone or ""),
                str(user.region or ""),
                str(user.area or ""),
                str(user.city or ""),
                str(user.home or ""),
            ]
        ).casefold()
        if query_text and query_text not in haystack:
            continue
        result.append(
            {
                "user": user,
                "sheep_count": int(sheep_count or 0),
            }
        )
    return result


def get_owner_regions(session, user_model):
    values = (
        session.query(user_model.region)
        .filter(user_model.is_deleted == False, user_model.region.isnot(None), user_model.region != "")
        .distinct()
        .order_by(user_model.region.asc())
        .all()
    )
    return [value[0] for value in values if value[0]]


def get_sheep_rows(
    session,
    sheep_model,
    user_model,
    color_model,
    query_text: str = "",
    gender: str = "",
    paid: str = "",
    synced: str = "",
):
    rows = (
        session.query(sheep_model)
        .outerjoin(user_model, sheep_model.owner_id == user_model.id)
        .outerjoin(color_model, sheep_model.color_id == color_model.id)
        .filter(sheep_model.is_deleted == False)
        .order_by(sheep_model.id.desc())
        .all()
    )

    query_text = (query_text or "").strip().casefold()
    result = []
    for sheep in rows:
        if gender and (sheep.gender or "") != gender:
            continue
        if paid == "paid" and not bool(getattr(sheep, "is_paid", False)):
            continue
        if paid == "unpaid" and bool(getattr(sheep, "is_paid", False)):
            continue
        if synced == "synced" and not bool(getattr(sheep, "synced", False)):
            continue
        if synced == "unsynced" and bool(getattr(sheep, "synced", False)):
            continue

        owner = getattr(sheep, "owner", None)
        color = getattr(getattr(sheep, "color", None), "name", "") or ""
        haystack = " ".join(
            [
                str(sheep.id_n or ""),
                str(sheep.nick or ""),
                str(owner.name if owner else ""),
                str(color),
            ]
        ).casefold()
        if query_text and query_text not in haystack:
            continue

        result.append(
            {
                "sheep": sheep,
                "owner_name": str(owner.name or "") if owner else "",
                "color_name": color,
            }
        )
    return result
