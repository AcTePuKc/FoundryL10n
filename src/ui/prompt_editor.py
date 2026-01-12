from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QTextEdit, QLabel
from core.i18n import I18N

PROMPT_LIBRARY = (
    ("prompt_library_standard", "prompt_template_standard"),
    ("prompt_library_tag_surgeon_pass2", "prompt_template_tag_surgeon_pass2"),
    ("prompt_library_narrative_polish", "prompt_template_narrative_polish"),
)

class PromptEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.prompt_label = QLabel(I18N.t("ui_prompt_library"))
        layout.addWidget(self.prompt_label)
        self.library_combo = QComboBox()
        self.library_combo.currentIndexChanged.connect(self.load_template)
        layout.addWidget(self.library_combo)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(I18N.t("ui_prompt_library_placeholder"))
        layout.addWidget(self.editor)

        self.populate_library()
        self.load_template()

    def retranslate_ui(self):
        self.prompt_label.setText(I18N.t("ui_prompt_library"))
        self.editor.setPlaceholderText(I18N.t("ui_prompt_library_placeholder"))
        self.populate_library()

    def load_template(self):
        template_key = self.library_combo.currentData()
        if not template_key:
            return
        self.editor.setPlainText(I18N.t(template_key))

    def populate_library(self):
        current_key = self.library_combo.currentData()
        self.library_combo.blockSignals(True)
        self.library_combo.clear()
        for name_key, template_key in PROMPT_LIBRARY:
            self.library_combo.addItem(I18N.t(name_key), template_key)
        self.library_combo.blockSignals(False)
        if current_key:
            index = self.library_combo.findData(current_key)
            if index != -1:
                self.library_combo.setCurrentIndex(index)
        if self.library_combo.count() and self.library_combo.currentIndex() == -1:
            self.library_combo.setCurrentIndex(0)
