from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLabel,
                               QPushButton, QHBoxLayout, QCheckBox,
                               QListWidget, QToolButton, QLineEdit,
                               QFormLayout, QComboBox, QDateEdit,
                               QDoubleSpinBox)
from PySide6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
                           QTextDocument, QTextOption)
from PySide6.QtCore import Qt, Signal, QEvent, QDate
from core.i18n import I18N
from core.tag_utils import extract_tags, tag_regex


class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#FF9D00"))  # Orange
        self.tag_format.setFontWeight(QFont.Weight.Bold)
        self.pattern = tag_regex()

    def highlightBlock(self, text):
        for match in self.pattern.finditer(text):
            self.setFormat(match.start(), match.end() -
                           match.start(), self.tag_format)


class EditorPanel(QWidget):
    request_next_needed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QHBoxLayout(self)
        self._create_editor_container()
        self._create_highlighters()
        self._configure_shortcuts()
        self._create_provider_side_panel()
        self._init_provider_field_builders()
        self._wire_signals()
        self._main_layout.addWidget(self.editor_container, 1)
        self._main_layout.addWidget(self.provider_fields_panel)

    def _create_editor_container(self) -> None:
        # 1. Widgets
        self.source_label = QLabel(I18N.t("ui_editor_source_label"))
        self.editor_container = QWidget()
        editor_layout = QVBoxLayout(self.editor_container)
        editor_layout.addWidget(self.source_label)
        self.source_edit = QTextEdit()
        self.source_edit.setReadOnly(True)

        editor_layout.addWidget(self.source_edit)

        self.ai_draft_label = QLabel(I18N.t("ui_editor_ai_draft_label"))
        editor_layout.addWidget(self.ai_draft_label)
        self.ai_draft_display = QTextEdit()
        self.ai_draft_display.setReadOnly(True)
        self.ai_draft_display.setMaximumHeight(60)
        self.ai_draft_display.setStyleSheet(
            "font-style: italic;"
        )
        editor_layout.addWidget(self.ai_draft_display)

        self.tag_helper_label = QLabel(I18N.t("ui_tag_helper_label"))
        self.tag_helper_label.setToolTip(I18N.t("ui_tag_helper_tooltip"))
        editor_layout.addWidget(self.tag_helper_label)
        self.tag_helper_container = QWidget()
        self.tag_helper_layout = QHBoxLayout(self.tag_helper_container)
        self.tag_helper_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_helper_layout.setSpacing(4)
        editor_layout.addWidget(self.tag_helper_container)
        self._tag_buttons = []

        self.active_translation_label = QLabel(
            I18N.t("ui_editor_active_translation_label")
        )
        editor_layout.addWidget(self.active_translation_label)

        self.remote_change_container = QWidget()
        remote_layout = QVBoxLayout(self.remote_change_container)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.setSpacing(4)
        self.remote_change_label = QLabel(I18N.t("ui_remote_change_detected"))
        self.remote_change_label.setStyleSheet(
            "color: #ffcc80; font-weight: bold;"
        )
        self.remote_change_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        remote_layout.addWidget(self.remote_change_label)
        self.remote_change_diff = QTextEdit()
        self.remote_change_diff.setReadOnly(True)
        self.remote_change_diff.setMaximumHeight(140)
        self.remote_change_diff.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.remote_change_diff.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.remote_change_diff.setStyleSheet(
            "background-color: #263238; color: #ffecb3; font-family: monospace;"
        )
        remote_layout.addWidget(self.remote_change_diff)
        self.remote_change_container.setVisible(False)
        editor_layout.addWidget(self.remote_change_container)
        self.trans_edit = QTextEdit()
        editor_layout.addWidget(self.trans_edit)

        # Controls
        ctrl_layout = QHBoxLayout()
        self.cb_verified = QCheckBox(I18N.t("ui_mark_verified"))

        self.btn_translate_now = QPushButton(I18N.t("btn_translate_line"))
        self.btn_translate_now.setStyleSheet(
            "background-color: #34495e; color: white;"
        )

        self.btn_save = QPushButton(I18N.t("btn_save_ctrl_enter"))

        ctrl_layout.addWidget(self.cb_verified)
        ctrl_layout.addWidget(self.btn_translate_now)
        ctrl_layout.addWidget(self.btn_save)
        editor_layout.addLayout(ctrl_layout)

        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_rollback = QPushButton(I18N.t("btn_reset_ai_draft"))
        self.btn_prev = QPushButton(I18N.t("btn_prev"))
        self.btn_next = QPushButton(I18N.t("btn_next"))
        self.btn_invisibles = QPushButton(I18N.t("btn_show_invisibles"))
        self.btn_invisibles.setCheckable(True)
        self.btn_invisibles.setFixedWidth(60)
        nav_layout.addWidget(self.btn_rollback)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_invisibles)
        editor_layout.addLayout(nav_layout)

        self.history_label = QLabel(I18N.t("ui_history_label"))
        editor_layout.addWidget(self.history_label)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        editor_layout.addWidget(self.history_list)
        self.btn_use_history = QPushButton(I18N.t("btn_use_history"))
        self.btn_use_history.setEnabled(False)
        editor_layout.addWidget(self.btn_use_history)

        # 7. Fuzzy Match Suggestion
        self.fuzzy_label = QLabel(I18N.t("ui_fuzzy_label"))
        editor_layout.addWidget(self.fuzzy_label)
        self.fuzzy_display = QTextEdit()
        self.fuzzy_display.setReadOnly(True)
        self.fuzzy_display.setMaximumHeight(80)
        self.fuzzy_display.setStyleSheet(
            "background-color: #0d47a1; color: white; border-radius: 4px;"
        )
        editor_layout.addWidget(self.fuzzy_display)

        self.btn_use_fuzzy = QPushButton(I18N.t("btn_use_suggestion"))
        self.btn_use_fuzzy.setVisible(False)
        editor_layout.addWidget(self.btn_use_fuzzy)
        self.set_tag_chips([])

    def _create_highlighters(self) -> None:
        # 2. Highlighting
        self.source_highlighter = TagHighlighter(self.source_edit.document())
        self.trans_highlighter = TagHighlighter(self.trans_edit.document())

    def _configure_shortcuts(self) -> None:
        # 3. Shortcuts
        self.trans_edit.installEventFilter(self)

    def _create_provider_side_panel(self) -> None:
        self.provider_fields_panel = QWidget()
        provider_fields_layout = QVBoxLayout(self.provider_fields_panel)
        provider_fields_layout.setContentsMargins(8, 0, 0, 0)
        provider_fields_layout.setSpacing(6)

        self.provider_fields_toggle = QToolButton()
        self.provider_fields_toggle.setText(I18N.t("ui_provider_fields"))
        self.provider_fields_toggle.setCheckable(True)
        self.provider_fields_toggle.setChecked(False)
        self.provider_fields_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.provider_fields_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.provider_fields_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        provider_fields_layout.addWidget(self.provider_fields_toggle)

        self.provider_fields_body = QWidget()
        self.provider_fields_body_layout = QVBoxLayout(self.provider_fields_body)
        self.provider_fields_body_layout.setContentsMargins(4, 0, 0, 0)
        self.provider_fields_body_layout.setSpacing(4)
        self.provider_fields_placeholder = QLabel(
            I18N.t("ui_provider_fields_empty")
        )
        self.provider_fields_placeholder.setStyleSheet(
            "color: #90a4ae; font-style: italic;"
        )
        self.provider_fields_body_layout.addWidget(
            self.provider_fields_placeholder
        )
        self.provider_fields_content = QWidget()
        self.provider_fields_form = QFormLayout(self.provider_fields_content)
        self.provider_fields_form.setContentsMargins(0, 0, 0, 0)
        self.provider_fields_form.setSpacing(4)
        self.provider_fields_content.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.provider_fields_body_layout.addWidget(self.provider_fields_content)
        self.provider_fields_content.setVisible(False)
        provider_fields_layout.addWidget(self.provider_fields_body)
        self.provider_fields_body.setVisible(False)
        self.provider_field_widgets: dict[str, QWidget] = {}

    def _init_provider_field_builders(self) -> None:
        self._field_builders = {
            "text": self._build_text_widget,
            "textarea": self._build_textarea_widget,
            "number": self._build_number_widget,
            "boolean": self._build_boolean_widget,
            "select": self._build_select_widget,
            "date": self._build_date_widget,
        }

    def _clear_provider_fields(self) -> None:
        while self.provider_fields_form.count():
            item = self.provider_fields_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                layout = item.layout()
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()
        self.provider_field_widgets.clear()

    def _build_provider_field_widget(
        self,
        field_type: str,
        validation: dict,
        value: object,
    ) -> QWidget | None:
        builder = self._field_builders.get(field_type.lower())
        if builder is None:
            return None
        widget = builder(validation, value)
        if widget is not None:
            widget.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            if help_text := validation.get("help"):
                widget.setToolTip(str(help_text))
        return widget

    def _build_text_widget(self, validation: dict, value: object) -> QLineEdit:
        widget = QLineEdit()
        if value is not None:
            widget.setText(str(value))
        if placeholder := validation.get("placeholder"):
            widget.setPlaceholderText(str(placeholder))
        return widget

    def _build_textarea_widget(self, validation: dict, value: object) -> QTextEdit:
        widget = QTextEdit()
        if value is not None:
            widget.setPlainText(str(value))
        if placeholder := validation.get("placeholder"):
            widget.setPlaceholderText(str(placeholder))
        widget.setMaximumHeight(120)
        return widget

    def _build_number_widget(self, validation: dict, value: object) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        step = validation.get("step")
        widget.setDecimals(0 if isinstance(step, int) else 4)
        widget.setMinimum(float(validation.get("min", -1e9)))
        widget.setMaximum(float(validation.get("max", 1e9)))
        if step is not None:
            widget.setSingleStep(float(step))
        if value is not None:
            try:
                widget.setValue(float(value))
            except (TypeError, ValueError):
                pass
        return widget

    def _build_boolean_widget(self, validation: dict, value: object) -> QCheckBox:
        widget = QCheckBox()
        if value is not None:
            if isinstance(value, str):
                widget.setChecked(value.strip().lower() in {"1", "true", "yes", "y"})
            else:
                widget.setChecked(bool(value))
        return widget

    def _build_select_widget(self, validation: dict, value: object) -> QComboBox:
        widget = QComboBox()
        options = validation.get("options", [])
        if isinstance(options, list):
            widget.addItems([str(opt) for opt in options])
        if value is not None:
            value_text = str(value)
            if widget.findText(value_text) < 0:
                widget.addItem(value_text)
            widget.setCurrentText(value_text)
        return widget

    def _build_date_widget(self, validation: dict, value: object) -> QDateEdit:
        widget = QDateEdit()
        widget.setCalendarPopup(True)
        if isinstance(value, QDate):
            widget.setDate(value)
        elif isinstance(value, str):
            parsed = QDate.fromString(value, Qt.DateFormat.ISODate)
            if parsed.isValid():
                widget.setDate(parsed)
        widget.setDisplayFormat("yyyy-MM-dd")
        return widget

    def set_provider_fields(
        self,
        custom_fields: list[dict],
        field_values: dict | None = None,
    ) -> None:
        self._clear_provider_fields()
        has_fields = False
        values = field_values if isinstance(field_values, dict) else {}
        for field in custom_fields:
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id", "")).strip()
            if not field_id:
                continue
            label_text = str(field.get("label") or field_id)
            if field.get("required"):
                label_text = f"{label_text} *"
            field_type = str(field.get("type", "text"))
            validation = field.get("validation") if isinstance(field.get("validation"), dict) else {}
            value = values.get(field_id, field.get("default"))
            widget = self._build_provider_field_widget(field_type, validation, value)
            if widget is None:
                continue
            label = QLabel(label_text)
            if help_text := validation.get("help"):
                label.setToolTip(str(help_text))
            self.provider_fields_form.addRow(label, widget)
            self.provider_field_widgets[field_id] = widget
            has_fields = True
        self.provider_fields_placeholder.setVisible(not has_fields)
        self.provider_fields_content.setVisible(has_fields)

    def get_provider_field_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for field_id, widget in self.provider_field_widgets.items():
            if isinstance(widget, QLineEdit):
                values[field_id] = widget.text()
            elif isinstance(widget, QTextEdit):
                values[field_id] = widget.toPlainText()
            elif isinstance(widget, QDoubleSpinBox):
                values[field_id] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[field_id] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[field_id] = widget.currentText()
            elif isinstance(widget, QDateEdit):
                values[field_id] = widget.date().toString(Qt.DateFormat.ISODate)
        return values

    def _wire_signals(self) -> None:
        self.btn_invisibles.clicked.connect(self.toggle_invisibles)
        self.provider_fields_toggle.toggled.connect(
            self.toggle_provider_fields_panel
        )

    def _extract_tags(self, text: str) -> list[str]:
        return extract_tags(text)

    def set_tag_chips(self, tags: list[str]) -> None:
        for btn in self._tag_buttons:
            self.tag_helper_layout.removeWidget(btn)
            btn.deleteLater()
        self._tag_buttons = []

        has_tags = bool(tags)
        self.tag_helper_label.setVisible(has_tags)
        self.tag_helper_container.setVisible(has_tags)
        if not has_tags:
            return

        _TAG_BTN_STYLE = (
            "QPushButton {"
            "background-color: #2c3e50;"
            "color: white;"
            "border-radius: 10px;"
            "padding: 2px 8px;"
            "}"
            "QPushButton:hover {"
            "background-color: #3a5169;"
            "}"
        )

        for tag in tags:
            btn = QPushButton(tag)
            btn.setToolTip(I18N.t("ui_tag_helper_tooltip"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setStyleSheet(_TAG_BTN_STYLE)
            btn.clicked.connect(lambda checked=False, t=tag: self.insert_tag(t))
            self.tag_helper_layout.addWidget(btn)
            self._tag_buttons.append(btn)

        self.tag_helper_layout.addStretch(1)

    def refresh_tag_chips(self, source_text: str) -> None:
        tags = self._extract_tags(source_text or "")
        self.set_tag_chips(tags)

    def insert_tag(self, tag: str) -> None:
        cursor = self.trans_edit.textCursor()
        cursor.insertText(tag)
        self.trans_edit.setTextCursor(cursor)
        self.trans_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def toggle_invisibles(self):

        option = self.trans_edit.document().defaultTextOption()
        if self.btn_invisibles.isChecked():
            # Show spaces as dots and line breaks as symbols
            option.setFlags(QTextOption.Flag.ShowTabsAndSpaces |
                            QTextOption.Flag.ShowLineAndParagraphSeparators)
        else:
            option.setFlags(QTextOption.Flag.IncludeTrailingSpaces)  # Default

        self.trans_edit.document().setDefaultTextOption(option)
        self.source_edit.document().setDefaultTextOption(option)

    def eventFilter(self, obj, event):
        """Fixed: Using QEvent constants for stability."""
        if obj is self.trans_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.btn_save.click()
                    return True
        return super().eventFilter(obj, event)

    def set_font_size(self, font_obj: QFont):
        self.source_edit.setFont(font_obj)
        self.trans_edit.setFont(font_obj)
        self.ai_draft_display.setFont(font_obj)
        self.history_list.setFont(font_obj)
        self.remote_change_diff.setFont(font_obj)

    def set_remote_change(self, diff_text: str | None) -> None:
        if diff_text:
            self.remote_change_diff.setPlainText(diff_text)
            self.remote_change_container.setVisible(True)
        else:
            self.remote_change_diff.clear()
            self.remote_change_container.setVisible(False)

    def toggle_provider_fields_panel(self, is_open: bool) -> None:
        self.provider_fields_body.setVisible(is_open)
        self.provider_fields_toggle.setArrowType(
            Qt.ArrowType.DownArrow if is_open else Qt.ArrowType.RightArrow
        )

    def retranslate_ui(self):
        translatable_widgets = {
            self.source_label: "ui_editor_source_label",
            self.ai_draft_label: "ui_editor_ai_draft_label",
            self.tag_helper_label: "ui_tag_helper_label",
            self.active_translation_label: "ui_editor_active_translation_label",
            self.remote_change_label: "ui_remote_change_detected",
            self.cb_verified: "ui_mark_verified",
            self.btn_save: "btn_save_ctrl_enter",
            self.btn_rollback: "btn_reset_ai_draft",
            self.btn_prev: "btn_prev",
            self.btn_next: "btn_next",
            self.btn_invisibles: "btn_show_invisibles",
            self.history_label: "ui_history_label",
            self.btn_use_history: "btn_use_history",
            self.fuzzy_label: "ui_fuzzy_label",
            self.btn_use_fuzzy: "btn_use_suggestion",
            self.provider_fields_toggle: "ui_provider_fields",
            self.provider_fields_placeholder: "ui_provider_fields_empty",
        }
        for widget, key in translatable_widgets.items():
            widget.setText(I18N.t(key))
        self.tag_helper_label.setToolTip(I18N.t("ui_tag_helper_tooltip"))
