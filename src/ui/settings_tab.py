import os
import json
from pathlib import Path
from core.database import TranslationRecord, Session, engine, global_replace_in_db
from core.i18n import I18N
from sqlmodel import SQLModel, delete, col
from services.llm_service import LLMService
from PySide6.QtWidgets import (
    QWidget, QComboBox, QDoubleSpinBox, QLineEdit, QPushButton, QInputDialog,
    QHBoxLayout, QFileDialog, QMessageBox, QCheckBox, QTextEdit, QLabel,
    QVBoxLayout, QGroupBox, QGridLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QIcon, QFont


class SettingsTab(QWidget):
    font_changed = Signal(float)
    profile_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.llm_service = LLMService()

        # =====================================================
        # Global styling
        # =====================================================
        self.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #eeeeee;
        }
        QGroupBox {
            border: 1px solid #444444;
            border-radius: 6px;
            margin-top: 12px;
            background-color: #323232;
        }
        QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox {
            background-color: #1e1e1e;
            border: 1px solid #555555;
            color: #ffffff;
            padding: 4px;
        }
        QPushButton {
            background-color: #454545;
            border: 1px solid #666666;
            padding: 6px;
        }
        QPushButton:hover {
            background-color: #555555;
        }
        QHeaderView::section {
            background-color: #3c3f41;
            color: white;
            border: 1px solid #222222;
        }
        QTableWidget {
            gridline-color: #444444;
            background-color: #2b2b2b;
        }
        """)

        # =====================================================
        # Main layout + scroll
        # =====================================================
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # =====================================================
        # GENERAL (single dense row)
        # =====================================================
        self.general_group = self.create_group(I18N.t("ui_general"))
        gen = QHBoxLayout(self.general_group)
        gen.setSpacing(8)

        self.target_lang_input = QLineEdit("BG")
        self.target_lang_input.setMaximumWidth(50)
        self.target_lang_input.textChanged.connect(self.update_ui_language)

        self.project_name = QLineEdit("default_game")
        self.project_name.setMaximumWidth(140)

        self.profile_name = QLineEdit("New_Profile")
        self.profile_name.setMaximumWidth(140)

        self.btn_save = QPushButton(I18N.t("btn_save"))
        self.btn_save.setIcon(QIcon.fromTheme("document-save"))
        self.btn_save.clicked.connect(self.save_current_profile)

        self.btn_load = QPushButton(I18N.t("btn_load"))
        self.btn_load.setIcon(QIcon.fromTheme("document-open"))
        self.btn_load.clicked.connect(self.load_profile_dialog)

        self.model_dropdown = QComboBox()
        self.model_dropdown.setMinimumWidth(160)

        btn_refresh = QPushButton()
        btn_refresh.setIcon(QIcon.fromTheme("view-refresh"))
        btn_refresh.clicked.connect(self.refresh_models)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.1)
        self.temp_spin.setMaximumWidth(70)

        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(8, 30)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setMaximumWidth(70)
        self.font_size_spin.valueChanged.connect(self.font_changed.emit)

        self.strict_mode = QCheckBox(I18N.t("ui_strict"))
        self.strict_mode.setChecked(True)

        self.ui_lang_label = QLabel(I18N.t("ui_interface_lang"))
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItems(["EN", "BG"])
        self.ui_lang_combo.setMaximumWidth(60)
        self.ui_lang_combo.currentTextChanged.connect(
            self.change_interface_language)

        gen.addWidget(QLabel(I18N.t("ui_lang")))
        gen.addWidget(self.target_lang_input)
        gen.addWidget(QLabel(I18N.t("ui_project")))
        gen.addWidget(self.project_name)
        gen.addWidget(QLabel(I18N.t("ui_profile")))
        gen.addWidget(self.profile_name)
        gen.addWidget(self.btn_save)
        gen.addWidget(self.btn_load)
        gen.addSpacing(12)
        gen.addWidget(QLabel(I18N.t("ui_model")))
        gen.addWidget(self.model_dropdown)
        gen.addWidget(btn_refresh)
        gen.addWidget(QLabel(I18N.t("ui_temp")))
        gen.addWidget(self.temp_spin)
        gen.addWidget(QLabel(I18N.t("ui_font")))
        gen.addWidget(self.font_size_spin)
        gen.addWidget(self.strict_mode)

        gen.addWidget(self.ui_lang_label)
        gen.addWidget(self.ui_lang_combo)

        gen.addStretch()

        layout.addWidget(self.general_group)

        # =====================================================
        # RESOURCES (max 2 rows)
        # =====================================================
        self.res_group = self.create_group(I18N.t("ui_recources"))
        res = QGridLayout(self.res_group)
        res.setHorizontalSpacing(12)
        res.setVerticalSpacing(6)

        self.gloss_path = QLineEdit("glossary.tsv")
        self.style_path = QLineEdit("style.md")
        self.forbidden_path = QLineEdit("forbidden.txt")

        self.resource_labels = []
        self.browse_buttons = []

        resources = [
            ("ui_glossary",
             self.gloss_path,
             "TSV (*.tsv *.csv)",
             I18N.t("tip_glossary")),
            ("ui_style_guide",
             self.style_path,
             "Text (*.md *.txt)",
             I18N.t("tip_style_guide")),
            ("ui_forbidden_terms",
             self.forbidden_path,
             "Text (*.txt)",
             I18N.t("tip_forbidden_terms")),
        ]

        for i, (label_key, edit, filt, tip) in enumerate(resources):
            col = i % 3
            row = i // 3

            browse = QPushButton(I18N.t("btn_browse"))
            browse.setIcon(QIcon.fromTheme("document-open"))
            browse.clicked.connect(
                lambda _, e=edit, f=filt: self.browse_file(e, f)
            )
            self.browse_buttons.append(browse)

            h = QHBoxLayout()
            h.addWidget(edit)
            h.addWidget(browse)

            label_widget = QLabel(I18N.t(label_key))
            if tip:
                label_widget.setToolTip(tip)

            self.resource_labels.append((label_widget, label_key))

            res.addWidget(label_widget, row * 2, col)
            res.addLayout(h, row * 2 + 1, col)

        layout.addWidget(self.res_group)
        # =====================================================
        # PROMPT (dominant)
        # =====================================================
        self.prompt_group = self.create_group(I18N.t("ui_prompt"))
        prompt_layout = QVBoxLayout(self.prompt_group)
        self.prompt_group.setMinimumHeight(300)

        header = QHBoxLayout()

        self.template_label = QLabel(I18N.t("ui_template"))
        header.addWidget(self.template_label)

        self.template_combo = QComboBox()
        self.template_combo.addItems([
            I18N.t("tmpl_standard"),
            I18N.t("tmpl_technical_pass2"),
            I18N.t("tmpl_creative_polish")
        ])
        self.template_combo.currentIndexChanged.connect(self.apply_template)

        header.addWidget(self.template_combo)

        header.addStretch()
        header.setContentsMargins(0, 0, 0, 0)

        self.prompt_editor = QTextEdit()
        self.prompt_editor.setAcceptRichText(False)
        self.prompt_editor.setFont(QFont("Consolas", 10))
        self.prompt_editor.setPlaceholderText(
            "{target_lang}, {glossary}, {style}, {forbidden}, {source}"
        )
        self.prompt_editor.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        prompt_layout.addLayout(header)
        prompt_layout.addWidget(self.prompt_editor)

        layout.addWidget(self.prompt_group, 1)

        # =====================================================
        # DATABASE TOOLS + DANGER (same row)
        # =====================================================
        self.tools_group = self.create_group(I18N.t("ui_database_tools"))
        tools = QHBoxLayout(self.tools_group)
        self.tools_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )

        self.btn_replace = QPushButton(I18N.t("btn_global_replace"))
        self.btn_replace.clicked.connect(self.run_global_db_replace)

        self.btn_purge = QPushButton(I18N.t("btn_purge_unverified"))
        self.btn_purge.clicked.connect(self.purge_unverified_records)

        tools.addWidget(self.btn_replace)
        tools.addWidget(self.btn_purge)
        tools.addStretch()

        self.danger_group = self.create_group(I18N.t("ui_danger_zone"))
        self.danger_group.setProperty("class", "danger")
        danger = QHBoxLayout(self.danger_group)

        self.danger_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )

        self.btn_clear_errors = QPushButton(I18N.t("btn_clear_errors"))
        self.btn_clear_errors.clicked.connect(self.clear_mismatches)

        self.btn_wipe = QPushButton(I18N.t("btn_wipe_all"))
        self.btn_wipe.setProperty("danger", True)
        self.btn_wipe.clicked.connect(self.clear_memory)

        danger.addWidget(self.btn_clear_errors)
        danger.addWidget(self.btn_wipe)
        danger.addStretch()

        bottom = QHBoxLayout()
        bottom.addWidget(self.tools_group, 1)
        bottom.addWidget(self.danger_group, 1)

        layout.addStretch(1)

        layout.addLayout(bottom)

        s = QSettings("FoundryL10n", "Workstation")
        ui_lang = str(s.value("ui_language", "EN")).upper()
        I18N.set_language(ui_lang)
        self.ui_lang_combo.setCurrentText(ui_lang)
        self.retranslate_ui()

        # =====================================================
        # Init
        # =====================================================
        self.refresh_models()
        self.load_settings()

    def change_interface_language(self, lang_code: str):
        """Change Language"""
        lang = lang_code.upper()

        # 1) сменяме езика глобално
        I18N.set_language(lang)

        # 2) записваме в QSettings, за да помним избора
        s = QSettings("FoundryL10n", "Workstation")
        s.setValue("ui_language", lang)

        # 3) ретранслейтваме текущия таб
        self.retranslate_ui()

    def retranslate_ui(self):
        # Groups
        self.general_group.setTitle(I18N.t("ui_general"))
        self.res_group.setTitle(I18N.t("ui_recources"))
        self.prompt_group.setTitle(I18N.t("ui_prompt"))
        self.tools_group.setTitle(I18N.t("ui_database_tools"))
        self.danger_group.setTitle(I18N.t("ui_danger_zone"))

        # Checkbox
        self.strict_mode.setText(I18N.t("ui_strict"))

        # Stuff
        self.ui_lang_label.setText(I18N.t("ui_interface_lang"))

        # Template label + combo items
        self.template_label.setText(I18N.t("ui_template"))
        self.template_combo.setItemText(0, I18N.t("tmpl_standard"))
        self.template_combo.setItemText(1, I18N.t("tmpl_technical_pass2"))
        self.template_combo.setItemText(2, I18N.t("tmpl_creative_polish"))

        # Buttons
        self.btn_replace.setText(I18N.t("btn_global_replace"))
        self.btn_purge.setText(I18N.t("btn_purge_unverified"))
        self.btn_clear_errors.setText(I18N.t("btn_clear_errors"))
        self.btn_wipe.setText(I18N.t("btn_wipe_all"))
        self.btn_save.setText(I18N.t("btn_save"))

        # Browse buttons
        for btn in self.browse_buttons:
            btn.setText(I18N.t("btn_browse"))

        for lbl, key in self.resource_labels:
            lbl.setText(I18N.t(key))

    def update_ui_language(self):
        lang = self.target_lang_input.text().upper()
        if lang in ["BG", "EN"]:
            I18N.set_language(lang)

    def create_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        return group

    def purge_unverified_records(self):
        """Clean up the DB by removing everything that isn't verified."""
        settings = self.get_settings()
        # Use your standardized 'project_name' variable
        p_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG")

        reply = QMessageBox.question(
            self,
            I18N.t("dlg_purge_memory_title"),
            I18N.t("dlg_purge_memory_text").format(
                project=p_name,
                lang=lang,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with Session(engine) as session:
                stmt = delete(TranslationRecord).where(
                    col(TranslationRecord.project_name) == p_name,
                    col(TranslationRecord.target_lang) == lang,
                    col(TranslationRecord.is_verified).is_(False)
                )
                session.exec(stmt)
                session.commit()

            QMessageBox.information(
                self,
                I18N.t("dlg_success_title"),
                I18N.t("dlg_purge_memory_success"),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                I18N.t("dlg_error_title"),
                I18N.t("dlg_purge_memory_error").format(error=e),
            )

    def run_global_db_replace(self):
        """Triggers the Global Replace logic via input dialogs."""
        find_t, ok1 = QInputDialog.getText(
            self,
            I18N.t("dlg_global_replace_title"),
            I18N.t("msg_global_find")
        )
        if not ok1 or not find_t:
            return

        repl_t, ok2 = QInputDialog.getText(
            self,
            I18N.t("dlg_global_replace_title"),
            I18N.t("msg_global_replace_with").format(text=find_t),
        )
        if not ok2:
            return

        settings = self.get_settings()
        project = settings.get(
            "project_name", settings.get("project", "default"))
        lang = settings.get("lang", "BG")

        count = global_replace_in_db(project, lang, find_t, repl_t)

        QMessageBox.information(
            self,
            I18N.t("dlg_success_title"),
            I18N.t("dlg_memory_update_success").format(count=count)
        )

    def save_current_profile(self):
        """Saves all current UI settings into a JSON profile and remembers its path."""
        raw_name = self.profile_name.text().strip()
        safe_name = os.path.basename(raw_name)

        if not safe_name or safe_name in {".", ".."}:
            QMessageBox.warning(
                self,
                I18N.t("dlg_error_title"),
                I18N.t("msg_profile_name_required")
            )
            return

        os.makedirs("profiles", exist_ok=True)
        save_path = Path("profiles") / f"{safe_name}.json"

        data = self.get_settings()

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            # Remember this profile as "last used"
            settings = QSettings("FoundryL10n", "TranslatorApp")
            settings.setValue("last_profile_path", str(save_path.resolve()))

            QMessageBox.information(
                self,
                I18N.t("dlg_success_title"),
                I18N.t("msg_profile_saved").format(name=safe_name)
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                I18N.t("dlg_error_title"),
                I18N.t("msg_profile_save_failed").format(error=e)
            )

    def load_profile_dialog(self):
        """Opens a file dialog to pick a profile JSON."""
        os.makedirs("profiles", exist_ok=True)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Profile",
            "profiles",
            "JSON Files (*.json)",
        )

        if file_path:
            self.apply_profile_from_file(file_path)

    def get_default_prompt(self):
        return (
            "### STORY CONTEXT (Reference only):\n"
            "{context}\n\n"
            "### ROLE: Expert {target_lang} Game Localizer\n"
            "### TASK: Translate the Source Text.\n\n"
            "### RULES:\n"
            "1. GLOSSARY: {glossary}\n"
            "2. TAGS: Keep [#_0_] anchors in place.\n\n"
            "### SOURCE:\n"
            "{source}\n\n"
            "### TRANSLATION:\n"
        )

    def apply_profile_from_file(self, path: str, show_message: bool = True):
        """Reads JSON and force-updates all UI fields."""

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "lang" in data:
                self.target_lang_input.setText(data["lang"])

            if "project_name" in data:
                self.project_name.setText(data["project_name"])
            elif "project" in data:
                self.project_name.setText(data["project"])

            if "glossary_path" in data:
                self.gloss_path.setText(data["glossary_path"])
            if "style_path" in data:
                self.style_path.setText(data["style_path"])
            if "forbidden_path" in data:
                self.forbidden_path.setText(data["forbidden_path"])

            if "temp" in data:
                try:
                    self.temp_spin.setValue(float(data["temp"]))
                except (ValueError, TypeError):
                    pass

            if "prompt_template" in data:
                self.prompt_editor.setPlainText(data["prompt_template"])

            if "model" in data:
                idx = self.model_dropdown.findText(data["model"])
                if idx >= 0:
                    self.model_dropdown.setCurrentIndex(idx)

            profile_base = os.path.basename(path).replace(".json", "")
            self.profile_name.setText(profile_base)
            self.save_settings()
            self.profile_loaded.emit()

            if show_message:
                QMessageBox.information(
                    self,
                    I18N.t("dlg_success_title"),
                    I18N.t("msg_profile_loaded").format(name=profile_base),
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                I18N.t("dlg_error_title"),
                I18N.t("msg_profile_load_failed").format(error=e),
            )

    def apply_template(self):
        """Pre-loads specific prompt structures based on selection."""
        idx = self.template_combo.currentIndex()
        if idx == 0:  # Standard
            self.prompt_editor.setPlainText(self.get_default_prompt())
        elif idx == 1:  # Fixer
            self.prompt_editor.setPlainText(
                "### ROLE: Technical Fixer\n"
                "I have a translation that broke the technical tags. \n"
                "1. FIX the tags [#_x_] based on the Source.\n"
                "2. IMPROVE the Bulgarian grammar in the Existing Translation.\n\n"
                "### SOURCE (English):\n{source}\n\n"
                "### EXISTING TRANSLATION (BG):\n{translation}\n\n"
                "### CORRECTED TRANSLATION:\n"
            )
        elif idx == 2:  # Creative
            self.prompt_editor.setPlainText(
                "### ROLE: Fantasy Writer\n"
                "Re-write this {target_lang} translation to be more epic and poetic.\n"
                "Glossary: {glossary}\n"
                "Source: {source}\n"
                "Target:"
            )

    def browse_file(self, line_edit, file_filter):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            I18N.t("dlg_select_file_title"),
            "",
            file_filter
        )

        if file_path:
            line_edit.setText(file_path)

    def refresh_models(self):
        models = self.llm_service.get_models()
        self.model_dropdown.clear()
        if models:
            self.model_dropdown.addItems(models)

    def save_settings(self):
        """Saves only the form-related settings."""
        settings = QSettings("FoundryL10n", "TranslatorApp")
        settings.setValue("project_name", self.project_name.text())
        settings.setValue("target_lang", self.target_lang_input.text())
        settings.setValue("model", self.model_dropdown.currentText())
        settings.setValue("glossary_path", self.gloss_path.text())
        settings.setValue("style_path", self.style_path.text())
        settings.setValue("forbidden_path", self.forbidden_path.text())
        settings.setValue("temp", self.temp_spin.value())
        settings.setValue("strict_mode", self.strict_mode.isChecked())
        # Save the current text in the prompt editor
        settings.setValue("custom_prompt", self.prompt_editor.toPlainText())
        # Save the font size
        settings.setValue("ui_font_size", self.font_size_spin.value())

    def load_settings(self):
        settings = QSettings("FoundryL10n", "TranslatorApp")

        # 1. Last used profile
        last_p = str(settings.value("last_profile_path", ""))
        if last_p and os.path.exists(last_p):
            self.apply_profile_from_file(last_p, show_message=False)
            return

        # 2. Fallback
        self.project_name.setText(
            str(settings.value("project_name", "default_game")))
        self.target_lang_input.setText(
            str(settings.value("target_lang", "BG")))

        saved_model = str(settings.value("model", ""))
        idx = self.model_dropdown.findText(saved_model)
        if idx >= 0:
            self.model_dropdown.setCurrentIndex(idx)

        self.gloss_path.setText(
            str(settings.value("glossary_path", "glossary.tsv")))
        self.style_path.setText(str(settings.value("style_path", "style.md")))
        self.forbidden_path.setText(
            str(settings.value("forbidden_path", "forbidden.txt"))
        )

        is_strict = str(settings.value(
            "strict_mode", "true")).lower() == "true"
        self.strict_mode.setChecked(is_strict)

        default_p = self.get_default_prompt()
        self.prompt_editor.setPlainText(
            str(settings.value("custom_prompt", default_p))
        )

        try:
            f_size = float(str(settings.value("ui_font_size", 12)))
            self.font_size_spin.setValue(f_size)
            self.font_changed.emit(f_size)
        except (ValueError, TypeError):
            self.font_size_spin.setValue(12)

    def get_settings(self):
        return {
            "project_name": self.project_name.text(),
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
        reply = QMessageBox.question(
            self,
            I18N.t("dlg_retry_errors_title"),
            I18N.t("msg_retry_errors_clear_tags")
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with Session(engine) as session:
                    # We wrap the attribute in col() so Pylance knows .like() exists
                    statement = delete(TranslationRecord).where(
                        col(TranslationRecord.translation).like(
                            "%[TAG ERROR]%")
                    )
                    session.exec(statement)
                    session.commit()
                QMessageBox.information(
                    self,
                    I18N.t("dlg_success_title"),
                    I18N.t("msg_errors_cleared")
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    I18N.t("dlg_database_error_title"),
                    I18N.t("msg_clear_errors_failed").format(error=e)
                )

    def clear_memory(self):
        reply = QMessageBox.question(
            self,
            I18N.t("dlg_wipe_all_title"),
            I18N.t("msg_wipe_all_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                SQLModel.metadata.drop_all(engine)
                SQLModel.metadata.create_all(engine)
                QMessageBox.information(
                    self,
                    I18N.t("dlg_success_title"),
                    I18N.t("msg_memory_wiped")
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    I18N.t("dlg_error_title"),
                    I18N.t("msg_wipe_failed").format(error=e)
                )
