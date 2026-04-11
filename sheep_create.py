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
from auth_state import AuthState
from services.db_service import get_db
from services.sheep_lookup_service import (
    get_all_colors,
    get_all_owners,
    get_current_owner_for_sheep,
    get_owner_by_id,
    get_sheep_by_idn,
)
from sheep_picker_dialog import SheepPickerDialog

# БД-модели
try:
    from db.models import Sheep, Color, User, Application, Owner, Lamb
    db = get_db()
except Exception as e:
    db = None; Sheep = None; Color = None; User = None; Application = None; Owner = None; Lamb = None
    _db_error = str(e)
else:
    _db_error = None

from services.sheep_service import save_sheep_bundle


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
        self._editing_application_id = None
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

        main.addLayout(self._build_header_layout())

        # ── Секции слева/справа (без сплиттера, аккуратные карточки) ─────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        main.addLayout(top_row)

        gb_ident = self._build_identification_group()
        gb_pedig = self._build_pedigree_group()
        top_row.addWidget(gb_ident, 1)
        top_row.addWidget(gb_pedig, 1)
        self.chk_app, self.gb_app, self.gb_lamb = self._build_application_section(main)
        container_layout.addWidget(self._build_actions_bar())
        self._connect_ui_signals()

    def _build_header_layout(self):
        header = QHBoxLayout()
        title = QLabel("Добавить овцу")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)

        if self.owner_id is not None and db and User:
            owner = get_owner_by_id(db, User, self.owner_id)
            self._owner_fixed = True
            owner_widget = QLabel(f"Владелец: <b>{getattr(owner, 'name', 'ID ' + str(self.owner_id))}</b>")
        else:
            self._owner_fixed = False
            self.cb_owner = QComboBox()
            self.cb_owner.addItem("— выберите —", None)
            if db and User:
                try:
                    for owner in get_all_owners(db, User):
                        self.cb_owner.addItem(owner.name or f"ID {owner.id}", owner.id)
                except Exception:
                    pass
            self.cb_owner.setStyleSheet("font-weight: 600;")
            owner_widget = QWidget()
            owner_layout = QHBoxLayout(owner_widget)
            owner_layout.setContentsMargins(0, 0, 0, 0)
            owner_layout.addWidget(QLabel("Владелец:"))
            owner_layout.addWidget(self.cb_owner)
            owner_layout.addStretch(1)

        header.addWidget(owner_widget)
        return header

    def _build_actions_bar(self):
        actions_bar = QWidget(self)
        actions_bar.setObjectName("actionsBar")
        actions = QHBoxLayout(actions_bar)
        actions.setContentsMargins(16, 10, 16, 10)

        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut("Esc")
        self.btn_save_new = QPushButton("Сохранить")
        self.btn_save_new.setShortcut("Ctrl+S")
        self.btn_main = QPushButton("Главное меню")

        actions.addWidget(self.btn_back)
        actions.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        actions.addWidget(self.btn_save_new)
        actions.addWidget(self.btn_main)
        return actions_bar

    def _connect_ui_signals(self):
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

        self.setTabOrder(self.txt_note, self.btn_save_new)
        self.setTabOrder(self.btn_save_new, self.btn_main)
        QTimer.singleShot(0, self.ed_idn.setFocus)

    def _build_identification_group(self):
        group = QGroupBox("Идентификация")
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        group.setLayout(form)

        self.ed_idn = QLineEdit()
        self.ed_idn.setPlaceholderText("15 цифр. Пример: 996000000000123")
        self.ed_idn.setValidator(QRegExpValidator(QRegExp(r"^\d{0,15}$")))
        form.addRow(self._lab("ID №*"), self.ed_idn)

        self.ed_nick = QLineEdit()
        form.addRow(self._lab("Кличка"), self.ed_nick)

        self.dt_date = QDateEdit(calendarPopup=True)
        self.dt_date.setDisplayFormat("dd.MM.yyyy")
        self.dt_date.setDate(QDate.currentDate())
        form.addRow(self._lab("Дата бонитировки"), self.dt_date)

        self.dt_dob = QDateEdit(calendarPopup=True)
        self.dt_dob.setDisplayFormat("dd.MM.yyyy")
        self.dt_dob.setDate(QDate.currentDate())
        form.addRow(self._lab("Дата рождения*"), self.dt_dob)

        self._configure_date_edit_widgets()

        self.ed_age = QLineEdit()
        self.ed_age.setPlaceholderText("Г.Г, напр. 2.3 или 2,3")
        form.addRow(self._lab("Возраст"), self.ed_age)

        self.cb_gender = QComboBox()
        self.cb_gender.addItem("Овца", "O")
        self.cb_gender.addItem("Баран", "B")
        form.addRow(self._lab("Пол*"), self.cb_gender)

        self.cb_color = QComboBox()
        self.cb_color.addItem("— выберите —", None)
        if db and Color:
            try:
                for color in get_all_colors(db, Color):
                    self.cb_color.addItem(color.name, color.id)
            except Exception:
                pass
        form.addRow(self._lab("Окрас*"), self.cb_color)
        return group

    def _configure_date_edit_widgets(self):
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
        weekday_format = QTextCharFormat()
        weekday_format.setForeground(QBrush(QColor("#ffffff")))
        weekday_format.setBackground(QBrush(QColor("#111111")))
        for calendar in (cal_date, cal_dob):
            for day in range(1, 8):
                calendar.setWeekdayTextFormat(day, weekday_format)

    def _build_pedigree_group(self):
        group = QGroupBox("Родословная")
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        group.setLayout(form)

        father_row = QHBoxLayout()
        self.ed_father = QLineEdit()
        self.ed_father.setPlaceholderText("id_n отца")
        self.ed_father.setReadOnly(True)
        btn_f_pick = QPushButton("Выбрать…")
        btn_f_pick.setShortcut("F2")
        btn_f_pick.clicked.connect(self._pick_father)
        btn_f_clear = QPushButton("×")
        btn_f_clear.setToolTip("Очистить")
        btn_f_clear.clicked.connect(lambda: self.ed_father.clear())
        father_row.addWidget(self.ed_father, 1)
        father_row.addWidget(btn_f_pick)
        father_row.addWidget(btn_f_clear)
        form.addRow(self._lab("Отец"), father_row)

        mother_row = QHBoxLayout()
        self.ed_mother = QLineEdit()
        self.ed_mother.setPlaceholderText("id_n матери")
        self.ed_mother.setReadOnly(True)
        btn_m_pick = QPushButton("Выбрать…")
        btn_m_pick.setShortcut("F3")
        btn_m_pick.clicked.connect(self._pick_mother)
        btn_m_clear = QPushButton("×")
        btn_m_clear.setToolTip("Очистить")
        btn_m_clear.clicked.connect(lambda: self.ed_mother.clear())
        mother_row.addWidget(self.ed_mother, 1)
        mother_row.addWidget(btn_m_pick)
        mother_row.addWidget(btn_m_clear)
        form.addRow(self._lab("Мать"), mother_row)

        self.txt_comment = QPlainTextEdit()
        self.txt_comment.setPlaceholderText("Комментарий…")
        self.txt_comment.setFixedHeight(92)
        self.txt_comment.setTabChangesFocus(True)
        form.addRow(self._lab("Комментарий"), self.txt_comment)
        return group

    def _build_application_section(self, parent_layout):
        checkbox = QCheckBox("Добавить бонитировку (Ctrl+B)")
        checkbox.setShortcut("Ctrl+B")
        parent_layout.addWidget(checkbox)

        group = QGroupBox("Бонитировка")
        parent_layout.addWidget(group, 0)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        group.setLayout(layout)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        def isb(required_min, maximum, suffix):
            spinbox = QDoubleSpinBox()
            spinbox.setRange(0, maximum)
            spinbox.setDecimals(1)
            spinbox.setSingleStep(1.0)
            spinbox.setSpecialValueText("—")
            spinbox.setValue(0)
            if suffix:
                spinbox.setSuffix(" " + suffix)
            spinbox._req_min = required_min
            return spinbox

        self.sp_weight = isb(40, 250, "кг")
        self.sp_crest_height = isb(70, 120, "см")
        self.sp_sacrum_height = isb(70, 120, "см")
        self.sp_oblique_torso = isb(60, 120, "см")
        self.sp_chest_width = isb(15, 45, "см")
        self.sp_chest_depth = isb(27, 60, "см")
        self.sp_maklokakh = isb(15, 40, "см")
        self.sp_chest_girth = isb(60, 150, "см")
        self.sp_kurdyk_girth = isb(35, 160, "см")
        self.cb_kurdyk = QComboBox(); self.cb_kurdyk.addItems(["—", "Приподнятый", "Средний", "Приспущенный"])
        self.sp_pasterns = isb(7, 15, "см")
        self.sp_ears_height = isb(17, 27, "см")
        self.sp_ears_width = isb(7, 15, "см")
        self.sp_head_height = isb(24, 40, "см")
        self.sp_head_width = isb(7, 15, "см")
        self.sp_exterior = QSpinBox(); self.sp_exterior.setRange(1, 5); self.sp_exterior.setValue(1)
        self.cb_size = QComboBox(); self.cb_size.addItems(["—", "Крупный", "Средний", "Мелкий"])
        self.cb_fur = QComboBox(); self.cb_fur.addItems(["—", "Крепкая", "Рыхлая"])
        self.cb_rank = QComboBox()
        self.cb_rank.addItem("—", None)
        self.cb_rank.addItem("E — Элита", "E")
        self.cb_rank.addItem("1 — 1-й", "1")
        self.cb_rank.addItem("2 — 2-й", "2")
        self.cb_rank.addItem("B — Брак", "B")
        self.txt_note = QPlainTextEdit()
        self.txt_note.setFixedHeight(76)
        self.txt_note.setTabChangesFocus(True)

        for spinbox in (
            self.sp_weight, self.sp_crest_height, self.sp_sacrum_height, self.sp_oblique_torso,
            self.sp_chest_width, self.sp_chest_depth, self.sp_maklokakh, self.sp_chest_girth,
            self.sp_kurdyk_girth, self.sp_pasterns, self.sp_ears_height, self.sp_ears_width,
            self.sp_head_height, self.sp_head_width
        ):
            spinbox.editingFinished.connect(lambda sp=spinbox: self._enforce_req_min(sp))

        form.addRow(self._lab_range("Вес", self.sp_weight, "кг"), self.sp_weight)
        form.addRow(self._lab_range("Высота в холке", self.sp_crest_height, "см"), self.sp_crest_height)
        form.addRow(self._lab_range("Высота в крестце", self.sp_sacrum_height, "см"), self.sp_sacrum_height)
        form.addRow(self._lab_range("Косая длина туловища", self.sp_oblique_torso, "см"), self.sp_oblique_torso)
        form.addRow(self._lab_range("Ширина груди", self.sp_chest_width, "см"), self.sp_chest_width)
        form.addRow(self._lab_range("Глубина груди", self.sp_chest_depth, "см"), self.sp_chest_depth)
        form.addRow(self._lab_range("Ширина в маклаках", self.sp_maklokakh, "см"), self.sp_maklokakh)
        form.addRow(self._lab_range("Обхват груди", self.sp_chest_girth, "см"), self.sp_chest_girth)
        form.addRow(self._lab_range("Обхват курдюка", self.sp_kurdyk_girth, "см"), self.sp_kurdyk_girth)
        form.addRow(self._lab("Форма курдюка"), self.cb_kurdyk)
        form.addRow(self._lab_range("Обхват пясти", self.sp_pasterns, "см"), self.sp_pasterns)
        form.addRow(self._lab_range("Длина ушей", self.sp_ears_height, "см"), self.sp_ears_height)
        form.addRow(self._lab_range("Ширина ушей", self.sp_ears_width, "см"), self.sp_ears_width)
        form.addRow(self._lab_range("Длина головы", self.sp_head_height, "см"), self.sp_head_height)
        form.addRow(self._lab_range("Ширина головы", self.sp_head_width, "см"), self.sp_head_width)
        form.addRow(self._lab("Общая оценка"), self.sp_exterior)
        form.addRow(self._lab("Величина"), self.cb_size)
        form.addRow(self._lab("Конституция"), self.cb_fur)
        form.addRow(self._lab("Классность"), self.cb_rank)
        form.addRow(self._lab("Примечание"), self.txt_note)

        lamb_group = QGroupBox("Данные ягнёнка")
        parent_layout.addWidget(lamb_group, 0)
        lamb_layout = QFormLayout()
        lamb_layout.setHorizontalSpacing(16)
        lamb_layout.setVerticalSpacing(8)
        lamb_group.setLayout(lamb_layout)

        self.sp_lamb_weight = QDoubleSpinBox()
        self.sp_lamb_weight.setRange(0, 120)
        self.sp_lamb_weight.setDecimals(1)
        self.sp_lamb_weight.setSingleStep(0.5)
        self.sp_lamb_weight.setSpecialValueText("—")
        self.sp_lamb_weight.setValue(0)
        self.sp_lamb_weight.setSuffix(" кг")

        self.sp_litter_size = QSpinBox()
        self.sp_litter_size.setRange(0, 4)
        self.sp_litter_size.setSpecialValueText("—")
        self.sp_litter_size.setValue(0)

        lamb_layout.addRow(self._lab("Вес ягнёнка"), self.sp_lamb_weight)
        lamb_layout.addRow(self._lab("В числе сколько родился"), self.sp_litter_size)

        group.setVisible(False)
        group.setMaximumHeight(0)
        lamb_group.setVisible(True)
        lamb_group.setMaximumHeight(lamb_group.sizeHint().height())
        checkbox.toggled.connect(self._toggle_app_section)
        self._set_app_enabled(False)
        return checkbox, group, lamb_group

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
        lamb_gb = self.gb_lamb
        if on:
            gb.setVisible(True)
            lamb_gb.setVisible(False)
            lamb_gb.setMaximumHeight(0)
        else:
            lamb_gb.setVisible(True)
            lamb_gb.setMaximumHeight(lamb_gb.sizeHint().height())
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
            s = get_sheep_by_idn(db, Sheep, idn)
        except Exception:
            s = None

        if s:
            self._existing_sheep_id = s.id
            try:
                current_owner_link = get_current_owner_for_sheep(db, Owner, s.id) if Owner is not None else None
            except Exception:
                current_owner_link = None
            gender_txt = "баран" if (s.gender or "B") == "B" else "овца"
            if self._shown_existing_idn != idn:
                QMessageBox.information(self, "Найдена запись",
                    f"Уже есть {gender_txt} с таким номером id_n.\nДанные подставлены из базы.")
                self._shown_existing_idn = idn
            self._prefill_existing_sheep(s, current_owner_link)
            self.statusBar().showMessage(f"id_n уже существует (ID {s.id}) — создайте с другим id_n или отредактируйте запись", 8000)
        else:
            self._existing_sheep_id = None
            self._shown_existing_idn = None
        self._checking_idn = False

    def _prefill_existing_sheep(self, sheep, owner_link=None):
        self._editing_application_id = None
        self.ed_nick.setText(sheep.nick or "")
        if sheep.dob:
            try:
                dob = QDate(sheep.dob.year, sheep.dob.month, sheep.dob.day)
                if dob.isValid():
                    self.dt_dob.setDate(dob)
            except Exception:
                pass

        idx = 0 if (sheep.gender or "O") == "O" else 1
        self.cb_gender.setCurrentIndex(idx)

        if sheep.color_id is not None:
            for i in range(self.cb_color.count()):
                if self.cb_color.itemData(i) == sheep.color_id:
                    self.cb_color.setCurrentIndex(i)
                    break

        if not self._owner_fixed:
            owner_id = getattr(owner_link, "owner_id", None) or getattr(sheep, "owner_id", None)
            if owner_id is not None:
                for i in range(self.cb_owner.count()):
                    if self.cb_owner.itemData(i) == owner_id:
                        self.cb_owner.setCurrentIndex(i)
                        break

        father = next((parent for parent in getattr(sheep, "parents", []) if getattr(parent, "gender", None) == "B"), None)
        mother = next((parent for parent in getattr(sheep, "parents", []) if getattr(parent, "gender", None) == "O"), None)
        self.ed_father.setText(getattr(father, "id_n", "") or "")
        self.ed_mother.setText(getattr(mother, "id_n", "") or "")
        self.txt_comment.setPlainText(sheep.comment or "")
        self.chk_app.setChecked(False)
        self._reset_application_fields()
        self._prefill_lamb_fields(getattr(sheep, "lamb", None))

    def load_for_edit(self, sheep_id: int, application_id: int = None):
        if db is None or Sheep is None:
            return
        sheep = db.query(Sheep).filter_by(id=sheep_id, is_deleted=False).first()
        if sheep is None:
            QMessageBox.warning(self, "Редактирование", "Овца не найдена.")
            return

        self._existing_sheep_id = sheep.id
        self.ed_idn.setText(sheep.id_n or "")
        self._shown_existing_idn = sheep.id_n or None
        owner_link = get_current_owner_for_sheep(db, Owner, sheep.id) if Owner is not None else None
        self._prefill_existing_sheep(sheep, owner_link)

        if application_id and Application is not None:
            application = db.query(Application).filter_by(id=application_id, sheep_id=sheep.id, is_deleted=False).first()
            if application is not None:
                self._editing_application_id = application.id
                self.chk_app.setChecked(True)
                if application.date:
                    app_date = QDate(application.date.year, application.date.month, application.date.day)
                    if app_date.isValid():
                        self.dt_date.setDate(app_date)
                self._prefill_application_fields(application)

    def _prefill_application_fields(self, application):
        value_fields = (
            (self.sp_weight, "weight"),
            (self.sp_crest_height, "crest_height"),
            (self.sp_sacrum_height, "sacrum_height"),
            (self.sp_oblique_torso, "oblique_torso"),
            (self.sp_chest_width, "chest_width"),
            (self.sp_chest_depth, "chest_depth"),
            (self.sp_maklokakh, "maklokakh_width"),
            (self.sp_chest_girth, "chest_girth"),
            (self.sp_kurdyk_girth, "kurdyk_girth"),
            (self.sp_pasterns, "pasterns_girth"),
            (self.sp_ears_height, "ears_height"),
            (self.sp_ears_width, "ears_width"),
            (self.sp_head_height, "head_height"),
            (self.sp_head_width, "head_width"),
        )
        for spinbox, field_name in value_fields:
            value = getattr(application, field_name, None)
            spinbox.setValue(float(value) if value is not None else 0)

        self.cb_kurdyk.setCurrentIndex({"": 0, None: 0, "raised": 1, "medium": 2, "lowered": 3}.get(application.kurdyk_form, 0))
        self.cb_size.setCurrentIndex({None: 0, "big": 1, "medium": 2, "small": 3}.get(application.size, 0))
        self.cb_fur.setCurrentIndex({None: 0, "strong": 1, "loose": 2}.get(application.fur_structure, 0))

        if application.rank is not None:
            for i in range(self.cb_rank.count()):
                if self.cb_rank.itemData(i) == application.rank:
                    self.cb_rank.setCurrentIndex(i)
                    break
        else:
            self.cb_rank.setCurrentIndex(0)

        self.sp_exterior.setValue(int(application.exterior or 1))
        self.txt_note.setPlainText(application.note or "")

    def _prefill_lamb_fields(self, lamb):
        if lamb is None:
            self._reset_lamb_fields()
            return
        self.sp_lamb_weight.setValue(float(getattr(lamb, "weight", None) or 0))
        self.sp_litter_size.setValue(int(getattr(lamb, "litter_size", None) or 0))

    def _reset_application_fields(self):
        for sp in (
            self.sp_weight, self.sp_crest_height, self.sp_sacrum_height, self.sp_oblique_torso,
            self.sp_chest_width, self.sp_chest_depth, self.sp_maklokakh, self.sp_chest_girth,
            self.sp_kurdyk_girth, self.sp_pasterns, self.sp_ears_height, self.sp_ears_width,
            self.sp_head_height, self.sp_head_width
        ):
            sp.setValue(0)
        self.sp_exterior.setValue(1)
        self.cb_kurdyk.setCurrentIndex(0)
        self.cb_size.setCurrentIndex(0)
        self.cb_fur.setCurrentIndex(0)
        self.cb_rank.setCurrentIndex(0)
        self.txt_note.clear()

    def _reset_lamb_fields(self):
        self.sp_lamb_weight.setValue(0)
        self.sp_litter_size.setValue(0)

    # ---------- Валидация ----------
    def _validate_owner(self) -> bool:
        owner_id = self.owner_id if self._owner_fixed else self.cb_owner.currentData()
        if owner_id is None:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца")
            return False
        return True

    def _validate_idn(self) -> bool:
        idn = (self.ed_idn.text() or "").strip()
        if len(idn) != 15 or not idn.isdigit():
            QMessageBox.warning(self, "Ошибка", "ID № должен состоять из 15 цифр")
            self.ed_idn.setFocus()
            return False
        try:
            dup = get_sheep_by_idn(db, Sheep, idn)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return False
        if dup and self._existing_sheep_id is None:
            QMessageBox.warning(self, "Ошибка", "Такая бирка уже есть — используйте другой id_n")
            self.ed_idn.setFocus()
            return False
        return True

    def _validate_main_fields(self) -> bool:
        dob = self.dt_dob.date()
        if not dob.isValid() or dob.year() < 2010:
            QMessageBox.warning(self, "Ошибка", "Проверьте дату рождения (не раньше 2010)")
            self.dt_dob.setFocus()
            return False

        if self.cb_gender.currentData() not in ("O","B"):
            QMessageBox.warning(self, "Ошибка", "Укажите пол")
            self.cb_gender.setFocus()
            return False

        if self.cb_color.currentData() is None:
            QMessageBox.warning(self, "Ошибка", "Выберите окрас")
            self.cb_color.setFocus()
            return False

        if self.chk_app.isChecked() and not self.dt_date.date().isValid():
            QMessageBox.warning(self, "Ошибка", "Укажите дату бонитировки")
            self.dt_date.setFocus()
            return False
        return True

    def _validate_application_fields(self) -> bool:
        if not self.chk_app.isChecked():
            return True

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

    def _build_lamb_payload(self):
        if self.chk_app.isChecked():
            return None
        weight = self._val_or_none(self.sp_lamb_weight)
        litter_size = int(self.sp_litter_size.value()) if self.sp_litter_size.value() > 0 else None
        if weight is None and litter_size is None:
            return None
        return {
            "weight": weight,
            "litter_size": litter_size,
            "created_by_user_id": (AuthState.user or {}).get("id"),
        }

    def _validate_lamb_fields(self) -> bool:
        if self.chk_app.isChecked():
            return True
        if self.sp_lamb_weight.value() < 0:
            QMessageBox.warning(self, "Ошибка", "Вес ягнёнка не может быть меньше нуля")
            self.sp_lamb_weight.setFocus()
            return False
        if self.sp_lamb_weight.value() > 0 and self.sp_lamb_weight.value() <= 0:
            QMessageBox.warning(self, "Ошибка", "Вес ягнёнка должен быть больше нуля")
            self.sp_lamb_weight.setFocus()
            return False
        if self.sp_litter_size.value() not in (0, 1, 2, 3, 4):
            QMessageBox.warning(self, "Ошибка", "Поле 'в числе сколько родился' должно быть от 1 до 4")
            self.sp_litter_size.setFocus()
            return False
        return True

    def _validate(self) -> bool:
        if db is None or Sheep is None:
            QMessageBox.critical(self, "БД", _db_error or "Недоступна")
            return False

        if not self._validate_owner():
            return False
        if not self._validate_idn():
            return False
        if not self._validate_main_fields():
            return False
        if not self._validate_application_fields():
            return False
        if not self._validate_lamb_fields():
            return False

        return True

    def _build_application_payload(self, date_filling):
        if not self.chk_app.isChecked():
            return None

        return {
            "weight": self._val_or_none(self.sp_weight),
            "crest_height": self._val_or_none(self.sp_crest_height),
            "sacrum_height": self._val_or_none(self.sp_sacrum_height),
            "oblique_torso": self._val_or_none(self.sp_oblique_torso),
            "chest_width": self._val_or_none(self.sp_chest_width),
            "chest_depth": self._val_or_none(self.sp_chest_depth),
            "maklokakh_width": self._val_or_none(self.sp_maklokakh),
            "chest_girth": self._val_or_none(self.sp_chest_girth),
            "kurdyk_girth": self._val_or_none(self.sp_kurdyk_girth),
            "kurdyk_form": {0:"",1:"raised",2:"medium",3:"lowered"}.get(self.cb_kurdyk.currentIndex(),""),
            "pasterns_girth": self._val_or_none(self.sp_pasterns),
            "ears_height": self._val_or_none(self.sp_ears_height),
            "ears_width": self._val_or_none(self.sp_ears_width),
            "head_height": self._val_or_none(self.sp_head_height),
            "head_width": self._val_or_none(self.sp_head_width),
            "size": {0:None,1:"big",2:"medium",3:"small"}.get(self.cb_size.currentIndex(), None),
            "fur_structure": {0:None,1:"strong",2:"loose"}.get(self.cb_fur.currentIndex(), None),
            "exterior": int(self.sp_exterior.value()),
            "rank": (self.cb_rank.currentData() if self.cb_rank.currentData() else None),
            "note": self.txt_note.toPlainText().strip() or None,
            "date": date_filling,
            "created_by_user_id": (AuthState.user or {}).get("id"),
            "created_by_guest": AuthState.user is None,
        }

    def _build_save_payload(self):
        owner_id = self.owner_id if self._owner_fixed else self.cb_owner.currentData()
        date_filling = self.dt_date.date().toPyDate()
        price = None
        currency = "K"
        if hasattr(self, "ed_price"):
            price_raw = (self.ed_price.text() or "").strip()
            price = int(price_raw) if price_raw.isdigit() else None
        if hasattr(self, "cb_currency"):
            currency = "K" if self.cb_currency.currentIndex() == 0 else "U"

        return {
            "owner_id": owner_id,
            "existing_sheep_id": self._existing_sheep_id,
            "editing_application_id": self._editing_application_id,
            "created_by_user_id": (AuthState.user or {}).get("id"),
            "idn": self.ed_idn.text().strip(),
            "nick": self.ed_nick.text().strip() or None,
            "dob": self.dt_dob.date().toPyDate(),
            "gender": self.cb_gender.currentData(),
            "color_id": int(self.cb_color.currentData()),
            "comment": self.txt_comment.toPlainText().strip() or None,
            "date_filling": date_filling,
            "parent_idns": (
                (self.ed_father.text() or "").strip(),
                (self.ed_mother.text() or "").strip(),
            ),
            "price": price,
            "currency": currency,
            "is_negotiable_price": self.chk_neg_price.isChecked() if hasattr(self, "chk_neg_price") else False,
            "sell": self.chk_sell.isChecked() if hasattr(self, "chk_sell") else False,
            "out": self.chk_out.isChecked() if hasattr(self, "chk_out") else False,
            "hide": self.chk_hide.isChecked() if hasattr(self, "chk_hide") else False,
            "created_by_guest": AuthState.user is None,
            "application": self._build_application_payload(date_filling),
            "lamb": self._build_lamb_payload(),
        }

    # ---------- Сохранение ----------
    def _save(self, and_close: bool):
        if not self._validate():
            return

        payload = self._build_save_payload()

        try:
            s, created = save_sheep_bundle(db, payload)
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return

        action_txt = "Овца добавлена" if created else "Овца обновлена"
        self.statusBar().showMessage(f"{action_txt} (ID {s.id})", 5000)
        self.created.emit(s.id)

        if and_close:
            QMessageBox.information(self, "Готово", f"{action_txt} (ID {s.id})")
            self.close()
        else:
            if self.chk_app.isChecked():
                self.chk_app.setChecked(False)
            self._reset_form(keep_owner=True)
            self.statusBar().showMessage(f"{action_txt} (ID {s.id}). Можно вводить следующую.", 7000)

    # ---------- Очистка формы ----------
    def _reset_form(self, keep_owner=True):
        if not keep_owner and not self._owner_fixed:
            self.cb_owner.setCurrentIndex(0)
        self._existing_sheep_id = None
        self._editing_application_id = None
        self._shown_existing_idn = None
        self._last_checked_idn = None
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
        self._reset_application_fields()
        self._reset_lamb_fields()
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
