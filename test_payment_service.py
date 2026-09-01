import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from db.models import Application, Sheep, init_db
from services import payment_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class PaymentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session = init_db(os.path.join(self.temp_dir.name, "payment-test.db"))
        self.sheep = Sheep(id_n="payment-sheep", remote_id=10, synced=True, is_paid=False)
        self.application = Application(
            sheep=self.sheep,
            remote_id=20,
            synced=True,
            is_paid=False,
        )
        self.session.add_all([self.sheep, self.application])
        self.session.commit()
        self.rows = [{
            "sheep": self.sheep,
            "applications": [self.application],
            "latest_application": self.application,
        }]

    def tearDown(self):
        engine = self.session.get_bind()
        self.session.close()
        engine.dispose()
        self.temp_dir.cleanup()

    def test_create_payment_reconciles_already_paid_items_before_qr(self):
        status_response = FakeResponse(payload={
            "paid_sheep_ids": [10],
            "unpaid_sheep_ids": [],
            "paid_application_ids": [20],
            "unpaid_application_ids": [],
        })
        request = MagicMock(return_value=status_response)

        with patch.object(payment_service, "_request_with_auth", request):
            payload = payment_service.create_payment(self.session, self.rows)

        self.session.refresh(self.sheep)
        self.session.refresh(self.application)
        self.assertTrue(payload["already_paid"])
        self.assertTrue(self.sheep.is_paid)
        self.assertTrue(self.application.is_paid)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1], payment_service.CHECK_BY_ITEMS_STATUS_URL)

    def test_create_payment_applies_already_paid_ids_from_race_response(self):
        responses = [
            FakeResponse(payload={
                "paid_sheep_ids": [],
                "unpaid_sheep_ids": [10],
                "paid_application_ids": [],
                "unpaid_application_ids": [20],
            }),
            FakeResponse(status_code=201, payload={
                "reference": "payment-reference",
                "payment_token": "payment-token",
                "already_paid_sheep_ids": [10],
                "already_paid_application_ids": [],
            }),
        ]

        with patch.object(payment_service, "_request_with_auth", side_effect=responses):
            payload = payment_service.create_payment(self.session, self.rows)

        self.session.refresh(self.sheep)
        self.session.refresh(self.application)
        self.assertFalse(payload.get("already_paid", False))
        self.assertTrue(self.sheep.is_paid)
        self.assertIsNone(self.sheep.payment_reference)
        self.assertFalse(self.application.is_paid)
        self.assertEqual(self.application.payment_reference, "payment-reference")

    def test_create_payment_recovers_when_server_reports_all_paid(self):
        responses = [
            FakeResponse(payload={
                "paid_sheep_ids": [],
                "unpaid_sheep_ids": [10],
                "paid_application_ids": [],
                "unpaid_application_ids": [20],
            }),
            FakeResponse(
                status_code=400,
                payload={"detail": "Все выбранные овцы и бонитировки уже оплачены."},
            ),
            FakeResponse(payload={
                "paid_sheep_ids": [10],
                "unpaid_sheep_ids": [],
                "paid_application_ids": [20],
                "unpaid_application_ids": [],
            }),
        ]

        with patch.object(payment_service, "_request_with_auth", side_effect=responses):
            payload = payment_service.create_payment(self.session, self.rows)

        self.session.refresh(self.sheep)
        self.session.refresh(self.application)
        self.assertTrue(payload["already_paid"])
        self.assertTrue(self.sheep.is_paid)
        self.assertTrue(self.application.is_paid)

    def test_reference_status_is_followed_by_exact_item_statuses(self):
        self.sheep.payment_reference = "existing-reference"
        self.application.payment_reference = "existing-reference"
        self.session.commit()
        responses = [
            FakeResponse(payload={
                "status": "paid",
                "payment_token": "existing-token",
            }),
            FakeResponse(payload={
                "paid_sheep_ids": [10],
                "unpaid_sheep_ids": [],
                "paid_application_ids": [],
                "unpaid_application_ids": [20],
            }),
        ]

        with patch.object(payment_service, "_request_with_auth", side_effect=responses):
            summary = payment_service.refresh_payment_statuses(self.session, self.rows)

        self.session.refresh(self.sheep)
        self.session.refresh(self.application)
        self.assertTrue(self.sheep.is_paid)
        self.assertFalse(self.application.is_paid)
        self.assertTrue(summary["used_reference_check"])
        self.assertTrue(summary["used_items_check"])


if __name__ == "__main__":
    unittest.main()
