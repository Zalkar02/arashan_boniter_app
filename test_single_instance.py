import os
import subprocess
import sys
import textwrap

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import services.single_instance as si


def test_second_instance_is_refused(tmp_path):
    first = si.acquire_instance_lock(str(tmp_path), wait_ms=0)
    assert first is not None
    assert si.acquire_instance_lock(str(tmp_path), wait_ms=100) is None
    first.unlock()
    again = si.acquire_instance_lock(str(tmp_path), wait_ms=0)
    assert again is not None
    again.unlock()


def test_lock_of_running_instance_never_goes_stale(tmp_path):
    lock = si.acquire_instance_lock(str(tmp_path), wait_ms=0)
    assert lock.staleLockTime() == 0
    lock.unlock()


def test_second_instance_asks_first_to_show_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    activated = []
    server = si.start_activation_server(str(tmp_path), on_activate=lambda: activated.append(1))
    assert server is not None
    # вторая копия — отдельный процесс, как в жизни
    child = textwrap.dedent(f"""
        import os, sys
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        sys.path.insert(0, {os.getcwd()!r})
        from PyQt5.QtCore import QCoreApplication
        app = QCoreApplication([])
        import services.single_instance as si
        sys.exit(0 if si.request_activation({str(tmp_path)!r}) else 1)
    """)
    proc = subprocess.Popen([sys.executable, "-c", child])
    for _ in range(300):
        app.processEvents()
        if proc.poll() is not None and activated:
            break
        import time
        time.sleep(0.01)
    assert proc.wait(5) == 0
    assert activated == [1]
    server.close()


def test_no_answer_when_nobody_listens(tmp_path):
    QApplication.instance() or QApplication([])
    assert si.request_activation(str(tmp_path), timeout_ms=200) is False
