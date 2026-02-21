# sheep_create.py — окно создания овцы (переработанный дизайн)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QDateEdit,
    QPushButton, QMessageBox, QDialog, QListWidget, QListWidgetItem, QCheckBox, QSpacerItem, QSizePolicy,
    QScrollArea, QFrame, QHeaderView
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QRegExp, QTimer, QPropertyAnimation, QEasingCurve, QLocale
from PyQt5.QtGui import QTextCharFormat, QBrush, QColor
from PyQt5.QtGui import QRegExpValidator

# БД-модели
try:
    from db.models import init_db, Sheep, Color, User, Application, Owner
    db = init_db()
except Exception as e:
    db = None; Sheep = None; Color = None; User = None; Application = None; Owner = None
    _db_error = str(e)
else:
    _db_error = None


# ────────────────────────────────────────────────────────────────────────────────
# Диалог выбора овцы (работает "как раньше"): фильтр по полу + текстовый поиск
# ────────────────────────────────────────────────────────────────────────────────
class SheepPickerDialog(QDialog):
    def __init__(self, parent=None, title="Выбрать овцу", gender_filter=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 520)
        self.selected_idn = None
        self._gender = (gender_filter or "").upper()   # "B" (баран) / "O" (овца) / ""

        v = QVBoxLayout(self)
        self.ed_search = QLineEdit(self); self.ed_search.setPlaceholderText("Поиск по id_n или кличке…")
        v.addWidget(self.ed_search)

        self.list = QListWidget(self); v.addWidget(self.list, 1)

        row = QHBoxLayout(); v.addLayout(row)
        btn_cancel = QPushButton("Отмена"); btn_ok = QPushButton("Выбрать")
        row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._choose)
        self.list.itemDoubleClicked.connect(lambda _: self._choose())

        self.ed_search.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        if db is None or Sheep is None:
            return

        q = (self.ed_search.text() or "").strip().casefold()
        try:
            rows = db.query(Sheep).order_by(Sheep.id.desc()).all()
        except Exception:
            rows = []

        want_gender = self._gender in ("B","O")
        for s in rows:
            # фильтр по полу (если задан)
            g = (getattr(s, "gender", "") or "").upper()
            if want_gender and g != self._gender:
                continue

            idn  = (getattr(s, "id_n", "") or "")
            nick = (getattr(s, "nick", "") or "")
            if q and (q not in idn.casefold()) and (q not in nick.casefold()):
                continue

            gender_txt = "Овца" if g == "O" else "Баран"
            it = QListWidgetItem(f"{idn or '—'} — {nick or 'без клички'} ({gender_txt})")
            it.setData(Qt.UserRole + 1, idn)   # возвращаем id_n
            self.list.addItem(it)

        if self.list.count() == 0:
            self.list.addItem(QListWidgetItem("Ничего не найдено"))

    def _choose(self):
        it = self.list.currentItem()
        if not it:
            QMessageBox.warning(self, "Выбор", "Выберите запись"); return
        idn = it.data(Qt.UserRole + 1) or ""
        if not idn:   # кликнули по "Ничего не найдено"
            return
        self.selected_idn = idn
        self.accept()


