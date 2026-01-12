from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.i18n import I18N


class LoginDialog(QDialog):
    submitted = Signal(dict)

    def __init__(self, provider_name: str, auth_type: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.auth_type = auth_type.lower()
        self.setWindowTitle(I18N.t("dlg_login_title").format(provider=provider_name))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.fields: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)

        self.info_label = QLabel(
            I18N.t("msg_login_hint").format(provider=provider_name, auth=self.auth_type)
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.form_layout = QFormLayout()
        layout.addLayout(self.form_layout)
        self._build_fields()

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #d32f2f;")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_cancel = QPushButton(I18N.t("btn_cancel"))
        self.btn_login = QPushButton(I18N.t("btn_login"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_login.clicked.connect(self._submit)
        button_row.addWidget(self.btn_cancel)
        button_row.addWidget(self.btn_login)
        layout.addLayout(button_row)

    def _build_fields(self) -> None:
        for key, widget in self.fields.items():
            self.form_layout.removeWidget(widget)
            widget.deleteLater()
        self.fields.clear()

        if self.auth_type == "basic":
            self._add_field("username", I18N.t("label_username"))
            password = self._add_field("password", I18N.t("label_password"))
            password.setEchoMode(QLineEdit.EchoMode.Password)
            return

        if self.auth_type == "oauth2":
            self._add_field("client_id", I18N.t("label_client_id"))
            secret = self._add_field("client_secret", I18N.t("label_client_secret"))
            secret.setEchoMode(QLineEdit.EchoMode.Password)
            return

        token = self._add_field("token", I18N.t("label_api_token"))
        token.setEchoMode(QLineEdit.EchoMode.Password)

    def _add_field(self, key: str, label: str) -> QLineEdit:
        field = QLineEdit()
        self.form_layout.addRow(QLabel(label), field)
        self.fields[key] = field
        return field

    def _submit(self) -> None:
        credentials = {key: field.text().strip() for key, field in self.fields.items()}
        if any(value == "" for value in credentials.values()):
            self.set_error(I18N.t("msg_login_missing_fields"))
            return
        self.submitted.emit(credentials)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
