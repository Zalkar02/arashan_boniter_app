import datetime

from db.models import User


def owner_exists_by_username(session, username: str) -> bool:
    return session.query(User).filter_by(username=username).first() is not None


def create_owner(session, payload: dict):
    owner = User(
        created_by_user_id=payload.get("created_by_user_id"),
        username=payload["username"],
        password=payload["password"],
        name=payload["name"],
        phone=payload.get("phone"),
        region=payload.get("region"),
        area=payload.get("area"),
        city=payload.get("city"),
        home=payload.get("home"),
    )
    session.add(owner)
    session.commit()
    return owner


def update_owner(session, owner, payload: dict):
    owner.username = payload["username"]
    owner.password = payload["password"]
    owner.name = payload["name"]
    owner.phone = payload.get("phone")
    owner.region = payload.get("region")
    owner.area = payload.get("area")
    owner.city = payload.get("city")
    owner.home = payload.get("home")
    owner.updated_at = datetime.datetime.utcnow()
    owner.synced = False
    session.commit()
    return owner


def soft_delete_owner(session, owner, current_user_id):
    if owner is None:
        raise RuntimeError("Владелец не найден.")
    if getattr(owner, "created_by_user_id", None) != current_user_id:
        raise RuntimeError("Удалять можно только своих владельцев.")
    owner.is_deleted = True
    owner.updated_at = datetime.datetime.utcnow()
    owner.synced = False
    session.commit()
