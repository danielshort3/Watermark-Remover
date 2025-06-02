from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
)


class BatchGridDialog(QDialog):
    """Dialog for entering batch song information using a grid."""

    def __init__(self, instruments, keys, parent=None):
        super().__init__(parent)
        self.instruments = instruments
        self.keys = keys
        self.setWindowTitle("Batch Song List")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Title", "Instrument", "Key"])

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        remove_btn = QPushButton("Remove Row")
        add_btn.clicked.connect(self.add_row)
        remove_btn.clicked.connect(self.remove_row)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        self.add_row()

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        title_edit = QLineEdit()
        instrument_combo = QComboBox()
        instrument_combo.addItems(self.instruments)
        key_combo = QComboBox()
        key_combo.addItems(self.keys)
        self.table.setCellWidget(row, 0, title_edit)
        self.table.setCellWidget(row, 1, instrument_combo)
        self.table.setCellWidget(row, 2, key_combo)

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_entries(self):
        entries = []
        for row in range(self.table.rowCount()):
            title_widget = self.table.cellWidget(row, 0)
            instrument_widget = self.table.cellWidget(row, 1)
            key_widget = self.table.cellWidget(row, 2)
            title = title_widget.text().strip() if title_widget else ""
            instrument = instrument_widget.currentText() if instrument_widget else ""
            key = key_widget.currentText() if key_widget else ""
            if title:
                entries.append((title, instrument, key))
        return entries
