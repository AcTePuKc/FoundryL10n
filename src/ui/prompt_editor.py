from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QTextEdit, QLabel
from core.i18n import I18N

PROMPTS = {
    "Standard Localizer": (
        "### STORY CONTEXT:\n{context}\n\n"
        "### ROLE: Expert {target_lang} Game Localizer\n"
        "### TASK: Translate the string accurately. Use natural dialogue.\n"
        "### RULES:\n"
        "- GLOSSARY: {glossary}\n"
        "- STYLE: {style}\n"
        "- TAGS: Keep all [#_x_] anchors in their relative positions.\n"
        "- OUTPUT: ONLY the Bulgarian translation. NO chat. NO 'Разбира се'.\n\n"
        "SOURCE: {source}\n"
        "TARGET:"
    ),
    "Tag Surgeon (Pass 2)": (
        "### ROLE: Technical Editor\n"
        "### TASK: Re-insert anchors into the DRAFT based on the SOURCE.\n"
        "### RULES:\n"
        "1. DO NOT change the words in the DRAFT.\n"
        "2. Only place the anchors [#_0_], [#_1_], etc., where they belong.\n"
        "3. NO chat. NO explanations.\n\n"
        "SOURCE MAP: {source}\n"
        "DRAFT TEXT: {translation}\n"
        "FIXED RESULT:"
    ),
    "Narrative Polish": (
        "### ROLE: Creative Writer\n"
        "Re-write this {target_lang} translation to be more epic and high-fantasy.\n"
        "Rules: {style}\n"
        "Source: {source}\n"
        "Target:"
    )
}

class PromptEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.prompt_label = QLabel(I18N.t("ui_prompt_library"))
        layout.addWidget(self.prompt_label)
        self.library_combo = QComboBox()
        self.library_combo.addItems(list(PROMPTS.keys()))
        self.library_combo.currentIndexChanged.connect(self.load_template)
        layout.addWidget(self.library_combo)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(I18N.t("ui_prompt_library_placeholder"))
        layout.addWidget(self.editor)
        
        self.load_template()

    def retranslate_ui(self):
        self.prompt_label.setText(I18N.t("ui_prompt_library"))
        self.editor.setPlaceholderText(I18N.t("ui_prompt_library_placeholder"))

    def load_template(self):
        name = self.library_combo.currentText()
        self.editor.setPlainText(PROMPTS[name])
