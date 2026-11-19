from db.models import init_db


_db_session = None


def get_db():
    global _db_session
    if _db_session is None:
        _db_session = init_db()
    return _db_session


def release_pending_changes():
    """Отпустить базу перед синхронизацией.

    Все сохранения в окнах коммитятся сразу, поэтому открытая транзакция общей
    сессии — это остаток оборвавшейся операции. Она держит блокировку записи,
    и синхронизация (отдельное подключение) падает с «database is locked».
    """
    if _db_session is not None and _db_session.in_transaction():
        _db_session.rollback()
