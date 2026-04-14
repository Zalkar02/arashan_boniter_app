from sqlalchemy import func, or_


def get_owner_rows(
    session,
    user_model,
    sheep_model,
    owner_model,
    query_text: str = "",
    region: str = "",
    offset: int = 0,
    limit: int = 50,
):
    query_text = (query_text or "").strip()
    region = (region or "").strip()

    owner_link_counts = (
        session.query(
            owner_model.owner_id.label("owner_id"),
            func.count(func.distinct(owner_model.sheep_id)).label("sheep_count"),
        )
        .join(sheep_model, sheep_model.id == owner_model.sheep_id)
        .filter(sheep_model.is_deleted == False)
        .group_by(owner_model.owner_id)
        .subquery()
    )

    query = (
        session.query(
            user_model,
            func.coalesce(owner_link_counts.c.sheep_count, 0).label("sheep_count"),
        )
        .outerjoin(owner_link_counts, owner_link_counts.c.owner_id == user_model.id)
        .filter(user_model.is_deleted == False)
    )

    if region:
        query = query.filter(user_model.region == region)

    if query_text:
        like = f"%{query_text}%"
        has_non_ascii = any(ord(ch) > 127 for ch in query_text)
        name_filter = (
            user_model.name_norm.like(f"%{query_text.casefold()}%")
            if has_non_ascii
            else user_model.name.ilike(like)
        )
        query = query.filter(
            or_(
                name_filter,
                user_model.username.ilike(like),
                user_model.phone.ilike(like),
                user_model.region.ilike(like),
                user_model.area.ilike(like),
                user_model.city.ilike(like),
                user_model.home.ilike(like),
            )
        )

    total = query.count()
    rows = (
        query
        .order_by(user_model.name.asc(), user_model.id.desc())
        .offset(max(0, int(offset)))
        .limit(max(1, int(limit)))
        .all()
    )
    return [{"user": user, "sheep_count": int(sheep_count or 0)} for user, sheep_count in rows], total


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
    offset: int = 0,
    limit: int = 50,
):
    query_text = (query_text or "").strip()
    query = (
        session.query(sheep_model, user_model.name.label("owner_name"), color_model.name.label("color_name"))
        .outerjoin(user_model, sheep_model.owner_id == user_model.id)
        .outerjoin(color_model, sheep_model.color_id == color_model.id)
        .filter(sheep_model.is_deleted == False)
    )

    if gender:
        query = query.filter(sheep_model.gender == gender)
    if paid == "paid":
        query = query.filter(sheep_model.is_paid == True)
    elif paid == "unpaid":
        query = query.filter(sheep_model.is_paid == False)
    if synced == "synced":
        query = query.filter(sheep_model.synced == True)
    elif synced == "unsynced":
        query = query.filter(sheep_model.synced == False)

    if query_text:
        has_non_ascii = any(ord(ch) > 127 for ch in query_text)
        like = f"%{query_text}%"
        if has_non_ascii:
            norm = query_text.casefold()
            query = query.filter(
                or_(
                    sheep_model.id_n.ilike(like),
                    sheep_model.nick_norm.like(f"%{norm}%"),
                )
            )
        else:
            query = query.filter(
                or_(
                    sheep_model.id_n.ilike(like),
                    sheep_model.nick.ilike(like),
                    user_model.name.ilike(like),
                    color_model.name.ilike(like),
                )
            )

    total = query.count()
    rows = (
        query.order_by(sheep_model.id.desc())
        .offset(max(0, int(offset)))
        .limit(max(1, int(limit)))
        .all()
    )
    return [
        {
            "sheep": sheep,
            "owner_name": str(owner_name or ""),
            "color_name": str(color_name or ""),
        }
        for sheep, owner_name, color_name in rows
    ], total
