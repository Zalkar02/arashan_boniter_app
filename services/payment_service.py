import requests

from api_config import build_api_url
from services.auth_service import load_tokens, refresh_access_token


CREATE_PAYMENT_URL = build_api_url("/api/payments/mkassa/dynamic-qr/")
TOKEN_REFRESH_URL = build_api_url("/api/token/refresh/")
CHECK_BY_ITEMS_STATUS_URL = build_api_url("/api/payments/mkassa/statuses/by-items/")
ALREADY_PAID_MARKER = "уже оплачен"


def _get_headers():
    access = load_tokens().get("access")
    if not access:
        raise RuntimeError("Нет access token. Войдите в систему заново.")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access}",
    }


def _should_refresh_token(response):
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    return payload.get("code") == "token_not_valid"


def _request_with_auth(method, url, **kwargs):
    response = requests.request(method, url, headers=_get_headers(), **kwargs)
    if not _should_refresh_token(response):
        return response

    try:
        access = refresh_access_token(TOKEN_REFRESH_URL)
    except Exception as exc:
        raise RuntimeError(f"Failed to refresh payment token: {exc}") from exc

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access}",
    }
    return requests.request(method, url, headers=headers, **kwargs)


def _collect_payment_items(selected_rows):
    sheep_ids = []
    application_ids = []
    sheep_by_remote_id = {}
    applications_by_remote_id = {}

    for row in selected_rows:
        sheep = row["sheep"]
        latest_application = row.get("latest_application")
        remote_id = getattr(sheep, "remote_id", None)
        include_sheep = not bool(getattr(sheep, "is_paid", False))
        if remote_id and include_sheep:
            remote_id = int(remote_id)
            sheep_ids.append(remote_id)
            sheep_by_remote_id[remote_id] = sheep
        target_applications = row["applications"]
        if latest_application is not None:
            target_applications = [latest_application]
        for application in target_applications:
            app_remote_id = getattr(application, "remote_id", None)
            if app_remote_id and not bool(getattr(application, "is_paid", False)):
                app_remote_id = int(app_remote_id)
                application_ids.append(app_remote_id)
                applications_by_remote_id[app_remote_id] = application

    return {
        "sheep_ids": sorted(set(sheep_ids)),
        "application_ids": sorted(set(application_ids)),
        "sheep_by_remote_id": sheep_by_remote_id,
        "applications_by_remote_id": applications_by_remote_id,
    }


def _already_paid_result(status_summary=None):
    status_summary = status_summary or {}
    return {
        "already_paid": True,
        "quantity": 0,
        "total_amount": 0,
        "checked_items": status_summary.get("checked_items", 0),
        "paid_items": status_summary.get("paid_items", 0),
    }


def create_payment(session, selected_rows):
    # Reconcile local flags first. This prevents creating a second payment when
    # another device has already completed it.
    status_summary = _refresh_statuses_by_items(session, selected_rows)
    session.commit()

    payment_items = _collect_payment_items(selected_rows)
    sheep_ids = payment_items["sheep_ids"]
    application_ids = payment_items["application_ids"]

    if not sheep_ids and not application_ids:
        return _already_paid_result(status_summary)

    response = _request_with_auth(
        "POST",
        CREATE_PAYMENT_URL,
        json={
            "sheep_ids": sorted(set(sheep_ids)),
            "application_ids": sorted(set(application_ids)),
        },
    )
    payload = _parse_json(response)
    if response.status_code != 201:
        detail = payload.get("detail") if isinstance(payload, dict) else response.text
        if response.status_code == 400 and ALREADY_PAID_MARKER in str(detail).lower():
            status_summary = _refresh_statuses_by_items(session, selected_rows)
            session.commit()
            return _already_paid_result(status_summary)
        raise RuntimeError(detail or "Не удалось создать оплату.")

    reference = payload.get("reference")
    payment_token = payload.get("payment_token")
    already_paid_sheep_ids = _extract_id_set(payload, "already_paid_sheep_ids")
    already_paid_application_ids = _extract_id_set(
        payload,
        "already_paid_application_ids",
    )

    for remote_id, sheep in payment_items["sheep_by_remote_id"].items():
        if remote_id in already_paid_sheep_ids:
            sheep.is_paid = True
            continue
        sheep.payment_reference = reference
        sheep.payment_token = payment_token
    for remote_id, application in payment_items["applications_by_remote_id"].items():
        if remote_id in already_paid_application_ids:
            application.is_paid = True
            continue
        application.payment_reference = reference
        application.payment_token = payment_token
    session.commit()
    return payload


