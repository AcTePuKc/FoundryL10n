from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLabel,
                               QPushButton, QHBoxLayout, QCheckBox, QListWidget)
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument
from PySide6.QtCore import Qt, Signal, QEvent
import re


class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#FF9D00"))  # Orange
        self.tag_format.setFontWeight(QFont.Weight.Bold)
        self.pattern = re.compile(r"(\[#_\d+_\]|<[^>]+>|\[[^\]]+\])")

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
        layout.addWidget(QLabel("Source:"))
        self.source_edit = QTextEdit()
        self.source_edit.setReadOnly(True)
        self.source_edit.setStyleSheet(
            "background-color: #2b2b2b; color: #a9b7c6;"
        )
        layout.addWidget(self.source_edit)

        layout.addWidget(QLabel("Original AI Draft:"))
        self.ai_draft_display = QTextEdit()
        self.ai_draft_display.setReadOnly(True)
        self.ai_draft_display.setMaximumHeight(60)
        self.ai_draft_display.setStyleSheet(
            "background-color: #1e1e1e; color: #777; font-style: italic;"
        )
        layout.addWidget(self.ai_draft_display)

        layout.addWidget(QLabel("Active Translation:"))
        self.trans_edit = QTextEdit()
        layout.addWidget(self.trans_edit)

        # Controls
        ctrl_layout = QHBoxLayout()
        self.cb_verified = QCheckBox("Mark Verified (🟢)")

        self.btn_translate_now = QPushButton("🤖 Translate Line")
        self.btn_translate_now.setStyleSheet(
            "background-color: #34495e; color: white;"
        )

        self.btn_save = QPushButton("Save (Ctrl+Enter)")

        ctrl_layout.addWidget(self.cb_verified)
        ctrl_layout.addWidget(self.btn_translate_now)
        ctrl_layout.addWidget(self.btn_save)
        layout.addLayout(ctrl_layout)

        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_rollback = QPushButton("↺ Reset to AI Draft")
        self.btn_prev = QPushButton("<< Prev")
        self.btn_next = QPushButton("Next >>")
        nav_layout.addWidget(self.btn_rollback)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        layout.addLayout(nav_layout)

        layout.addWidget(QLabel("History:"))
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        layout.addWidget(self.history_list)

        # 7. Fuzzy Match Suggestion
        layout.addWidget(QLabel("<b>Smart Suggestion (Fuzzy Match):</b>"))
        self.fuzzy_display = QTextEdit()
        self.fuzzy_display.setReadOnly(True)
        self.fuzzy_display.setMaximumHeight(80)
        self.fuzzy_display.setStyleSheet(
            "background-color: #0d47a1; color: white; border-radius: 4px;"
        )
        layout.addWidget(self.fuzzy_display)

        self.btn_use_fuzzy = QPushButton("Use Suggestion")
        self.btn_use_fuzzy.setVisible(False)
        layout.addWidget(self.btn_use_fuzzy)

        # 2. Highlighting
        self.source_highlighter = TagHighlighter(self.source_edit.document())
        self.trans_highlighter = TagHighlighter(self.trans_edit.document())

        # 3. Shortcuts
        self.trans_edit.installEventFilter(self)


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
