# user_create.py — создание пользователя/владельца без .ui
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt

try:
    from db.models import init_db, User
    db = init_db()
except Exception as e:
    db = None
    User = None
    _db_error = str(e)
else:
    _db_error = None


# Справочники
REGION_CHOICES = [
    ("B", "Баткен"),
    ("1", "Бишкек"),
    ("J", "Джалал-Абад"),
    ("I", "Иссык-Куль"),
    ("N", "Нарын"),
    ("O", "Ош"),
    ("T", "Талас"),
    ("C", "Чуй"),
]

AREA_CHOICES = [
    ("1", "Ак-Суйский район"),
    ("2", "Ак-Талинский район"),
    ("3", "Аксыйский район"),
    ("4", "Ала-Букинский район"),
    ("5", "Алайский район"),
    ("6", "Аламудунский район"),
    ("7", "Араванский район"),
    ("8", "Ат-Башынский район"),
    ("45", "Айтматовский район"),
    ("9", "Базар-Коргонский район"),
    ("10", "Бакай-Атинский район"),
    ("11", "Баткенский район"),
    ("12", "Джумгальский район"),
    ("13", "Жайылский район"),
    ("14", "Жети-Огузский район"),
    ("15", "Иссык-Кульский район"),
    ("16", "Кадамжайский район"),
    ("17", "Кара-Бууринский район"),
    ("18", "Кара-Кулжинский район"),
    ("19", "Кара-Сууский район"),
    ("20", "Кеминский район"),
    ("21", "Кочкорский район"),
    ("44", "Ленинский район"),
    ("22", "Лейлекский район"),
    ("23", "Манасский район"),
    ("24", "Московский район"),
    ("25", "Нарынский район"),
    ("26", "Ноокатский район"),
    ("27", "Ноокенский район"),
    ("41", "Октябрьский район"),
    ("42", "Первомайский район"),
    ("28", "Панфиловский район"),
    ("43", "Свердловский район"),
    ("29", "Сокулукский район"),
    ("30", "Сузакский район"),
    ("31", "Таласский район"),
    ("32", "Тогуз-Тороуский район"),
    ("33", "Токтогульский район"),
    ("34", "Тонский район"),
    ("35", "Тюпский район"),
    ("36", "Узгенский район"),
    ("37", "Чаткальский район"),
    ("38", "Чон-Алайский район"),
    ("39", "Чуйский район"),
    ("40", "Ысык-Атинский район"),
]

# area_code -> region_code (как в REGION_CHOICES: B, 1, J, I, N, O, T, C)
AREA_TO_REGION = {
    "1": "I",   # Ак-Суйский → Иссык-Куль
    "2": "N",   # Ак-Талинский → Нарын
    "3": "J",   # Аксыйский → Джалал-Абад
    "4": "J",   # Ала-Букинский → Джалал-Абад
    "5": "O",   # Алайский → Ош
    "6": "C",   # Аламудунский → Чуй
    "7": "O",   # Араванский → Ош
    "8": "N",   # Ат-Башынский → Нарын
    "45":"T",   # Айтматовский → Талас
    "9": "J",   # Базар-Коргонский → Джалал-Абад
    "10":"T",   # Бакай-Атинский → Талас
    "11":"B",   # Баткенский → Баткен
    "12":"N",   # Джумгальский → Нарын
    "13":"C",   # Жайылский → Чуй
    "14":"I",   # Жети-Огузский → Иссык-Куль
    "15":"I",   # Иссык-Кульский → Иссык-Куль
    "16":"B",   # Кадамжайский → Баткен
    "17":"T",   # Кара-Бууринский → Талас
    "18":"O",   # Кара-Кулжинский → Ош
    "19":"O",   # Кара-Сууский → Ош
    "20":"C",   # Кеминский → Чуй
    "21":"N",   # Кочкорский → Нарын
    "44":"1",   # Ленинский → Бишкек (город)
    "22":"B",   # Лейлекский → Баткен
    "23":"T",   # Манасский → Талас
    "24":"C",   # Московский → Чуй
    "25":"N",   # Нарынский → Нарын
    "26":"O",   # Ноокатский → Ош
    "27":"J",   # Ноокенский → Джалал-Абад
    "41":"1",   # Октябрьский → Бишкек (город)
    "42":"1",   # Первомайский → Бишкек (город)
    "28":"C",   # Панфиловский → Чуй
    "43":"1",   # Свердловский → Бишкек (город)
    "29":"C",   # Сокулукский → Чуй
    "30":"J",   # Сузакский → Джалал-Абад
    "31":"T",   # Таласский → Талас
    "32":"J",   # Тогуз-Тороуский → Джалал-Абад
    "33":"J",   # Токтогульский → Джалал-Абад
    "34":"I",   # Тонский → Иссык-Куль
    "35":"I",   # Тюпский → Иссык-Куль
    "36":"O",   # Узгенский → Ош
    "37":"J",   # Чаткальский → Джалал-Абад
    "38":"O",   # Чон-Алайский → Ош
    "39":"C",   # Чуйский → Чуй
    "40":"C",   # Ысык-Атинский → Чуй
}



class OwnerCreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать владельца")
        self.resize(500, 450)
        self.setModal(True)
        self.created_id = None

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form, 1)

        # Поля
        self.ed_username = QLineEdit(); form.addRow("Логин", self.ed_username)
        self.ed_password = QLineEdit(); form.addRow("Пароль", self.ed_password)
        self.ed_name = QLineEdit(); form.addRow("ФИО", self.ed_name)
        self.ed_phone = QLineEdit(); form.addRow("Телефон", self.ed_phone)

        self.cb_region = QComboBox()
        self.cb_region.addItem("— выберите —", None)
        for code, label in REGION_CHOICES:
            self.cb_region.addItem(label, code)
        form.addRow("Область", self.cb_region)

        # --- РАЙОН (зависит от области) ---
        self.cb_area = QComboBox()
        self.cb_area.addItem("— выберите —", None)
        self.cb_area.setEnabled(False)  # пока область не выбрана
        form.addRow("Район", self.cb_area)

        # связь: при смене области — пересобрать районы
        self.cb_region.currentIndexChanged.connect(
            lambda _: self._refill_areas_for_region(self.cb_region.currentData())
        )

        self.ed_city = QLineEdit(); form.addRow("Город/Село", self.ed_city)
        self.ed_home = QLineEdit(); form.addRow("Улица, дом", self.ed_home)

        # Кнопки
        row = QHBoxLayout()
        root.addLayout(row)
        self.btn_cancel = QPushButton("Отмена"); self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Сохранить"); self.btn_save.clicked.connect(self._save)
        row.addStretch(1); row.addWidget(self.btn_cancel); row.addWidget(self.btn_save)

    def _save(self):
        if db is None or User is None:
            QMessageBox.critical(self, "БД", f"База недоступна.\n{_db_error or ''}")
            self.reject()
            return
        
        if not self._validate():
            return

        username = self.ed_username.text().strip()
        password = self.ed_password.text().strip()
        name = self.ed_name.text().strip()
        
        self._ensure_area_valid_for_region()

        u = User()
        u.username = username
        u.password = password   # ⚠️ пока в чистом виде; для реального проекта нужно хэшировать!
        u.name = name
        u.phone = self.ed_phone.text().strip()
        u.region = self.cb_region.currentData()
        u.area = self.cb_area.currentData()
        u.city = self.ed_city.text().strip()
        u.home = self.ed_home.text().strip()

        try:
            db.add(u)
            db.commit()
            self.created_id = u.id
            QMessageBox.information(self, "Готово", "Владелец создан")
            self.accept()
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Ошибка БД", str(e))
        
    def _refill_areas_for_region(self, region_code):
        """Пересобирает список районов под выбранную область."""
        self.cb_area.blockSignals(True)
        self.cb_area.clear()
        self.cb_area.addItem("— выберите —", None)

        if region_code is None:
            self.cb_area.setEnabled(False)
            self.cb_area.blockSignals(False)
            return

        # добавляем только районы этой области
        for code, label in AREA_CHOICES:
            if AREA_TO_REGION.get(code) == region_code:
                self.cb_area.addItem(label, code)

        self.cb_area.setEnabled(True)
        self.cb_area.setCurrentIndex(0)  # курсор на плейсхолдер
        self.cb_area.blockSignals(False)

    def _ensure_area_valid_for_region(self):
        """Если выбранный район не относится к области — сбросить на пустой."""
        region_code = self.cb_region.currentData()
        area_code = self.cb_area.currentData()
        if area_code is None:
            return
        if AREA_TO_REGION.get(area_code) != region_code:
            self.cb_area.setCurrentIndex(0)
    
    def _validate(self) -> bool:
        if db is None or User is None:
            QMessageBox.critical(self, "БД", f"База недоступна.\n{_db_error or ''}")
            return False

        username = self.ed_username.text().strip()
        password = self.ed_password.text()
        name = self.ed_name.text().strip()

        if not username:
            QMessageBox.warning(self, "Ошибка", "Заполните логин")
            self.ed_username.setFocus(); return False

        if db.query(User).filter_by(username=username).first():
            QMessageBox.warning(self, "Ошибка", "Такой логин уже есть")
            self.ed_username.setFocus(); return False

        if not password or len(password) < 6:
            QMessageBox.warning(self, "Ошибка", "Пароль должен быть не короче 6 символов")
            self.ed_password.setFocus(); return False

        if not name:
            QMessageBox.warning(self, "Ошибка", "Заполните ФИО")
            self.ed_name.setFocus(); return False

        if hasattr(self, "_ensure_area_valid_for_region"):
            self._ensure_area_valid_for_region()

        region_code = self.cb_region.currentData()
        if region_code is None:
            QMessageBox.warning(self, "Ошибка", "Выберите область")
            self.cb_region.setFocus(); return False

        area_code = self.cb_area.currentData()
        if area_code is None:
            QMessageBox.warning(self, "Ошибка", "Выберите район")
            self.cb_area.setFocus(); return False

        return True


