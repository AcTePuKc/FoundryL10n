from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLabel, 
                             QPushButton, QHBoxLayout, QCheckBox)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

class EditorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # 1. Source Area
        layout.addWidget(QLabel("Source (English):"))
        self.source_edit = QTextEdit()
        self.source_edit.setReadOnly(True)
        # Dark theme for the source
        self.source_edit.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; border: 1px solid #444;")
        layout.addWidget(self.source_edit)

        # 2. Translation Area
        layout.addWidget(QLabel("Translation (BG):"))
        self.trans_edit = QTextEdit()
        self.trans_edit.setStyleSheet("font-size: 14pt;")
        layout.addWidget(self.trans_edit)

        # 3. Controls (Verify & Save)
        ctrl_layout = QHBoxLayout()
        self.cb_verified = QCheckBox("Mark as Verified (🟢)")
        self.btn_save = QPushButton("Save Segment")
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setStyleSheet("font-weight: bold;")
        
        ctrl_layout.addWidget(self.cb_verified)
        ctrl_layout.addWidget(self.btn_save)
        layout.addLayout(ctrl_layout)

        # 4. Navigation (Next/Prev Error)
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("<< Prev Error")
        self.btn_next = QPushButton("Next Error >>")
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        layout.addLayout(nav_layout)

        # 5. Install Shortcut Filter
        # This makes Ctrl+Enter work in the text box
        self.trans_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Shortcut Handler: Ctrl+Enter to save and move to next error."""
        if obj is self.trans_edit and event.type() == event.Type.KeyPress:
            if (event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter) and \
               event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.btn_save.click()
                self.btn_next.click()
                return True
        return super().eventFilter(obj, event)

    def set_font_size(self, size):
        font = QFont("Consolas", size)
        self.source_edit.setFont(font)
        self.trans_edit.setFont(font)