def refresh_payment_statuses(session, selected_rows):
    references = {}
    rows_without_reference = []
    for row in selected_rows:
        sheep = row["sheep"]
        row_references = set()
        sheep_reference = getattr(sheep, "payment_reference", None)
        if sheep_reference:
            row_references.add(sheep_reference)
        for application in row["applications"]:
            app_reference = getattr(application, "payment_reference", None)
            if app_reference:
                row_references.add(app_reference)
        if not row_references:
            rows_without_reference.append(row)
            continue
        for reference in row_references:
            references.setdefault(reference, []).append(row)

    if not references and not rows_without_reference:
        raise RuntimeError("У выбранных овец нет созданной оплаты.")

    summary = {
        "checked_references": 0,
        "paid_references": 0,
        "checked_items": 0,
        "paid_items": 0,
        "used_reference_check": False,
        "used_items_check": False,
    }

    for reference, rows in references.items():
        status_url = build_api_url(f"/api/payments/mkassa/{reference}/status/")
        response = _request_with_auth("GET", status_url)
        payload = _parse_json(response)
        if response.status_code != 200:
            detail = payload.get("detail") if isinstance(payload, dict) else response.text
            raise RuntimeError(detail or "Не удалось проверить статус оплаты.")

        is_paid = payload.get("status") == "paid"
        payment_token = payload.get("payment_token")
        for row in rows:
            sheep = row["sheep"]
            if payment_token and getattr(sheep, "payment_reference", None) == reference:
                sheep.payment_token = payment_token
            for application in row["applications"]:
                if (
                    payment_token
                    and getattr(application, "payment_reference", None) == reference
                ):
                    application.payment_token = payment_token

        summary["used_reference_check"] = True
        summary["checked_references"] += 1
        if is_paid:
            summary["paid_references"] += 1

    # A reference may cover only one repeat application, not every object in
    # the displayed row. The by-items endpoint is authoritative for local flags.
    items_summary = _refresh_statuses_by_items(session, selected_rows)
    summary["used_items_check"] = True
    summary["checked_items"] += items_summary["checked_items"]
    summary["paid_items"] += items_summary["paid_items"]

    session.commit()
    return summary


def _refresh_statuses_by_items(session, rows_without_reference):
    sheep_by_remote_id = {}
    app_by_remote_id = {}

    for row in rows_without_reference:
        sheep = row["sheep"]
        sheep_remote_id = getattr(sheep, "remote_id", None)
        if sheep_remote_id is not None:
            sheep_by_remote_id[int(sheep_remote_id)] = sheep

        latest_application = row.get("latest_application")
        target_apps = [latest_application] if latest_application is not None else row.get("applications", [])
        for app in target_apps:
            app_remote_id = getattr(app, "remote_id", None)
            if app_remote_id is not None:
                app_by_remote_id[int(app_remote_id)] = app

    sheep_ids = sorted(sheep_by_remote_id.keys())
    application_ids = sorted(app_by_remote_id.keys())
    if not sheep_ids and not application_ids:
        raise RuntimeError("Для проверки нет синхронизированных овец или бонитировок.")

    response = _request_with_auth(
        "POST",
        CHECK_BY_ITEMS_STATUS_URL,
        json={
            "sheep_ids": sheep_ids,
            "application_ids": application_ids,
        },
    )
    payload = _parse_json(response)
    if response.status_code == 404:
        raise RuntimeError(
            "Сервер не поддерживает проверку оплаты по списку ID. "
            "Добавьте endpoint статусов по sheep_ids/application_ids."
        )
    if response.status_code != 200:
        detail = payload.get("detail") if isinstance(payload, dict) else response.text
        raise RuntimeError(detail or "Не удалось проверить статус оплаты по списку.")

    paid_sheep_ids, unpaid_sheep_ids, paid_app_ids, unpaid_app_ids = _extract_paid_unpaid_lists(payload)

    for remote_id, sheep in sheep_by_remote_id.items():
        if remote_id in paid_sheep_ids:
            sheep.is_paid = True
        elif remote_id in unpaid_sheep_ids:
            sheep.is_paid = False

    for remote_id, app in app_by_remote_id.items():
        if remote_id in paid_app_ids:
            app.is_paid = True
        elif remote_id in unpaid_app_ids:
            app.is_paid = False

    return {
        "checked_items": len(sheep_ids) + len(application_ids),
        "paid_items": len(paid_sheep_ids) + len(paid_app_ids),
    }


def _extract_paid_unpaid_lists(payload):
    if not isinstance(payload, dict):
        return set(), set(), set(), set()

    paid_sheep_ids = _extract_id_set(payload, "paid_sheep_ids", "sheep_paid_ids", "paid_sheep")
    unpaid_sheep_ids = _extract_id_set(payload, "unpaid_sheep_ids", "sheep_unpaid_ids", "unpaid_sheep")
    paid_app_ids = _extract_id_set(payload, "paid_application_ids", "application_paid_ids", "paid_applications")
    unpaid_app_ids = _extract_id_set(payload, "unpaid_application_ids", "application_unpaid_ids", "unpaid_applications")

    paid_obj = payload.get("paid")
    if isinstance(paid_obj, dict):
        paid_sheep_ids |= _extract_id_set(paid_obj, "sheep_ids", "sheep", "ids")
        paid_app_ids |= _extract_id_set(paid_obj, "application_ids", "applications")

    unpaid_obj = payload.get("unpaid")
    if isinstance(unpaid_obj, dict):
        unpaid_sheep_ids |= _extract_id_set(unpaid_obj, "sheep_ids", "sheep", "ids")
        unpaid_app_ids |= _extract_id_set(unpaid_obj, "application_ids", "applications")

    return paid_sheep_ids, unpaid_sheep_ids, paid_app_ids, unpaid_app_ids


def _extract_id_set(source, *keys):
    result = set()
    if not isinstance(source, dict):
        return result
    for key in keys:
        values = source.get(key)
        if isinstance(values, list):
            for value in values:
                try:
                    result.add(int(value))
                except Exception:
                    continue
    return result


def _parse_json(response):
    try:
        return response.json()
    except Exception:
        return {}
