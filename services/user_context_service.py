def get_current_user_name(user: dict | None) -> str:
    if not user:
        return "Неопознанный оператор"
    return user.get("name") or user.get("username") or ""
