from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem,
    QDialogButtonBox
)


class SuggestionDialog(QDialog):
    """Allow user to choose from alternative key/instrument suggestions."""

    def __init__(self, current_instrument, available_keys, suggestions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Alternative")
        self._selected = None

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for key in available_keys:
            item = QListWidgetItem(f"{current_instrument} in {key}")
            item.setData(0x0100, (current_instrument, key))  # Qt.UserRole
            self.list_widget.addItem(item)

        for s in suggestions.get("direct", []) + suggestions.get("closest", []):
            label = f"{s['instrument']} in {s['key']}"
            if s.get('interval') and s.get('interval_direction') != 'none':
                label += f" ({s['interval']} {s['interval_direction']})"
            elif s.get('interval'):
                label += f" ({s['interval']})"
            item = QListWidgetItem(label)
            item.setData(0x0100, (s['instrument'], s['key']))
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(0x0100)
