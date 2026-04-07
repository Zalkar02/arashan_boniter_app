from db.models import init_db


_db_session = None


def get_db():
    global _db_session
    if _db_session is None:
        _db_session = init_db()
    return _db_session
