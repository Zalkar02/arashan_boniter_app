import re
from unicodedata import normalize


REGION_LABELS = {
    "B": "Баткен",
    "1": "Бишкек",
    "J": "Джалал-Абад",
    "I": "Иссык-Куль",
    "N": "Нарын",
    "O": "Ош",
    "T": "Талас",
    "C": "Чуй",
}

AREA_LABELS = {
    "1": "Ак-Суйский район",
    "2": "Ак-Талинский район",
    "3": "Аксыйский район",
    "4": "Ала-Букинский район",
    "5": "Алайский район",
    "6": "Аламудунский район",
    "7": "Араванский район",
    "8": "Ат-Башынский район",
    "45": "Айтматовский район",
    "9": "Базар-Коргонский район",
    "10": "Бакай-Атинский район",
    "11": "Баткенский район",
    "12": "Джумгальский район",
    "13": "Жайылский район",
    "14": "Жети-Огузский район",
    "15": "Иссык-Кульский район",
    "16": "Кадамжайский район",
    "17": "Кара-Бууринский район",
    "18": "Кара-Кулжинский район",
    "19": "Кара-Сууский район",
    "20": "Кеминский район",
    "21": "Кочкорский район",
    "44": "Ленинский район",
    "22": "Лейлекский район",
    "23": "Манасский район",
    "24": "Московский район",
    "25": "Нарынский район",
    "26": "Ноокатский район",
    "27": "Ноокенский район",
    "41": "Октябрьский район",
    "42": "Первомайский район",
    "28": "Панфиловский район",
    "43": "Свердловский район",
    "29": "Сокулукский район",
    "30": "Сузакский район",
    "31": "Таласский район",
    "32": "Тогуз-Тороуский район",
    "33": "Токтогульский район",
    "34": "Тонский район",
    "35": "Тюпский район",
    "36": "Узгенский район",
    "37": "Чаткальский район",
    "38": "Чон-Алайский район",
    "39": "Чуйский район",
    "40": "Ысык-Атинский район",
}


def _norm(value: str) -> str:
    if not value:
        return ""
    value = normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.casefold()


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _display_region(value: str) -> str:
    value = (value or "").strip()
    return REGION_LABELS.get(value, value)


def _display_area(value: str) -> str:
    value = (value or "").strip()
    return AREA_LABELS.get(value, value)


def find_owners(session, user_model, raw_query: str):
    query = (raw_query or "").strip()
    query_norm = _norm(query)
    query_digits = _digits(query)

    candidates = session.query(user_model).filter_by(is_deleted=False).order_by(user_model.name).all()
    if not query:
        return candidates

    owners = []
    for owner in candidates:
        name_ok = query_norm in _norm(owner.name)
        phone_ok = bool(query_digits and query_digits in _digits(owner.phone))
        if name_ok or phone_ok:
            owners.append(owner)
    return owners


def format_owner_display(owner) -> str:
    name = owner.name or "Без имени"
    phone = (owner.phone or "").strip() or "Телефон не указан"
    location_parts = [
        _display_region(owner.region),
        _display_area(owner.area),
        (owner.city or "").strip(),
    ]
    location = ", ".join([part for part in location_parts if part]) or "Локация не указана"
    address = (owner.home or "").strip() or "Адрес не указан"
    username = (owner.username or "").strip() or "—"

    return "\n".join(
        [
            name,
            f"{phone} | {location}",
            f"{address} | логин: {username}",
        ]
    )
