from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QTextEdit, QLabel

PROMPTS = {
    "Standard Translator": (
        "### ROLE: Expert {target_lang} Game Localizer\n"
        "Translate the following string accurately.\n"
        "Rules:\n- Glossary: {glossary}\n- Style: {style}\n"
        "- Tags: Keep [#_0_], [#_1_] exactly where they are.\n\n"
        "Source: {source}\nTarget:"
    ),
    "Technical Fixer (Strict)": (
        "### ROLE: Technical Fixer\n"
        "I have a translation that broke the tags. Fix the tags and the Bulgarian grammar.\n"
        "Source: {source}\n"
        "Rules: Preserve all [#_x_] anchors.\n"
        "Target:"
    ),
    "Narrative Polish": (
        "### ROLE: Creative Writer\n"
        "Make this Bulgarian translation sound more heroic and high-fantasy.\n"
        "Source: {source}\nTarget:"
    )
}

class PromptEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Prompt Library:"))
        self.library_combo = QComboBox()
        self.library_combo.addItems(list(PROMPTS.keys()))
        self.library_combo.currentIndexChanged.connect(self.load_template)
        layout.addWidget(self.library_combo)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText("Use {source}, {target_lang}, {glossary}, {style}")
        layout.addWidget(self.editor)
        
        self.load_template()

    def load_template(self):
        name = self.library_combo.currentText()
        self.editor.setPlainText(PROMPTS[name])