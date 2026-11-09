import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import legacy_migration


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE sheep (id INTEGER PRIMARY KEY, nick TEXT)")
    conn.executemany("INSERT INTO sheep (nick) VALUES (?)", [(r,) for r in rows])
    conn.commit()
    return conn


class CopyUserDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "repo")
        self.dest = os.path.join(self.tmp.name, "data")
        os.makedirs(os.path.join(self.src, ".app_state", "print_jobs"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_db_state_and_sync_files(self):
        # Соединение остаётся открытым: данные лежат в WAL, как у работающего приложения.
        conn = _make_db(os.path.join(self.src, "sheep_local.db"), ["Ак", "Кара"])
        with open(os.path.join(self.src, ".app_state", "tokens.json"), "w") as fh:
            fh.write('{"access": "x"}')
        with open(os.path.join(self.src, ".app_state", "print_jobs", "job.json"), "w") as fh:
            fh.write("{}")
        with open(os.path.join(self.src, "last_sync.txt"), "w") as fh:
            fh.write("2026-11-01T00:00:00")

        try:
            self.assertTrue(legacy_migration.copy_user_data(self.src, self.dest))
        finally:
            conn.close()

        copied = sqlite3.connect(os.path.join(self.dest, "sheep_local.db"))
        try:
            nicks = [r[0] for r in copied.execute("SELECT nick FROM sheep ORDER BY id")]
        finally:
            copied.close()
        self.assertEqual(nicks, ["Ак", "Кара"])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, ".app_state", "tokens.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, ".app_state", "print_jobs", "job.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "last_sync.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "sheep_local.db.part")))

    def test_does_not_overwrite_existing_installed_data(self):
        _make_db(os.path.join(self.src, "sheep_local.db"), ["Старая"]).close()
        os.makedirs(self.dest)
        _make_db(os.path.join(self.dest, "sheep_local.db"), ["Новая"]).close()

        self.assertFalse(legacy_migration.copy_user_data(self.src, self.dest))

        conn = sqlite3.connect(os.path.join(self.dest, "sheep_local.db"))
        try:
            nicks = [r[0] for r in conn.execute("SELECT nick FROM sheep")]
        finally:
            conn.close()
        self.assertEqual(nicks, ["Новая"])

    def test_works_without_db(self):
        self.assertTrue(legacy_migration.copy_user_data(self.src, self.dest))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "sheep_local.db")))


class LegacyDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"))
        self.marker = os.path.join(self.tmp.name, ".migrated_to_installed.json")
        self.patches = [
            patch.object(legacy_migration, "PROJECT_ROOT", self.tmp.name),
            patch.object(legacy_migration, "MARKER_PATH", self.marker),
            patch.object(legacy_migration, "is_frozen", return_value=False),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_git_checkout_is_legacy(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARASHAN_DEV", None)
            self.assertTrue(legacy_migration.is_legacy_checkout())

    def test_dev_flag_disables_migration(self):
        with patch.dict(os.environ, {"ARASHAN_DEV": "1"}):
            self.assertFalse(legacy_migration.is_legacy_checkout())

    def test_frozen_app_is_not_legacy(self):
        with patch.object(legacy_migration, "is_frozen", return_value=True):
            self.assertFalse(legacy_migration.is_legacy_checkout())

    def test_redirect_launches_installed_app(self):
        app_path = os.path.join(self.tmp.name, "ArashanBoniter.AppImage")
        open(app_path, "w").close()
        with open(self.marker, "w") as fh:
            json.dump({"app_path": app_path, "version": "0.1.2"}, fh)
        with patch.dict(os.environ, {}, clear=False), patch.object(legacy_migration, "_launch") as launch:
            os.environ.pop("ARASHAN_DEV", None)
            self.assertTrue(legacy_migration.redirect_to_installed())
        launch.assert_called_once_with(app_path)

    def test_no_redirect_without_marker_or_app(self):
        with patch.dict(os.environ, {}, clear=False), patch.object(legacy_migration, "_launch") as launch:
            os.environ.pop("ARASHAN_DEV", None)
            self.assertFalse(legacy_migration.redirect_to_installed())
            with open(self.marker, "w") as fh:
                json.dump({"app_path": os.path.join(self.tmp.name, "missing")}, fh)
            self.assertFalse(legacy_migration.redirect_to_installed())
        launch.assert_not_called()


class CheckTests(unittest.TestCase):
    def test_offers_latest_even_if_source_version_is_newer(self):
        info = {"latest_version": "0.1.2", "has_updates": True, "required": True, "asset": {"url": "u", "sha256": "s"}}
        with patch.object(legacy_migration, "check_for_updates", return_value=info) as check:
            result = legacy_migration.check()
        check.assert_called_once_with(current_version="0.0.0")
        self.assertTrue(result["legacy"])
        self.assertFalse(result["required"])


class LinuxShortcutTests(unittest.TestCase):
    def test_rewrites_old_shortcuts_to_appimage(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = os.path.join(tmp, "Desktop")
            os.makedirs(desktop)
            old = os.path.join(desktop, "arashan-boniter.desktop")
            with open(old, "w") as fh:
                fh.write("[Desktop Entry]\nExec=/home/u/arashan/run.sh\n")
            with patch.dict(os.environ, {"XDG_DATA_HOME": os.path.join(tmp, "share")}), \
                    patch.object(legacy_migration, "_desktop_dir", return_value=desktop), \
                    patch.object(legacy_migration.subprocess, "run"):
                legacy_migration.replace_linux_shortcuts("/home/u/Applications/ArashanBoniter.AppImage")
            for path in (old, os.path.join(tmp, "share", "applications", "arashan-boniter.desktop")):
                with open(path) as fh:
                    content = fh.read()
                self.assertIn('Exec="/home/u/Applications/ArashanBoniter.AppImage"', content)
                self.assertNotIn("run.sh", content)


if __name__ == "__main__":
    unittest.main()
