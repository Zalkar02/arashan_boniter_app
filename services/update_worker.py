from PyQt5.QtCore import QThread, pyqtSignal

from services import legacy_migration
from services.update_service import apply_update, check_for_updates, download_update


class UpdateWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, mode: str, info: dict = None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.info = info or {}

    def run(self):
        try:
            if self.mode == "install":
                path = download_update(self.info, progress=self.progress.emit)
                apply_update(path)
                result = {"installed": True}
            elif self.mode == "legacy_install":
                legacy_migration.migrate(self.info, progress=self.progress.emit)
                result = {"installed": True}
            elif self.mode == "legacy_check":
                result = legacy_migration.check()
            else:
                result = check_for_updates()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)
