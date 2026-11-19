import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from services.single_instance import acquire_instance_lock


def test_second_instance_is_refused(tmp_path):
    first = acquire_instance_lock(str(tmp_path), wait_ms=0)
    assert first is not None
    assert acquire_instance_lock(str(tmp_path), wait_ms=100) is None
    first.unlock()
    again = acquire_instance_lock(str(tmp_path), wait_ms=0)
    assert again is not None
    again.unlock()
