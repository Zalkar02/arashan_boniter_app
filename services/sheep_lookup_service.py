def get_owner_by_id(session, user_model, owner_id: int):
    return session.query(user_model).filter_by(id=owner_id, is_deleted=False).first()


def get_all_owners(session, user_model):
    return session.query(user_model).filter_by(is_deleted=False).order_by(user_model.name).all()


def get_all_colors(session, color_model):
    return session.query(color_model).order_by(color_model.name).all()


def get_all_sheep(session, sheep_model):
    return session.query(sheep_model).filter_by(is_deleted=False).order_by(sheep_model.id.desc()).all()


def get_sheep_by_idn(session, sheep_model, idn: str):
    return session.query(sheep_model).filter_by(id_n=idn, is_deleted=False).first()


def get_current_owner_for_sheep(session, owner_model, sheep_id: int):
    return (
        session.query(owner_model)
        .filter_by(sheep_id=sheep_id)
        .order_by(owner_model.owner_bool.desc(), owner_model.date1.desc().nullslast(), owner_model.id.desc())
        .first()
    )


def get_latest_application_for_sheep(session, application_model, sheep_id: int):
    return (
        session.query(application_model)
        .filter_by(sheep_id=sheep_id)
        .order_by(application_model.date.desc().nullslast(), application_model.id.desc())
        .first()
    )
