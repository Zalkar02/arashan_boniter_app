# --- Select2-like QComboBox, стабильная версия для PyQt5 ---
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtCore import Qt, QSortFilterProxyModel

# Совместимость с разными сборками PyQt5
try:
    from PyQt5.QtCore import QRegularExpression
    _HAS_QREGEX = True
except Exception:
    _HAS_QREGEX = False
    from PyQt5.QtCore import QRegExp

from PyQt5.QtGui import QStandardItemModel, QStandardItem

class SearchableComboBox(QComboBox):
    """
    - Живой поиск по подстроке (регистр не важен)
    - Enter выбирает первый отфильтрованный вариант
    - Корректно синхронизирует текст в lineEdit() и текущее значение
    """
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCompleter(None)  # не мешаемся с внутренним комплитером
        self.lineEdit().setPlaceholderText(placeholder)

        # Флаг, чтобы не ловить наши же программные изменения текста
        self._programmatic = False

        # Исходная модель + прокси-фильтр
        self._source_model = QStandardItemModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterRole(Qt.DisplayRole)
        super().setModel(self._proxy)
        self.setModelColumn(0)

        # Сигналы
        self.lineEdit().textEdited.connect(self._on_text_edited)
        # Мышью по списку
        self.view().pressed.connect(self._on_view_pressed)
        # Когда Qt сам активировал индекс — синхронизируем текст
        self.activated.connect(lambda _idx: self._sync_lineedit_to_current())

    # --- публичные методы совместимы с QComboBox ---
    def addItem(self, text: str, userData=None):
        it = QStandardItem(text)
        it.setData(userData, Qt.UserRole)
        self._source_model.appendRow(it)

    def insertItem(self, index: int, text: str, userData=None):
        it = QStandardItem(text)
        it.setData(userData, Qt.UserRole)
        self._source_model.insertRow(index, it)

    def addItems(self, items):
        for it in items:
            if isinstance(it, (tuple, list)) and len(it) == 2:
                self.addItem(it[0], it[1])
            else:
                self.addItem(str(it))

    def clear(self):
        self._source_model.clear()
        self._programmatic = True
        try:
            self.lineEdit().clear()
        finally:
            self._programmatic = False

    def clearItems(self):
        self.clear()

    def currentData(self, role=Qt.UserRole):
        return super().currentData(role)

    # --- поведение как у select2 ---
    def keyPressEvent(self, e):
        # Enter/Return: выбрать первый видимый элемент
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self._proxy.rowCount() > 0:
            self._select_proxy_row(0)
            e.accept()
            return
        # Esc: очистить фильтр и закрыть попап, если открыт
        if e.key() == Qt.Key_Escape:
            if self.view().isVisible():
                self.hidePopup()
                e.accept()
                return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        # Удобно сразу показать список и выделить весь текст для набора
        self.lineEdit().selectAll()
        if not self.view().isVisible():
            self.showPopup()

    # --- фильтрация ---
    def _on_text_edited(self, text: str):
        if self._programmatic:
            return
        self._apply_filter(text)
        if not self.view().isVisible():
            self.showPopup()

    def _apply_filter(self, text: str):
        if _HAS_QREGEX:
            rx = QRegularExpression(QRegularExpression.escape(text)) if text else QRegularExpression()
            self._proxy.setFilterRegularExpression(rx)
        else:
            rx = QRegExp(text, Qt.CaseInsensitive, QRegExp.FixedString) if text else QRegExp()
            self._proxy.setFilterRegExp(rx)

    # --- выбор элемента и синхронизация текста ---
    def _on_view_pressed(self, proxy_index):
        self._select_proxy_row(proxy_index.row())

    def _select_proxy_row(self, proxy_row: int):
        if proxy_row < 0 or proxy_row >= self._proxy.rowCount():
            return
        try:
            self._programmatic = True
            super().setCurrentIndex(proxy_row)  # индекс по ПРОКСИ-модели
            self._sync_lineedit_to_current()
        finally:
            self._programmatic = False
        self.hidePopup()

    def _sync_lineedit_to_current(self):
        # Выставить текст выбранного элемента, не запуская повторную фильтрацию
        txt = self.currentText()
        self.lineEdit().blockSignals(True)
        self.lineEdit().setText(txt)
        self.lineEdit().blockSignals(False)

    # Не даём внешнему коду подменять модель и ломать прокси
    def setModel(self, *args, **kwargs):
        pass
