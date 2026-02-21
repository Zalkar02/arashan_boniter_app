# migrate_users_add_cols.py — одноразовая миграция для SQLite (users)
from sqlalchemy import create_engine, text

# 👉 если у тебя путь другой — поправь:
DB_URL = "sqlite:///sheep_local.db"

NEEDED_COLS = {
    "password": "VARCHAR",
    "region": "VARCHAR",
    "area": "VARCHAR",
    "city": "VARCHAR",
    "home": "VARCHAR",
    "username": "VARCHAR",  # на всякий случай, если старый дамп без логина
}

def get_columns(conn):
    res = conn.execute(text("PRAGMA table_info(users)"))
    return {row[1] for row in res}  # set of column names

def add_column(conn, name, sqltype):
    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sqltype}"))

def ensure_unique_index_on_username(conn):
    # создадим уникальный индекс (в SQLite это ок вместо constraint)
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
    ))

def main():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        cols = get_columns(conn)

        for col, sqltype in NEEDED_COLS.items():
            if col not in cols:
                add_column(conn, col, sqltype)

        ensure_unique_index_on_username(conn)

    print("✅ Migration done.")

if __name__ == "__main__":
    main()
