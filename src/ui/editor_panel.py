import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLabel,
                               QPushButton, QHBoxLayout, QCheckBox, QListWidget)
from PySide6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
                           QTextDocument, QTextOption)
from PySide6.QtCore import Qt, Signal, QEvent
from core.masker import Masker
from core.i18n import I18N


class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#FF9D00"))  # Orange
        self.tag_format.setFontWeight(QFont.Weight.Bold)
        self.pattern = re.compile(r"(@@\s*PLACEHOLDER_\d+\s*@@|<[^>]+>|\[[^\]]+\]|\{[^\}]+\}|%.*?[dsf])")

    def highlightBlock(self, text):
        for match in self.pattern.finditer(text):
            self.setFormat(match.start(), match.end() -
                           match.start(), self.tag_format)


class EditorPanel(QWidget):
    request_next_needed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # 1. Widgets
        self.source_label = QLabel(I18N.t("ui_editor_source_label"))
        layout.addWidget(self.source_label)
        self.source_edit = QTextEdit()
        self.source_edit.setReadOnly(True)
        
        layout.addWidget(self.source_edit)

        self.ai_draft_label = QLabel(I18N.t("ui_editor_ai_draft_label"))
        layout.addWidget(self.ai_draft_label)
        self.ai_draft_display = QTextEdit()
        self.ai_draft_display.setReadOnly(True)
        self.ai_draft_display.setMaximumHeight(60)
        self.ai_draft_display.setStyleSheet(
            "font-style: italic;"
        )
        layout.addWidget(self.ai_draft_display)

        self.tag_helper_label = QLabel(I18N.t("ui_tag_helper_label"))
        self.tag_helper_label.setToolTip(I18N.t("ui_tag_helper_tooltip"))
        layout.addWidget(self.tag_helper_label)
        self.tag_helper_container = QWidget()
        self.tag_helper_layout = QHBoxLayout(self.tag_helper_container)
        self.tag_helper_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_helper_layout.setSpacing(4)
        layout.addWidget(self.tag_helper_container)
        self._tag_buttons = []

        self.active_translation_label = QLabel(
            I18N.t("ui_editor_active_translation_label")
        )
        layout.addWidget(self.active_translation_label)
        self.trans_edit = QTextEdit()
        layout.addWidget(self.trans_edit)

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
        layout.addLayout(ctrl_layout)

        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_rollback = QPushButton(I18N.t("btn_reset_ai_draft"))
        self.btn_prev = QPushButton(I18N.t("btn_prev"))
        self.btn_next = QPushButton(I18N.t("btn_next"))
        self.btn_invisibles = QPushButton(I18N.t("btn_show_invisibles"))
        self.btn_invisibles.setCheckable(True)
        self.btn_invisibles.setFixedWidth(60)
        self.btn_invisibles.clicked.connect(self.toggle_invisibles)
        nav_layout.addWidget(self.btn_rollback)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_invisibles)
        layout.addLayout(nav_layout)

        self.history_label = QLabel(I18N.t("ui_history_label"))
        layout.addWidget(self.history_label)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        layout.addWidget(self.history_list)

        # 7. Fuzzy Match Suggestion
        self.fuzzy_label = QLabel(I18N.t("ui_fuzzy_label"))
        layout.addWidget(self.fuzzy_label)
        self.fuzzy_display = QTextEdit()
        self.fuzzy_display.setReadOnly(True)
        self.fuzzy_display.setMaximumHeight(80)
        self.fuzzy_display.setStyleSheet(
            "background-color: #0d47a1; color: white; border-radius: 4px;"
        )
        layout.addWidget(self.fuzzy_display)

        self.btn_use_fuzzy = QPushButton(I18N.t("btn_use_suggestion"))
        self.btn_use_fuzzy.setVisible(False)
        layout.addWidget(self.btn_use_fuzzy)

        # 2. Highlighting
        self.source_highlighter = TagHighlighter(self.source_edit.document())
        self.trans_highlighter = TagHighlighter(self.trans_edit.document())

        # 3. Shortcuts
        self.trans_edit.installEventFilter(self)
        self.set_tag_chips([])

    def _extract_tags(self, text: str) -> list[str]:
        matches = self._tag_extractor_pattern.findall(text)
        return [m[0] if isinstance(m, tuple) else m for m in matches if m]

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

        for tag in tags:
            btn = QPushButton(tag)
            btn.setToolTip(I18N.t("ui_tag_helper_tooltip"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setStyleSheet(
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
                    self.request_next_needed.emit()
                    return True
        return super().eventFilter(obj, event)

    def set_font_size(self, font_obj: QFont):
        self.source_edit.setFont(font_obj)
        self.trans_edit.setFont(font_obj)
        self.ai_draft_display.setFont(font_obj)
        self.history_list.setFont(font_obj)

    def retranslate_ui(self):
        translatable_widgets = {
            self.source_label: "ui_editor_source_label",
            self.ai_draft_label: "ui_editor_ai_draft_label",
            self.tag_helper_label: "ui_tag_helper_label",
            self.active_translation_label: "ui_editor_active_translation_label",
            self.cb_verified: "ui_mark_verified",
            self.btn_save: "btn_save_ctrl_enter",
            self.btn_rollback: "btn_reset_ai_draft",
            self.btn_prev: "btn_prev",
            self.btn_next: "btn_next",
            self.btn_invisibles: "btn_show_invisibles",
            self.history_label: "ui_history_label",
            self.fuzzy_label: "ui_fuzzy_label",
            self.btn_use_fuzzy: "btn_use_suggestion",
        }
        for widget, key in translatable_widgets.items():
            widget.setText(I18N.t(key))
        self.tag_helper_label.setToolTip(I18N.t("ui_tag_helper_tooltip"))
