"""Окна не должны держать базу после сбоя оплаты: иначе синхронизация
падает с «database is locked»."""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import services.db_service as db_service
import services.payment_service as payment_service
from db.models import Sheep, init_db


def _sync_can_write(path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 0.2})
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE sheep SET nick = nick"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.fixture()
def ui_session(tmp_path):
    path = tmp_path / "local.db"
    session = init_db(str(path))
    session.add(Sheep(id=1, id_n="A1", remote_id=10, payment_reference="REF1", is_deleted=False))
    session.commit()
    yield session, path
    session.close()


def _failing_check(*responses):
    calls = list(responses)

    def fake(*args, **kwargs):
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    return fake


def test_failed_payment_check_does_not_lock_database(ui_session):
    session, path = ui_session
    sheep = session.get(Sheep, 1)
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"status": "pending", "payment_token": "T2"}
    rows = [{"sheep": sheep, "applications": [], "latest_application": None}]
    with patch.object(payment_service, "_request_with_auth",
                      side_effect=_failing_check(ok, ConnectionError("нет сети"))):
        with pytest.raises(ConnectionError):
            payment_service.refresh_payment_statuses(session, rows)

    session.query(Sheep).count()  # окно обновляется
    assert _sync_can_write(path)
    assert session.get(Sheep, 1).payment_token is None


def test_release_pending_changes_before_sync(ui_session, monkeypatch):
    session, path = ui_session
    monkeypatch.setattr(db_service, "_db_session", session)
    session.get(Sheep, 1).nick = "оборванная правка"
    session.query(Sheep).count()  # autoflush открыл запись
    assert not _sync_can_write(path)

    db_service.release_pending_changes()
    assert _sync_can_write(path)
