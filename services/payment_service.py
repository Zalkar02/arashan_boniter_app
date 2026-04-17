import requests

from api_config import build_api_url
from services.auth_service import load_tokens, refresh_access_token


CREATE_PAYMENT_URL = build_api_url("/api/payments/mkassa/dynamic-qr/")
TOKEN_REFRESH_URL = build_api_url("/api/token/refresh/")
CHECK_BY_ITEMS_STATUS_URL = build_api_url("/api/payments/mkassa/statuses/by-items/")


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


def create_payment(session, selected_rows):
    sheep_ids = []
    application_ids = []
    local_sheep = []
    local_applications = []

    for row in selected_rows:
        sheep = row["sheep"]
        latest_application = row.get("latest_application")
        remote_id = getattr(sheep, "remote_id", None)
        include_sheep = not bool(getattr(sheep, "is_paid", False))
        if remote_id and include_sheep:
            sheep_ids.append(remote_id)
            local_sheep.append(sheep)
        target_applications = row["applications"]
        if latest_application is not None:
            target_applications = [latest_application]
        for application in target_applications:
            app_remote_id = getattr(application, "remote_id", None)
            if app_remote_id and not bool(getattr(application, "is_paid", False)):
                application_ids.append(app_remote_id)
                local_applications.append(application)

    if not sheep_ids and not application_ids:
        raise RuntimeError("Для оплаты нет синхронизированных овец или бонитировок.")

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
        raise RuntimeError(detail or "Не удалось создать оплату.")

    reference = payload.get("reference")
    payment_token = payload.get("payment_token")
    for sheep in local_sheep:
        sheep.payment_reference = reference
        sheep.payment_token = payment_token
    for application in local_applications:
        application.payment_reference = reference
        application.payment_token = payment_token
    session.commit()
    return payload


def refresh_payment_statuses(session, selected_rows):
    references = {}
    rows_without_reference = []
    for row in selected_rows:
        sheep = row["sheep"]
        sheep_reference = getattr(sheep, "payment_reference", None)
        if sheep_reference:
            references.setdefault(sheep_reference, []).append(row)
            continue
        has_reference = False
        for application in row["applications"]:
            app_reference = getattr(application, "payment_reference", None)
            if app_reference:
                references.setdefault(app_reference, []).append(row)
                has_reference = True
                break
        if not has_reference:
            rows_without_reference.append(row)

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
            sheep.payment_reference = reference
            if payment_token:
                sheep.payment_token = payment_token
            if is_paid:
                sheep.is_paid = True
            for application in row["applications"]:
                application.payment_reference = reference
                if payment_token:
                    application.payment_token = payment_token
                if is_paid:
                    application.is_paid = True

        summary["used_reference_check"] = True
        summary["checked_references"] += 1
        if is_paid:
            summary["paid_references"] += 1

    if rows_without_reference:
        items_summary = _refresh_statuses_by_items(session, rows_without_reference)
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
