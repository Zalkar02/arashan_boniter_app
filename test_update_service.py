import hashlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services import update_service
from services.update_service import UpdateError


def _manifest(version="1.3.0", min_version="1.0.0", sha="a" * 64):
    return {
        "version": version,
        "min_supported_version": min_version,
        "notes": "notes",
        "platforms": {
            "windows": {"url": "https://s3.example/x/Setup-1.3.0.exe", "sha256": sha},
            "linux": {"url": "https://s3.example/x/App-1.3.0.AppImage", "sha256": sha},
        },
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None, body=b""):
        self.status_code = status_code
        self._payload = payload
        self._body = body
        self.headers = {"Content-Length": str(len(body))}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def iter_content(self, size):
        for i in range(0, len(self._body), size):
            yield self._body[i:i + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(update_service.parse_version("v1.2.3"), (1, 2, 3))
        self.assertGreater(update_service.parse_version("1.10.0"), update_service.parse_version("1.9.9"))

    def test_invalid_version(self):
        with self.assertRaises(UpdateError):
            update_service.parse_version("abc")


class CheckTests(unittest.TestCase):
    def check(self, manifest, current="1.0.0", status=200):
        response = FakeResponse(status, manifest)
        with patch.object(update_service.requests, "get", return_value=response):
            return update_service.check_for_updates(current, "https://s3.example/x")

    def test_new_version_available(self):
        info = self.check(_manifest())
        self.assertTrue(info["has_updates"])
        self.assertFalse(info["required"])
        self.assertEqual(info["latest_version"], "1.3.0")

    def test_up_to_date(self):
        self.assertFalse(self.check(_manifest(), current="1.3.0")["has_updates"])

    def test_required_when_below_minimum(self):
        info = self.check(_manifest(min_version="1.2.0"), current="1.1.0")
        self.assertTrue(info["required"])

    def test_missing_base_url(self):
        with self.assertRaises(UpdateError):
            update_service.check_for_updates("1.0.0", "")

    def test_server_error(self):
        with self.assertRaises(UpdateError):
            self.check({}, status=500)

    def test_network_error(self):
        with patch.object(
            update_service.requests, "get",
            side_effect=update_service.requests.ConnectionError("down"),
        ):
            with self.assertRaises(UpdateError):
                update_service.check_for_updates("1.0.0", "https://s3.example/x")


class DownloadTests(unittest.TestCase):
    def test_download_verifies_checksum(self):
        body = b"installer-bytes" * 1000
        info = {
            "latest_version": "1.3.0",
            "asset": {"url": "https://s3.example/x/App.AppImage", "sha256": hashlib.sha256(body).hexdigest()},
        }
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(update_service.requests, "get", return_value=FakeResponse(body=body)):
                path = update_service.download_update(info, progress=lambda d, t: seen.append((d, t)), dest_dir=tmp)
            self.assertEqual(open(path, "rb").read(), body)
            self.assertFalse(os.path.exists(path + ".part"))
        self.assertEqual(seen[-1][0], len(body))

    def test_download_rejects_bad_checksum(self):
        info = {
            "latest_version": "1.3.0",
            "asset": {"url": "https://s3.example/x/App.AppImage", "sha256": "0" * 64},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(update_service.requests, "get", return_value=FakeResponse(body=b"data")):
                with self.assertRaises(UpdateError):
                    update_service.download_update(info, dest_dir=tmp)
            self.assertEqual(os.listdir(tmp), [])


class ApplyTests(unittest.TestCase):
    def test_apply_refused_when_not_installed_build(self):
        with patch.object(update_service, "can_self_update", return_value=False):
            with self.assertRaises(UpdateError):
                update_service.apply_update("/tmp/x")

    def test_linux_replaces_appimage_and_relaunches(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "App.AppImage")
            new_file = os.path.join(tmp, "dl.AppImage")
            open(target, "wb").write(b"old")
            open(new_file, "wb").write(b"new")
            with (
                patch.object(update_service, "can_self_update", return_value=True),
                patch.object(update_service.sys, "platform", "linux"),
                patch.dict(os.environ, {"APPIMAGE": target}),
                patch.object(update_service.subprocess, "Popen") as popen,
            ):
                update_service.apply_update(new_file)
            self.assertEqual(open(target, "rb").read(), b"new")
            self.assertTrue(os.access(target, os.X_OK))
            self.assertFalse(os.path.exists(new_file))
            self.assertEqual(popen.call_args[0][0][-1], target)

    def test_windows_runs_silent_installer(self):
        with (
            patch.object(update_service, "can_self_update", return_value=True),
            patch.object(update_service.sys, "platform", "win32"),
            patch.object(update_service.subprocess, "Popen") as popen,
        ):
            update_service.apply_update("C:/Setup.exe")
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "C:/Setup.exe")
        self.assertIn("/SILENT", args)


if __name__ == "__main__":
    unittest.main()
