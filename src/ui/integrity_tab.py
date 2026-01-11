from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                               QPushButton, QLabel, QHeaderView, QHBoxLayout)
from core.i18n import I18N


class IntegrityTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        self.btn_auto_normalize = QPushButton(
            I18N.t("btn_auto_normalize_all")
        )
        self.btn_auto_normalize.setToolTip(
            I18N.t("tip_auto_normalize_all")
        )
        self.btn_auto_normalize.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        
        self.title_label = QLabel(I18N.t("ui_project_consistency_title"))
        self.subtitle_label = QLabel(I18N.t("ui_project_consistency_subtitle"))
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        
        top_layout.addWidget(self.btn_auto_normalize)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [
                I18N.t("header_source"),
                I18N.t("header_detected_variants"),
                I18N.t("header_action"),
            ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.btn_refresh = QPushButton(I18N.t("btn_scan_conflicts"))
        self.btn_refresh.setMinimumHeight(40)
        layout.addWidget(self.btn_refresh)

    def show_all_memory(self, project_records):
        """Displays every single translation stored for this project."""
        self.table.setRowCount(len(project_records))
        self.table.setHorizontalHeaderLabels(
            [
                I18N.t("header_source"),
                I18N.t("header_current_translation"),
                I18N.t("header_status"),
            ])
        for i, r in enumerate(project_records):
            self.table.setItem(i, 0, QTableWidgetItem(r.source_text))
            self.table.setItem(i, 1, QTableWidgetItem(r.translation))
            status = "🟢" if r.is_verified else "🟡"
            self.table.setItem(i, 2, QTableWidgetItem(status))

    def populate_report(self, report_data):
        self.table.setRowCount(len(report_data))
        for i, entry in enumerate(report_data):
            # Column 0: Source
            self.table.setItem(i, 0, QTableWidgetItem(entry['source']))

            # Column 1: Variants
            variant_str = " | ".join(
                [f"'{k}' ({v}x)" for k, v in entry['variants'].items()])
            self.table.setItem(i, 1, QTableWidgetItem(variant_str))

            # Column 2: Resolve Button
            btn_resolve = QPushButton(I18N.t("btn_normalize"))
            # We'll connect this in the main window
            self.table.setCellWidget(i, 2, btn_resolve)

    def retranslate_ui(self):
        self.btn_auto_normalize.setText(I18N.t("btn_auto_normalize_all"))
        self.btn_auto_normalize.setToolTip(I18N.t("tip_auto_normalize_all"))
        self.title_label.setText(I18N.t("ui_project_consistency_title"))
        self.subtitle_label.setText(I18N.t("ui_project_consistency_subtitle"))
        self.btn_refresh.setText(I18N.t("btn_scan_conflicts"))
        self.table.setHorizontalHeaderLabels(
            [
                I18N.t("header_source"),
                I18N.t("header_detected_variants"),
                I18N.t("header_action"),
            ]
        )
        for row in range(self.table.rowCount()):
            btn = self.table.cellWidget(row, 2)
            if isinstance(btn, QPushButton):
                btn.setText(I18N.t("btn_normalize"))
