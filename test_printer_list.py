"""Список принтеров в Windows не должен запускать PowerShell (медленно, окно консоли)."""
import sys
import types
from unittest.mock import patch

import services.passport_print_service as pps


def _fake_qt(names):
    module = types.ModuleType("PyQt5.QtPrintSupport")
    module.QPrinterInfo = types.SimpleNamespace(availablePrinterNames=lambda: names)
    return module


def test_windows_printers_come_from_qt_without_subprocess():
    with patch.object(pps.os, "name", "nt"), \
            patch.dict(sys.modules, {"PyQt5.QtPrintSupport": _fake_qt(["HP LaserJet", "HP LaserJet", " Canon "])}), \
            patch.object(pps.subprocess, "run") as run:
        assert pps.list_system_printers() == ["HP LaserJet", "Canon"]
    run.assert_not_called()


def test_windows_powershell_fallback_hides_console():
    with patch.object(pps.os, "name", "nt"), \
            patch.object(pps, "_list_printers_qt", return_value=None), \
            patch.object(pps.shutil, "which", return_value="powershell.exe"), \
            patch.object(pps.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
            patch.object(pps.subprocess, "run") as run:
        run.return_value = types.SimpleNamespace(returncode=0, stdout="P1\nP2\n")
        assert pps.list_system_printers() == ["P1", "P2"]
    assert run.call_args.kwargs["creationflags"] == 0x08000000
