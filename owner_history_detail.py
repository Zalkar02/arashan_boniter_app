import datetime
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QPalette, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auth_state import AuthState
from payment_qr_dialog import PaymentQrDialog
from sheep_create import SheepCreateWindow
from services.db_service import get_db
from services.history_service import format_owner_sheep_row, get_owner_detail_rows
from services.passport_print_service import (
    clear_pending_print_job,
    get_back_print_order,
    get_pending_print_job,
    get_print_batch_size,
    print_pdf_pages,
    print_pdf_page_range,
    save_pending_print_job,
    generate_passports_pdf,
)
from services.payment_service import create_payment, refresh_payment_statuses
from services.sheep_service import soft_delete_sheep_record
from services.sync_worker import SyncWorker

try:
    from db.models import Application, Sheep, User, Owner
    db = get_db()
except Exception as e:
    db = None
    Application = None
    Sheep = None
    User = None
    Owner = None
    _db_error = str(e)
else:
    _db_error = None


def _mark_batch_printed(session, batch):
    sheep_ids = [row["sheep"].id for row in batch if row.get("sheep") is not None]
    if not sheep_ids:
        return
    sheep_rows = session.query(Sheep).filter(Sheep.id.in_(sheep_ids)).all()
    for sheep in sheep_rows:
        sheep.is_printed = True
    application_ids = []
    for row in batch:
        for application in row.get("applications") or []:
            if getattr(application, "id", None) is not None:
                application_ids.append(application.id)
    if application_ids:
        application_rows = session.query(Application).filter(Application.id.in_(application_ids)).all()
        for application in application_rows:
            application.is_printed = True
    session.commit()


