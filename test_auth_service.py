import json
import os
import tempfile
import unittest
from unittest.mock import patch

from services import auth_service


class AuthStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tokens_path = os.path.join(self.temp_dir.name, "tokens.json")
        self.user_path = os.path.join(self.temp_dir.name, "user.json")
        self.patches = [
            patch.object(auth_service, "TOKENS_PATH", self.tokens_path),
            patch.object(auth_service, "USER_PATH", self.user_path),
            patch.object(auth_service, "ensure_state_dir", return_value=None),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    def test_tokens_and_user_round_trip(self):
        auth_service.save_tokens("access-token", "refresh-token")
        auth_service.save_user({"id": 5, "name": "Тест"})

        self.assertEqual(
            auth_service.load_tokens(),
            {"access": "access-token", "refresh": "refresh-token"},
        )
        self.assertEqual(auth_service.load_user(), {"id": 5, "name": "Тест"})
        self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(self.temp_dir.name)))

    def test_invalid_json_is_treated_as_missing_state(self):
        with open(self.tokens_path, "w", encoding="utf-8") as file:
            file.write("not-json")
        with open(self.user_path, "w", encoding="utf-8") as file:
            json.dump([], file)

        self.assertEqual(auth_service.load_tokens(), {})
        self.assertIsNone(auth_service.load_user())

    def test_clear_session_removes_persisted_state(self):
        auth_service.save_tokens("access-token", "refresh-token")
        auth_service.save_user({"id": 5})

        auth_service.clear_session()

        self.assertFalse(os.path.exists(self.tokens_path))
        self.assertFalse(os.path.exists(self.user_path))


if __name__ == "__main__":
    unittest.main()
