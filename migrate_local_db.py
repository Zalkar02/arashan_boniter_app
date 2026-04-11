from db.models import init_db


def main():
    session = init_db()
    session.close()
    print("Local database migration complete.")


if __name__ == "__main__":
    main()