class PrintBatchDialog(QDialog):
    def __init__(self, session, batches, owner_data, owner_id, parent=None):
        super().__init__(parent)
        self.db = session
        self.batches = batches
        self.owner_data = owner_data
        self.owner_id = owner_id
        self.batch_index = 0
        self.current_pdf_path = ""
        self.front_printed = False
        self.back_printed = False

        self.setWindowTitle("Печать паспортов")
        self.setModal(True)
        self.resize(620, 260)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        self.lbl_title = QLabel("")
        title_font = self.lbl_title.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.lbl_title.setFont(title_font)
        root.addWidget(self.lbl_title)

        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        root.addWidget(self.lbl_info)

        buttons = QHBoxLayout()
        self.btn_front = QPushButton("Печать лицевой")
        self.btn_back = QPushButton("Печать оборота")
        self.btn_next = QPushButton("Следующая пачка")
        self.btn_close = QPushButton("Закрыть")
        buttons.addWidget(self.btn_front)
        buttons.addWidget(self.btn_back)
        buttons.addWidget(self.btn_next)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self.btn_front.clicked.connect(self.print_front)
        self.btn_back.clicked.connect(self.print_back)
        self.btn_next.clicked.connect(self.next_batch)
        self.btn_close.clicked.connect(self.accept)

        self._prepare_current_batch()

    def _prepare_current_batch(self):
        if self.batch_index >= len(self.batches):
            clear_pending_print_job()
            self.lbl_title.setText("Печать завершена")
            self.lbl_info.setText("Все пачки обработаны. Можно закрыть окно.")
            self.btn_front.setEnabled(False)
            self.btn_back.setEnabled(False)
            self.btn_next.setEnabled(False)
            return

        batch = self.batches[self.batch_index]
        self.current_pdf_path = generate_passports_pdf(self.db, batch, owner=self.owner_data)
        self.front_printed = False
        self.back_printed = False
        clear_pending_print_job()
        self._refresh_state()

    def _refresh_state(self):
        total_batches = len(self.batches)
        batch = self.batches[self.batch_index]
        self.lbl_title.setText(f"Пачка {self.batch_index + 1} из {total_batches}")
        self.lbl_info.setText(
            "\n".join(
                [
                    f"Карточек в пачке: {len(batch)}",
                    "1. Нажмите «Печать лицевой».",
                    "2. Переверните листы.",
                    "3. Нажмите «Печать оборота».",
                    "4. Перейдите к следующей пачке.",
                ]
            )
        )
        self.btn_front.setEnabled(not self.front_printed)
        self.btn_back.setEnabled(self.front_printed and not self.back_printed)
        self.btn_next.setEnabled(self.back_printed)

    def print_front(self):
        batch = self.batches[self.batch_index]
        total = len(batch)
        try:
            front_result = print_pdf_page_range(self.current_pdf_path, 1, total)
            save_pending_print_job(
                pdf_path=self.current_pdf_path,
                total_cards=total,
                owner_id=self.owner_id,
                sheep_ids=[row["sheep"].id for row in batch],
            )
            self.front_printed = True
            self._refresh_state()
            QMessageBox.information(
                self,
                "Печать",
                f"Лицевые страницы отправлены на печать.\n{front_result}\n\nТеперь переверните листы.",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Печать", str(exc))

    def print_back(self):
        job = get_pending_print_job()
        if not job:
            QMessageBox.warning(self, "Печать", "Нет сохранённой пачки для печати оборота.")
            return
        batch = self.batches[self.batch_index]
        total = len(batch)
        try:
            if get_back_print_order() == "reverse":
                back_result = print_pdf_pages(
                    self.current_pdf_path,
                    list(range(total * 2, total, -1)),
                )
            else:
                back_result = print_pdf_page_range(self.current_pdf_path, total + 1, total * 2)
            _mark_batch_printed(self.db, batch)
            clear_pending_print_job()
            self.back_printed = True
            self._refresh_state()
            QMessageBox.information(self, "Печать", f"Оборотные страницы отправлены на печать.\n{back_result}")
        except Exception as exc:
            QMessageBox.warning(self, "Печать", str(exc))

    def next_batch(self):
        self.batch_index += 1
        self._prepare_current_batch()


class OwnerHistoryDetailWindow(QMainWindow):
    def __init__(self, owner_id: int, parent=None):
        super().__init__(parent)
        self._suppress_restore = False
        self.owner_id = owner_id
        self.owner_data = None
        self.rows = []
        self.filtered_rows = []
        self.sync_worker = None
        self.sync_dialog = None

        self.setWindowTitle("Детали хозяйства")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)
        self.showMaximized()

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        self.lbl_title = QLabel("Хозяйство")
        title_font = self.lbl_title.font()
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setBold(True)
        self.lbl_title.setFont(title_font)
        header.addWidget(self.lbl_title)
        header.addStretch(1)

        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        header.addWidget(self.btn_back)
        layout.addLayout(header)

        self.lbl_subtitle = QLabel("")
        layout.addWidget(self.lbl_subtitle)

        filters = QHBoxLayout()
        self.cmb_period = QComboBox()
        self.cmb_period.addItem("За 1 месяц", "1m")
        self.cmb_period.addItem("За 3 месяца", "3m")
        self.cmb_period.addItem("За 1 год", "1y")
        self.cmb_period.addItem("За всё время", "all")
        self.cmb_paid_filter = QComboBox()
        self.cmb_paid_filter.addItem("Оплата: все", "")
        self.cmb_paid_filter.addItem("Только оплаченные", "paid")
        self.cmb_paid_filter.addItem("Только не оплаченные", "unpaid")
        self.cmb_sync_filter = QComboBox()
        self.cmb_sync_filter.addItem("Синхронизация: все", "")
        self.cmb_sync_filter.addItem("Только синхронизированные", "synced")
        self.cmb_sync_filter.addItem("Только не синхронизированные", "unsynced")
        self.cmb_printed_filter = QComboBox()
        self.cmb_printed_filter.addItem("Печать: все", "")
        self.cmb_printed_filter.addItem("Только напечатанные", "printed")
        self.cmb_printed_filter.addItem("Только не напечатанные", "unprinted")
        filters.addWidget(QLabel("Период:"))
        filters.addWidget(self.cmb_period)
        filters.addWidget(self.cmb_paid_filter)
        filters.addWidget(self.cmb_sync_filter)
        filters.addWidget(self.cmb_printed_filter)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 11, self)
        self.table.setHorizontalHeaderLabels(
            [
                "",
                "Тип",
                "ID №",
                "Кличка",
                "Пол",
                "Возраст",
                "Дата внесения",
                "Бонитировка",
                "Синхронизация",
                "Оплата",
                "Паспорт",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet(
            """
            QTableWidget {
                gridline-color: #e6e8eb;
                background: #ffffff;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #111111;
            }
            QHeaderView::section {
                background: #f3f4f6;
                color: #111111;
                padding: 8px;
                border: 0;
                border-bottom: 1px solid #d1d5db;
                border-right: 1px solid #e5e7eb;
                font-weight: 600;
            }
            """
        )
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(9, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(10, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        quick_actions = QHBoxLayout()
        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_select_unpaid = QPushButton("Выбрать неоплаченные")
        self.btn_clear_selection = QPushButton("Снять выбор")
        quick_actions.addWidget(self.btn_select_all)
        quick_actions.addWidget(self.btn_select_unpaid)
        quick_actions.addWidget(self.btn_clear_selection)
        quick_actions.addStretch(1)
        layout.addLayout(quick_actions)

        actions = QHBoxLayout()
        self.btn_sync = QPushButton("Синхронизировать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_delete = QPushButton("Удалить")
        self.btn_pay = QPushButton("Оплатить выбранные")
        self.btn_refresh_payment = QPushButton("Проверить оплату")
        self.btn_print = QPushButton("Печать паспортов")
        actions.addWidget(self.btn_sync)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_delete)
        actions.addWidget(self.btn_pay)
        actions.addWidget(self.btn_refresh_payment)
        actions.addWidget(self.btn_print)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.btn_back.clicked.connect(self.go_back)
        self.btn_select_all.clicked.connect(self.select_all_rows)
        self.btn_select_unpaid.clicked.connect(self.select_unpaid_rows)
        self.btn_clear_selection.clicked.connect(self.clear_checked_rows)
        self.btn_sync.clicked.connect(self.sync_records)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_pay.clicked.connect(self.pay_selected)
        self.btn_refresh_payment.clicked.connect(self.refresh_payment_status)
        self.btn_print.clicked.connect(self.open_print_dialog)
        self.table.cellClicked.connect(self.handle_cell_clicked)
        self.cmb_period.currentIndexChanged.connect(self.apply_filters)
        self.cmb_paid_filter.currentIndexChanged.connect(self.apply_filters)
        self.cmb_sync_filter.currentIndexChanged.connect(self.apply_filters)
        self.cmb_printed_filter.currentIndexChanged.connect(self.apply_filters)

        self.reload()

    def reload(self):
        if db is None or Application is None or Sheep is None or User is None or Owner is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
            return

        try:
            db.expire_all()
        except Exception:
            pass

        try:
            detail = get_owner_detail_rows(db, User, Sheep, Application, Owner, self.owner_id)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return

        if detail is None:
            QMessageBox.warning(self, "Хозяйство", "Хозяйство не найдено.")
            self.close()
            return

        self.owner_data = detail["owner"]
        self.rows = detail["rows"]

        self.lbl_title.setText(f"Хозяйство: {detail['owner_name']}")
        self.lbl_subtitle.setText(
            f"Телефон: {detail['phone'] or '—'}    Населённый пункт: {detail['location'] or '—'}"
        )

        self.apply_filters()

    def apply_filters(self):
        period = self.cmb_period.currentData() or "1m"
        paid_filter = self.cmb_paid_filter.currentData() or ""
        sync_filter = self.cmb_sync_filter.currentData() or ""
        printed_filter = self.cmb_printed_filter.currentData() or ""

        today = datetime.date.today()
        if period == "all":
            since = None
        elif period == "3m":
            since = today - datetime.timedelta(days=90)
        elif period == "1y":
            since = today - datetime.timedelta(days=365)
        else:
            since = today - datetime.timedelta(days=30)

        filtered = []
        for row in self.rows:
            sheep = row["sheep"]
            created_at = getattr(sheep, "date_filling", None)
            latest_application = row.get("latest_application")
            latest_app_date = getattr(latest_application, "date", None) if latest_application is not None else None
            activity_date = created_at
            if latest_app_date and (activity_date is None or latest_app_date > activity_date):
                activity_date = latest_app_date
            if since is not None and activity_date and activity_date < since:
                continue
            if paid_filter == "paid" and row.get("is_unpaid"):
                continue
            if paid_filter == "unpaid" and not row.get("is_unpaid"):
                continue
            row_synced = bool(row.get("is_synced", getattr(sheep, "synced", False)))
            if sync_filter == "synced" and not row_synced:
                continue
            if sync_filter == "unsynced" and row_synced:
                continue
            if printed_filter == "printed" and not bool(getattr(sheep, "is_printed", False)):
                continue
            if printed_filter == "unprinted" and bool(getattr(sheep, "is_printed", False)):
                continue
            filtered.append(row)

        self.filtered_rows = filtered
        self.table.setRowCount(len(self.filtered_rows))
        for r, row in enumerate(self.filtered_rows):
            checkbox_item = QTableWidgetItem("")
            checkbox_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            checkbox_item.setCheckState(Qt.Unchecked)
            self.table.setItem(r, 0, checkbox_item)

            values = format_owner_sheep_row(row)
            for c, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                if c == 2:
                    item.setData(Qt.UserRole, row["sheep"].id)
                self.table.setItem(r, c, item)

        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 110)
        self.statusBar().showMessage(f"Овец в хозяйстве: {len(self.filtered_rows)} из {len(self.rows)}")

    def _selected_rows(self):
        selected = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked and 0 <= row < len(self.filtered_rows):
                selected.append(self.filtered_rows[row])
        return selected

    def _single_selected_row(self):
        selected = self._selected_rows()
        if not selected:
            current_row = self.table.currentRow()
            if 0 <= current_row < len(self.filtered_rows):
                return self.filtered_rows[current_row]
            return None
        if len(selected) != 1:
            QMessageBox.information(self, "Редактирование", "Выберите только одну строку.")
            return None
        return selected[0]

    def handle_cell_clicked(self, row, column):
        if column == 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _set_checked_rows(self, predicate):
        for row_index, row_data in enumerate(self.filtered_rows):
            item = self.table.item(row_index, 0)
            if item is None:
                continue
            item.setCheckState(Qt.Checked if predicate(row_data) else Qt.Unchecked)

    def select_all_rows(self):
        self._set_checked_rows(lambda _: True)

    def select_unpaid_rows(self):
        self._set_checked_rows(lambda row: row.get("is_unpaid"))

    def clear_checked_rows(self):
        self._set_checked_rows(lambda _: False)

    def sync_records(self):
        if self.sync_worker is not None and self.sync_worker.isRunning():
            return

        self.sync_worker = SyncWorker(self, owner_id=self.owner_id)
        self.sync_worker.finished_ok.connect(self._on_sync_finished)
        self.sync_worker.cancelled.connect(self._on_sync_cancelled)
        self.sync_worker.failed.connect(self._on_sync_failed)
        self.sync_worker.progress.connect(self._on_sync_progress)
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("Продолжение...")
        self._create_sync_dialog()
        self.statusBar().showMessage("Синхронизация хозяйства выполняется...")
        self.sync_worker.start()

    def _create_sync_dialog(self):
        self.sync_dialog = QProgressDialog("Подготовка синхронизации...", "Остановить", 0, 0, self)
        self.sync_dialog.setWindowTitle("Синхронизация хозяйства")
        self.sync_dialog.setWindowModality(Qt.WindowModal)
        self.sync_dialog.setMinimumDuration(0)
        self.sync_dialog.setAutoClose(False)
        self.sync_dialog.setAutoReset(False)
        self.sync_dialog.canceled.connect(self._request_stop_sync)
        self.sync_dialog.show()

    def _request_stop_sync(self):
        if self.sync_worker is None:
            return
        self.sync_worker.stop()
        if self.sync_dialog is not None:
            self.sync_dialog.setLabelText("Останавливаем синхронизацию...")
            self.sync_dialog.setCancelButton(None)

    def _on_sync_progress(self, stage: str, model_name: str, current: int, total: int, message: str):
        if self.sync_dialog is None:
            return
        if total > 0:
            if self.sync_dialog.maximum() != total:
                self.sync_dialog.setRange(0, total)
            self.sync_dialog.setValue(min(current, total))
        else:
            self.sync_dialog.setRange(0, 0)
        self.sync_dialog.setLabelText(message or "Синхронизация хозяйства...")

    def _on_sync_finished(self):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Синхронизировать")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        try:
            db.expire_all()
        except Exception:
            pass
        self.reload()
        prev = getattr(self, "prev", None)
        if prev is not None and hasattr(prev, "reload"):
            prev.reload()
        self.statusBar().showMessage("Синхронизация хозяйства завершена.", 5000)
        QMessageBox.information(self, "Синхронизация", "Синхронизация хозяйства завершена.")
        self.sync_worker = None

    def _on_sync_cancelled(self):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Продолжить синхронизацию")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        self.statusBar().showMessage("Синхронизация хозяйства остановлена.", 5000)
        QMessageBox.information(self, "Синхронизация", "Синхронизация хозяйства остановлена. Можно продолжить позже.")
        self.sync_worker = None

    def _on_sync_failed(self, message: str):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Продолжить синхронизацию")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        self.statusBar().showMessage("Синхронизация завершилась с ошибкой.", 5000)
        QMessageBox.warning(self, "Синхронизация", f"Не удалось выполнить синхронизацию.\n{message}")
        self.sync_worker = None

    def edit_selected(self):
        row = self._single_selected_row()
        if row is None:
            return

        sheep = row["sheep"]
        application = row.get("latest_application") if row.get("record_type") != "Овца" else None
        editor = SheepCreateWindow(owner_id=self.owner_id, parent=self)
        editor.prev = self
        editor.load_for_edit(sheep.id, getattr(application, "id", None))
        editor.created.connect(lambda _sid: self.reload())
        editor.showMaximized()
        self.hide()

    def delete_selected(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(self, "Удаление", "Выберите одну или несколько строк.")
            return

        current_user_id = (AuthState.user or {}).get("id")
        if current_user_id is None:
            QMessageBox.warning(self, "Удаление", "Для удаления нужно войти в систему.")
            return

        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить выбранные записи: {len(selected)}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        deleted_count = 0
        for row in selected:
            try:
                soft_delete_sheep_record(db, row, current_user_id)
                deleted_count += 1
            except Exception as e:
                QMessageBox.warning(self, "Удаление", str(e))
                return

        self.reload()
        self.statusBar().showMessage(f"Удалено записей: {deleted_count}", 5000)

    def pay_selected(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(self, "Оплата", "Выберите одну или несколько овец.")
            return

        pending = [row for row in selected if row["can_pay"]]
        blocked = len(selected) - len(pending)
        if not pending:
            QMessageBox.warning(
                self,
                "Оплата",
                "Среди выбранных нет овец, готовых к оплате. Нужна синхронизация и неоплаченная овца.",
            )
            return

        try:
            payload = create_payment(db, pending)
        except Exception as e:
            QMessageBox.warning(self, "Оплата", str(e))
            return

        self.reload()
        payment_token = payload.get("payment_token")
        reference = payload.get("reference") or "—"
        full_item_price = payload.get("unit_price", 0)
        full_item_quantity = payload.get("full_item_quantity", 0)
        application_only_quantity = payload.get("application_only_quantity", 0)
        application_only_price = payload.get("application_only_price", 0)
        breakdown_lines = []
        if full_item_quantity:
            breakdown_lines.append(f"По {full_item_price} сом: {full_item_quantity}")
        if application_only_quantity:
            breakdown_lines.append(f"По {application_only_price} сом: {application_only_quantity}")

        if payment_token:
            dlg = PaymentQrDialog(
                payment_token=payment_token,
                total_amount=payload.get("total_amount", 0),
                quantity=payload.get("quantity", 0),
                reference=reference,
                full_item_price=full_item_price,
                full_item_quantity=full_item_quantity,
                application_only_quantity=application_only_quantity,
                application_only_price=application_only_price,
                parent=self,
            )
            dlg.exec_()
            if dlg.should_check_payment:
                self._refresh_payment_status_for_rows(pending, show_message=True)
            return

        message = (
            f"Создана оплата.\n"
            f"Количество: {payload.get('quantity', 0)}\n"
            f"Сумма: {payload.get('total_amount', 0)} сом\n"
            f"{chr(10).join(breakdown_lines) + chr(10) if breakdown_lines else ''}"
            f"Reference: {reference}\n"
            f"Недоступно в текущем выборе: {blocked}"
        )
        QMessageBox.information(self, "Оплата", message)

    def refresh_payment_status(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(self, "Проверка оплаты", "Выберите одну или несколько овец.")
            return

        try:
            self._refresh_payment_status_for_rows(selected, show_message=True)
        except Exception as e:
            QMessageBox.warning(self, "Проверка оплаты", str(e))
            return

    def _refresh_payment_status_for_rows(self, rows, show_message: bool = False):
        summary = refresh_payment_statuses(db, rows)
        self.reload()
        if not show_message:
            return summary
        checked_total = int(summary.get("checked_references", 0)) + int(summary.get("checked_items", 0))
        paid_total = int(summary.get("paid_references", 0)) + int(summary.get("paid_items", 0))
        sources = []
        if summary.get("used_reference_check"):
            sources.append("по reference")
        if summary.get("used_items_check"):
            sources.append("по списку ID")
        source_text = ", ".join(sources) if sources else "—"
        QMessageBox.information(
            self,
            "Проверка оплаты",
            f"Проверено: {checked_total}.\n"
            f"Оплачено: {paid_total}.\n"
            f"Источник проверки: {source_text}.",
        )
        return summary

    def open_print_dialog(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(self, "Печать", "Выберите одну или несколько овец.")
            return

        printable = [row for row in selected if row["can_print"]]
        if not printable:
            QMessageBox.warning(
                self,
                "Печать",
                "Среди выбранных нет овец с доступным паспортом. Печать возможна только после оплаты.",
            )
            return

        batch_size = get_print_batch_size()
        batches = [printable[index:index + batch_size] for index in range(0, len(printable), batch_size)]
        dlg = PrintBatchDialog(db, batches, self.owner_data, self.owner_id, self)
        dlg.exec_()

    def go_back(self):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        self._suppress_restore = True
        self.close()

    def closeEvent(self, ev):
        if self.sync_worker is not None and self.sync_worker.isRunning():
            QMessageBox.information(self, "Синхронизация", "Дождитесь завершения синхронизации.")
            ev.ignore()
            return
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)
