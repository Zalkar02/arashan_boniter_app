from db.models import init_db, User, Sheep
from services.owner_search_service import _norm


def main():
    session = init_db()
    try:
        users = session.query(User).filter((User.name_norm.is_(None)) | (User.name_norm == "")).all()
        for user in users:
            user.name_norm = _norm(getattr(user, "name", "") or "")
        sheep_rows = session.query(Sheep).filter((Sheep.nick_norm.is_(None)) | (Sheep.nick_norm == "")).all()
        for sheep in sheep_rows:
            sheep.nick_norm = _norm(getattr(sheep, "nick", "") or "")
        if users:
            session.commit()
    finally:
        session.close()
    print("Local database migration complete.")


if __name__ == "__main__":
    main()
