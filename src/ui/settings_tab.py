from PySide6.QtWidgets import (QWidget, QFormLayout, QComboBox, QDoubleSpinBox, 
                             QLineEdit, QPushButton, QHBoxLayout, QFileDialog, 
                             QMessageBox, QCheckBox, QTextEdit, QLabel, QVBoxLayout, QGroupBox)
from PySide6.QtCore import QSettings, Signal 
from services.llm_service import LLMService
from core.database import TranslationRecord, Session, engine
from sqlmodel import SQLModel, delete, col

class SettingsTab(QWidget):
    font_changed = Signal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.llm_service = LLMService()

        
        
        # Main Layout is Vertical
        self.main_layout = QVBoxLayout(self)
        
        # 1. GENERAL SETTINGS GROUP
        gen_group = QGroupBox("General Configuration")
        gen_form = QFormLayout(gen_group)

        self.target_lang_input = QLineEdit("BG")
        gen_form.addRow("Target Language:", self.target_lang_input)

        self.model_dropdown = QComboBox()
        self.refresh_btn = QPushButton("Refresh Ollama")
        self.refresh_btn.clicked.connect(self.refresh_models)
        gen_form.addRow("Ollama Model:", self.model_dropdown)
        gen_form.addRow("", self.refresh_btn)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.0)
        self.temp_spin.setValue(0.1)
        self.temp_spin.setSingleStep(0.1)
        gen_form.addRow("AI Temperature:", self.temp_spin)

        self.strict_mode = QCheckBox("Strict Tag Validation (Retry on error)")
        self.strict_mode.setChecked(True)
        gen_form.addRow("Validation:", self.strict_mode)

        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(8, 30)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.font_changed.emit)
        gen_form.addRow("UI Font Size:", self.font_size_spin)
        
        self.main_layout.addWidget(gen_group)

        # 2. RESOURCES GROUP
        res_group = QGroupBox("Resource Paths")
        res_form = QFormLayout(res_group)

        self.gloss_path = QLineEdit("glossary.tsv")
        self.style_path = QLineEdit("style.md")
        self.forbidden_path = QLineEdit("forbidden.txt")

        for label, edit, filt in [
            ("Glossary:", self.gloss_path, "TSV/CSV (*.tsv *.csv)"),
            ("Style Guide:", self.style_path, "Text/MD (*.md *.txt)"),
            ("Forbidden:", self.forbidden_path, "Text (*.txt)")
        ]:
            row = QHBoxLayout()
            row.addWidget(edit)
            btn = QPushButton("Browse")
            btn.clicked.connect(lambda checked=False, e=edit, f=filt: self.browse_file(e, f))
            row.addWidget(btn)
            res_form.addRow(label, row)
            
        self.main_layout.addWidget(res_group)

        # 3. PROMPT EDITOR GROUP
        prompt_group = QGroupBox("Prompt Editor & Library")
        prompt_layout = QVBoxLayout(prompt_group)

        # Template Library Selector
        lib_row = QHBoxLayout()
        lib_row.addWidget(QLabel("Templates:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(["Standard Localizer", "Technical Fixer (Pass 2)", "Creative Polish"])
        self.template_combo.currentIndexChanged.connect(self.apply_template)
        lib_row.addWidget(self.template_combo, 1)
        prompt_layout.addLayout(lib_row)

        self.prompt_editor = QTextEdit()
        self.prompt_editor.setAcceptRichText(False)
        self.prompt_editor.setPlaceholderText("Use placeholders: {target_lang}, {glossary}, {style}, {forbidden}, {source}")
        prompt_layout.addWidget(self.prompt_editor)
        self.main_layout.addWidget(prompt_group)

        # 4. DANGER ZONE
        danger_group = QGroupBox("Database Maintenance")
        danger_layout = QHBoxLayout(danger_group)
        
        self.btn_clear_errors = QPushButton("Clear Tag Errors")
        self.btn_clear_errors.clicked.connect(self.clear_mismatches)
        
        self.btn_clear_all = QPushButton("Wipe All Memory")
        self.btn_clear_all.setStyleSheet("background-color: #ff4d4d; color: white;")
        self.btn_clear_all.clicked.connect(self.clear_memory)
        
        danger_layout.addWidget(self.btn_clear_errors)
        danger_layout.addWidget(self.btn_clear_all)
        self.main_layout.addWidget(danger_group)

        # Initialization
        self.refresh_models()
        self.load_settings()

    def get_default_prompt(self):
        return (
            "### ROLE: Expert {target_lang} Game Localizer\n"
            "### RULES:\n"
            "- Glossary: {glossary}\n"
            "- Style: {style}\n"
            "- Forbidden: {forbidden}\n"
            "- TAGS: Keep all [#_0_], [#_1_] anchors exactly where they are.\n\n"
            "### SOURCE TEXT:\n{source}\n\n"
            "### TRANSLATION:\n"
        )

    def apply_template(self):
        """Pre-loads specific prompt structures based on selection."""
        idx = self.template_combo.currentIndex()
        if idx == 0: # Standard
            self.prompt_editor.setPlainText(self.get_default_prompt())
        elif idx == 1: # Fixer
            self.prompt_editor.setPlainText(
                "### ROLE: Technical Fixer\n"
                "I have a translation that broke the technical tags. \n"
                "1. FIX the tags [#_x_] based on the Source.\n"
                "2. IMPROVE the Bulgarian grammar in the Existing Translation.\n\n"
                "### SOURCE (English):\n{source}\n\n"
                "### EXISTING TRANSLATION (BG):\n{translation}\n\n"
                "### CORRECTED TRANSLATION:\n"
            )
        elif idx == 2: # Creative
            self.prompt_editor.setPlainText(
                "### ROLE: Fantasy Writer\n"
                "Re-write this {target_lang} translation to be more epic and poetic.\n"
                "Glossary: {glossary}\n"
                "Source: {source}\n"
                "Target:"
            )

    def browse_file(self, line_edit, file_filter):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
        if file_path:
            line_edit.setText(file_path)

    def refresh_models(self):
        models = self.llm_service.get_models()
        self.model_dropdown.clear()
        if models:
            self.model_dropdown.addItems(models)
    
    def save_settings(self):
        """Saves only the form-related settings."""
        s = QSettings("FoundryL10n", "TranslatorApp")
        s.setValue("target_lang", self.target_lang_input.text())
        s.setValue("model", self.model_dropdown.currentText())
        s.setValue("glossary_path", self.gloss_path.text())
        s.setValue("style_path", self.style_path.text())
        s.setValue("forbidden_path", self.forbidden_path.text())
        s.setValue("temp", self.temp_spin.value())
        s.setValue("strict_mode", self.strict_mode.isChecked())
        # Save the current text in the prompt editor
        s.setValue("custom_prompt", self.prompt_editor.toPlainText())
        # Save the font size
        s.setValue("ui_font_size", self.font_size_spin.value())

    def load_settings(self):
        """Loads only the form-related settings with string casting."""
        s = QSettings("FoundryL10n", "TranslatorApp")
        self.target_lang_input.setText(str(s.value("target_lang", "BG")))
        
        saved_model = str(s.value("model", ""))
        idx = self.model_dropdown.findText(saved_model)
        if idx >= 0: 
            self.model_dropdown.setCurrentIndex(idx)
        
        self.gloss_path.setText(str(s.value("glossary_path", "glossary.tsv")))
        self.style_path.setText(str(s.value("style_path", "style.md")))
        self.forbidden_path.setText(str(s.value("forbidden_path", "forbidden.txt")))
        
        is_strict = str(s.value("strict_mode", "true")).lower() == "true"
        self.strict_mode.setChecked(is_strict)

        # Load the prompt
        default_p = self.get_default_prompt()
        self.prompt_editor.setPlainText(str(s.value("custom_prompt", default_p)))

        # Load font size and trigger the update
        try:
            f_size = float(str(s.value("ui_font_size", 12)))
            self.font_size_spin.setValue(f_size)
            # Manually emit once to apply font on startup
            self.font_changed.emit(f_size)
        except (ValueError, TypeError):
            self.font_size_spin.setValue(12)

    def get_settings(self):
        return {
            "model": self.model_dropdown.currentText(),
            "temp": self.temp_spin.value(),
            "lang": self.target_lang_input.text(),
            "glossary_path": self.gloss_path.text(),
            "style_path": self.style_path.text(),
            "forbidden_path": self.forbidden_path.text(),
            "strict_mode": self.strict_mode.isChecked(),
            "prompt_template": self.prompt_editor.toPlainText()
        }
    
    def clear_mismatches(self):
        """Fixed: Using col() to satisfy Pylance type checking."""
        reply = QMessageBox.question(self, "Retry Errors", "Clear ONLY tag mismatches from memory?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with Session(engine) as session:
                    # We wrap the attribute in col() so Pylance knows .like() exists
                    statement = delete(TranslationRecord).where(
                        col(TranslationRecord.translation).like("%[TAG ERROR]%")
                    )
                    session.exec(statement)
                    session.commit()
                QMessageBox.information(self, "Success", "Error rows cleared from memory.")
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not clear errors: {e}")

    def clear_memory(self):
        reply = QMessageBox.question(self, "Wipe All", "Delete ALL saved translations?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                SQLModel.metadata.drop_all(engine)
                SQLModel.metadata.create_all(engine)
                QMessageBox.information(self, "Success", "Memory is now empty.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to wipe DB: {e}")