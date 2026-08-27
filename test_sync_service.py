import datetime
import os
import tempfile
import unittest
import uuid
from unittest.mock import MagicMock, patch

from db.models import Application, Boniter, Color, Owner, Sheep, init_db
from sync import sync as sync_module


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class SyncServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "sync-test.db")
        self.session = init_db(self.db_path)

    def tearDown(self):
        engine = self.session.get_bind()
        self.session.close()
        engine.dispose()
        self.temp_dir.cleanup()

    def test_requests_have_a_timeout(self):
        response = FakeResponse(payload=[])
        with (
            patch.object(sync_module, "load_tokens", return_value={"access": "token"}),
            patch.object(sync_module.requests, "request", return_value=response) as request,
        ):
            sync_module._request_with_auth("GET", "https://example.test/sync")

        self.assertEqual(request.call_args.kwargs["timeout"], sync_module.SYNC_REQUEST_TIMEOUT)

    def test_missing_upload_ack_keeps_record_unsynced(self):
        color = Color(name="Белый", synced=False)
        self.session.add(color)
        self.session.commit()

        with (
            patch.object(sync_module, "UPLOAD_MODELS", [Color]),
            patch.object(
                sync_module,
                "_request_with_auth",
                return_value=FakeResponse(payload=[]),
            ),
        ):
            with self.assertRaises(RuntimeError):
                sync_module.sync_to_server(self.session)

        self.session.refresh(color)
        self.assertFalse(color.synced)
        self.assertIsNone(color.remote_id)

    def test_valid_upload_ack_sets_remote_id(self):
        color = Color(name="Черный", synced=False)
        self.session.add(color)
        self.session.commit()

        payload = [{"local_id": color.id, "remote_id": 101, "status": "ok"}]
        request = MagicMock(return_value=FakeResponse(payload=payload))
        with (
            patch.object(sync_module, "UPLOAD_MODELS", [Color]),
            patch.object(sync_module, "_request_with_auth", request),
        ):
            result = sync_module.sync_to_server(
                self.session,
                client_id="4ed18fb8-8f6c-4bf9-8167-604364897a38",
            )

        self.session.refresh(color)
        self.assertTrue(result)
        self.assertTrue(color.synced)
        self.assertEqual(color.remote_id, 101)
        self.assertEqual(
            request.call_args.kwargs["json"][0]["client_id"],
            "4ed18fb8-8f6c-4bf9-8167-604364897a38",
        )

    def test_sync_client_id_is_stable_for_the_database(self):
        first = sync_module.get_sync_client_id(self.session)
        second = sync_module.get_sync_client_id(self.session)

        self.assertEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)

    def test_server_cursor_is_timezone_aware(self):
        response = FakeResponse(payload={"cursor": "2026-08-27T12:00:00Z"})
        with patch.object(sync_module, "_request_with_auth", return_value=response):
            cursor = sync_module.get_server_sync_cursor()

        self.assertEqual(cursor.utcoffset(), datetime.timedelta(0))

    def test_owner_model_persists_soft_delete_state(self):
        self.assertIn("is_deleted", Owner.__table__.columns)

    def test_colors_are_always_downloaded_as_a_full_reference_list(self):
        request = MagicMock(
            return_value=FakeResponse(
                payload={
                    "results": [{"id": 7, "name": "Белый", "is_deleted": False}],
                    "next": None,
                    "count": 1,
                }
            )
        )
        with (
            patch.object(sync_module, "DOWNLOAD_MODELS", [Color]),
            patch.object(sync_module, "get_last_sync_time", return_value=datetime.datetime(2026, 8, 27)),
            patch.object(sync_module, "_apply_deleted_records", return_value=True),
            patch.object(sync_module, "_request_with_auth", request),
        ):
            result = sync_module.sync_from_server(self.session)

        self.assertTrue(result)
        self.assertEqual(self.session.query(Color).one().remote_id, 7)
        self.assertEqual(request.call_args.kwargs["params"], {"full": "1"})

    def test_reference_sync_loads_boniter_and_repairs_dangling_fk(self):
        sheep = Sheep(id_n="dangling-boniter", boniter=3, synced=False)
        application = Application(sheep=sheep, boniter=3, synced=False)
        self.session.add_all([sheep, application])
        self.session.commit()

        responses = [
            FakeResponse(payload={"results": [], "next": None, "count": 0}),
            FakeResponse(
                payload={
                    "results": [{"id": 3, "name": "Server Boniter", "contact_info": ""}],
                    "next": None,
                    "count": 1,
                }
            ),
        ]
        with patch.object(sync_module, "_request_with_auth", side_effect=responses):
            result = sync_module.sync_reference_data(self.session)

        boniter = self.session.query(Boniter).one()
        self.session.refresh(sheep)
        self.session.refresh(application)
        self.assertTrue(result)
        self.assertEqual(boniter.remote_id, 3)
        self.assertEqual(sheep.boniter, boniter.id)
        self.assertEqual(application.boniter, boniter.id)

    def test_blocked_dependency_error_identifies_record_and_relation(self):
        sheep = Sheep(id_n="missing-boniter", boniter=99, synced=False)
        self.session.add(sheep)
        self.session.commit()

        with patch.object(sync_module, "UPLOAD_MODELS", [Sheep]):
            with self.assertRaises(RuntimeError) as raised:
                sync_module.sync_to_server(self.session, client_id="client-id")

        message = str(raised.exception)
        self.assertIn(f"локальная запись #{sheep.id}", message)
        self.assertIn("бонитёр 99", message)
        self.assertIn("локальная запись отсутствует", message)

    def test_owner_upload_uses_shared_sync_pipeline(self):
        scoped = {Color: []}
        with (
            patch.object(sync_module, "_get_owner_scope_objects", return_value=scoped),
            patch.object(sync_module, "_sync_models_to_server", return_value=True) as shared_sync,
        ):
            result = sync_module.sync_owner_to_server(
                self.session,
                owner_id=25,
                client_id="client-id",
            )

        self.assertTrue(result)
        self.assertIs(shared_sync.call_args.kwargs["candidates_by_model"], scoped)
        self.assertEqual(shared_sync.call_args.kwargs["client_id"], "client-id")

    def test_download_does_not_overwrite_unsynced_local_record(self):
        color = Color(name="Локальное название", remote_id=10, synced=False)
        self.session.add(color)
        self.session.commit()

        payload = {
            "results": [{"id": 10, "name": "Серверное название"}],
            "next": None,
            "count": 1,
        }
        with (
            patch.object(sync_module, "DOWNLOAD_MODELS", [Color]),
            patch.object(sync_module, "get_last_sync_time", return_value=datetime.datetime(2000, 1, 1)),
            patch.object(sync_module, "_apply_deleted_records", return_value=True),
            patch.object(
                sync_module,
                "_request_with_auth",
                return_value=FakeResponse(payload=payload),
            ),
            patch.object(sync_module, "_log_conflict"),
        ):
            with self.assertRaises(RuntimeError):
                sync_module.sync_from_server(self.session)

        self.session.refresh(color)
        self.assertEqual(color.name, "Локальное название")
        self.assertFalse(color.synced)

    def test_sheep_parent_can_arrive_on_a_later_page(self):
        responses = [
            FakeResponse(
                payload={
                    "results": [{"id": 1, "id_n": "child", "parent": [2]}],
                    "next": "next-page",
                    "count": 2,
                }
            ),
            FakeResponse(
                payload={
                    "results": [{"id": 2, "id_n": "parent", "parent": []}],
                    "next": None,
                    "count": 2,
                }
            ),
        ]
        with (
            patch.object(sync_module, "DOWNLOAD_MODELS", [Sheep]),
            patch.object(sync_module, "SYNC_BATCH_SIZE", 1),
            patch.object(sync_module, "get_last_sync_time", return_value=datetime.datetime(2000, 1, 1)),
            patch.object(sync_module, "_apply_deleted_records", return_value=True),
            patch.object(sync_module, "_request_with_auth", side_effect=responses),
        ):
            result = sync_module.sync_from_server(self.session)

        child = self.session.query(Sheep).filter_by(remote_id=1).one()
        self.assertTrue(result)
        self.assertEqual([parent.remote_id for parent in child.parents], [2])

    def test_missing_sheep_parent_is_downloaded_by_id(self):
        responses = [
            FakeResponse(
                payload={
                    "results": [{"id": 1, "id_n": "child", "parent": [2]}],
                    "next": None,
                    "count": 1,
                }
            ),
            FakeResponse(
                payload={
                    "results": [{"id": 2, "id_n": "parent", "parent": []}],
                    "next": None,
                    "count": 1,
                }
            ),
        ]
        request = MagicMock(side_effect=responses)
        with (
            patch.object(sync_module, "DOWNLOAD_MODELS", [Sheep]),
            patch.object(sync_module, "get_last_sync_time", return_value=datetime.datetime(2000, 1, 1)),
            patch.object(sync_module, "_apply_deleted_records", return_value=True),
            patch.object(sync_module, "_request_with_auth", request),
        ):
            result = sync_module.sync_from_server(self.session)

        child = self.session.query(Sheep).filter_by(remote_id=1).one()
        self.assertTrue(result)
        self.assertEqual([parent.remote_id for parent in child.parents], [2])
        self.assertEqual(request.call_args.kwargs["params"], {"ids": "2"})

    def test_successful_run_saves_start_watermark_and_closes_session(self):
        fake_session = MagicMock()
        server_cursor = datetime.datetime(2026, 8, 27, 12, 0, tzinfo=datetime.timezone.utc)
        with (
            patch.object(sync_module, "init_db", return_value=fake_session),
            patch.object(sync_module, "get_server_sync_cursor", return_value=server_cursor),
            patch.object(sync_module, "get_sync_client_id", return_value="client-id"),
            patch.object(sync_module, "sync_reference_data", return_value=True),
            patch.object(sync_module, "sync_to_server", return_value=True),
            patch.object(sync_module, "sync_from_server", return_value=True),
            patch.object(sync_module, "update_last_sync_time") as update_watermark,
        ):
            result = sync_module.run_sync()

        self.assertTrue(result)
        update_watermark.assert_called_once_with(server_cursor)
        fake_session.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
