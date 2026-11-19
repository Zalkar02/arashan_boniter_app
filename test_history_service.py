import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Application, Base, Owner, Sheep, User
from services.history_service import (
    build_owner_history_summary,
    filter_owner_history,
    format_owner_history_row,
    get_owner_history_rows,
)

TODAY = datetime.date.today()
OLD = TODAY - datetime.timedelta(days=400)


@pytest.fixture()
def rows():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    asan = User(id=1, name="Асан Уулу", phone="0555-12-34-56", region="C", area="39", city="", is_deleted=False)
    bakyt = User(id=2, name="Бакыт", phone="0700111222", region="O", area="", city="Ош", is_deleted=False)
    gone = User(id=3, name="Удалённый", phone="0777000000", is_deleted=True)
    s.add_all([asan, bakyt, gone])
    s.flush()
    s.add_all([
        Sheep(id=1, id_n="A1", owner_id=1, date_filling=OLD, is_deleted=False),
        Sheep(id=2, id_n="A2", owner_id=1, date_filling=OLD, is_deleted=False),
        Sheep(id=3, id_n="B1", owner_id=None, date_filling=TODAY, is_deleted=False),
        Sheep(id=4, id_n="DEL", owner_id=1, date_filling=TODAY, is_deleted=True),
        Sheep(id=5, id_n="G1", owner_id=3, date_filling=TODAY, is_deleted=False),
    ])
    s.flush()
    s.add(Owner(sheep_id=3, owner_id=2, owner_bool=True, is_deleted=False))
    s.add_all([
        Application(id=1, sheep_id=1, date=OLD, is_paid=True, is_deleted=False),
        Application(id=2, sheep_id=2, date=OLD, is_paid=False, is_deleted=False),
        Application(id=3, sheep_id=2, date=TODAY, is_paid=True, is_deleted=True),
        Application(id=4, sheep_id=3, date=TODAY, is_paid=False, is_deleted=False),
    ])
    s.commit()
    result = build_owner_history_summary(s, Application, Sheep, Owner, User)
    s.close()
    return result


def by_name(rows, name):
    return next(r for r in rows if r["name"] == name)


def test_counters(rows):
    assert {r["name"] for r in rows} == {"Асан Уулу", "Бакыт"}
    a = by_name(rows, "Асан Уулу")
    assert a["total_sheep"] == 2
    assert a["sheep_with_applications"] == 2
    assert a["sheep_without_applications"] == 0
    assert a["recent_sheep"] == 0
    assert a["unpaid_sheep"] == 1  # удалённая заявка не в счёт
    assert a["latest_activity"] == OLD
    b = by_name(rows, "Бакыт")
    assert b["total_sheep"] == 1
    assert b["recent_sheep"] == 1
    assert b["unpaid_sheep"] == 1
    assert b["location"] == "Ош"
    assert rows[0]["name"] == "Бакыт"  # свежая активность первой


def test_format_row(rows):
    assert len(format_owner_history_row(rows[0])) == 8


def test_search_name_case_and_cyrillic(rows):
    assert [r["name"] for r in filter_owner_history(rows, "асан")] == ["Асан Уулу"]
    assert [r["name"] for r in filter_owner_history(rows, "БАКЫТ")] == ["Бакыт"]
    assert [r["name"] for r in filter_owner_history(rows, "уулу асан")] == ["Асан Уулу"]


def test_search_region_code_label(rows):
    assert [r["name"] for r in filter_owner_history(rows, "Чуй")] == ["Асан Уулу"]


def test_search_phone_digits(rows):
    assert [r["name"] for r in filter_owner_history(rows, "555123")] == ["Асан Уулу"]


def test_search_none_and_empty(rows):
    assert filter_owner_history(rows, "несуществующий") == []
    assert filter_owner_history(rows, "") == rows
    assert filter_owner_history(rows, "   ") == rows


def test_deleted_not_listed(rows):
    assert not filter_owner_history(rows, "Удалённый")
