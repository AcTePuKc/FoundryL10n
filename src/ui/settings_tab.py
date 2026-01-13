import os
import json
from pathlib import Path
from typing import Optional
from core.database import TranslationRecord, Session, engine, global_replace_in_db
from core.i18n import I18N
from sqlmodel import SQLModel, delete, col
from services.llm_service import LLMService
from PySide6.QtWidgets import (
    QApplication, QWidget, QComboBox, QDoubleSpinBox, QLineEdit, QPushButton,
    QInputDialog, QHBoxLayout, QFileDialog, QMessageBox, QCheckBox, QTextEdit,
    QLabel, QVBoxLayout, QGroupBox, QFormLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import QSettings, Signal, Qt
from PySide6.QtGui import QIcon, QFont
from ui.theme_helpers import get_available_themes, load_theme


class SettingsTab(QWidget):
    font_changed = Signal(float)
    profile_loaded = Signal()
    language_changed = Signal(str)
    provider_changed = Signal(str)
    login_requested = Signal(str)
    llm_status_warning = Signal(str)
    ORGANIZATION_NAME = "FoundryL10n"
    APP_NAME = "TranslatorApp"

    def __init__(self, parent=None, plugin_registry: Optional['PluginRegistry'] = None):
        super().__init__(parent)
        self.llm_service = LLMService()
        self.plugin_registry = plugin_registry

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
        # GENERAL
        # =====================================================
        self.general_group = self.create_group(I18N.t("ui_general"))
        gen = QFormLayout(self.general_group)
        gen.setContentsMargins(12, 10, 12, 12)
        gen.setHorizontalSpacing(12)
        gen.setVerticalSpacing(8)
        gen.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.lang_label = QLabel(I18N.t("ui_lang"))
        self.target_lang_input = QLineEdit("BG")
        self.target_lang_input.setMaximumWidth(60)
        self.target_lang_input.textChanged.connect(self.update_ui_language)

        self.project_label = QLabel(I18N.t("ui_project"))
        self.project_name = QLineEdit("default_game")
        self.project_name.setMaximumWidth(200)

        self.profile_label = QLabel(I18N.t("ui_profile"))
        self.profile_name = QLineEdit("New_Profile")
        self.profile_name.setMaximumWidth(200)

        self.btn_save = QPushButton(I18N.t("btn_save"))
        self.btn_save.setIcon(QIcon.fromTheme("document-save"))
        self.btn_save.clicked.connect(self.save_current_profile)

        self.btn_load = QPushButton(I18N.t("btn_load"))
        self.btn_load.setIcon(QIcon.fromTheme("document-open"))
        self.btn_load.clicked.connect(self.load_profile_dialog)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)
        profile_row.addWidget(self.profile_name)
        profile_row.addWidget(self.btn_save)
        profile_row.addWidget(self.btn_load)
        profile_row.addStretch()

        gen.addRow(self.lang_label, self.target_lang_input)
        gen.addRow(self.project_label, self.project_name)
        gen.addRow(self.profile_label, profile_row)

        layout.addWidget(self.general_group)

        # =====================================================
        # TRANSLATION
        # =====================================================
        self.translation_group = self.create_group(I18N.t("ui_translation"))
        translation_layout = QFormLayout(self.translation_group)
        translation_layout.setContentsMargins(12, 10, 12, 12)
        translation_layout.setHorizontalSpacing(12)
        translation_layout.setVerticalSpacing(8)
        translation_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.model_label = QLabel(I18N.t("ui_model"))
        self.model_dropdown = QComboBox()
        self.model_dropdown.setMinimumWidth(200)
        self.llm_status_label = QLabel(I18N.t("ui_llm_status"))
        self.llm_status_value = QLabel("")
        self.llm_status_value.setWordWrap(True)
        self._llm_status_ok = None
        self._llm_status_error = None
        self._llm_status_count = None
        self._last_llm_warning = None

        self.provider_label = QLabel(I18N.t("ui_provider"))
        self.provider_dropdown = QComboBox()
        self.provider_dropdown.setMinimumWidth(200)
        self.provider_dropdown.currentIndexChanged.connect(
            self.on_provider_changed
        )
        self.btn_login = QPushButton(I18N.t("btn_login"))
        self.btn_login.setEnabled(False)
        self.btn_login.clicked.connect(self.request_login)

        btn_refresh = QPushButton()
        btn_refresh.setIcon(QIcon.fromTheme("view-refresh"))
        btn_refresh.clicked.connect(self.refresh_models)

        provider_row = QHBoxLayout()
        provider_row.setSpacing(8)
        provider_row.addWidget(self.provider_dropdown)
        provider_row.addWidget(self.btn_login)
        provider_row.addStretch()

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        model_row.addWidget(self.model_dropdown)
        model_row.addWidget(btn_refresh)
        model_row.addStretch()

        self.temp_label = QLabel(I18N.t("ui_temp"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.1)
        self.temp_spin.setMaximumWidth(70)

        self.strict_mode = QCheckBox(I18N.t("ui_strict"))
        self.strict_mode.setChecked(True)

        translation_layout.addRow(self.provider_label, provider_row)
        translation_layout.addRow(self.model_label, model_row)
        translation_layout.addRow(self.llm_status_label, self.llm_status_value)
        translation_layout.addRow(self.temp_label, self.temp_spin)
        translation_layout.addRow(self.strict_mode)

        layout.addWidget(self.translation_group)

        # =====================================================
        # APPEARANCE
        # =====================================================
        self.appearance_group = self.create_group(I18N.t("ui_appearance"))
        appearance_layout = QFormLayout(self.appearance_group)
        appearance_layout.setContentsMargins(12, 10, 12, 12)
        appearance_layout.setHorizontalSpacing(12)
        appearance_layout.setVerticalSpacing(8)
        appearance_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.font_label = QLabel(I18N.t("ui_font"))
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(8, 30)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setMaximumWidth(70)
        self.font_size_spin.valueChanged.connect(self.font_changed.emit)

        self.theme_label = QLabel(I18N.t("ui_theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(160)
        self.populate_themes()
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        self.ui_lang_label = QLabel(I18N.t("ui_interface_lang"))
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItems(["EN", "BG"])
        self.ui_lang_combo.setMaximumWidth(80)
        self.ui_lang_combo.currentTextChanged.connect(
            self.change_interface_language)

        appearance_layout.addRow(self.font_label, self.font_size_spin)
        appearance_layout.addRow(self.theme_label, self.theme_combo)
        appearance_layout.addRow(self.ui_lang_label, self.ui_lang_combo)

        layout.addWidget(self.appearance_group)

        # =====================================================
        # RESOURCES
        # =====================================================
        self.res_group = self.create_group(I18N.t("ui_recources"))
        res = QFormLayout(self.res_group)
        res.setContentsMargins(12, 10, 12, 12)
        res.setHorizontalSpacing(12)
        res.setVerticalSpacing(8)
        res.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.gloss_path = QLineEdit("glossary.tsv")
        self.style_path = QLineEdit("style.md")
        self.forbidden_path = QLineEdit("forbidden.txt")

        self.resource_labels = []
        self.browse_buttons = []

        resources = [
            ("ui_glossary",
             self.gloss_path,
             "filter_tsv",
             "tip_glossary"),
            ("ui_style_guide",
             self.style_path,
             "filter_text",
             "tip_style_guide"),
            ("ui_forbidden_terms",
             self.forbidden_path,
             "filter_text",
             "tip_forbidden_terms"),
        ]

        for label_key, edit, filter_key, tip_key in resources:
            browse = QPushButton(I18N.t("btn_browse"))
            browse.setIcon(QIcon.fromTheme("document-open"))
            browse.clicked.connect(
                lambda _, e=edit, f=filter_key: self.browse_file(e, f)
            )
            self.browse_buttons.append(browse)

            h = QHBoxLayout()
            h.addWidget(edit)
            h.addWidget(browse)

            label_widget = QLabel(I18N.t(label_key))
            if tip_key:
                label_widget.setToolTip(I18N.t(tip_key))

            self.resource_labels.append(
                (label_widget, label_key, tip_key)
            )

            res.addRow(label_widget, h)

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

        self.reset_prompt_button = QPushButton(I18N.t("btn_reset_prompt"))
        self.reset_prompt_button.clicked.connect(self.reset_prompt_to_default)
        header.addWidget(self.reset_prompt_button)

        header.addStretch()
        header.setContentsMargins(0, 0, 0, 0)

        self.prompt_editor = QTextEdit()
        self.prompt_editor.setAcceptRichText(False)
        self.prompt_editor.setFont(QFont("Consolas", 10))
        self.prompt_editor.setPlaceholderText(I18N.t("ui_prompt_placeholder"))
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

        s = QSettings(self.ORGANIZATION_NAME, "Workstation")
        ui_lang = str(s.value("ui_language", "EN")).upper()
        I18N.set_language(ui_lang)
        self.ui_lang_combo.blockSignals(True)
        self.ui_lang_combo.setCurrentText(ui_lang)
        self.ui_lang_combo.blockSignals(False)
        self.retranslate_ui()

        # =====================================================
        # Init
        # =====================================================
        self.populate_providers()
        self.refresh_models()
        self.load_settings()

    def change_interface_language(self, lang_code: str):
        """Change Language"""
        lang = lang_code.upper()

        I18N.set_language(lang)

        s = QSettings(self.ORGANIZATION_NAME, "Workstation")
        s.setValue("ui_language", lang)

        self.retranslate_ui()
        self.language_changed.emit(lang)

    def retranslate_ui(self):
        # Groups
        self.general_group.setTitle(I18N.t("ui_general"))
        self.translation_group.setTitle(I18N.t("ui_translation"))
        self.appearance_group.setTitle(I18N.t("ui_appearance"))
        self.res_group.setTitle(I18N.t("ui_recources"))
        self.prompt_group.setTitle(I18N.t("ui_prompt"))
        self.tools_group.setTitle(I18N.t("ui_database_tools"))
        self.danger_group.setTitle(I18N.t("ui_danger_zone"))

        # Checkbox
        self.strict_mode.setText(I18N.t("ui_strict"))

        # Stuff
        self.lang_label.setText(I18N.t("ui_lang"))
        self.project_label.setText(I18N.t("ui_project"))
        self.profile_label.setText(I18N.t("ui_profile"))
        self.provider_label.setText(I18N.t("ui_provider"))
        self.model_label.setText(I18N.t("ui_model"))
        self.llm_status_label.setText(I18N.t("ui_llm_status"))
        self.temp_label.setText(I18N.t("ui_temp"))
        self.font_label.setText(I18N.t("ui_font"))
        self.theme_label.setText(I18N.t("ui_theme"))
        self.ui_lang_label.setText(I18N.t("ui_interface_lang"))
        self.prompt_editor.setPlaceholderText(
            I18N.t("ui_prompt_placeholder")
        )

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
        self.btn_load.setText(I18N.t("btn_load"))
        self.reset_prompt_button.setText(I18N.t("btn_reset_prompt"))

        # Browse buttons
        for btn in self.browse_buttons:
            btn.setText(I18N.t("btn_browse"))

        for lbl, key, tip_key in self.resource_labels:
            lbl.setText(I18N.t(key))
            if tip_key:
                lbl.setToolTip(I18N.t(tip_key))

        self.update_theme_labels()
        self.populate_providers()
        self._refresh_llm_status_label()

    def update_ui_language(self):
        lang = self.target_lang_input.text().upper()
        if lang in ["BG", "EN"] and self.target_lang_input.text() != lang:
            self.target_lang_input.setText(lang)

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
            I18N.t("btn_global_replace"),
            I18N.t("msg_global_find")
        )
        if not ok1 or not find_t:
            return

        repl_t, ok2 = QInputDialog.getText(
            self,
            I18N.t("btn_global_replace"),
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
            settings = QSettings(self.ORGANIZATION_NAME, self.APP_NAME)
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
            I18N.t("dlg_load_profile_title"),
            "profiles",
            I18N.t("filter_json"),
        )

        if file_path:
            self.apply_profile_from_file(file_path)

    def get_default_prompt(self):
        return I18N.t("prompt_default")

    def reset_prompt_to_default(self):
        default_prompt = self.get_default_prompt()
        self.prompt_editor.setPlainText(default_prompt)
        settings = QSettings(self.ORGANIZATION_NAME, self.APP_NAME)
        settings.remove("custom_prompt")
        self.prompt_editor.setFocus(Qt.FocusReason.OtherFocusReason)

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

            if "provider_id" in data:
                idx = self.provider_dropdown.findData(data["provider_id"])
                if idx >= 0:
                    self.provider_dropdown.blockSignals(True)
                    self.provider_dropdown.setCurrentIndex(idx)
                    self.provider_dropdown.blockSignals(False)

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
                I18N.t("prompt_template_technical")
            )
        elif idx == 2:  # Creative
            self.prompt_editor.setPlainText(
                I18N.t("prompt_template_creative")
            )

    def browse_file(self, line_edit, file_filter):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            I18N.t("dlg_select_file_title"),
            "",
            I18N.t(file_filter)
        )

        if file_path:
            line_edit.setText(file_path)

    def refresh_models(self):
        ok, error = self.llm_service.check_connection()
        models = []
        if ok:
            models = self.llm_service.get_models()
        self.model_dropdown.clear()
        if models:
            self.model_dropdown.addItems(models)
        else:
            self.model_dropdown.addItem(I18N.t("llm_model_unavailable"))
        self.update_llm_status(ok, error, len(models))

    def update_llm_status(self, is_available, error, model_count):
        self._llm_status_ok = is_available
        self._llm_status_error = error
        self._llm_status_count = model_count
        self._refresh_llm_status_label()

    def _refresh_llm_status_label(self):
        if self._llm_status_ok is None:
            return
        if self._llm_status_ok:
            count = self._llm_status_count or 0
            status = I18N.t("llm_status_available").format(count=count)
            self.llm_status_value.setStyleSheet("color: #2e7d32;")
            self.llm_status_value.setToolTip(status)
        else:
            error = self._llm_status_error or I18N.t("llm_status_unknown_error")
            status = I18N.t("llm_status_unavailable").format(error=error)
            self.llm_status_value.setStyleSheet("color: #d97706;")
            self.llm_status_value.setToolTip(status)
            warning = I18N.t("log_llm_unavailable").format(error=error)
            if warning != self._last_llm_warning:
                self._last_llm_warning = warning
                print(warning)
                self.llm_status_warning.emit(warning)
        self.llm_status_value.setText(status)

    def populate_providers(self):
        focused = QApplication.focusWidget()
        selected_id = self.provider_dropdown.currentData()
        self.provider_dropdown.blockSignals(True)
        self.provider_dropdown.clear()

        entries = self.plugin_registry.entries if self.plugin_registry else ()

        if not entries:
            self.provider_dropdown.addItem(I18N.t("ui_provider_none"), "")
            self.provider_dropdown.setEnabled(False)
            self.provider_dropdown.blockSignals(False)
            self.btn_login.setEnabled(False)
            if (
                focused is not None
                and focused is not self.provider_dropdown
                and focused.isVisible()
            ):
                focused.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        self.provider_dropdown.setEnabled(True)
        for entry in entries:
            if entry.is_valid:
                label = f"{entry.name} ({entry.metadata_id})"
                self.provider_dropdown.addItem(label, entry.metadata_id)
                continue

            label = I18N.t("ui_provider_invalid").format(name=entry.name)
            index = self.provider_dropdown.count()
            self.provider_dropdown.addItem(label, entry.metadata_id or "")
            model = self.provider_dropdown.model()
            item = model.item(index) if model is not None else None
            if item is not None:
                item.setEnabled(False)
                if entry.errors:
                    item.setToolTip("\n".join(entry.errors))

        if selected_id:
            idx = self.provider_dropdown.findData(selected_id)
            if idx >= 0:
                self.provider_dropdown.setCurrentIndex(idx)
        self.provider_dropdown.blockSignals(False)
        self.update_login_button()
        if (
            focused is not None
            and focused is not self.provider_dropdown
            and focused.isVisible()
        ):
            focused.setFocus(Qt.FocusReason.OtherFocusReason)

    def populate_themes(self):
        self.theme_combo.clear()
        self.available_themes = get_available_themes()
        themes = list(self.available_themes)
        if "dark" not in themes:
            themes.insert(0, "dark")
        self.available_themes = themes
        for theme in themes:
            self.theme_combo.addItem(self.get_theme_label(theme), theme)

    def get_theme_label(self, theme_name: str) -> str:
        label_key = f"theme_{theme_name}"
        label = I18N.t(label_key)
        if label == label_key:
            return theme_name.replace("_", " ").title()
        return label

    def update_theme_labels(self):
        for index in range(self.theme_combo.count()):
            theme_name = self.theme_combo.itemData(index)
            self.theme_combo.setItemText(
                index, self.get_theme_label(theme_name)
            )

    def on_theme_changed(self):
        theme_name = self.theme_combo.currentData()
        if not theme_name:
            theme_name = "dark"
        self.apply_theme(theme_name)
        settings = QSettings(self.ORGANIZATION_NAME, self.APP_NAME)
        settings.setValue("ui_theme", theme_name)

    def apply_theme(self, theme_name: str, restore_focus: bool = True):
        focused = QApplication.focusWidget() if restore_focus else None
        load_theme(theme_name)
        if focused is not None:
            focused.setFocus(Qt.FocusReason.OtherFocusReason)

    def get_valid_theme(self, theme_name: str) -> str:
        if theme_name in self.available_themes:
            return theme_name
        return "dark"

    def save_settings(self):
        """Saves only the form-related settings."""
        settings = QSettings(self.ORGANIZATION_NAME, self.APP_NAME)
        settings.setValue("project_name", self.project_name.text())
        settings.setValue("target_lang", self.target_lang_input.text())
        settings.setValue("model", self.model_dropdown.currentText())
        settings.setValue("provider_id", self.provider_dropdown.currentData())
        settings.setValue("glossary_path", self.gloss_path.text())
        settings.setValue("style_path", self.style_path.text())
        settings.setValue("forbidden_path", self.forbidden_path.text())
        settings.setValue("temp", self.temp_spin.value())
        settings.setValue("strict_mode", self.strict_mode.isChecked())
        # Save the current text in the prompt editor
        current_prompt = self.prompt_editor.toPlainText()
        default_prompt = self.get_default_prompt()
        if current_prompt == default_prompt:
            settings.remove("custom_prompt")
        else:
            settings.setValue("custom_prompt", current_prompt)
        # Save the font size
        settings.setValue("ui_font_size", self.font_size_spin.value())
        # Save the theme selection
        settings.setValue("ui_theme", self.theme_combo.currentData())

    def load_settings(self):
        settings = QSettings(self.ORGANIZATION_NAME, self.APP_NAME)

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

        saved_provider = str(settings.value("provider_id", ""))
        provider_index = self.provider_dropdown.findData(saved_provider)
        if provider_index >= 0:
            self.provider_dropdown.blockSignals(True)
            self.provider_dropdown.setCurrentIndex(provider_index)
            self.provider_dropdown.blockSignals(False)

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

        theme_name = self.get_valid_theme(
            str(settings.value("ui_theme", "dark"))
        )
        theme_index = self.theme_combo.findData(theme_name)
        if theme_index == -1:
            theme_index = self.theme_combo.findData("dark")
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(theme_index)
        self.theme_combo.blockSignals(False)
        self.apply_theme(theme_name, restore_focus=False)

    def get_settings(self):
        return {
            "project_name": self.project_name.text(),
            "provider_id": self.provider_dropdown.currentData(),
            "model": self.model_dropdown.currentText(),
            "temp": self.temp_spin.value(),
            "lang": self.target_lang_input.text(),
            "glossary_path": self.gloss_path.text(),
            "style_path": self.style_path.text(),
            "forbidden_path": self.forbidden_path.text(),
            "strict_mode": self.strict_mode.isChecked(),
            "prompt_template": self.prompt_editor.toPlainText()
        }

    def on_provider_changed(self):
        provider_id = self.provider_dropdown.currentData()
        self.save_settings()
        self.update_login_button(provider_id)
        self.provider_changed.emit(provider_id or "")

    def update_login_button(self, provider_id: str | None = None) -> None:
        current_id = provider_id or self.provider_dropdown.currentData()
        is_valid = (
            current_id
            and self.plugin_registry
            and current_id in self.plugin_registry.providers
        )
        self.btn_login.setEnabled(bool(is_valid))

    def request_login(self) -> None:
        provider_id = self.provider_dropdown.currentData()
        if provider_id:
            self.login_requested.emit(provider_id)

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
            I18N.t("btn_wipe_all"),
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
