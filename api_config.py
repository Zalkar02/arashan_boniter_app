import os


API_HOST = os.getenv("API_HOST", "https://arashan.zet.kg").rstrip("/")


def build_api_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{API_HOST}{normalized}"