# ────────────────────────────────────────────────────────────────────────────────
# Окно создания овцы (QMainWindow) — новый «карточный» дизайн
# ────────────────────────────────────────────────────────────────────────────────
class SheepCreateWindow(QMainWindow):
    """
    - Немодальное окно; «Назад» и закрытие возвращают к выбору владельца
    - Секции: заголовок, Идентификация, Родословная, Бонитировка (целые числа)
    - «Сохранить и создать ещё» очищает форму и оставляет владельца
    - Проверка id_n: автозаполнение и подстановка данных при совпадении
    """
    created = pyqtSignal(int)  # ID созданной овцы

    def __init__(self, owner_id: int = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить овцу")
        self.resize(1120, 740)
        self.owner_id = owner_id
        self._owner_fixed = False
        self._existing_sheep_id = None
        self._suppress_restore = False
        self._checking_idn = False
        self._last_checked_idn = None
        self._shown_existing_idn = None
        self._build_ui()

        if db is None or Sheep is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
        self.statusBar().showMessage("Готово")

    # ---------- UI ----------
    def _build_ui(self):
        # Scrollable root
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        self.setCentralWidget(container)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container_layout.addWidget(scroll, 1)

        root = QWidget()
        scroll.setWidget(root)

        main = QVBoxLayout(root)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        # Общий стиль для групп
        self.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel.formlabel { color:#444; min-width: 180px; }
            QPushButton { padding:6px 12px; }
            QComboBox:focus { border: 2px solid #1f6feb; }
            QComboBox:focus QAbstractItemView { outline: none; }
        """)

        # ── Заголовок (владелец жирным) ───────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Добавить овцу")
        tf = title.font(); tf.setPointSize(tf.pointSize()+6); tf.setBold(True); title.setFont(tf)
        header.addWidget(title)

        header.addStretch(1)

        if self.owner_id is not None and db and User:
            u = db.query(User).get(self.owner_id)
            self._owner_fixed = True
            owner_lbl = QLabel(f"Владелец: <b>{getattr(u, 'name', 'ID ' + str(self.owner_id))}</b>")
        else:
            self._owner_fixed = False
            self.cb_owner = QComboBox()
            self.cb_owner.addItem("— выберите —", None)
            if db and User:
                try:
                    for u in db.query(User).order_by(User.name).all():
                        self.cb_owner.addItem(u.name or f"ID {u.id}", u.id)
                except Exception:
                    pass
            self.cb_owner.setStyleSheet("font-weight: 600;")
            owner_lbl = QWidget()
            ol = QHBoxLayout(owner_lbl); ol.setContentsMargins(0,0,0,0)
            ol.addWidget(QLabel("Владелец:")); ol.addWidget(self.cb_owner); ol.addStretch(1)

        header.addWidget(owner_lbl)
        main.addLayout(header)

        # ── Секции слева/справа (без сплиттера, аккуратные карточки) ─────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        main.addLayout(top_row)

        gb_ident = QGroupBox("Идентификация")
        gb_pedig = QGroupBox("Родословная")
        top_row.addWidget(gb_ident, 1)
        top_row.addWidget(gb_pedig, 1)

        # Идентификация: формы в две колонки
        f1 = QFormLayout(); f1.setHorizontalSpacing(16); f1.setVerticalSpacing(10)
        gb_ident.setLayout(f1)

        self.ed_idn = QLineEdit(); self.ed_idn.setPlaceholderText("15 цифр. Пример: 996000000000123")
        self.ed_idn.setValidator(QRegExpValidator(QRegExp(r"^\d{0,15}$")))
        f1.addRow(self._lab("ID №*"), self.ed_idn)

        self.ed_nick = QLineEdit()
        f1.addRow(self._lab("Кличка"), self.ed_nick)

        self.dt_date = QDateEdit(calendarPopup=True); self.dt_date.setDisplayFormat("dd.MM.yyyy"); self.dt_date.setDate(QDate.currentDate())
        f1.addRow(self._lab("Дата бонитировки"), self.dt_date)

        self.dt_dob = QDateEdit(calendarPopup=True); self.dt_dob.setDisplayFormat("dd.MM.yyyy"); self.dt_dob.setDate(QDate.currentDate())
        f1.addRow(self._lab("Дата рождения*"), self.dt_dob)

        # Локализация и стиль календаря
        ru_locale = QLocale(QLocale.Russian, QLocale.Russia)
        self.dt_date.setLocale(ru_locale)
        self.dt_dob.setLocale(ru_locale)
        cal_style = """
            QCalendarWidget QWidget { color: #111; background: #ffffff; }
            QCalendarWidget QAbstractItemView:enabled {
                color: #111;
                background-color: #ffffff;
                selection-background-color: #1f6feb;
                selection-color: #ffffff;
            }
            QCalendarWidget QAbstractItemView:disabled {
                color: #9aa0a6;
                background-color: #f4f5f7;
            }
            QCalendarWidget QAbstractItemView::item {
                height: 24px;
                width: 24px;
            }
            QCalendarWidget QToolButton {
                color: #111;
                background: #f4f5f7;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QCalendarWidget QToolButton:hover { background: #e9edf5; }
            QCalendarWidget QToolButton#qt_calendar_monthbutton { font-weight: 600; }
            QCalendarWidget QHeaderView::section {
                background: #111111;
                color: #ffffff;
                padding: 2px 0;
                border: 1px solid #111111;
            }
        """
        cal_date = self.dt_date.calendarWidget()
        cal_dob = self.dt_dob.calendarWidget()
        cal_date.setStyleSheet(cal_style)
        cal_dob.setStyleSheet(cal_style)
        # Заголовок дней недели иногда не берёт стиль из календаря, задаём формат принудительно
        wd_fmt = QTextCharFormat()
        wd_fmt.setForeground(QBrush(QColor("#ffffff")))
        wd_fmt.setBackground(QBrush(QColor("#111111")))
        for cal in (cal_date, cal_dob):
            for day in range(1, 8):
                cal.setWeekdayTextFormat(day, wd_fmt)

        self.ed_age = QLineEdit(); self.ed_age.setPlaceholderText("Г.Г, напр. 2.3 или 2,3")
        f1.addRow(self._lab("Возраст"), self.ed_age)

        self.cb_gender = QComboBox(); self.cb_gender.addItem("Овца", "O"); self.cb_gender.addItem("Баран", "B")
        f1.addRow(self._lab("Пол*"), self.cb_gender)

        self.cb_color = QComboBox(); self.cb_color.addItem("— выберите —", None)
        if db and Color:
            try:
                for c in db.query(Color).order_by(Color.name).all():
                    self.cb_color.addItem(c.name, c.id)
            except Exception:
                pass
        f1.addRow(self._lab("Окрас*"), self.cb_color)

        # Родословная
        f2 = QFormLayout(); f2.setHorizontalSpacing(16); f2.setVerticalSpacing(10)
        gb_pedig.setLayout(f2)

        row_f = QHBoxLayout()
        self.ed_father = QLineEdit(); self.ed_father.setPlaceholderText("id_n отца"); self.ed_father.setReadOnly(True)
        btn_f_pick = QPushButton("Выбрать…"); btn_f_pick.setShortcut("F2"); btn_f_pick.clicked.connect(self._pick_father)
        btn_f_clear = QPushButton("×"); btn_f_clear.setToolTip("Очистить"); btn_f_clear.clicked.connect(lambda: self.ed_father.clear())
        row_f.addWidget(self.ed_father, 1); row_f.addWidget(btn_f_pick); row_f.addWidget(btn_f_clear)
        f2.addRow(self._lab("Отец"), row_f)

        row_m = QHBoxLayout()
        self.ed_mother = QLineEdit(); self.ed_mother.setPlaceholderText("id_n матери"); self.ed_mother.setReadOnly(True)
        btn_m_pick = QPushButton("Выбрать…"); btn_m_pick.setShortcut("F3"); btn_m_pick.clicked.connect(self._pick_mother)
        btn_m_clear = QPushButton("×"); btn_m_clear.setToolTip("Очистить"); btn_m_clear.clicked.connect(lambda: self.ed_mother.clear())
        row_m.addWidget(self.ed_mother, 1); row_m.addWidget(btn_m_pick); row_m.addWidget(btn_m_clear)
        f2.addRow(self._lab("Мать"), row_m)

        self.txt_comment = QPlainTextEdit(); self.txt_comment.setPlaceholderText("Комментарий…"); self.txt_comment.setFixedHeight(92)
        self.txt_comment.setTabChangesFocus(True)
        f2.addRow(self._lab("Комментарий"), self.txt_comment)

        # ── Бонитировка ───────────────────────────────────────────────────────
        self.chk_app = QCheckBox("Добавить бонитировку (Ctrl+B)")
        self.chk_app.setShortcut("Ctrl+B")
        main.addWidget(self.chk_app)

        gb_app = QGroupBox("Бонитировка")
        main.addWidget(gb_app, 0)
        v_app = QVBoxLayout(); v_app.setContentsMargins(12,12,12,12); v_app.setSpacing(10)
        gb_app.setLayout(v_app)
        self.gb_app = gb_app

        app_form = QFormLayout(); app_form.setHorizontalSpacing(16); app_form.setVerticalSpacing(8)
        v_app.addLayout(app_form)

        def isb(required_min, maximum, suffix):
            sp = QDoubleSpinBox()
            # 0 = пусто, реальные значения начинаются с required_min
            sp.setRange(0, maximum)
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.setSpecialValueText("—")
            sp.setValue(0)
            if suffix: sp.setSuffix(" " + suffix)
            sp._req_min = required_min
            return sp

        # порядок замеров как в бланке
        self.sp_weight = isb(40, 250, "кг")
        self.sp_crest_height = isb(70, 120, "см")
        self.sp_sacrum_height = isb(70, 120, "см")
        self.sp_oblique_torso = isb(60, 120, "см")
        self.sp_chest_width = isb(15, 45, "см")
        self.sp_chest_depth = isb(27, 60, "см")
        self.sp_maklokakh = isb(15, 40, "см")
        self.sp_chest_girth = isb(60, 150, "см")
        self.sp_kurdyk_girth = isb(35, 160, "см")
        self.cb_kurdyk = QComboBox(); self.cb_kurdyk.addItems(["—","Приподнятый","Средний","Приспущенный"])
        self.sp_pasterns = isb(7, 15, "см")
        self.sp_ears_height = isb(17, 27, "см")
        self.sp_ears_width = isb(7, 15, "см")
        self.sp_head_height = isb(24, 40, "см")
        self.sp_head_width = isb(7, 15, "см")

        self.sp_exterior = QSpinBox(); self.sp_exterior.setRange(1, 5); self.sp_exterior.setValue(1)
        self.cb_size = QComboBox(); self.cb_size.addItems(["—","Крупный","Средний","Мелкий"])
        self.cb_fur = QComboBox(); self.cb_fur.addItems(["—","Крепкая","Рыхлая"])
        self.cb_rank = QComboBox()
        self.cb_rank.addItem("—", None)
        self.cb_rank.addItem("E — Элита", "E")
        self.cb_rank.addItem("1 — 1-й", "1")
        self.cb_rank.addItem("2 — 2-й", "2")
        self.cb_rank.addItem("B — Брак", "B")
        self.txt_note = QPlainTextEdit(); self.txt_note.setFixedHeight(76)
        self.txt_note.setTabChangesFocus(True)

        # запрещаем значения меньше требуемого минимума, если поле не пустое
        for sp in (
            self.sp_weight, self.sp_crest_height, self.sp_sacrum_height, self.sp_oblique_torso,
            self.sp_chest_width, self.sp_chest_depth, self.sp_maklokakh, self.sp_chest_girth,
            self.sp_kurdyk_girth, self.sp_pasterns, self.sp_ears_height, self.sp_ears_width,
            self.sp_head_height, self.sp_head_width
        ):
            sp.editingFinished.connect(lambda sp=sp: self._enforce_req_min(sp))

        app_form.addRow(self._lab_range("Вес", self.sp_weight, "кг"), self.sp_weight)
        app_form.addRow(self._lab_range("Высота в холке", self.sp_crest_height, "см"), self.sp_crest_height)
        app_form.addRow(self._lab_range("Высота в крестце", self.sp_sacrum_height, "см"), self.sp_sacrum_height)
        app_form.addRow(self._lab_range("Косая длина туловища", self.sp_oblique_torso, "см"), self.sp_oblique_torso)
        app_form.addRow(self._lab_range("Ширина груди", self.sp_chest_width, "см"), self.sp_chest_width)
        app_form.addRow(self._lab_range("Глубина груди", self.sp_chest_depth, "см"), self.sp_chest_depth)
        app_form.addRow(self._lab_range("Ширина в маклаках", self.sp_maklokakh, "см"), self.sp_maklokakh)
        app_form.addRow(self._lab_range("Обхват груди", self.sp_chest_girth, "см"), self.sp_chest_girth)
        app_form.addRow(self._lab_range("Обхват курдюка", self.sp_kurdyk_girth, "см"), self.sp_kurdyk_girth)
        app_form.addRow(self._lab("Форма курдюка"), self.cb_kurdyk)
        app_form.addRow(self._lab_range("Обхват пясти", self.sp_pasterns, "см"), self.sp_pasterns)
        app_form.addRow(self._lab_range("Длина ушей", self.sp_ears_height, "см"), self.sp_ears_height)
        app_form.addRow(self._lab_range("Ширина ушей", self.sp_ears_width, "см"), self.sp_ears_width)
        app_form.addRow(self._lab_range("Длина головы", self.sp_head_height, "см"), self.sp_head_height)
        app_form.addRow(self._lab_range("Ширина головы", self.sp_head_width, "см"), self.sp_head_width)
        app_form.addRow(self._lab("Общая оценка"), self.sp_exterior)
        app_form.addRow(self._lab("Величина"), self.cb_size)
        app_form.addRow(self._lab("Конституция"), self.cb_fur)
        app_form.addRow(self._lab("Классность"), self.cb_rank)
        app_form.addRow(self._lab("Примечание"), self.txt_note)

        gb_app.setVisible(False)   # скрыто, пока чекбокс не активен
        gb_app.setMaximumHeight(0)
        # показываем/скрываем и включаем поля
        self.chk_app.toggled.connect(self._toggle_app_section)
        self._set_app_enabled(False)

        # ── Нижняя панель действий ────────────────────────────────────────────
        # ── Нижняя панель действий (фиксированная) ───────────────────────────
        actions_bar = QWidget(self)
        actions_bar.setObjectName("actionsBar")
        actions = QHBoxLayout(actions_bar)
        actions.setContentsMargins(16, 10, 16, 10)
        self.btn_back = QPushButton("Назад"); self.btn_back.setShortcut("Esc")
        self.btn_save_new = QPushButton("Сохранить"); self.btn_save_new.setShortcut("Ctrl+S")
        self.btn_main = QPushButton("Главное меню")
        actions.addWidget(self.btn_back)
        actions.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        actions.addWidget(self.btn_save_new); actions.addWidget(self.btn_main)
        container_layout.addWidget(actions_bar)

        # ── Логика ────────────────────────────────────────────────────────────
        self.ed_age.editingFinished.connect(self._normalize_age_input)
        self.ed_age.editingFinished.connect(self._age_to_dob)
        self.dt_date.dateChanged.connect(self._dob_age_sync)
        self.dt_dob.dateChanged.connect(self._dob_age_sync)

        self.ed_idn.editingFinished.connect(self._check_and_prefill_idn)
        try:
            self.ed_idn.returnPressed.connect(self._check_and_prefill_idn)
        except Exception:
            pass

        self.btn_save_new.clicked.connect(lambda: self._save(and_close=False))
        self.btn_main.clicked.connect(self._go_main_menu)
        self.btn_back.clicked.connect(self.close)

        # Таб-навигция: после "Примечание" переходим на кнопки
        self.setTabOrder(self.txt_note, self.btn_save_new)
        self.setTabOrder(self.btn_save_new, self.btn_main)

        QTimer.singleShot(0, self.ed_idn.setFocus)

    def _lab(self, text):
        l = QLabel(text); l.setObjectName("formlabel"); l.setProperty("class", "formlabel"); return l

    def _lab_range(self, text, sp, suffix):
        def _fmt(v):
            return str(int(v)) if abs(v - int(v)) < 1e-9 else str(v)
        req_min = getattr(sp, "_req_min", sp.minimum())
        rng = f"{_fmt(req_min)}-{_fmt(sp.maximum())}"
        if suffix:
            return self._lab(f"{text} ({rng} {suffix})")
        return self._lab(f"{text} ({rng})")

    def _val_or_none(self, sp):
        return None if abs(sp.value()) < 1e-9 else float(sp.value())

    def _enforce_req_min(self, sp):
        req_min = getattr(sp, "_req_min", sp.minimum())
        if sp.value() > 0 and sp.value() < req_min:
            sp.setValue(0)

    def _toggle_app_section(self, on: bool):
        # плавное раскрытие/свертывание
        self._set_app_enabled(on)
        gb = self.gb_app
        if on:
            gb.setVisible(True)
        start_h = gb.maximumHeight() if gb.maximumHeight() > 0 else 0
        end_h = gb.sizeHint().height() if on else 0
        self._app_anim = QPropertyAnimation(gb, b"maximumHeight")
        self._app_anim.setDuration(220)
        self._app_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._app_anim.setStartValue(start_h)
        self._app_anim.setEndValue(end_h)
        if not on:
            self._app_anim.finished.connect(lambda: gb.setVisible(False))
        self._app_anim.start()

    # Включение/выключение полей бонитировки
    def _set_app_enabled(self, on: bool):
        for w in (
            self.sp_weight, self.sp_crest_height, self.sp_sacrum_height, self.sp_oblique_torso,
            self.sp_chest_width, self.sp_chest_depth, self.sp_maklokakh, self.sp_chest_girth,
            self.sp_kurdyk_girth, self.sp_pasterns, self.sp_ears_height, self.sp_ears_width,
            self.sp_head_height, self.sp_head_width, self.cb_kurdyk, self.sp_exterior,
            self.cb_rank, self.txt_note, self.cb_size, self.cb_fur
        ):
            w.setEnabled(on)

    # ---------- Возраст/даты ----------
    def _autofill_idn(self):
        base = "996000000000000"
        raw = "".join(ch for ch in self.ed_idn.text() if ch.isdigit())
        if not raw:
            return
        if len(raw) < 15:
            completed = base[:len(base)-len(raw)] + raw
        else:
            completed = raw[:15]
        self.ed_idn.setText(completed)

    def _age_to_dob(self):
        txt = self.ed_age.text().strip().replace(",", ".")
        if not txt:
            return
        date = self.dt_date.date()
        if not date.isValid():
            return
        years, months = 0, 0
        try:
            if "." in txt:
                a, b = txt.split(".", 1); years = int(a or 0); months = int(b or 0)
            else:
                years = int(txt)
        except ValueError:
            return
        if months < 0:
            months = 0
        if months > 11:
            months = 11
        d = date.addYears(-years).addMonths(-months)
        self.dt_dob.setDate(d)

    def _normalize_age_input(self):
        txt = (self.ed_age.text() or "").strip()
        if not txt:
            return
        self.ed_age.setText(txt.replace(",", "."))

    def _dob_age_sync(self):
        # Пока пользователь печатает возраст, не перезаписываем поле.
        if self.ed_age.hasFocus():
            return
        date, dob = self.dt_date.date(), self.dt_dob.date()
        if not (date.isValid() and dob.isValid()):
            self.ed_age.clear(); return
        y = date.year() - dob.year()
        m = date.month() - dob.month()
        if date.day() < dob.day():
            m -= 1
        if m < 0:
            y -= 1; m += 12
        self.ed_age.setText(f"{max(0,y)}.{max(0,m)}")

    # ---------- Пикеры родителей ----------
    def _pick_father(self):
        dlg = SheepPickerDialog(self, "Выбрать отца", gender_filter="B")
        if dlg.exec_() == QDialog.Accepted:
            self.ed_father.setText(dlg.selected_idn or "")

    def _pick_mother(self):
        dlg = SheepPickerDialog(self, "Выбрать мать", gender_filter="O")
        if dlg.exec_() == QDialog.Accepted:
            self.ed_mother.setText(dlg.selected_idn or "")

    # ---------- Проверка и автоподстановка по id_n ----------
    def _check_and_prefill_idn(self):
        if self._checking_idn:
            return
        self._autofill_idn()
        idn = (self.ed_idn.text() or "").strip()
        if not idn or len(idn) != 15:
            return
        if self._last_checked_idn == idn:
            return
        self._last_checked_idn = idn
        self._checking_idn = True
        try:
            s = db.query(Sheep).filter_by(id_n=idn).first()
        except Exception:
            s = None

        if s:
            self._existing_sheep_id = s.id
            gender_txt = "баран" if (s.gender or "B") == "B" else "овца"
            if self._shown_existing_idn != idn:
                QMessageBox.information(self, "Найдена запись",
                    f"Уже есть {gender_txt} с таким номером id_n.\nДанные подставлены из базы.")
                self._shown_existing_idn = idn
            # Подставим поля
            self.ed_nick.setText(s.nick or "")
            if s.dob:
                try:
                    d = QDate(s.dob.year, s.dob.month, s.dob.day)
                    if d.isValid():
                        self.dt_dob.setDate(d)
                except Exception:
                    pass
            idx = 0 if (s.gender or "O") == "O" else 1
            self.cb_gender.setCurrentIndex(idx)
            if s.color_id is not None:
                for i in range(self.cb_color.count()):
                    if self.cb_color.itemData(i) == s.color_id:
                        self.cb_color.setCurrentIndex(i); break
            self.txt_comment.setPlainText(s.comment or "")
            self.statusBar().showMessage(f"id_n уже существует (ID {s.id}) — создайте с другим id_n или отредактируйте запись", 8000)
        else:
            self._existing_sheep_id = None
            self._shown_existing_idn = None
        self._checking_idn = False

    # ---------- Валидация ----------
    def _validate(self) -> bool:
        if db is None or Sheep is None:
            QMessageBox.critical(self, "БД", _db_error or "Недоступна"); return False

        owner_id = self.owner_id if self._owner_fixed else self.cb_owner.currentData()
        if owner_id is None:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца"); 
            return False

        idn = (self.ed_idn.text() or "").strip()
        if len(idn) != 15 or not idn.isdigit():
            QMessageBox.warning(self, "Ошибка", "ID № должен состоять из 15 цифр")
            self.ed_idn.setFocus(); return False
        # запрет на дубль для новой записи
        try:
            dup = db.query(Sheep).filter_by(id_n=idn).first()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e)); return False
        if dup and self._existing_sheep_id is None:
            QMessageBox.warning(self, "Ошибка", "Такая бирка уже есть — используйте другой id_n")
            self.ed_idn.setFocus(); return False

        dob = self.dt_dob.date()
        if not dob.isValid() or dob.year() < 2010:
            QMessageBox.warning(self, "Ошибка", "Проверьте дату рождения (не раньше 2010)")
            self.dt_dob.setFocus(); return False

        if self.cb_gender.currentData() not in ("O","B"):
            QMessageBox.warning(self, "Ошибка", "Укажите пол"); self.cb_gender.setFocus(); return False

        if self.cb_color.currentData() is None:
            QMessageBox.warning(self, "Ошибка", "Выберите окрас"); self.cb_color.setFocus(); return False

        if self.chk_app.isChecked() and not self.dt_date.date().isValid():
            QMessageBox.warning(self, "Ошибка", "Укажите дату бонитировки"); self.dt_date.setFocus(); return False

        # Если бонитировка включена — проверяем обязательные поля замеров
        if self.chk_app.isChecked():
            req_fields = [
                (self.sp_weight, "Вес"),
                (self.sp_crest_height, "Высота в холке"),
                (self.sp_sacrum_height, "Высота в крестце"),
                (self.sp_oblique_torso, "Косая длина туловища"),
                (self.sp_chest_width, "Ширина груди"),
                (self.sp_chest_depth, "Глубина груди"),
                (self.sp_maklokakh, "Ширина в маклаках"),
                (self.sp_chest_girth, "Обхват груди"),
                (self.sp_kurdyk_girth, "Обхват курдюка"),
                (self.sp_pasterns, "Обхват пясти"),
                (self.sp_ears_height, "Длина ушей"),
                (self.sp_ears_width, "Ширина ушей"),
                (self.sp_head_height, "Длина головы"),
                (self.sp_head_width, "Ширина головы"),
            ]
            for sp, label in req_fields:
                req_min = getattr(sp, "_req_min", sp.minimum())
                if sp.value() < req_min:
                    QMessageBox.warning(self, "Ошибка", f"Заполните поле: {label}")
                    sp.setFocus()
                    return False

        return True

    # ---------- Сохранение ----------
    def _save(self, and_close: bool):
        if not self._validate():
            return

        owner_id = self.owner_id if self._owner_fixed else self.cb_owner.currentData()
        idn = self.ed_idn.text().strip()
        nick = self.ed_nick.text().strip() or None
        dob  = self.dt_dob.date().toPyDate()
        gender = self.cb_gender.currentData()
        color_id = int(self.cb_color.currentData())
        comment = self.txt_comment.toPlainText().strip() or None
        date_filling = self.dt_date.date().toPyDate()
        father_idn = (self.ed_father.text() or "").strip()
        mother_idn = (self.ed_mother.text() or "").strip()
        price = None
        currency = "K"
        if hasattr(self, "ed_price"):
            price_raw = (self.ed_price.text() or "").strip()
            price = int(price_raw) if price_raw.isdigit() else None
        if hasattr(self, "cb_currency"):
            currency = "K" if self.cb_currency.currentIndex() == 0 else "U"

        try:
            # 1) овца: создать или обновить существующую
            s = None
            if self._existing_sheep_id is not None:
                s = db.query(Sheep).filter_by(id=self._existing_sheep_id).first()
            if s is None:
                s = Sheep(id_n=idn, nick=nick, dob=dob, gender=gender,
                          color_id=color_id, comment=comment, owner_id=int(owner_id),
                          price=price, currency=currency,
                          is_negotiable_price=self.chk_neg_price.isChecked() if hasattr(self, "chk_neg_price") else False,
                          sell=self.chk_sell.isChecked() if hasattr(self, "chk_sell") else False,
                          out=self.chk_out.isChecked() if hasattr(self, "chk_out") else False,
                          hide=self.chk_hide.isChecked() if hasattr(self, "chk_hide") else False)
                db.add(s); db.flush()  # получим ID
            else:
                s.nick = nick
                s.dob = dob
                s.gender = gender
                s.color_id = color_id
                s.comment = comment
                s.owner_id = int(owner_id)
                s.price = price
                s.currency = currency
                if hasattr(self, "chk_neg_price"):
                    s.is_negotiable_price = self.chk_neg_price.isChecked()
                if hasattr(self, "chk_sell"):
                    s.sell = self.chk_sell.isChecked()
                if hasattr(self, "chk_out"):
                    s.out = self.chk_out.isChecked()
                if hasattr(self, "chk_hide"):
                    s.hide = self.chk_hide.isChecked()

            # 2) связь с владельцем (для новой записи)
            if self._existing_sheep_id is None:
                link = Owner(sheep_id=s.id, owner_id=int(owner_id),
                             owner_bool=True, date1=date_filling, date2=date_filling)
                db.add(link)

            # 2.1) родители (если выбраны)
            for rel_idn in (father_idn, mother_idn):
                if not rel_idn or rel_idn == idn:
                    continue
                p = db.query(Sheep).filter_by(id_n=rel_idn).first()
                if p and p.id != s.id:
                    try:
                        if p not in s.parents:
                            s.parents.append(p)
                    except Exception:
                        pass

            # 3) бонитировка (если нужна)
            if self.chk_app.isChecked():
                app = Application(
                    sheep_id=s.id,
                    weight=self._val_or_none(self.sp_weight),
                    crest_height=self._val_or_none(self.sp_crest_height),
                    sacrum_height=self._val_or_none(self.sp_sacrum_height),
                    oblique_torso=self._val_or_none(self.sp_oblique_torso),
                    chest_width=self._val_or_none(self.sp_chest_width),
                    chest_depth=self._val_or_none(self.sp_chest_depth),
                    maklokakh_width=self._val_or_none(self.sp_maklokakh),
                    chest_girth=self._val_or_none(self.sp_chest_girth),
                    kurdyk_girth=self._val_or_none(self.sp_kurdyk_girth),
                    kurdyk_form={0:"",1:"raised",2:"medium",3:"lowered"}.get(self.cb_kurdyk.currentIndex(),""),
                    pasterns_girth=self._val_or_none(self.sp_pasterns),
                    ears_height=self._val_or_none(self.sp_ears_height),
                    ears_width=self._val_or_none(self.sp_ears_width),
                    head_height=self._val_or_none(self.sp_head_height),
                    head_width=self._val_or_none(self.sp_head_width),
                    size={0:None,1:"big",2:"medium",3:"small"}.get(self.cb_size.currentIndex(), None),
                    fur_structure={0:None,1:"strong",2:"loose"}.get(self.cb_fur.currentIndex(), None),
                    exterior=int(self.sp_exterior.value()),
                    rank=(self.cb_rank.currentData() if self.cb_rank.currentData() else None),
                    note=self.txt_note.toPlainText().strip() or None,
                    date=date_filling,
                )
                db.add(app)

            db.commit()

        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return

        action_txt = "Овца обновлена" if self._existing_sheep_id is not None else "Овца добавлена"
        self.statusBar().showMessage(f"{action_txt} (ID {s.id})", 5000)
        self.created.emit(s.id)

        if and_close:
            QMessageBox.information(self, "Готово", f"Овца добавлена (ID {s.id})")
            self.close()
        else:
            if self.chk_app.isChecked():
                self.chk_app.setChecked(False)
            self._reset_form(keep_owner=True)
            self.statusBar().showMessage(f"Овца добавлена (ID {s.id}). Можно вводить следующую.", 7000)

    # ---------- Очистка формы ----------
    def _reset_form(self, keep_owner=True):
        if not keep_owner and not self._owner_fixed:
            self.cb_owner.setCurrentIndex(0)
        self._existing_sheep_id = None
        self.ed_idn.clear()
        self.ed_nick.clear()
        self.dt_dob.setDate(QDate.currentDate())
        self.ed_age.clear()
        self.cb_gender.setCurrentIndex(0)
        self.cb_color.setCurrentIndex(0)
        self.ed_father.clear()
        self.ed_mother.clear()
        self.txt_comment.clear()
        if hasattr(self, "ed_price"):
            self.ed_price.clear()
        if hasattr(self, "cb_currency"):
            self.cb_currency.setCurrentIndex(0)
        if hasattr(self, "chk_neg_price"):
            self.chk_neg_price.setChecked(False)
        if hasattr(self, "chk_sell"):
            self.chk_sell.setChecked(False)
        if hasattr(self, "chk_out"):
            self.chk_out.setChecked(False)
        if hasattr(self, "chk_hide"):
            self.chk_hide.setChecked(False)
        for sp in (
            self.sp_weight, self.sp_crest_height, self.sp_sacrum_height, self.sp_oblique_torso,
            self.sp_chest_width, self.sp_chest_depth, self.sp_maklokakh, self.sp_chest_girth,
            self.sp_kurdyk_girth, self.sp_pasterns, self.sp_ears_height, self.sp_ears_width,
            self.sp_head_height, self.sp_head_width
        ):
            sp.setValue(sp.minimum())
        self.sp_exterior.setValue(1)
        self.cb_kurdyk.setCurrentIndex(0)
        self.cb_size.setCurrentIndex(0)
        self.cb_fur.setCurrentIndex(0)
        self.cb_rank.setCurrentIndex(0)
        self.txt_note.clear()
        self.ed_idn.setFocus()

    # ---------- Навигация ----------
    def closeEvent(self, ev):
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

    def _go_main_menu(self):
        prev = getattr(self, "prev", None)
        if prev is not None and getattr(prev, "prev", None) is not None:
            prev.prev.show()
            self._suppress_restore = True
            prev._suppress_restore = True
            prev.close()
            self.close()
            return
        self.close()
