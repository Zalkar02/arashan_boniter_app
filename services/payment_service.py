import requests

from api_config import build_api_url
from services.auth_service import load_tokens, refresh_access_token


CREATE_PAYMENT_URL = build_api_url("/api/payments/mkassa/dynamic-qr/")
TOKEN_REFRESH_URL = build_api_url("/api/token/refresh/")


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
        record_type = row.get("record_type")
        remote_id = getattr(sheep, "remote_id", None)
        if remote_id and record_type != "Бонитр.":
            sheep_ids.append(remote_id)
            local_sheep.append(sheep)
        target_applications = row["applications"]
        if latest_application is not None:
            target_applications = [latest_application]
        for application in target_applications:
            app_remote_id = getattr(application, "remote_id", None)
            if app_remote_id:
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
    for row in selected_rows:
        sheep = row["sheep"]
        sheep_reference = getattr(sheep, "payment_reference", None)
        if sheep_reference:
            references.setdefault(sheep_reference, []).append(row)
            continue
        for application in row["applications"]:
            app_reference = getattr(application, "payment_reference", None)
            if app_reference:
                references.setdefault(app_reference, []).append(row)
                break

    if not references:
        raise RuntimeError("У выбранных овец нет созданной оплаты.")

    results = []
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
        results.append(payload)

    session.commit()
    return results


def _parse_json(response):
    try:
        return response.json()
    except Exception:
        return {}
