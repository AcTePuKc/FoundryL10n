import os
import sys
import re
import csv
import json
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QFileDialog, QTableWidget,
                               QTableWidgetItem, QHeaderView, QProgressBar,
                               QLabel, QTabWidget, QTextEdit, QCheckBox,
                               QSplitter, QLineEdit, QMenu, QInputDialog, QMessageBox,
                               QScrollArea, QApplication)
from PySide6.QtGui import QColor, QCursor, QFont, QFontDatabase, QIcon
from PySide6.QtCore import Qt, QSettings
from sqlmodel import select, col
from services.resource_service import ResourceLoader
from core.parser import FoundryParser
from core.engine import TranslationEngine
from ui.worker import TranslationWorker
from ui.settings_tab import SettingsTab
from ui.editor_panel import EditorPanel
from ui.integrity_tab import IntegrityTab
from services.llm_service import LLMService
from core.i18n import I18N
from core.database import (save_translation, get_cached_record,
                           Session, TranslationRecord, engine,
                           find_translation_conflicts, get_project_integrity_report,
                           normalize_project_term)


class FoundryGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"FoundryL10n - {I18N.t('ui_workstation')}")
        self.segments = []
        self.current_row = -1
        self.input_path = Path()
        self.llm_service = LLMService()

        # Icon
        # --- ICON LOADING LOGIC ---
        if getattr(sys, 'frozen', False):
            # If running as EXE, resources are in the temp folder
            res_base = Path(getattr(sys, '_MEIPASS')) / "resources"
        else:
            # If running in Dev mode (src is current, resources is two levels up)
            res_base = Path(__file__).parent.parent.parent / "resources"

        icon_path = res_base / "icon_256.png"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Main Layout: Tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.setMinimumSize(800, 600)

        self.init_translate_tab()

        self.settings_tab = SettingsTab()
        self.settings_tab.font_changed.connect(self.apply_font_size)
        self.settings_tab.profile_loaded.connect(
            self.on_profile_loaded_profile)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.tabs.addTab(self.settings_tab, I18N.t("tab_settings"))


        # Connect editor actions
        self.editor.btn_translate_now.clicked.connect(
            self.translate_current_row)
        self.editor.btn_rollback.clicked.connect(self.rollback_to_ai)

        self._current_fuzzy_text = ""
        self.editor.btn_use_fuzzy.clicked.connect(self.on_use_fuzzy_clicked)

        # Integrity Tab
        self.integrity_tab = IntegrityTab()
        self.integrity_tab.btn_refresh.clicked.connect(self.run_integrity_scan)
        self.tabs.addTab(self.integrity_tab, I18N.t("tab_integrity"))
        self.integrity_tab.btn_auto_normalize.clicked.connect(
            self.run_auto_normalize)

        # Load states
        self.load_ui_state()
        self.settings_tab.load_settings()

    def init_translate_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # --- TOP CONTROL BAR ---
        top_bar = QHBoxLayout()
        self.btn_open = QPushButton("Open TSV")
        self.btn_open.clicked.connect(self.open_file)

        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #888; font-style: italic;")

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Filter keys or text...")
        self.search_bar.textChanged.connect(self.filter_table)

        self.cb_only_errors = QCheckBox("Show Only Errors")
        self.cb_only_errors.toggled.connect(self.filter_table)

        self.btn_toggle_editor = QPushButton("Toggle Editor")
        self.btn_toggle_editor.setCheckable(True)
        self.btn_toggle_editor.setChecked(True)
        self.btn_toggle_editor.clicked.connect(self.toggle_editor)

        self.btn_zen = QPushButton("Zen Mode")
        self.btn_zen.setCheckable(True)
        self.btn_zen.clicked.connect(self.toggle_zen_mode)
        top_bar.addWidget(self.btn_zen)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.file_label, 1)  # Give it stretch
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_bar)
        top_bar.addWidget(self.cb_only_errors)
        top_bar.addWidget(self.btn_toggle_editor)
        layout.addLayout(top_bar)

        # --- CENTRAL SPLITTER ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Table
        self.table = QTableWidget(0, 4)

        # Selection behavior
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection)

        # Headers
        self.table.setHorizontalHeaderLabels(
            ["State", "Key", "Source", "Translation"])

        # Column resize: Excel-like (drag)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Fixed State column (icon only)
        self.table.setColumnWidth(0, 40)   # State indicator only

        # Sensible starting widths
        self.table.setColumnWidth(1, 150)  # Key
        self.table.setColumnWidth(2, 400)  # Source
        self.table.setColumnWidth(3, 400)  # Translation

        header.sectionDoubleClicked.connect(self._auto_fit_column)

        # Context menu + selection change
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.itemSelectionChanged.connect(self.update_selection_info)

        # Right: Editor
        self.editor = EditorPanel()
        self.editor_container = QScrollArea()
        self.editor_container.setWidgetResizable(True)
        self.editor_container.setWidget(self.editor)
        self.editor.btn_save.clicked.connect(self.save_manual_edit)
        self.editor.btn_next.clicked.connect(self.nav_next_needed)
        self.editor.btn_prev.clicked.connect(lambda: self.nav_error(-1))
        self.editor.request_next_needed.connect(self.nav_next_needed)
        self.editor.history_list.itemDoubleClicked.connect(
            self.restore_from_history_list)

        self.editor.history_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.history_list.customContextMenuRequested.connect(
            self.show_history_context_menu)

        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.editor_container)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        layout.addWidget(self.splitter)

        # --- BOTTOM BAR (Counters + Log) ---
        self.thought_log = QTextEdit()
        self.thought_log.setReadOnly(True)
        self.thought_log.setMaximumHeight(80)
        self.thought_log.setStyleSheet(
            "background-color: #1e1e1e; color: #888;")
        layout.addWidget(self.thought_log)

        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()

        self.cb_follow = QCheckBox("Follow")
        self.cb_follow.setChecked(True)

        self.btn_run = QPushButton("Start Bulk Translation")
        self.btn_run.clicked.connect(self.handle_run_clicked)
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setStyleSheet("font-weight: bold;")

        self.lbl_stats = QLabel(
            "\U0001f7e2 0 | \U0001f7e1 0 | \U0001f536 0 | \U0001f534 0 | \U0001f535 0 | \u26aa 0")
        self.lbl_stats.setToolTip(
            "\U0001f7e2 QA Done (Verified)\\n"
            "\U0001f7e1 AI Draft (Needs Review)\\n"
            "\U0001f536 Risk Alert (Term Missing/Anomaly)\\n"
            "\U0001f534 Tag Error\\n"
            "\U0001f535 Translation Conflict\\n"
            "\u26aa Pending"
        )

        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.cb_follow)
        bottom.addWidget(self.lbl_stats)
        bottom.addWidget(self.btn_run)
        layout.addLayout(bottom)

        self.tabs.addTab(page, "Workstation")
        self.table.itemChanged.connect(self.on_table_cell_edited)

    # --- LOGIC & SLOTS ---
    def on_profile_loaded_profile(self):
        if not hasattr(self, "segments"):
            return

        self.audit_database_consistency()
        self.update_stats()
        self.thought_log.append("Profile Loaded -> Re-Audit Done")

    def get_current_project(self):
        return self.settings_tab.get_settings().get('project_name', 'default')

    def on_table_cell_edited(self, item):
        """Syncs table cell edits to the Editor Panel."""
        if item.column() != 3:
            return  # Translation column only

        row = item.row()
        new_text = item.text()
        seg = self.segments[row]

        # Avoid pointless loops
        if seg.translation == new_text:
            return

        seg.translation = new_text

        # If the editor is looking at this row, update the editor box
        if self.current_row == row:
            self.editor.trans_edit.blockSignals(True)
            self.editor.trans_edit.setPlainText(
                new_text.replace("[TAG ERROR] ", ""))
            self.editor.trans_edit.blockSignals(False)

    def on_use_fuzzy_clicked(self):
        """Apply current fuzzy suggestion when the button is clicked."""
        if self._current_fuzzy_text:
            self.apply_fuzzy_suggestion(self._current_fuzzy_text)

    def nav_next_needed(self):
        """Jumps to the next row that is Red (Error) or White (Untranslated)."""
        start = self.current_row + 1
        for i in range(start, self.table.rowCount()):
            seg = self.segments[i]
            # Jump if it's an error OR if it's empty
            if "[TAG ERROR]" in seg.translation or not seg.translation or not seg.is_verified:
                self.table.setCurrentCell(i, 1)
                return
        self.thought_log.append("<b>[INFO]</b>: Reached the end of the file.")

    def _auto_fit_column(self, index):
        if index > 0:  # Don't auto-fit the icon column
            self.table.resizeColumnToContents(index)

    def toggle_zen_mode(self):
        """Hides UI elements and switches table to 'Full Screen' Stretch mode."""
        is_zen = self.btn_zen.isChecked()

        # 1. Hide/Show standard elements
        self.thought_log.setVisible(not is_zen)
        self.progress_bar.setVisible(not is_zen)
        self.lbl_stats.setVisible(not is_zen)
        self.file_label.setVisible(not is_zen)
        self.editor_container.setVisible(not is_zen)
        self.btn_toggle_editor.setChecked(not is_zen)

        # 2. Dynamic Column Stretching
        header = self.table.horizontalHeader()
        if is_zen:
            # In Zen Mode, make Source and Translation fill the screen
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        else:
            # When leaving Zen, go back to Interactive (Excel-style)
            # This allows you to drag them again
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)

            # Restore your preferred widths from the saved state
            self.load_ui_state()

    def run_auto_normalize(self):
        settings = self.settings_tab.get_settings()
        reply = QMessageBox.question(self, "Auto-Normalize",
                                     "This will pick the most frequent translation for every conflict in the database and apply it. Proceed?")
        if reply == QMessageBox.StandardButton.Yes:
            from core.database import auto_normalize_all_conflicts
            count = auto_normalize_all_conflicts(
                settings['project_name'], settings['lang'])
            QMessageBox.information(
                self, "Success", f"Cleaned up {count} inconsistent records in Memory.")
            self.run_integrity_scan()  # Refresh the list
            self.refresh_table_from_db()  # Refresh the workstation icons

    def remove_current_from_memory(self):
        """Wipes the current selection from the database entirely."""
        indices = self.table.selectionModel().selectedRows()
        if not indices:
            return

        reply = QMessageBox.question(self, "Forget Translation",
                                     f"Delete {len(indices)} rows from permanent memory?\nThis cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            from core.database import delete_record
            settings = self.settings_tab.get_settings()

            for idx in indices:
                row = idx.row()
                seg = self.segments[row]
                # 1. Kill it in the DB
                delete_record(seg.source_text,
                              settings['lang'], settings['project_name'])
                # 2. Reset the UI segment
                seg.translation = ""
                seg.is_verified = False
                seg.thought = "Purged from memory"
                self.update_row_visuals(row)

            self.update_stats()
            QMessageBox.information(
                self, "Success", "Segments purged from database.")

    def clear_selected_rows(self):
        """Wipes translations for all highlighted rows in UI and DB."""
        # Get unique selected row indices
        indices = self.table.selectionModel().selectedRows()
        if not indices:
            return

        reply = QMessageBox.question(self, "Clear Selected",
                                     f"Wipe translations for {len(indices)} selected rows?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            settings = self.settings_tab.get_settings()
            lang = settings.get('lang', 'BG')
            project_name = settings.get(
                'project_name', settings.get('project', 'default'))

            for index in indices:
                row_idx = index.row()
                if self.table.isRowHidden(row_idx):
                    continue
                seg = self.segments[row_idx]

                # Wipe data
                seg.translation = ""
                seg.is_verified = False
                seg.never_translate = False
                seg.thought = "Wiped by user"

                # Update Database (Save as empty string)
                save_translation(
                    seg.source_text,
                    lang,
                    "",
                    project_name=project_name,
                    verified=False,
                    skip=False,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )

                # Update Table Visuals
                self.update_row_visuals(row_idx)

            self.update_stats()

    def toggle_editor(self):
        self.editor_container.setVisible(self.btn_toggle_editor.isChecked())

    def filter_table(self):
        search_text = self.search_bar.text().lower()
        only_errors = self.cb_only_errors.isChecked()

        for i in range(self.table.rowCount()):
            key_item = self.table.item(i, 1)
            src_item = self.table.item(i, 2)

            key = key_item.text().lower() if key_item else ""
            src = src_item.text().lower() if src_item else ""
            # Get translation from the segment data directly
            trans = self.segments[i].translation.lower()

            match_search = search_text in key or search_text in src or search_text in trans
            match_error = "[TAG ERROR]" in trans.upper(
            ) if only_errors else True

            self.table.setRowHidden(i, not (match_search and match_error))

    def translate_current_row(self):
        """Sends the currently selected single row to the LLM with a Stop option."""
        if self.current_row < 0:
            return

        # Ако вече има работещ single_worker → това действие е STOP
        if hasattr(self, "single_worker") and self.single_worker.isRunning():
            self.single_worker.stop()
            # по желание: self.single_worker.terminate() ако stop() не стига
            self.editor.btn_translate_now.setText("🤖 Translate Line")
            self.editor.btn_translate_now.setStyleSheet(
                "background-color: #34495e; color: white;"
            )
            return

        seg = self.segments[self.current_row]
        settings = self.settings_tab.get_settings()

        # Влизаме в режим "мисли"
        self.editor.btn_translate_now.setText("🛑 Stop Thinking")
        self.editor.btn_translate_now.setStyleSheet(
            "background-color: #c0392b; color: white;"
        )

        project_name = settings.get("project_name", "default")

        svc = LLMService(model_name=settings["model"])
        self.single_worker = TranslationWorker(
            segments=[seg],
            target_lang=settings["lang"],
            llm_service=svc,
            glossary_path=settings["glossary_path"],
            style_path=settings["style_path"],
            forbidden_path=settings["forbidden_path"],
            prompt_template=settings["prompt_template"],
            temp=settings["temp"],
            project_name=project_name,
        )

        self.single_worker.finished_signal.connect(self.on_single_done)
        self.single_worker.start()

    def on_single_done(self, result):
        self.editor.btn_translate_now.setEnabled(True)
        self.editor.btn_translate_now.setText("🤖 Translate Line")

        # Update visuals and editor content
        self.update_row_visuals(self.current_row)
        seg = self.segments[self.current_row]
        self.editor.trans_edit.setPlainText(
            seg.translation.replace("[TAG ERROR] ", ""))
        self.editor.ai_draft_display.setPlainText(seg.ai_draft)
        self.update_stats()

    def update_selection_info(self):
        """Updates the status bar with selection count without making the window explode."""
        selected_indices = self.table.selectionModel().selectedRows()
        count = len(selected_indices)

        # 1. Start with fresh stats
        v, qa, risk, err, pend, conflict = 0, 0, 0, 0, 0, 0
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                txt = item.text()
                if txt == "🟢":
                    v += 1
                elif txt == "🟡":
                    qa += 1
                elif txt == "🔶":
                    risk += 1
                elif txt == "🔴":
                    err += 1
                elif txt == "🔵":
                    conflict += 1
                else:
                    pend += 1

        stats_text = f"🟢 {v} | 🟡 {qa} | 🔶 {risk} | 🔴 {err} | 🔵 {conflict} | ⚪ {pend}"

        # 2. Add selection info ONLY if more than 1 is selected
        # HERO FIX: We set the text CLEANly here to prevent the "selected: 4 selected: 3" loop
        if count > 1:
            self.lbl_stats.setText(f"SELECTED: {count} rows | {stats_text}")
        else:
            self.lbl_stats.setText(stats_text)

    def on_row_selected(self):
        """When a row is clicked, load data into the editor safely."""
        row = self.table.currentRow()
        if row < 0:
            return

        self.current_row = row
        seg = self.segments[row]

        # Block signals so the editor doesn't try to sync
        # back to the table while we are just loading the row data.
        self.editor.trans_edit.blockSignals(True)
        self.editor.source_edit.blockSignals(True)

        # 1. Update text fields
        self.editor.source_edit.setText(seg.source_text)
        self.editor.ai_draft_display.setText(seg.ai_draft)
        self.editor.trans_edit.setPlainText(
            seg.translation.replace("[TAG ERROR] ", "")
        )

        # Unblock after loading is finished
        self.editor.trans_edit.blockSignals(False)
        self.editor.source_edit.blockSignals(False)

        # 2. Sync checkboxes with segment flags
        self.editor.cb_verified.setChecked(getattr(seg, "is_verified", False))

        # 3. LOAD HISTORY LIST
        self.editor.history_list.clear()
        try:
            settings = self.settings_tab.get_settings()
            record = get_cached_record(
                seg.source_text,
                settings.get("lang", "BG"),
                project_name=settings.get("project_name", "default"),
            )

            if record and record.history_json:
                history_data = json.loads(record.history_json or "[]")
                for old_ver in reversed(history_data):
                    if old_ver.strip():
                        self.editor.history_list.addItem(old_ver)
        except Exception:
            pass

        # 4. Conditional Fuzzy Match Search
        is_verified = getattr(seg, 'is_verified', False)
        is_skip = getattr(seg, 'never_translate', False)

        if is_verified or is_skip:
            self.editor.fuzzy_display.clear()
            self.editor.btn_use_fuzzy.setVisible(False)
        else:
            self.search_fuzzy_matches(seg.source_text)

    def search_fuzzy_matches(self, text):
        """Looks for similar lines and updates the editor panel."""
        self.editor.fuzzy_display.clear()
        self.editor.btn_use_fuzzy.setVisible(False)
        self._current_fuzzy_text = ""

        if self.current_row < 0:
            return

        seg = self.segments[self.current_row]
        if getattr(seg, "is_verified", False):
            return

        settings = self.settings_tab.get_settings()
        engine_helper = TranslationEngine(self.llm_service)

        match = engine_helper.find_fuzzy_match(
            text,
            settings.get("project_name", "default"),
            settings.get("lang", "BG"),
        )

        if match:
            info = (
                f"Score: {match['score']}%\n"
                f"Source: {match['source']}\n"
                f"Suggestion: {match['translation']}"
            )
            self.editor.fuzzy_display.setText(info)
            self.editor.btn_use_fuzzy.setVisible(True)
            self._current_fuzzy_text = match["translation"]

    def apply_fuzzy_suggestion(self, text: str) -> None:
        """Copies the fuzzy match translation into the active editor."""
        self.editor.trans_edit.setPlainText(text)
        self.editor.btn_use_fuzzy.setVisible(False)
        self.thought_log.append(
            "<b>[SMART]</b>: Applied fuzzy match suggestion.")

    def nav_error(self, direction):
        """Navigates to the next or previous Red row."""
        start = self.current_row + direction
        rng = range(start, self.table.rowCount()
                    ) if direction > 0 else range(start, -1, -1)

        for i in rng:
            if "[TAG ERROR]" in self.segments[i].translation:
                self.table.setCurrentCell(i, 1)
                break

    def save_manual_edit(self):
        """Master commit from the Editor: save text, force-verify, and persist scoped to project/lang."""
        if self.current_row < 0:
            return

        seg = self.segments[self.current_row]

        # 1) Get text from Editor
        new_text = self.editor.trans_edit.toPlainText()

        # 2) Update segment state (SYNC is important)
        seg.translation = new_text
        seg.is_verified = True  # Save always verifies
        seg.thought = "Verified by Human"
        self.editor.cb_verified.setChecked(True)

        # 3) Project/Lang
        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG")

        # 4) Save to DB with all flags
        save_translation(
            seg.source_text,
            lang,
            new_text,
            project_name=project_name,
            verified=True,
            skip=getattr(seg, "never_translate", False),
            ai_draft=getattr(seg, "ai_draft", ""),
        )

        # 5) UI refresh
        self.update_row_visuals(self.current_row)
        self.update_stats()
        self.table.setFocus()

        # 6) QoL: auto-jump to next line that needs attention
        self.nav_next_needed()

    def get_best_font(self, size: int):
        """Scans the system for the best font supporting the target language's script."""
        settings = self.settings_tab.get_settings()
        # e.g., "BG", "JA", "AR"
        lang_code = settings.get('lang', 'BG').upper()

        db = QFontDatabase()

        # 1. Map Language Codes to Qt Writing Systems
        # This covers the major "Non-Latin" game localization targets
        script_map = {
            "BG": QFontDatabase.WritingSystem.Cyrillic,
            "RU": QFontDatabase.WritingSystem.Cyrillic,
            "UK": QFontDatabase.WritingSystem.Cyrillic,
            "EL": QFontDatabase.WritingSystem.Greek,
            "JA": QFontDatabase.WritingSystem.Japanese,
            "ZH": QFontDatabase.WritingSystem.SimplifiedChinese,
            "KO": QFontDatabase.WritingSystem.Korean,
            "AR": QFontDatabase.WritingSystem.Arabic,
            "HE": QFontDatabase.WritingSystem.Hebrew,
            "TH": QFontDatabase.WritingSystem.Thai,
            "HI": QFontDatabase.WritingSystem.Devanagari,
        }

        # Determine the writing system (Default to Latin if unknown)
        target_system = script_map.get(
            lang_code, QFontDatabase.WritingSystem.Latin)
        supported_families = db.families(target_system)

        # 2. Cross-platform priority list
        priority_list = [
            "Segoe UI", "San Francisco", "Ubuntu", "Noto Sans",
            "DejaVu Sans", "Arial", "MS PGothic", "Microsoft YaHei"
        ]

        selected_family = ""
        for family in priority_list:
            if family in supported_families:
                selected_family = family
                break

        # Fallback: Just take the first font that supports the required script
        if not selected_family and supported_families:
            selected_family = supported_families[0]

        font = QFont(selected_family or "Sans Serif", size)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        return font

    def apply_font_size(self, size):
        """Updates font size globally using the universal font scanner."""
        new_font = self.get_best_font(int(size))

        self.table.setFont(new_font)

        if hasattr(self, 'editor'):
            self.editor.source_edit.setFont(new_font)
            self.editor.trans_edit.setFont(new_font)
            self.editor.history_list.setFont(new_font)
            # Update the AI Draft display as well
            if hasattr(self.editor, 'ai_draft_display'):
                self.editor.ai_draft_display.setFont(new_font)

        if hasattr(self, 'lbl_stats'):
            self.lbl_stats.setFont(new_font)

        self.thought_log.setFont(new_font)
        self.current_font = new_font

    def show_context_menu(self, pos):
        """Right-click menu for the table."""
        # If nothing is selected, try to select the row under the mouse
        if not self.table.selectionModel().hasSelection():
            item = self.table.itemAt(pos)
            if item:
                self.table.selectRow(item.row())

        selected_indices = self.table.selectionModel().selectedRows()
        if not selected_indices:
            return

        menu = QMenu(self)
        count = len(selected_indices)

        if count > 1:
            # --- MULTI-ROW ACTIONS ---
            menu.addAction(f"🟢 Verify {count} Rows").triggered.connect(
                lambda: self.bulk_verify_selected(selected_indices))

            menu.addAction(f"⚪ Unverify {count} Rows").triggered.connect(
                lambda: self.bulk_unverify_selected(selected_indices))

            menu.addAction(f"⚪ Skip {count} (Never Translate)").triggered.connect(
                lambda: self.bulk_skip_selected(selected_indices))

            menu.addSeparator()
            menu.addAction("🔥 Purge from Memory (Delete Record)").triggered.connect(
                self.remove_current_from_memory)

            menu.addSeparator()
            menu.addAction("🧪 Generate Pseudo-Loc").triggered.connect(self.run_pseudo_batch)
            menu.addAction("🔥 Purge Record").triggered.connect(self.remove_current_from_memory)

            menu.addAction(f"🗑️ Clear {count} Translations").triggered.connect(
                self.clear_selected_rows)
        else:
            # --- SINGLE-ROW ACTIONS ---
            row = selected_indices[0].row()
            menu.addAction("📋 Copy Source").triggered.connect(
                lambda: self.quick_action(row, "copy"))
            menu.addAction("🟢 Mark Verified").triggered.connect(
                lambda: self.quick_action(row, "verify"))
            menu.addAction("⚪ Never Translate").triggered.connect(
                lambda: self.quick_action(row, "skip"))
            menu.addSeparator()
            menu.addAction("🗑️ Clear Translation (Del)").triggered.connect(
                lambda: self.quick_action(row, "clear"))
            menu.addAction("🔥 Purge Record").triggered.connect(
                self.remove_current_from_memory)

        # --- GLOBAL ACTIONS ---
        menu.addSeparator()
        menu.addAction("🔍 Search & Replace...").triggered.connect(
            self.show_find_replace)
        menu.addAction("📦 Export Verified to Glossary...").triggered.connect(
            self.export_verified_glossary)

        # Map local table coordinates to global screen coordinates correctly
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def bulk_verify_selected(self, indices):
        if not indices:
            return
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            if seg.translation:
                seg.is_verified = True  # Update memory
                # Update DB
                save_translation(
                    seg.source_text,
                    lang,
                    seg.translation,
                    project_name=project_name,
                    verified=True,
                    skip=seg.never_translate,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )
                self.update_row_visuals(row)
        self.update_stats()

    def quick_action(self, row, action_type):
        seg = self.segments[row]
        settings = self.settings_tab.get_settings()

        lang = settings.get("lang", "BG")
        project_name = settings.get(
            "project_name", settings.get("project", "default"))

        # Current flags
        is_ver = bool(getattr(seg, "is_verified", False))
        is_skip = bool(getattr(seg, "never_translate", False))

        if action_type == "skip":
            # Never translate → copy source and flag as skip
            seg.translation = seg.source_text
            is_skip = True
            is_ver = False

        elif action_type == "copy":
            # Copy source text into translation
            seg.translation = seg.source_text

        elif action_type == "clear":
            # Clear translation and reset flags
            seg.translation = ""
            is_ver = False
            is_skip = False

        elif action_type == "verify":
            # Mark as manually verified
            is_ver = True

        # Persist to DB with full context
        save_translation(
            seg.source_text,
            lang,
            seg.translation,
            project_name=project_name,
            verified=is_ver,
            skip=is_skip,
            ai_draft=getattr(seg, "ai_draft", ""),
        )

        # Sync back to segment object
        seg.is_verified = is_ver
        seg.never_translate = is_skip

        self.update_row_visuals(row)
        self.update_stats()

    def update_row_visuals(self, row_idx: int):
        if row_idx < 0 or row_idx >= len(self.segments):
            return

        seg = self.segments[row_idx]

        # Ensure items exist
        for column_index in (0, 3):
            if not self.table.item(row_idx, column_index):
                self.table.setItem(row_idx, column_index, QTableWidgetItem())

        state_item = self.table.item(row_idx, 0)
        trans_item = self.table.item(row_idx, 3)

        # --- FLAGS ---
        is_skip = getattr(seg, "never_translate", False)
        is_verified = getattr(seg, "is_verified", False)
        is_conflict = getattr(seg, "has_conflict", False)

        translation = seg.translation or ""
        thought = seg.thought or ""

        has_tag_error = "[TAG ERROR]" in translation
        has_risk = "⚠️" in thought

        # --- PRIORITY RESOLUTION (single source of truth) ---
        if is_conflict:
            icon, color = "🔵", QColor("#1a237e")
        elif is_skip:
            icon, color = "⚪", QColor("#3c3f41")
        elif has_tag_error:
            icon, color = "🔴", QColor("#441111")
        elif has_risk:
            icon, color = "🔶", QColor("#443311")
        elif is_verified:
            icon, color = "🟢", QColor("#113311")
        elif translation:
            icon, color = "🟡", QColor("#333311")
        else:
            icon, color = "⚪", QColor("#222222")

        # --- APPLY VISUALS ---
        if state_item:
            state_item.setText(icon)
        if trans_item:
            trans_item.setText(translation)

        for c in range(4):
            item = self.table.item(row_idx, c)
            if item:
                item.setBackground(color)
                item.setForeground(QColor("#eeeeee"))

        # --- TOOLTIP LOGIC (derived from resolved state) ---
        status_msg = f"Status: {icon}\n"

        if is_skip:
            status_msg += "Row is LOCKED and invisible to AI."
        elif is_conflict:
            status_msg += "CONFLICT: Database has multiple translations for this text."
        elif has_tag_error:
            status_msg += "TAG MISMATCH: AI moved or deleted anchors."
        elif has_risk:
            # Extract first audit warning safely
            status_msg += f"AUDIT ALERT: {thought.split('|')[0].strip()}"
        elif is_verified:
            status_msg += "VERIFIED: Human checked and approved."
        elif translation:
            status_msg += "AI DRAFT: Needs human review."
        else:
            status_msg += "UNTRANSLATED."

        if state_item:
            state_item.setToolTip(status_msg)

        # QoL: show full text on hover
        if trans_item:
            trans_item.setToolTip(translation)

        src_item = self.table.item(row_idx, 2)
        if src_item:
            src_item.setToolTip(seg.source_text)

    def run_pseudo_batch(self):
        engine = TranslationEngine(self.llm_service)
        engine.run_pseudo_localization(self.segments)
        for i in range(self.table.rowCount()):
            self.update_row_visuals(i)
        self.update_stats()

    def show_find_replace(self):
        text_find, ok1 = QInputDialog.getText(self, "Find", "Text to find:")
        if not ok1 or not text_find:
            return
        text_replace, ok2 = QInputDialog.getText(
            self, "Replace", f"Replace '{text_find}' with:")
        if not ok2:
            return

        count = 0
        for seg in self.segments:
            if text_find in seg.translation:
                seg.translation = seg.translation.replace(
                    text_find, text_replace)
                count += 1

        # Refresh the table view
        for i in range(self.table.rowCount()):
            self.update_row_visuals(i)

        QMessageBox.information(
            self, "Finished", f"Replaced {count} occurrences.")

    def on_tab_changed(self, index):
        """If returning to the workstation, refresh the icons based on current project."""
        if index == 0 and self.segments:
            # Re-scan the database for the new project name/lang
            self.refresh_table_from_db()

    def show_history_context_menu(self, pos):
        """Right-click menu for the history list to purge bad versions."""
        item = self.editor.history_list.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        # Simply add the action without assigning it to a variable
        menu.addAction("🗑️ Delete this version from history")

        # If the user clicks the action, menu.exec returns the action object (True-ish)
        if menu.exec(QCursor.pos()):
            settings = self.settings_tab.get_settings()
            seg = self.segments[self.current_row]

            from core.database import get_cached_record, Session, engine
            record = get_cached_record(
                seg.source_text,
                settings['lang'],
                project_name=settings.get('project_name', 'default')
            )

            if record and record.history_json:
                try:
                    h_data = json.loads(record.history_json)
                    # Filter out the specific text from this history item
                    new_h = [v for v in h_data if v != item.text()]

                    with Session(engine) as session:
                        session.add(record)
                        record.history_json = json.dumps(new_h)
                        session.commit()

                    # Refresh the side panel to show the updated list
                    self.on_row_selected()
                except Exception as e:
                    print(f"History purge error: {e}")

    def refresh_table_from_db(self):
        """Force-syncs table with DB, preserving session-specific errors and risks."""
        settings = self.settings_tab.get_settings()
        p_name = settings.get('project_name', 'default')
        lang = settings['lang']

        for i, seg in enumerate(self.segments):
            # 1. PRESERVE TRANSIENT STATE
            # Store current session info before we look at the DB
            current_is_error = "[TAG ERROR]" in seg.translation
            current_thought = seg.thought or ""
            has_warning = "⚠️" in current_thought

            # 2. DATABASE LOOKUP
            record = get_cached_record(
                seg.source_text, lang, project_name=p_name)

            if record:
                # HERO LOGIC: Only overwrite if the DB has a VERIFIED translation
                # OR if we don't currently have an error marker.
                if record.is_verified or not current_is_error:
                    seg.translation = record.translation
                    seg.is_verified = record.is_verified
                    seg.never_translate = record.never_translate
                    seg.ai_draft = record.ai_draft

                    # Only overwrite the thought if it doesn't contain a session warning
                    if not has_warning:
                        seg.thought = "Restored from Memory"
            else:
                # If no record in DB, we keep what we have in memory (preserving [TAG ERROR])
                pass

            # 3. VISUAL UPDATE
            self.update_row_visuals(i)

        self.update_stats()

    def run_integrity_scan(self):
        """Scans DB and populates the Integrity Hub (Integrity tab)."""

        settings = self.settings_tab.get_settings()
        project_name = settings.get(
            "project_name", settings.get("project", "default"))
        lang = settings.get("lang", "BG")

        report = get_project_integrity_report(project_name, lang)

        # Fill the Integrity tab table
        self.integrity_tab.populate_report(report)

        # Wire up the Normalize buttons
        for i in range(self.integrity_tab.table.rowCount()):
            btn = self.integrity_tab.table.cellWidget(i, 2)
            if isinstance(btn, QPushButton):
                source = report[i]["source"]
                variants = list(report[i]["variants"].keys())
                btn.clicked.connect(
                    lambda checked=False, s=source, v=variants: self.resolve_conflict_dialog(s, v))

    def resolve_conflict_dialog(self, source, variants):
        """Shows a dialog to pick the one true translation and normalizes the DB."""

        settings = self.settings_tab.get_settings()
        project_name = settings.get(
            "project_name", settings.get("project", "default"))
        lang = settings.get("lang", "BG")

        choice, ok = QInputDialog.getItem(
            self,
            "Resolve Conflict",
            f"Pick the correct translation for:\n\n{source}",
            variants,
            0,
            False,
        )

        if ok and choice:
            normalize_project_term(project_name, lang, source, choice)
            QMessageBox.information(
                self,
                "Success",
                "Database normalized. Run the scan again to verify updated conflicts.",
            )

            # Refresh Integrity Hub and table markers
            self.run_integrity_scan()
            self.audit_database_consistency()

    def audit_database_consistency(self):
        """Scans the DB for conflicts and marks rows using normalized comparison."""
        settings = self.settings_tab.get_settings()
        p_name = settings.get('project_name', 'default')
        lang = settings['lang']

        # This returns a list of normalized source strings that have conflicts
        conflicts = find_translation_conflicts(p_name, lang)

        if not conflicts:
            # Clear any old blue markers if conflicts were resolved
            for seg in self.segments:
                seg.has_conflict = False
            return

        count = 0
        for i, seg in enumerate(self.segments):
            # HERO FIX: Normalize the segment source text exactly like the DB does
            norm_seg_src = " ".join(seg.source_text.lower().split())

            if norm_seg_src in conflicts:
                seg.has_conflict = True
                self.update_row_visuals(i)
                count += 1
            else:
                seg.has_conflict = False

        if count > 0:
            self.thought_log.append(
                f"<b>[INTEGRITY]</b>: Found {count} rows with inconsistent translations (🔵)")
            self.update_stats()

    def global_db_replace(self):
        """Finds and replaces text across the ENTIRE database for this project/lang."""
        text_find, ok1 = QInputDialog.getText(
            self, "Global DB Fix", "Find in Database (Translation column):"
        )
        if not ok1 or not text_find:
            return

        text_replace, ok2 = QInputDialog.getText(
            self, "Global DB Fix", f"Replace '{text_find}' with:"
        )
        if not ok2:
            return

        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG")

        with Session(engine) as session:
            statement = select(TranslationRecord).where(
                TranslationRecord.project_name == project_name,
                TranslationRecord.target_lang == lang,
                col(TranslationRecord.translation).like(f"%{text_find}%"),
            )
            records = session.exec(statement).all()

            if not records:
                QMessageBox.information(
                    self, "Global Fix", "No matches found in database.")
                return

            reply = QMessageBox.question(
                self,
                "Confirm Global Fix",
                f"This will update {len(records)} entries in your permanent memory. Proceed?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                for r in records:
                    if r.translation:
                        r.translation = r.translation.replace(
                            text_find, text_replace)
                        r.is_verified = True
                        session.add(r)
                session.commit()

        QMessageBox.information(
            self,
            "Success",
            f"Updated {len(records)} records in Memory. Reload file to see changes.",
        )

    def keyPressEvent(self, event):
        """Standard window-level shortcut for the Delete key."""
        if event.key() == Qt.Key.Key_Delete:
            # Only trigger if the table is the active widget
            if self.table.hasFocus():
                self.clear_selected_rows()
        super().keyPressEvent(event)

    def update_stats(self):
        """Calculates and updates the bottom bar dashboard counters."""
        v = qa = risk = err = pend = conflict = 0

        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if not item:
                continue
            txt = item.text()
            if txt == "🟢":
                v += 1
            elif txt == "🟡":
                qa += 1
            elif txt == "🔶":
                risk += 1
            elif txt == "🔴":
                err += 1
            elif txt == "🔵":
                conflict += 1
            else:
                pend += 1

        # 1. Update the text with clear separators
        self.lbl_stats.setText(
            f"🟢 {v} | 🟡 {qa} | 🔶 {risk} | 🔴 {err} | 🔵 {conflict} |  ⚪ {pend}"
        )
        self.lbl_stats.setStyleSheet("""
            QLabel { 
                font-family: 'Consolas', 'Courier New'; 
                font-weight: bold; 
                padding: 2px 10px;
                background-color: #1e1e1e;
                border-radius: 4px;
                color: #ffffff;
            }
        """)

        # 2. Update the Tooltip (Hover info)
        self.lbl_stats.setToolTip(
            "<b>Foundry Dashboard Status:</b><br>"
            "🟢 QA Done (Human Verified)<br>"
            "🟡 AI Draft (Needs Review)<br>"
            "🔶 Risk Alert (Term Missing or Length Anomaly)<br>"
            "🔴 Tag Error (Technical Mismatch)<br>"
            "🔵 Consistency Conflict (Same English has different BG in DB)<br>"
            "⚪ Pending (Untouched)"
        )

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TSV", "", "TSV Files (*.tsv)"
        )
        if not path:
            return

        self.input_path = Path(path)
        self.file_label.setText(str(self.input_path))

        # PERFORMANCE: Freeze table updates while we populate rows
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)

        try:
            # 1. Parse the TSV
            self.segments = FoundryParser().parse_tsv(self.input_path)
            self.table.setRowCount(len(self.segments))

            # 2. Get current project settings
            settings = self.settings_tab.get_settings()
            target_lang = settings["lang"]
            project_name = self.get_current_project()

            # 3. Load the glossary dictionary specifically for the audit

            engine_helper = TranslationEngine(self.llm_service)
            # We load it from the path defined in your settings tab
            glossary_dict = ResourceLoader.load_glossary_dict(
                settings["glossary_path"])

            # 4. Load cached translations + audit-on-load
            for i, seg in enumerate(self.segments):
                record = get_cached_record(
                    seg.source_text, target_lang, project_name
                )
                if record:
                    seg.translation = record.translation
                    seg.is_verified = record.is_verified
                    seg.never_translate = record.never_translate
                    seg.ai_draft = record.ai_draft
                    seg.thought = "Restored from Memory"

                    # Run audit immediately so 🔶 appears on rows already in DB
                    if seg.translation and "[TAG ERROR]" not in seg.translation:
                        engine_helper.audit_segment(seg, glossary_dict)

                # 5. Populate Table Row
                self.table.setItem(i, 0, QTableWidgetItem("⚪"))
                self.table.setItem(i, 1, QTableWidgetItem(seg.key))
                self.table.setItem(i, 2, QTableWidgetItem(seg.source_text))
                self.table.setItem(i, 3, QTableWidgetItem(seg.translation))

                # Apply state colors/icons
                self.update_row_visuals(i)

        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        # UI Refresh
        self.btn_run.setEnabled(True)
        self.progress_bar.setMaximum(len(self.segments))
        self.update_stats()

        # Set progress bar to current completion level
        finished_count = sum(1 for s in self.segments if s.is_verified)
        self.progress_bar.setValue(finished_count)

        # Final consistency audit for 🔵 markers
        self.audit_database_consistency()

    def handle_run_clicked(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.btn_run.setText("Start Bulk")
            self.progress_bar.setValue(0)  # RESET BAR
        else:
            self.start_translation()

    def start_translation(self):
        settings = self.settings_tab.get_settings()
        self.btn_run.setText("Stop Bulk Translation")
        self.btn_run.setStyleSheet(
            "background-color: #aa3333; font-weight: bold;")

        svc = LLMService(model_name=settings['model'])
        self.worker = TranslationWorker(
            segments=self.segments,
            target_lang=settings['lang'],
            llm_service=svc,
            glossary_path=settings['glossary_path'],
            style_path=settings['style_path'],
            forbidden_path=settings['forbidden_path'],
            prompt_template=settings['prompt_template'],
            project_name=settings.get('project_name', 'default'),
            temp=settings['temp']
        )
        self.worker.progress_signal.connect(self.update_row_ui)
        self.worker.finished_signal.connect(self.on_done)
        self.worker.start()

    def bulk_lock_selected(self, indices):
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            # Pass all current flags to database
            save_translation(
                seg.source_text,
                lang,
                seg.translation,
                project_name=project_name,
                verified=seg.is_verified,
                skip=seg.never_translate,
                ai_draft=getattr(seg, 'ai_draft', ""),
            )
            self.update_row_visuals(row)
        self.update_stats()

    def restore_from_history_list(self, item):
        """When you double-click a history item, it puts it in the editor."""
        version_text = item.text()
        self.editor.trans_edit.setPlainText(version_text)
        self.thought_log.append("Restored version from history list.")

    def rollback_to_ai(self):
        """Restores the translation to the original AI draft."""
        if self.current_row < 0:
            return
        seg = self.segments[self.current_row]

        if seg.ai_draft:
            self.editor.trans_edit.setPlainText(seg.ai_draft)
            self.thought_log.append("Rolled back to original AI Draft.")
        else:
            QMessageBox.information(
                self, "No History", "No AI Draft found for this line.")

    def bulk_skip_selected(self, indices):
        """Marks all selected rows as 'Never Translate'."""
        reply = QMessageBox.question(self, "Never Translate",
                                     f"Mark {len(indices)} rows as 'Never Translate'? They will be skipped by the AI.")
        if reply == QMessageBox.StandardButton.Yes:
            settings = self.settings_tab.get_settings()
            lang = settings.get('lang', 'BG')
            project_name = settings.get(
                'project_name', settings.get('project', 'default'))
            for idx in indices:
                row = idx.row()
                seg = self.segments[row]
                # In 'Skip' mode, we usually keep the original source as the translation
                seg.translation = seg.source_text
                seg.is_verified = False
                seg.never_translate = True
                seg.thought = "Never Translate (Bulk)"
                # skip=True tells the DB to never send this to LLM
                save_translation(
                    seg.source_text,
                    lang,
                    seg.translation,
                    project_name=project_name,
                    verified=False,
                    skip=True,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )
                self.update_row_visuals(row)
            self.update_stats()

    def bulk_unverify_selected(self, indices):
        """Reverts verified rows back to 'AI Draft' state."""
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            seg.is_verified = False
            # Save to DB with verified=False
            save_translation(
                seg.source_text,
                lang,
                seg.translation,
                project_name=project_name,
                verified=False,
                skip=seg.never_translate,
                ai_draft=getattr(seg, 'ai_draft', ""),
            )
            self.update_row_visuals(row)
        self.update_stats()

    def export_verified_glossary(self):
        """Export all Verified (Green) segments into a project/lang-scoped glossary TSV.

        - Default name: {project_name}_{lang}_verified_glossary.tsv
        - Appends to existing file instead of overwriting.
        - Skips duplicates (same term + translation).
        - Strips technical tags (<...>, [...], {...}, [#_0_]) and normalizes whitespace.
        """
        # 1) Collect verified segments
        verified_segments = [
            s for s in self.segments if getattr(s, "is_verified", False)]
        if not verified_segments:
            QMessageBox.warning(
                self, "Export", "No verified segments found to export.")
            return

        # 2) Build default filename from project + language
        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG").lower()
        default_name = f"{project_name}_{lang}_verified_glossary.tsv"

        # 3) Ask user where to save
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Verified Glossary",
            default_name,
            "TSV Files (*.tsv)",
        )
        if not path:
            return

        # 4) Tag stripper: internal markers + original tags/placeholders
        tag_pattern = re.compile(r"\[#_\d+_\]|<[^>]+>|\[[^\]]+\]|\{[^\}]+\}")

        # 5) Load existing term/translation pairs to avoid duplicates
        existing_pairs: set[tuple[str, str]] = set()
        file_exists = os.path.exists(path)
        file_nonempty = file_exists and os.path.getsize(path) > 0

        if file_nonempty:
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f, delimiter="\t")
                    # Skip header if present
                    header_skipped = False
                    for row in reader:
                        if not header_skipped:
                            header_skipped = True
                            # crude check: if header looks like "term" "translation", skip it
                            if len(row) >= 2 and row[0].lower() == "term":
                                continue
                        if len(row) >= 2:
                            term = row[0].strip()
                            trans = row[1].strip()
                            if term and trans:
                                existing_pairs.add((term, trans))
            except (OSError, csv.Error) as e:
                QMessageBox.critical(self, "Export Error",
                                     f"Failed to read existing glossary:\n{e}")
                return

        # 6) Append new lines without duplicates
        exported_count = 0
        file_empty = not file_exists or not file_nonempty

        try:
            with open(path, "a", encoding="utf-8", newline="") as f:
                if file_empty:
                    f.write("term\ttranslation\n")

                for seg in verified_segments:
                    # Clean tags from source and translation
                    raw_src = seg.source_text or ""
                    raw_trans = seg.translation or ""

                    src = tag_pattern.sub("", raw_src)
                    trans = tag_pattern.sub("", raw_trans)

                    # Whitespace crunch: collapse multiple spaces and trim
                    src = " ".join(src.split()).strip()
                    trans = " ".join(trans.split()).strip()

                    if not src or not trans:
                        continue

                    key = (src, trans)
                    if key in existing_pairs:
                        continue  # already present

                    f.write(f"{src}\t{trans}\n")
                    existing_pairs.add(key)
                    exported_count += 1
        except OSError as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to write glossary:\n{e}")
            return

        # 7) User feedback
        if exported_count > 0:
            QMessageBox.information(
                self,
                "Export Complete",
                f"Added {exported_count} new terms to glossary:\n{os.path.basename(path)}",
            )
        else:
            QMessageBox.information(
                self,
                "No New Terms",
                "All verified term/translation pairs are already in this glossary.",
            )

    def update_row_ui(self, val):
        self.progress_bar.setValue(val)
        self.update_row_visuals(val - 1)
        self.update_stats()
        if self.cb_follow.isChecked():
            self.table.setCurrentCell(val - 1, 1)

    def on_done(self, result):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Start Bulk Translation")
        self.btn_run.setStyleSheet("font-weight: bold;")
        self.save_ui_state()
        self.settings_tab.save_settings()

        parser = FoundryParser()
        settings = self.settings_tab.get_settings()
        out = Path("out") / settings['lang'] / self.input_path.name
        parser.save_tsv(result, out)
        self.file_label.setText(f"Finished! Saved to: {out}")

    def save_ui_state(self):
        """Saves window geometry, splitter, table header, and current tab."""
        settings = QSettings("FoundryL10n", "Workstation")

        # Window position/size/state
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())

        # Splitter layout
        settings.setValue("splitter_sizes", self.splitter.saveState())

        # Table header (column widths, order, etc.)
        settings.setValue("table_header_state",
                          self.table.horizontalHeader().saveState())

        # Active tab index
        settings.setValue("current_tab", self.tabs.currentIndex())

    def load_ui_state(self):
        """
        Restores window geometry, splitter, table header, and current tab safely.
        Includes a safety check to ensure the window fits on the current screen.
        """
        settings = QSettings("FoundryL10n", "Workstation")
        try:
            # 1) Restore window geometry (position and size)
            geom = settings.value("window_geometry")
            if geom is not None:
                self.restoreGeometry(geom)

            # 2) TV/Screen Safety Check: 
            # If the restored geometry is larger than the actual TV/Monitor resolution,
            # or if it's positioned off-screen, force it to a safe default.
            screen_geo = self.screen().availableGeometry()
            if self.width() > screen_geo.width() or self.height() > screen_geo.height():
                # Fallback to a safe workstation size if the saved state is "impossible"
                self.resize(1200, 800)
                # Center the window on the current screen
                self.move(
                    (screen_geo.width() - self.width()) // 2,
                    (screen_geo.height() - self.height()) // 2
                )

            # 3) Restore internal window state (maximized, etc.)
            state = settings.value("window_state")
            if state is not None:
                self.restoreState(state)

            # 4) Restore splitter layout (Table vs Editor ratio)
            splitter_state = settings.value("splitter_sizes")
            if splitter_state is not None:
                self.splitter.restoreState(splitter_state)

            # 5) Restore table header state (Column widths)
            header_state = settings.value("table_header_state")
            if header_state is not None:
                self.table.horizontalHeader().restoreState(header_state)

            # 6) Restore active tab with Pylance-safe casting
            raw_tab = settings.value("current_tab", 0)
            idx = int(str(raw_tab))
            if 0 <= idx < self.tabs.count():
                self.tabs.setCurrentIndex(idx)

        except Exception as exc:
            # We use a simple print here so startup doesn't crash if config is corrupted
            print(f"UI Restore Warning: {exc}")

    def closeEvent(self, event):
        """Stops all threads and saves settings before exiting."""
        # 1. Save UI State
        self.save_ui_state()
        self.settings_tab.save_settings()

        # 2. Force Stop the Worker
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()  # Tell it to stop the loop
            self.worker.terminate()  # Force kill the thread if it's stuck in Ollama
            self.worker.wait()  # Wait for cleanup

        event.accept()


def run_gui():
    app = QApplication(sys.argv)
    window = FoundryGUI()
    window.show()
    sys.exit(app.exec())
