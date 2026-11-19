import datetime

from db.models import Owner, Sheep, User, init_db
from services.database_browser_service import get_owner_rows


def test_sheep_count_follows_current_owner(tmp_path):
    session = init_db(str(tmp_path / "local.db"))
    session.add_all([
        User(id=1, username="old", name="Старый"),
        User(id=2, username="new", name="Новый"),
    ])
    day = datetime.date(2026, 1, 1)
    # овца 1 передана от Старого к Новому
    session.add(Sheep(id=1, id_n="A1", owner_id=2, is_deleted=False))
    session.add(Owner(sheep_id=1, owner_id=1, owner_bool=False, date1=day))
    session.add(Owner(sheep_id=1, owner_id=2, owner_bool=True, date1=day))
    # овца 2 без owner_id: владелец берётся из действующей записи владения
    session.add(Sheep(id=2, id_n="A2", owner_id=None, is_deleted=False))
    session.add(Owner(sheep_id=2, owner_id=1, owner_bool=True, date1=day))
    # удалённая овца не считается
    session.add(Sheep(id=3, id_n="A3", owner_id=2, is_deleted=True))
    session.commit()

    rows, total = get_owner_rows(session, User, Sheep, Owner)
    counts = {row["user"].username: row["sheep_count"] for row in rows}
    assert total == 2
    assert counts == {"old": 1, "new": 1}
