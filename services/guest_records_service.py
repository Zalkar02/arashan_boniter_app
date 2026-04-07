from db.models import Application, Sheep


def claim_guest_records(session):
    sheep_rows = session.query(Sheep).filter_by(created_by_guest=True).all()
    application_rows = session.query(Application).filter_by(created_by_guest=True).all()

    for sheep in sheep_rows:
        sheep.created_by_guest = False
        sheep.synced = False

    for application in application_rows:
        application.created_by_guest = False
        application.synced = False

    session.commit()
    return {
        "sheep_count": len(sheep_rows),
        "application_count": len(application_rows),
    }
