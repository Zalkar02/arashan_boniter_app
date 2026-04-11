from PyQt5.QtCore import QThread, pyqtSignal

from services.update_service import check_for_updates, pull_updates


class UpdateWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode

    def run(self):
        try:
            if self.mode == "pull":
                result = pull_updates()
            else:
                result = check_for_updates()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)
