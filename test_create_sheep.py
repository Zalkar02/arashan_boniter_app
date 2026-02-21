from db.models import Sheep, User, Color, Application, Boniter, init_db
import datetime

session = init_db()

# --- Создаём цвет ---
color = session.query(Color).filter_by(name="Тестовый белый").first()
if not color:
    color = Color(name="Тестовый белый", synced=False)
    session.add(color)
    session.commit()
    print("Цвет создан:", color.name)

# --- Создаём пользователя ---
user = session.query(User).filter_by(username="test_owner").first()
if not user:
    user = User(
        username="test_owner",
        name="Тест Владелец",
        phone="996500000000",
        region="Бишкек",
        area="Центр",
        city="Бишкек",
        home="улица 1",
        synced=False
    )
    session.add(user)
    session.commit()
    print("Пользователь создан:", user.username)

# --- Создаём бонитёра ---
boniter = session.query(Boniter).filter_by(name="Zalkar").first()
if not boniter:
    boniter = Boniter(name="Zalkar", contact_info="test")
    session.add(boniter)
    session.commit()
    print("Бонитёр создан:", boniter.name)

# --- Создаём овцу ---
sheep_id_n = "996000000998888"
sheep = session.query(Sheep).filter_by(id_n=sheep_id_n).first()
if not sheep:
    sheep = Sheep(
        id_n=sheep_id_n,
        nick="Овца с бонитировкой",
        dob=datetime.date(2022, 6, 1),
        gender="O",
        rank="1",
        is_paid=False,
        synced=False,
        owner=user,
        color=color,
        date_filling=datetime.date.today()
    )
    session.add(sheep)
    session.commit()
    print("Овца создана:", sheep.nick)
else:
    print("Овца уже существует:", sheep.nick)

# --- Создаём бонитировку ---
existing_app = session.query(Application).filter_by(sheep_id=sheep.id).first()
if not existing_app:
    application = Application(
        sheep=sheep,
        weight=80.0,
        crest_height=95.0,
        sacrum_height=95.0,
        oblique_torso=100.0,
        chest_width=30.0,
        chest_depth=45.0,
        maklokakh_width=28.0,
        chest_girth=110.0,
        kurdyk_girth=90.0,
        kurdyk_form="Округлая",
        pasterns_girth=10.0,
        ears_height=22.0,
        ears_width=9.0,
        head_height=32.0,
        head_width=12.0,
        exterior=4,
        rank="1",
        date=datetime.date.today(),
        note="Тестовая бонитировка",
        boniter=boniter.id,
        is_paid=False,
        synced=False
    )
    session.add(application)
    session.commit()
    print("Бонитировка создана.")
else:
    print("Бонитировка уже существует.")
