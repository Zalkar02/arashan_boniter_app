import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import update_service


class UpdateServiceTests(unittest.TestCase):
    def test_python_bin_finds_windows_virtual_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            windows_python = project_root / ".venv" / "Scripts" / "python.exe"
            windows_python.parent.mkdir(parents=True)
            windows_python.touch()

            with patch.object(update_service, "PROJECT_ROOT", project_root):
                result = update_service._python_bin()

        self.assertEqual(result, str(windows_python))

    def test_python_bin_uses_running_interpreter_for_source_install(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(update_service, "PROJECT_ROOT", Path(temp_dir)),
                patch.object(sys, "frozen", False, create=True),
            ):
                result = update_service._python_bin()

        self.assertEqual(result, sys.executable)

    def test_pull_updates_installs_dependencies_before_migration(self):
        calls = []

        def run_python(*args):
            calls.append(args)
            return "ok"

        with (
            patch.object(update_service, "check_for_updates", side_effect=[
                {"dirty": False},
                {"dirty": False, "behind": 0},
            ]),
            patch.object(update_service, "_run_git", return_value="updated"),
            patch.object(update_service, "_run_python", side_effect=run_python),
        ):
            update_service.pull_updates()

        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[-1], ("migrate_local_db.py",))
        self.assertEqual(calls[-2][:4], ("-m", "pip", "install", "-r"))


if __name__ == "__main__":
    unittest.main()
