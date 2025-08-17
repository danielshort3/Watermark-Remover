from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QGridLayout,
    QRadioButton,
    QButtonGroup,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

try:
    from PyQt5.QtPdf import QPdfDocument
except Exception:  # pragma: no cover - PyQt5 may not be available
    QPdfDocument = None
import os


class PdfSelectionDialog(QDialog):
    """Dialog showing previews of PDFs allowing the user to choose one."""

    def __init__(self, pdf_paths, labels, parent=None):
        super().__init__(parent)
        self.pdf_paths = pdf_paths
        self.labels = labels
        self.setWindowTitle("Select Version")

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        container = QWidget()
        grid = QGridLayout(container)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        for row, (pdf, label_text) in enumerate(zip(pdf_paths, labels)):
            page_widget = QWidget()
            pages_layout = QHBoxLayout(page_widget)
            if QPdfDocument is not None:
                doc = QPdfDocument()
                if doc.load(pdf) == QPdfDocument.NoError:
                    for page in range(min(5, doc.pageCount())):
                        image = doc.render(page)
                        if image is not None:
                            pix = QPixmap.fromImage(image)
                            lbl = QLabel()
                            lbl.setPixmap(
                                pix.scaledToHeight(200, Qt.SmoothTransformation)
                            )
                            pages_layout.addWidget(lbl)
            label = QLabel(os.path.basename(pdf))
            pages_layout.addWidget(label)
            grid.addWidget(page_widget, row, 0)

            radio = QRadioButton()
            radio.setToolTip(label_text)
            grid.addWidget(radio, row, 1, alignment=Qt.AlignTop)
            self.button_group.addButton(radio, row)

        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def selected_path(self):
        idx = self.button_group.checkedId()
        if idx < 0:
            return None
        return self.pdf_paths[idx]
