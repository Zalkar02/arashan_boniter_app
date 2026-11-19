"""Фоновая синхронизация: один работник за раз, значок состояния в окнах."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

import services.sync_controller as sc
import services.sync_worker as sw


@pytest.fixture()
def controller(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(sw, "release_pending_changes", lambda: None)
    monkeypatch.setattr(sc.AuthState, "user", {"id": 1})
    monkeypatch.setattr(sc, "load_tokens", lambda: {"access": "a", "refresh": "r"})
    ctrl = sc.SyncController(app)
    yield ctrl
    ctrl.shutdown()
    app.removeEventFilter(ctrl)


def _wait_finished(ctrl, timeout_ms=5000):
    loop = QEventLoop()
    ctrl.sync_finished.connect(lambda _ok: loop.quit())
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec_()
    QApplication.processEvents()


def test_auto_sync_runs_and_reports_success(controller, monkeypatch):
    calls = []
    monkeypatch.setattr(sw, "run_sync", lambda **kw: calls.append(kw) or True)
    controller._auto_tick()
    _wait_finished(controller)
    assert len(calls) == 1
    assert controller.status()[0].startswith("Синхронизировано в ")
    assert not controller.is_busy()


def test_failure_is_shown_in_status_not_dialog(controller, monkeypatch):
    def boom(**kw):
        raise ConnectionError("нет сети")
    monkeypatch.setattr(sw, "run_sync", boom)
    controller._auto_tick()
    _wait_finished(controller)
    text, tooltip = controller.status()
    assert text == "Синхронизация: ошибка"
    assert "нет сети" in tooltip


def test_offline_is_reported_plainly(controller, monkeypatch):
    def offline(**kw):
        raise OSError("HTTPConnectionPool(host='x', port=9): Max retries exceeded with url: /api_v2/sync/cursor/")
    monkeypatch.setattr(sw, "run_sync", offline)
    controller._auto_tick()
    _wait_finished(controller)
    text, tooltip = controller.status()
    assert text == "Синхронизация: нет связи с сервером"
    assert "Max retries" not in tooltip


def test_only_one_worker_at_a_time(controller):
    first = controller.create_worker()
    assert first is not None
    assert controller.create_worker() is None
    assert controller.create_worker(owner_id=5) is None


def test_no_auto_sync_without_login(controller, monkeypatch):
    monkeypatch.setattr(sc.AuthState, "user", None)
    controller._auto_tick()
    assert controller._worker is None
    assert "вход не выполнен" in controller.status()[0]


def test_status_label_added_to_shown_windows(controller):
    window = QMainWindow()
    window.show()
    QApplication.processEvents()
    label = window.findChild(QLabel, sc.STATUS_WIDGET_NAME)
    assert label is not None
    controller._set_status("Синхронизация: идёт…", "")
    assert label.text() == "Синхронизация: идёт…"
    window.show()  # повторный показ не добавляет второй значок
    assert len(window.findChildren(QLabel, sc.STATUS_WIDGET_NAME)) == 1
    window.close()


def test_start_auto_attaches_to_windows_shown_earlier(controller):
    window = QMainWindow()
    controller.parent().removeEventFilter(controller)  # окно показано до контроллера
    window.show()
    QApplication.processEvents()
    assert window.findChild(QLabel, sc.STATUS_WIDGET_NAME) is None
    controller.start_auto()
    assert window.findChild(QLabel, sc.STATUS_WIDGET_NAME) is not None
    controller.stop_auto()
    window.close()


def test_database_locked_is_explained(controller, monkeypatch):
    def locked(**kw):
        raise RuntimeError("(sqlite3.OperationalError) database is locked [SQL: UPDATE colors ...]")
    monkeypatch.setattr(sw, "run_sync", locked)
    messages = []
    worker = controller.create_worker()
    worker.failed.connect(messages.append)
    worker.start()
    _wait_finished(controller)
    assert messages == [sw.DATABASE_LOCKED_MESSAGE]
