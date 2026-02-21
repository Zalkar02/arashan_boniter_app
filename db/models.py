from sqlalchemy import (
    Column, Integer, String, Date, Boolean, ForeignKey,
    Float, DateTime, Numeric, Text, Table, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime

Base = declarative_base()

# связь "овца ↔ родители" (self many-to-many)
sheep_parents = Table(
    "sheep_parents",
    Base.metadata,
    Column("sheep_id", Integer, ForeignKey("sheep.id"), primary_key=True),
    Column("parent_id", Integer, ForeignKey("sheep.id"), primary_key=True),
)

# 👤 Пользователь
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    username = Column(String, unique=True)
    password = Column(String)                # пароль
    name = Column(String)
    phone = Column(String)
    region = Column(String)
    area = Column(String)
    city = Column(String)
    home = Column(String)

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class Color(Base):
    __tablename__ = 'colors'

    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)  # ID на сервере (для синхронизации)
    name = Column(String, unique=True, nullable=False)  # название цвета
    is_deleted = Column(Boolean, default=False)

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Color(name='{self.name}')>"


# 🐑 Овца
class Sheep(Base):
    __tablename__ = 'sheep'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    id_n = Column(String, unique=True)
    nick = Column(String)
    dob = Column(Date)
    gender = Column(String)
    comment = Column(String)
    rank = Column(String)
    color_id = Column(Integer, ForeignKey("colors.id"), nullable=True)
    color = relationship("Color")
    date_filling = Column(Date, default=datetime.date.today)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    owner = relationship("User")
    price = Column(Numeric(10, 0), nullable=True)
    currency = Column(String(1), default="K")
    is_negotiable_price = Column(Boolean, default=False)
    sell = Column(Boolean, default=False)
    out = Column(Boolean, default=False)
    hide = Column(Boolean, default=False)
    boniter = Column(Integer, ForeignKey("boniters.id"), nullable=True)
    boniter_rel = relationship("Boniter")
    is_paid = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

    parents = relationship(
        "Sheep",
        secondary=sheep_parents,
        primaryjoin=id == sheep_parents.c.sheep_id,
        secondaryjoin=id == sheep_parents.c.parent_id,
        backref="children",
    )


# 👥 Владелец (связь Sheep ↔ User)
class Owner(Base):
    __tablename__ = 'owners'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    sheep_id = Column(Integer, ForeignKey('sheep.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))
    owner_bool = Column(Boolean, default=False)  # текущий или нет
    date1 = Column(Date, default=datetime.date.today)
    date2 = Column(Date, nullable=True)

    sheep = relationship("Sheep")
    owner = relationship("User")

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class Boniter(Base):
    __tablename__ = 'boniters'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    name = Column(String)
    contact_info = Column(Text, nullable=True)

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


# 📝 Бонитировка
class Application(Base):
    __tablename__ = 'applications'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    sheep_id = Column(Integer, ForeignKey('sheep.id'))
    sheep = relationship("Sheep")
    weight = Column(Float)
    crest_height = Column(Float)
    sacrum_height = Column(Float)
    oblique_torso = Column(Float)
    chest_width = Column(Float)
    chest_depth = Column(Float)
    maklokakh_width = Column(Float)
    chest_girth = Column(Float)
    kurdyk_girth = Column(Float)
    kurdyk_form = Column(String)
    pasterns_girth = Column(Float)
    ears_height = Column(Float)
    ears_width = Column(Float)
    head_height = Column(Float)
    head_width = Column(Float)
    size = Column(String, nullable=True)
    fur_structure = Column(String, nullable=True)
    exterior = Column(Integer)
    rank = Column(String)
    date = Column(Date)
    note = Column(String)
    boniter = Column(Integer, ForeignKey("boniters.id"), nullable=True)
    boniter_rel = relationship("Boniter")
    is_paid = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class Photo(Base):
    __tablename__ = 'photos'
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, nullable=True)
    sheep_id = Column(Integer, ForeignKey('sheep.id'))
    sheep = relationship("Sheep")
    image = Column(String)

    synced = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


# 📦 Инициализация базы
def init_db(path="sheep_local.db"):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
