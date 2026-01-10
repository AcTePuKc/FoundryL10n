from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                               QPushButton, QLabel, QHeaderView)


class IntegrityTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Project Consistency Audit</b>"))
        layout.addWidget(
            QLabel("The following terms have inconsistent translations in the database:"))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Source", "Detected Variants", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.btn_refresh = QPushButton("🔄 Scan Database for Conflicts")
        self.btn_refresh.setMinimumHeight(40)
        layout.addWidget(self.btn_refresh)

    def show_all_memory(self, project_records):
        """Displays every single translation stored for this project."""
        self.table.setRowCount(len(project_records))
        self.table.setHorizontalHeaderLabels(
            ["Source", "Current Translation", "Status"])
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
            btn_resolve = QPushButton("Normalize...")
            # We'll connect this in the main window
            self.table.setCellWidget(i, 2, btn_resolve)
