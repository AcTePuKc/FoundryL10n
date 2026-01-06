import sys
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QProgressBar, 
                             QLabel, QTabWidget, QTextEdit, QCheckBox, QMessageBox)
from PySide6.QtGui import QColor
from PySide6.QtCore import QSettings
from core.parser import FoundryParser
from ui.worker import TranslationWorker
from ui.settings_tab import SettingsTab
from services.llm_service import LLMService
from ui.prompt_editor import PromptEditor

class FoundryGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FoundryL10n - Professional Translator")
        self.resize(1000, 750)
        self.segments = []
        
        # Internal Counters
        self.count_success = 0
        self.count_mismatch = 0
        self.count_cache = 0

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 1. Setup the Translate Tab
        self.init_translate_tab()
        
        # 2. Setup the Settings Tab
        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.settings_tab, "Settings")

        # 3. Setup the Prompt Editor Tab
        self.prompt_editor_tab = PromptEditor()
        self.tabs.addTab(self.prompt_editor_tab, "Prompt Editor")

        # 4. Load Persistence
        self.load_ui_state()
        self.settings_tab.load_settings()

    def init_translate_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # File selection
        top = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        btn_open = QPushButton("Open TSV File")
        btn_open.clicked.connect(self.open_file)
        top.addWidget(btn_open)
        top.addWidget(self.file_label, 1)
        layout.addLayout(top)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Key", "Source Text", "Translation"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Reasoning Log
        layout.addWidget(QLabel("AI Reasoning Log:"))
        self.thought_log = QTextEdit()
        self.thought_log.setReadOnly(True)
        self.thought_log.setMaximumHeight(120)
        self.thought_log.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: Consolas;")
        layout.addWidget(self.thought_log)

        # Progress and Controls
        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()
        
        self.cb_follow = QCheckBox("Follow Progress")
        self.cb_follow.setChecked(True)
        
        self.btn_run = QPushButton("Start Translation")
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.handle_run_clicked)
        
        self.btn_save = QPushButton("Save Manual Changes")
        self.btn_save.clicked.connect(self.manual_save)

        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.cb_follow)
        bottom.addWidget(self.btn_run)
        bottom.addWidget(self.btn_save)
        layout.addLayout(bottom)

        # Counter Bar
        counter_bar = QHBoxLayout()
        self.lbl_success = QLabel("Success: 0")
        self.lbl_mismatch = QLabel("Tag Errors: 0")
        self.lbl_cache = QLabel("Cache Hits: 0")
        
        self.lbl_success.setStyleSheet("color: #44ff44; font-weight: bold; margin-right: 15px;")
        self.lbl_mismatch.setStyleSheet("color: #ff4444; font-weight: bold; margin-right: 15px;")
        self.lbl_cache.setStyleSheet("color: #4444ff; font-weight: bold;")
        
        counter_bar.addWidget(self.lbl_success)
        counter_bar.addWidget(self.lbl_mismatch)
        counter_bar.addWidget(self.lbl_cache)
        counter_bar.addStretch()
        layout.addLayout(counter_bar)

        self.tabs.addTab(page, "Translate")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open TSV", "", "TSV Files (*.tsv)")
        if path:
            self.input_path = Path(path)
            self.file_label.setText(path)
            parser = FoundryParser()
            self.segments = parser.parse_tsv(self.input_path)
            
            self.table.setRowCount(len(self.segments))
            for i, seg in enumerate(self.segments):
                self.table.setItem(i, 0, QTableWidgetItem(seg.key))
                self.table.setItem(i, 1, QTableWidgetItem(seg.source_text))
                self.table.setItem(i, 2, QTableWidgetItem(seg.translation))
            
            self.btn_run.setEnabled(True)
            self.progress_bar.setMaximum(len(self.segments))

    def handle_run_clicked(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Stopping...")
        else:
            self.start_translation()

    def start_translation(self):
        # Reset counters for the UI
        self.count_success = 0
        self.count_mismatch = 0
        self.count_cache = 0
        self.lbl_success.setText("Success: 0")
        self.lbl_mismatch.setText("Tag Errors: 0")
        self.lbl_cache.setText("Cache Hits: 0")

        settings = self.settings_tab.get_settings()
        self.btn_run.setText("Stop Translation")
        self.btn_run.setStyleSheet("background-color: #ffaa00;")
        
        svc = LLMService(model_name=settings['model'])
        self.worker = TranslationWorker(
            segments=self.segments, 
            target_lang=settings['lang'], 
            llm_service=svc, 
            glossary_path=settings['glossary_path'],
            style_path=settings['style_path'],
            forbidden_path=settings['forbidden_path'],
            prompt_template=settings['prompt_template'],
            temp=settings['temp']
        )
        self.worker.progress_signal.connect(self.update_row)
        self.worker.finished_signal.connect(self.on_done)
        self.worker.start()

    def update_row(self, val: int):
        self.progress_bar.setValue(val)
        row_idx = val - 1
        seg = self.segments[row_idx]
        
        target_item = self.table.item(row_idx, 2)
        if not target_item:
            target_item = QTableWidgetItem()
            self.table.setItem(row_idx, 2, target_item)
        
        target_item.setText(seg.translation)
        
        if "CRITICAL" in seg.thought or "TAG MISMATCH" in seg.thought:
            self.count_mismatch += 1
            self.lbl_mismatch.setText(f"Tag Errors: {self.count_mismatch}")
            target_item.setBackground(QColor("#662222")) 
            target_item.setForeground(QColor("#ffffff"))
        elif "Restored" in seg.thought:
            self.count_cache += 1
            self.lbl_cache.setText(f"Cache Hits: {self.count_cache}")
            target_item.setBackground(QColor("#547CF4"))
            target_item.setForeground(QColor("#ffffff"))
        else:
            self.count_success += 1
            self.lbl_success.setText(f"Success: {self.count_success}")
            target_item.setBackground(QColor("#224422"))
            target_item.setForeground(QColor("#ffffff"))

        if self.cb_follow.isChecked():
            item_to_scroll = self.table.item(row_idx, 0)
            if item_to_scroll is not None:
                self.table.scrollToItem(item_to_scroll)
        
        if seg.thought:
            self.thought_log.append(f"<b>[{seg.key}]</b>: {seg.thought}")

    def load_ui_state(self):
        """Fixed: Type-safe loading of UI state."""
        settings = QSettings("FoundryL10n", "TranslatorApp")
        try:
            # We explicitly cast to str, then to int
            raw_val = settings.value("current_tab", 0)
            tab_index = int(str(raw_val))
        except (ValueError, TypeError):
            tab_index = 0

        if tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(tab_index)

    def save_ui_state(self):
        settings = QSettings("FoundryL10n", "TranslatorApp")
        settings.setValue("current_tab", self.tabs.currentIndex())

    def manual_save(self):
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 2)
            if item is not None:
                self.segments[i].translation = item.text()
        
        parser = FoundryParser()
        settings = self.settings_tab.get_settings()
        out = Path("out") / settings['lang'] / self.input_path.name
        
        try:
            parser.save_tsv(self.segments, out)
            QMessageBox.information(self, "Saved", f"Changes saved to {out}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save: {e}")

    def on_done(self, result):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Start Translation")
        self.btn_run.setStyleSheet("")
        
        self.save_ui_state()
        self.settings_tab.save_settings()

        parser = FoundryParser()
        settings = self.settings_tab.get_settings()
        out = Path("out") / settings['lang'] / self.input_path.name
        
        try:
            parser.save_tsv(result, out)
            self.file_label.setText(f"Finished! Saved to {out}")
        except Exception as e:
            self.file_label.setText(f"Save Error: {e}")
        
    def closeEvent(self, event):
        self.save_ui_state()
        self.settings_tab.save_settings()
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()

def run_gui():
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = FoundryGUI()
    window.show()
    sys.exit(app.exec())