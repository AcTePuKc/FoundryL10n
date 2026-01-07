import sys
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QProgressBar, 
                             QLabel, QTabWidget, QTextEdit, QCheckBox, 
                             QSplitter, QLineEdit, QMenu, QInputDialog, QMessageBox)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtCore import Qt, QSettings

from core.parser import FoundryParser
from ui.worker import TranslationWorker
from ui.settings_tab import SettingsTab
from services.llm_service import LLMService
from ui.editor_panel import EditorPanel
from core.database import save_translation

class FoundryGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FoundryL10n - Workstation")
        self.resize(1250, 850)
        self.segments = []
        self.current_row = -1
        self.input_path = Path()

        # Main Layout: Tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.init_translate_tab()
        
        self.settings_tab = SettingsTab()
        self.settings_tab.font_changed.connect(self.apply_font_size)

        self.tabs.addTab(self.settings_tab, "Settings")
        
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
        
        # FIXED: Re-added file_label definition
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
        top_bar.addWidget(self.file_label, 1) # Give it stretch
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_bar)
        top_bar.addWidget(self.cb_only_errors)
        top_bar.addWidget(self.btn_toggle_editor)
        layout.addLayout(top_bar)

        # --- CENTRAL SPLITTER ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Table
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setHorizontalHeaderLabels(["State", "Key", "Source", "Translation"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        
        # Right: Editor
        self.editor = EditorPanel()
        self.editor.btn_save.clicked.connect(self.save_manual_edit)
        self.editor.btn_next.clicked.connect(lambda: self.nav_error(1))
        self.editor.btn_prev.clicked.connect(lambda: self.nav_error(-1))
        
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter)

        # --- BOTTOM BAR (Counters + Log) ---
        self.thought_log = QTextEdit()
        self.thought_log.setReadOnly(True)
        self.thought_log.setMaximumHeight(80)
        self.thought_log.setStyleSheet("background-color: #1e1e1e; color: #888;")
        layout.addWidget(self.thought_log)

        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()
        
        self.cb_follow = QCheckBox("Follow")
        self.cb_follow.setChecked(True)

        self.btn_run = QPushButton("Start Bulk Translation")
        self.btn_run.clicked.connect(self.handle_run_clicked)
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setStyleSheet("font-weight: bold;")
        
        self.lbl_stats = QLabel("🟢 0 | 🔴 0 | ⚪ 0")
        
        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.cb_follow)
        bottom.addWidget(self.lbl_stats)
        bottom.addWidget(self.btn_run)
        layout.addLayout(bottom)

        self.tabs.addTab(page, "Workstation")

    # --- LOGIC & SLOTS ---

    def toggle_zen_mode(self):
        """Hides/Shows almost everything for a distraction-free view."""
        is_zen = self.btn_zen.isChecked()
        self.thought_log.setVisible(not is_zen)
        self.progress_bar.setVisible(not is_zen)
        self.lbl_stats.setVisible(not is_zen)
        self.file_label.setVisible(not is_zen)
        
        # Also hide the side panel
        self.editor.setVisible(not is_zen)
        # Sync the 'Toggle Editor' button so it doesn't get confused
        self.btn_toggle_editor.setChecked(not is_zen)
            
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
            
            for index in indices:
                row_idx = index.row()
                seg = self.segments[row_idx]
                
                # Wipe data
                seg.translation = ""
                seg.thought = "Wiped by user"
                
                # Update Database (Save as empty string)
                save_translation(seg.source_text, settings['lang'], "", verified=False)
                
                # Update Table Visuals
                self.update_row_visuals(row_idx)
            
            self.update_stats()

    def toggle_editor(self):
        self.editor.setVisible(self.btn_toggle_editor.isChecked())

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
            match_error = "[TAG ERROR]" in trans.upper() if only_errors else True
            
            self.table.setRowHidden(i, not (match_search and match_error))

    def on_row_selected(self):
        row = self.table.currentRow()
        if row < 0: 
            return
        self.current_row = row
        seg = self.segments[row]
        
        self.editor.source_edit.setText(seg.source_text)
        # Show translation without the ugly error tag for editing
        clean_trans = seg.translation.replace("[TAG ERROR] ", "")
        self.editor.trans_edit.setText(clean_trans)
        
        is_error = "[TAG ERROR]" in seg.translation
        self.editor.cb_verified.setChecked(not is_error and seg.translation != "")

    def nav_error(self, direction):
        """Navigates to the next or previous Red row."""
        start = self.current_row + direction
        rng = range(start, self.table.rowCount()) if direction > 0 else range(start, -1, -1)
        
        for i in rng:
            if "[TAG ERROR]" in self.segments[i].translation:
                self.table.setCurrentCell(i, 1)
                break

    def save_manual_edit(self):
        if self.current_row < 0: 
            return
        seg = self.segments[self.current_row]
        
        new_text = self.editor.trans_edit.toPlainText()
        is_verified = self.editor.cb_verified.isChecked()
        
        seg.translation = new_text
        seg.thought = "Verified by Human" if is_verified else "Manual Correction"
        
        # Save to DB
        settings = self.settings_tab.get_settings()
        save_translation(seg.source_text, settings['lang'], new_text, verified=is_verified)
        
        # This now updates the 4th column automatically because we updated update_row_visuals
        self.update_row_visuals(self.current_row)
        self.update_stats()
    
    def apply_font_size(self, size):
        """Updates font size for the table and the editor side-panel."""
        new_font = self.font()
        new_font.setPointSize(int(size))
        
        # Update Table
        self.table.setFont(new_font)
        
        # Update Editor (if visible)
        if hasattr(self, 'editor'):
            self.editor.set_font_size(int(size))
            
        # Update Thought Log
        self.thought_log.setFont(new_font)
        
    def show_context_menu(self, pos):
        selected_indices = self.table.selectionModel().selectedRows()
        if not selected_indices:
            return
            
        menu = QMenu()
        num_selected = len(selected_indices)
        
        if num_selected > 1:
            # --- MULTI-ROW ACTIONS ---
            v_act = menu.addAction(f"🟢 Verify {num_selected} Rows")
            v_act.triggered.connect(lambda: self.bulk_verify_selected(selected_indices))
            
            s_act = menu.addAction(f"⚪ Skip {num_selected} (Never Translate)")
            s_act.triggered.connect(lambda: self.bulk_skip_selected(selected_indices))
            
            menu.addSeparator()
            
            c_act = menu.addAction(f"🗑️ Clear {num_selected} Translations")
            c_act.triggered.connect(self.clear_selected_rows)
        else:
            # --- SINGLE-ROW ACTIONS ---
            row = selected_indices[0].row()
            menu.addAction("📋 Copy Source").triggered.connect(lambda: self.quick_action(row, "copy"))
            menu.addAction("🟢 Mark Verified").triggered.connect(lambda: self.quick_action(row, "verify"))
            menu.addAction("⚪ Never Translate").triggered.connect(lambda: self.quick_action(row, "skip"))
            menu.addSeparator()
            menu.addAction("🗑️ Clear (Del)").triggered.connect(lambda: self.quick_action(row, "clear"))
        
        menu.addSeparator()
        menu.addAction("🔍 Search & Replace...").triggered.connect(self.show_find_replace)

        menu.exec(QCursor.pos())

    def bulk_verify_selected(self, indices):
        """Marks all selected rows as verified."""
        settings = self.settings_tab.get_settings()
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            save_translation(seg.source_text, settings['lang'], seg.translation, verified=True)
            self.update_row_visuals(row)
        self.update_stats()

    def quick_action(self, row, action_type):
        seg = self.segments[row]
        settings = self.settings_tab.get_settings()
        
        if action_type == "skip":
            seg.translation = seg.source_text # Keep original
            seg.thought = "Never Translate"
            save_translation(seg.source_text, settings['lang'], seg.translation, verified=False, skip=True)
        elif action_type == "copy":
            seg.translation = seg.source_text
        elif action_type == "clear":
            seg.translation = ""
        elif action_type == "verify":
            seg.thought = "Verified"

        save_translation(seg.source_text, settings['lang'], seg.translation, verified=(action_type=="verify"))
        self.update_row_visuals(row)
        self.update_stats()

    def update_row_visuals(self, row_idx):
        seg = self.segments[row_idx]
        
        # Update the text in the translation column
        trans_item = self.table.item(row_idx, 3)
        if not trans_item:
            trans_item = QTableWidgetItem()
            self.table.setItem(row_idx, 3, trans_item)
        trans_item.setText(seg.translation)

        state_item = self.table.item(row_idx, 0)
        if not state_item:
            state_item = QTableWidgetItem()
            self.table.setItem(row_idx, 0, state_item)

        if "[TAG ERROR]" in seg.translation:
            state_item.setText("🔴")
            color = QColor("#441111")
        elif seg.translation == "":
            state_item.setText("⚪")
            color = QColor("#222222")
        else:
            state_item.setText("🟢")
            color = QColor("#113311")
        
        # Apply color to all 4 columns
        for c in range(4): # Change 3 to 4
            item = self.table.item(row_idx, c)
            if item:
                item.setBackground(color)
                item.setForeground(QColor("#eeeeee"))

    def show_find_replace(self):
        text_find, ok1 = QInputDialog.getText(self, "Find", "Text to find:")
        if not ok1 or not text_find: 
            return
        text_replace, ok2 = QInputDialog.getText(self, "Replace", f"Replace '{text_find}' with:")
        if not ok2: 
            return

        count = 0
        for seg in self.segments:
            if text_find in seg.translation:
                seg.translation = seg.translation.replace(text_find, text_replace)
                count += 1
        
        # Refresh the table view
        for i in range(self.table.rowCount()):
            self.update_row_visuals(i)
        
        QMessageBox.information(self, "Finished", f"Replaced {count} occurrences.")


    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for the whole window."""
        # If 'Delete' is pressed while the table is active
        if event.key() == Qt.Key.Key_Delete:
            if self.table.hasFocus():
                self.clear_selected_rows()
        super().keyPressEvent(event)    


    def update_stats(self):
        # Counts based on the state icons we set in update_row_visuals
        verified = 0
        errors = 0
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                if item.text() == "🟢": 
                    verified += 1
                if item.text() == "🔴": 
                    errors += 1
        
        total = len(self.segments)
        self.lbl_stats.setText(f"🟢 {verified} | 🔴 {errors} | ⚪ {total - (verified + errors)}")


    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open TSV", "", "TSV Files (*.tsv)")
        if path:
            self.input_path = Path(path)
            self.file_label.setText(str(self.input_path))
            
            # 1. Parse the TSV
            self.segments = FoundryParser().parse_tsv(self.input_path)
            self.table.setRowCount(len(self.segments))
            
            # 2. Get current project settings (target language)
            settings = self.settings_tab.get_settings()
            lang = settings['lang']
            
            # 3. Connect to DB to check for existing work
            from core.database import get_cached_record # Ensure import
            
            for i, seg in enumerate(self.segments):
                # LOOKUP: Check if we have this line in our memory already
                record = get_cached_record(seg.source_text, lang)
                
                if record:
                    # If found, fill the segment with DB data
                    seg.translation = record.translation
                    if record.is_verified:
                        seg.thought = "Restored (Verified)"
                    elif record.never_translate:
                        seg.thought = "Restored (Skipped)"
                    elif "[TAG ERROR]" in record.translation:
                        seg.thought = "Restored (Tag Mismatch)"
                    else:
                        seg.thought = "Restored from Memory"
                
                # 4. Populate Table Row
                self.table.setItem(i, 0, QTableWidgetItem("⚪"))
                self.table.setItem(i, 1, QTableWidgetItem(seg.key))
                self.table.setItem(i, 2, QTableWidgetItem(seg.source_text))
                self.table.setItem(i, 3, QTableWidgetItem(seg.translation))
                
                # Apply colors/icons immediately
                self.update_row_visuals(i)
            
            self.btn_run.setEnabled(True)
            self.progress_bar.setMaximum(len(self.segments))
            self.update_stats()

    def handle_run_clicked(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.btn_run.setText("Stopping...")
        else:
            self.start_translation()

    def start_translation(self):
        settings = self.settings_tab.get_settings()
        self.btn_run.setText("Stop Bulk Translation")
        self.btn_run.setStyleSheet("background-color: #aa3333; font-weight: bold;")
        
        svc = LLMService(model_name=settings['model'])
        self.worker = TranslationWorker(
            segments=self.segments, target_lang=settings['lang'], llm_service=svc, 
            glossary_path=settings['glossary_path'], style_path=settings['style_path'],
            forbidden_path=settings['forbidden_path'], prompt_template=settings['prompt_template'],
            temp=settings['temp']
        )
        self.worker.progress_signal.connect(self.update_row_ui)
        self.worker.finished_signal.connect(self.on_done)
        self.worker.start()


    def bulk_skip_selected(self, indices):
            """Marks all selected rows as 'Never Translate'."""
            reply = QMessageBox.question(self, "Never Translate", 
                                    f"Mark {len(indices)} rows as 'Never Translate'? They will be skipped by the AI.")
            if reply == QMessageBox.StandardButton.Yes:
                settings = self.settings_tab.get_settings()
                for idx in indices:
                    row = idx.row()
                    seg = self.segments[row]
                    # In 'Skip' mode, we usually keep the original source as the translation
                    seg.translation = seg.source_text
                    seg.thought = "Never Translate (Bulk)"
                    # skip=True tells the DB to never send this to LLM
                    save_translation(seg.source_text, settings['lang'], seg.translation, verified=False, skip=True)
                    self.update_row_visuals(row)
                self.update_stats()


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

    def load_ui_state(self):
        s = QSettings("FoundryL10n", "Workstation")
        try:
            idx = int(str(s.value("current_tab", 0)))
            self.tabs.setCurrentIndex(idx)
            if s.value("splitter_sizes"):
                self.splitter.restoreState(s.value("splitter_sizes"))
        except: 
            pass

    def save_ui_state(self):
        s = QSettings("FoundryL10n", "Workstation")
        s.setValue("current_tab", self.tabs.currentIndex())
        s.setValue("splitter_sizes", self.splitter.saveState())

    def closeEvent(self, event):
        self.save_ui_state()
        self.settings_tab.save_settings()
        event.accept()

def run_gui():
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = FoundryGUI()
    window.show()
    sys.exit(app.exec())