# migrate_sheep_add_cols.py — обновление схемы SQLite под новые поля/таблицы
from sqlalchemy import create_engine, text
from state_paths import ensure_db_path

DB_URL = f"sqlite:///{ensure_db_path()}"

TABLE_COLS = {
    "colors": {
        "is_deleted": "BOOLEAN DEFAULT 0",
    },
    "sheep": {
        "price": "NUMERIC",
        "currency": "VARCHAR(1) DEFAULT 'K'",
        "is_negotiable_price": "BOOLEAN DEFAULT 0",
        "sell": "BOOLEAN DEFAULT 0",
        "out": "BOOLEAN DEFAULT 0",
        "hide": "BOOLEAN DEFAULT 0",
        "boniter": "INTEGER",
        "created_by_guest": "BOOLEAN DEFAULT 0",
        "is_deleted": "BOOLEAN DEFAULT 0",
    },
    "applications": {
        "size": "VARCHAR",
        "fur_structure": "VARCHAR",
        "boniter": "INTEGER",
        "created_by_guest": "BOOLEAN DEFAULT 0",
        "is_deleted": "BOOLEAN DEFAULT 0",
    },
}

CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS boniters (
        id INTEGER PRIMARY KEY,
        remote_id INTEGER,
        name VARCHAR,
        contact_info TEXT,
        synced BOOLEAN DEFAULT 0,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY,
        remote_id INTEGER,
        sheep_id INTEGER,
        image VARCHAR,
        synced BOOLEAN DEFAULT 0,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sheep_parents (
        sheep_id INTEGER NOT NULL,
        parent_id INTEGER NOT NULL,
        PRIMARY KEY (sheep_id, parent_id)
    )
    """,
]

def get_columns(conn, table):
    res = conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in res}

def add_column(conn, table, name, sqltype):
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}"))

def ensure_columns(conn):
    for table, cols in TABLE_COLS.items():
        existing = get_columns(conn, table)
        for col, sqltype in cols.items():
            if col not in existing:
                add_column(conn, table, col, sqltype)

def ensure_tables(conn):
    for sql in CREATE_TABLES_SQL:
        conn.execute(text(sql))

def main():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        ensure_columns(conn)
        ensure_tables(conn)
    print("✅ Migration done.")

if __name__ == "__main__":
    main()
