import datetime

from db.models import Application, Lamb, Owner, Sheep
from services.owner_search_service import _norm


def _prepare_deleted_sheep_for_reuse(session, sheep, owner_id, date_filling):
    sheep.is_deleted = False
    sheep.synced = False
    sheep.updated_at = datetime.datetime.utcnow()
    sheep.is_paid = False
    sheep.is_printed = False
    sheep.payment_reference = None
    sheep.payment_token = None
    sheep.owner_id = owner_id
    sheep.parents = []

    old_applications = session.query(Application).filter_by(sheep_id=sheep.id).all()
    for application in old_applications:
        application.is_deleted = True
        application.synced = False
        application.updated_at = datetime.datetime.utcnow()
        application.is_paid = False
        application.is_printed = False
        application.payment_reference = None
        application.payment_token = None

    old_owner_links = session.query(Owner).filter_by(sheep_id=sheep.id).all()
    for link in old_owner_links:
        link.is_deleted = True
        link.owner_bool = False
        link.synced = False
        link.updated_at = datetime.datetime.utcnow()
        if not getattr(link, "date2", None):
            link.date2 = date_filling or datetime.date.today()

    lamb = session.query(Lamb).filter_by(sheep_id=sheep.id).first()
    if lamb is not None:
        lamb.is_deleted = True
        lamb.synced = False
        lamb.updated_at = datetime.datetime.utcnow()


def save_sheep_bundle(session, payload: dict):
    owner_id = int(payload["owner_id"])
    existing_sheep_id = payload.get("existing_sheep_id")
    editing_application_id = payload.get("editing_application_id")
    idn = payload["idn"]
    date_filling = payload["date_filling"]

    sheep = None
    reused_deleted_sheep = False
    if existing_sheep_id is not None:
        sheep = session.query(Sheep).filter_by(id=existing_sheep_id).first()
    elif idn:
        deleted_sheep = session.query(Sheep).filter_by(id_n=idn, is_deleted=True).first()
        if deleted_sheep is not None:
            sheep = deleted_sheep
            _prepare_deleted_sheep_for_reuse(session, sheep, owner_id, date_filling)
            reused_deleted_sheep = True
    previous_owner_id = None if reused_deleted_sheep else (getattr(sheep, "owner_id", None) if sheep is not None else None)

    sheep_fields = {
        "created_by_user_id": payload.get("created_by_user_id"),
        "id_n": idn,
        "nick": payload.get("nick"),
        "nick_norm": _norm(payload.get("nick") or ""),
        "dob": payload["dob"],
        "gender": payload["gender"],
        "color_id": payload["color_id"],
        "comment": payload.get("comment"),
        "owner_id": owner_id,
        "price": payload.get("price"),
        "currency": payload.get("currency", "K"),
        "is_negotiable_price": payload.get("is_negotiable_price", False),
        "sell": payload.get("sell", False),
        "out": payload.get("out", False),
        "hide": payload.get("hide", False),
        "created_by_guest": payload.get("created_by_guest", False),
        "date_filling": date_filling,
    }

    created = sheep is None
    if created:
        sheep = Sheep(**sheep_fields)
        session.add(sheep)
        session.flush()
    else:
        for field_name, value in sheep_fields.items():
            setattr(sheep, field_name, value)
        sheep.updated_at = datetime.datetime.utcnow()
        sheep.synced = False

    if created or reused_deleted_sheep:
        owner_link = Owner(
            sheep_id=sheep.id,
            owner_id=owner_id,
            owner_bool=True,
            date1=date_filling,
            date2=date_filling,
        )
        session.add(owner_link)
    elif previous_owner_id != owner_id:
        change_date = date_filling or datetime.date.today()
        active_links = (
            session.query(Owner)
            .filter_by(sheep_id=sheep.id, owner_bool=True)
            .all()
        )
        for link in active_links:
            link.owner_bool = False
            link.date2 = change_date
            link.updated_at = datetime.datetime.utcnow()
            link.synced = False
        new_link = Owner(
            sheep_id=sheep.id,
            owner_id=owner_id,
            owner_bool=True,
            date1=change_date,
            date2=change_date,
        )
        new_link.synced = False
        session.add(new_link)

    for relative_idn in payload.get("parent_idns", ()):
        if not relative_idn or relative_idn == idn:
            continue
        parent = session.query(Sheep).filter_by(id_n=relative_idn).first()
        if parent and parent.id != sheep.id and parent not in sheep.parents:
            sheep.parents.append(parent)

    application_data = payload.get("application")
    if application_data:
        application = None
        if editing_application_id:
            application = session.query(Application).filter_by(id=editing_application_id, sheep_id=sheep.id).first()
        if application is None:
            application = Application(sheep_id=sheep.id, **application_data)
            session.add(application)
        else:
            for field_name, value in application_data.items():
                setattr(application, field_name, value)
            application.updated_at = datetime.datetime.utcnow()
            application.synced = False

    lamb_data = payload.get("lamb")
    if lamb_data is not None:
        lamb = session.query(Lamb).filter_by(sheep_id=sheep.id).first()
        if lamb is None:
            lamb = Lamb(sheep_id=sheep.id, **lamb_data)
            session.add(lamb)
        else:
            for field_name, value in lamb_data.items():
                setattr(lamb, field_name, value)
            lamb.updated_at = datetime.datetime.utcnow()
            lamb.synced = False

    session.commit()
    return sheep, created


def soft_delete_sheep_record(session, row: dict, current_user_id):
    sheep = row["sheep"]
    latest_application = row.get("latest_application")
    record_type = row.get("record_type")

    if record_type == "Бонитр." and latest_application is not None:
        if getattr(latest_application, "created_by_user_id", None) != current_user_id:
            raise RuntimeError("Удалять можно только свои бонитировки.")
        latest_application.is_deleted = True
        latest_application.updated_at = datetime.datetime.utcnow()
        latest_application.synced = False
        session.commit()
        return "Бонитировка удалена"

    if getattr(sheep, "created_by_user_id", None) != current_user_id:
        raise RuntimeError("Удалять можно только своих овец.")

    sheep.is_deleted = True
    sheep.updated_at = datetime.datetime.utcnow()
    sheep.synced = False
    for application in row.get("applications", []):
        application.is_deleted = True
        application.updated_at = datetime.datetime.utcnow()
        application.synced = False
    session.commit()
    return "Овца удалена"
