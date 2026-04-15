from io import BytesIO

import qrcode
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class PaymentQrDialog(QDialog):
    def __init__(
        self,
        payment_token: str,
        total_amount: int,
        quantity: int,
        reference: str,
        full_item_price: int = 0,
        full_item_quantity: int = 0,
        application_only_quantity: int = 0,
        application_only_price: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.payment_token = payment_token
        self.seconds_left = 60
        self.should_check_payment = False

        self.setWindowTitle("QR для оплаты")
        self.resize(420, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Оплата через QR")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title)

        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setPixmap(self._build_qr_pixmap(payment_token))
        layout.addWidget(qr_label, 1)

        details = [
            f"Сумма: {total_amount} сом",
            f"Количество: {quantity}",
        ]
        if full_item_quantity:
            details.append(f"По {full_item_price}: {full_item_quantity}")
        if application_only_quantity:
            details.append(f"По {application_only_price}: {application_only_quantity}")
        details.append(f"Reference: {reference}")

        info = QLabel("\n".join(details))
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        self.lbl_timer = QLabel()
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_timer)
        self._update_timer_label()

        actions = QHBoxLayout()
        btn_check = QPushButton("Проверить оплату")
        btn_close = QPushButton("Закрыть")
        actions.addStretch(1)
        actions.addWidget(btn_check)
        actions.addWidget(btn_close)
        layout.addLayout(actions)

        btn_close.clicked.connect(self.accept)
        btn_check.clicked.connect(self._check_and_close)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _update_timer_label(self):
        self.lbl_timer.setText(f"QR закроется через: 00:{self.seconds_left:02d}")

    def _tick(self):
        self.seconds_left -= 1
        if self.seconds_left <= 0:
            self._timer.stop()
            self.should_check_payment = True
            self.accept()
            return
        self._update_timer_label()

    def _check_and_close(self):
        self.should_check_payment = True
        self.accept()

    def _build_qr_pixmap(self, payment_token: str) -> QPixmap:
        qr_image = qrcode.make(payment_token)
        buffer = BytesIO()
        qr_image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        return pixmap.scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
