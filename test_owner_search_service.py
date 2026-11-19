from sqlalchemy import text

from db.models import User, init_db
from services.owner_search_service import find_owners_page


def _ids(session, query):
    rows, total = find_owners_page(session, User, query, 0, 100)
    assert total == len(rows)
    return {row.id for row in rows}


def _session(tmp_path):
    session = init_db(str(tmp_path / "local.db"))
    session.add_all([
        User(id=1, username="u1", name="Каратаев Раимжан", phone="0555-12-34-56", region="C", area="39", city="Беловодское"),
        User(id=2, username="u2", name="Бакыт", phone="0700111222", region="O", city="Ош"),
        User(id=3, username="u3", name="Asan", phone="0777000000", region="T"),
    ])
    session.commit()
    return session


def test_name_norm_filled_on_insert_and_update(tmp_path):
    session = _session(tmp_path)
    user = session.get(User, 1)
    assert user.name_norm == "каратаев раимжан"
    user.name = "Новое  Имя"
    session.commit()
    assert user.name_norm == "новое имя"


def test_backfill_fixes_users_from_sync_without_name_norm(tmp_path):
    session = _session(tmp_path)
    session.execute(text("UPDATE users SET name_norm = NULL"))
    session.commit()
    session.close()
    session = init_db(str(tmp_path / "local.db"))
    assert session.get(User, 1).name_norm == "каратаев раимжан"


def test_cyrillic_search_does_not_depend_on_name_norm(tmp_path):
    session = _session(tmp_path)
    session.execute(text("UPDATE users SET name_norm = NULL"))
    session.commit()
    assert _ids(session, "Каратаев") == {1}
    assert _ids(session, "каратаев") == {1}


def test_words_in_any_order_and_location(tmp_path):
    session = _session(tmp_path)
    assert _ids(session, "раимжан каратаев") == {1}
    assert _ids(session, "беловодское") == {1}
    assert _ids(session, "чуй") == {1}
    assert _ids(session, "ош") == {2}


def test_phone_and_latin(tmp_path):
    session = _session(tmp_path)
    assert _ids(session, "0555 12 34") == {1}
    assert _ids(session, "0700") == {2}
    assert _ids(session, "asan") == {3}
