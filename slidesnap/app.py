from __future__ import annotations

import copy
import os
import sys
import traceback
import uuid
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .detection import Analyzer, Control
from .exporting import export_project
from .project import Project, Settings, library_path, recent_projects, timestamp
from .video import probe, read_at
from .widgets import DropCard, ImageView, ZoomView
from .watch import WatchPage


STYLE = """
QWidget { background: #0c1220; color: #e9eff9; font-family: Poppins; font-size: 12px; }
QMainWindow, QDialog { background: #0c1220; }
QLabel { background: transparent; }
QLabel#eyebrow { color: #6ce3c2; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#muted { color: #8e9eb7; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; }
QFrame#sidebar { background: #101827; border-right: 1px solid #253045; }
QFrame#card, QWidget#dropCard { background: #141e30; border: 1px solid #27334a; border-radius: 14px; }
QWidget#dropCard { border: 1px dashed #41536b; }
QPushButton { background: #1c2a40; border: 1px solid #30415a; border-radius: 8px; padding: 9px 14px; font-weight: 500; }
QPushButton:hover { background: #273c55; border-color: #597087; }
QPushButton:pressed { background: #344b64; }
QPushButton:disabled { color: #5e6d83; background: #162031; border-color: #263144; }
QPushButton#primary { background: #72e4c5; color: #0c2925; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #9af0d8; }
QPushButton#primary:disabled { background: #284a47; color: #799990; }
QPushButton#nav { text-align: left; background: transparent; border: none; padding: 13px 15px; color: #9bacc5; }
QPushButton#nav:checked { background: #223c3e; color: #8df0d3; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #0e1727; border: 1px solid #34435a; border-radius: 6px; padding: 7px; min-height: 19px; }
QComboBox QAbstractItemView { background: #162238; selection-background-color: #2d4b5a; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #52617b; border-radius: 4px; background: #121c2e; }
QCheckBox::indicator:checked { background: #72e4c5; border: 3px solid #24493f; }
QListWidget { background: #101929; border: 1px solid #29364b; border-radius: 10px; padding: 7px; outline: 0; }
QListWidget::item { padding: 9px; margin: 3px; border-radius: 7px; color: #cad6e9; }
QListWidget::item:selected { background: #263f4c; color: #b1ffe5; }
QListWidget::item:hover { background: #1d2e43; }
QProgressBar { background: #1b2b3e; border: 0; border-radius: 5px; min-height: 9px; max-height: 9px; color: transparent; }
QProgressBar::chunk { background: #72e4c5; border-radius: 5px; }
QSlider::groove:horizontal { background: #27364e; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: #72e4c5; width: 13px; margin: -5px 0; border-radius: 6px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #111c2d; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #40516b; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #223149; width: 2px; }
QToolTip { background: #263c50; color: white; padding: 6px; border: 1px solid #536b80; }
"""


def label(text, style=None):
    w = QLabel(text)
    if style:
        w.setObjectName(style)
    w.setWordWrap(True)
    return w


def image_pixmap(image):
    rgb = image.convert("RGB")
    # Own the pixel storage explicitly; avoid optional Pillow/Qt autodetection
    # and temporary-buffer lifetimes in frozen Windows applications.
    qimage = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width*3, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimage)


def button(text, callback, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName("primary")
    b.clicked.connect(callback)
    return b


def card():
    w = QFrame()
    w.setObjectName("card")
    layout = QVBoxLayout(w)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(13)
    return w, layout


class Job(QThread):
    message = Signal(str, object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            result = self.fn(lambda kind, data: self.message.emit(kind, data))
            self.message.emit("result", result)
        except Exception as exc:
            self.failed.emit(str(exc))


class FramePicker(QDialog):
    def __init__(self, source, seconds, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose an original video frame")
        self.resize(980, 680)
        self.source = source
        self.result_image = None
        self.actual = seconds
        self.metadata = probe(source)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Choose the frame with all your notes", "cardTitle"))
        layout.addWidget(label("Scrub to a solution or step through individual source frames. The saved image keeps the original content.", "muted"))
        self.preview = ImageView()
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.position = QDoubleSpinBox()
        self.position.setDecimals(3)
        self.position.setSuffix(" s")
        self.position.setRange(0, max(0, self.metadata["duration"]-.001))
        self.position.setValue(seconds)
        row.addWidget(button("Previous frame", lambda: self.step(-1)))
        row.addWidget(self.position)
        row.addWidget(button("Next frame", lambda: self.step(1)))
        row.addStretch()
        self.info = label("", "muted")
        row.addWidget(self.info)
        layout.addLayout(row)
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, round(self.metadata["duration"]*1000))
        self.scrub.setValue(round(seconds*1000))
        self.scrub.sliderReleased.connect(lambda: self.position.setValue(self.scrub.value()/1000))
        layout.addWidget(self.scrub)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Cancel", self.reject))
        actions.addWidget(button("Use this frame", self.accept, True))
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        self.position.valueChanged.connect(lambda: self.timer.start(120))
        self.refresh()

    def step(self, direction):
        # Use source PTS in a small neighborhood, including variable frame rates.
        from .video import decode_interval
        t = self.actual
        frames = [pts for _, pts in decode_interval(self.source, max(0, t-2), t+2)]
        candidates = [pts for pts in frames if pts < t-1e-5] if direction < 0 else [pts for pts in frames if pts > t+1e-5]
        if candidates:
            self.position.setValue(candidates[-1 if direction < 0 else 0] + 0.0001)

    def refresh(self):
        try:
            self.result_image, self.actual = read_at(self.source, self.position.value()+.0001)
            self.preview.set_image(image_pixmap(self.result_image))
            self.scrub.setValue(round(self.actual*1000))
            self.info.setText(timestamp(self.actual))
        except Exception as exc:
            self.info.setText(str(exc))

    def accept(self):
        self.timer.stop()
        self.refresh()
        if self.result_image is not None:
            super().accept()


class Presentation(QDialog):
    def __init__(self, project, start, parent=None):
        super().__init__(parent)
        self.project = project
        self.records = project.selected()
        self.index = min(max(0, start), len(self.records)-1)
        layout = QVBoxLayout(self)
        self.view = ZoomView()
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(button("Previous", lambda: self.move(-1)))
        self.caption = label("")
        row.addWidget(self.caption, 1)
        row.addWidget(button("Next", lambda: self.move(1)))
        row.addWidget(button("Exit presentation  Esc", self.close))
        layout.addLayout(row)
        self.refresh()

    def move(self, delta):
        self.index = min(max(0, self.index+delta), len(self.records)-1)
        self.refresh()

    def refresh(self):
        if self.records:
            r = self.records[self.index]
            self.view.set_image(self.project.image_path(r))
            self.caption.setText(f"{self.index+1} / {len(self.records)}    {timestamp(r['time'])}    {r['role']}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_PageDown):
            self.move(1)
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            self.move(-1)
        else:
            super().keyPressEvent(event)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SlideSnap - Video to study notes")
        self.resize(1380, 900)
        self.setMinimumSize(1120, 740)
        self.project = None
        self.source = None
        self.metadata = None
        self.worker = None
        self.control = None
        self.jobs = []
        self.busy = False
        self.last_export = None
        self.last_progress = None
        self.build()
        self.refresh_library()
        self.switch(0)

    def build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(208)
        nav = QVBoxLayout(self.sidebar)
        nav.setContentsMargins(20, 28, 20, 24)
        nav.setSpacing(9)
        nav.addWidget(label("SlideSnap", "cardTitle"))
        nav.addWidget(label("VIDEO TO STUDY NOTES", "eyebrow"))
        nav.addSpacing(33)
        self.nav_buttons = []
        for i, title in [(0, "01   Projects"), (1, "02   Auto capture"), (4, "03   Watch / capture"), (2, "04   Review notes"), (3, "05   Export")]:
            b = button(title, lambda checked=False, n=i: self.switch(n))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setProperty("page", i)
            nav.addWidget(b)
            self.nav_buttons.append(b)
        nav.addStretch()
        nav.addWidget(label("Keep the whole solution.", "cardTitle"))
        nav.addWidget(label("Handwritten notes, worked steps and answer highlights stay in your captures.", "muted"))
        nav.addSpacing(14)
        nav.addWidget(label("LOCAL PROCESSING  •  OFFLINE", "eyebrow"))
        root.addWidget(self.sidebar)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(30, 26, 30, 20)
        main.setSpacing(15)
        self.eyebrow = label("YOUR STUDY LIBRARY", "eyebrow")
        self.title = label("Pick up where you left off", "title")
        self.subtitle = label("Turn a lecture into notes you can actually revisit.", "muted")
        main.addWidget(self.eyebrow)
        main.addWidget(self.title)
        main.addWidget(self.subtitle)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_library())
        self.pages.addWidget(self.build_import())
        self.pages.addWidget(self.build_review())
        self.pages.addWidget(self.build_export())
        self.pages.addWidget(self.build_watch())
        main.addWidget(self.pages, 1)
        self.status = label("Ready. Your videos and notes stay on this computer.", "muted")
        main.addWidget(self.status)
        root.addWidget(content, 1)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.browse_video)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_project)

    def build_library(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        hero, box = card()
        box.addWidget(label("A video becomes your study deck", "cardTitle"))
        box.addWidget(label("Capture questions, answers, instructor notes and solutions. Read everything here, then export when you need it.", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("+  Import a video", lambda: self.switch(1), True))
        row.addWidget(button("Open saved project", self.open_project))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(hero)
        row = QHBoxLayout()
        row.addWidget(label("Saved projects", "cardTitle"))
        row.addStretch()
        row.addWidget(button("Refresh", self.refresh_library))
        layout.addLayout(row)
        self.library = QListWidget()
        self.library.setIconSize(QSize(150, 85))
        self.library.itemDoubleClicked.connect(self.open_recent)
        layout.addWidget(self.library, 1)
        layout.addWidget(label("Projects save automatically. Double-click one to read its screenshots or PDF without reprocessing.", "muted"))
        return page

    def build_import(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        left = QVBoxLayout()
        drop = DropCard()
        dl = QHBoxLayout(drop)
        dl.setContentsMargins(18, 16, 18, 16)
        dl.addWidget(label("Drop a lecture here\nMP4 · MKV · MOV · AVI · WEBM", "muted"), 1)
        self.browse_btn = button("Browse video", self.browse_video, True)
        dl.addWidget(self.browse_btn)
        drop.fileDropped.connect(self.load_video)
        left.addWidget(drop)
        self.file_info = label("No video selected", "muted")
        left.addWidget(self.file_info)
        self.preview = ImageView(editable=True)
        left.addWidget(self.preview, 1)
        self.preview_scrub = QSlider(Qt.Orientation.Horizontal)
        self.preview_scrub.setRange(0, 0)
        self.preview_scrub.sliderReleased.connect(self.scrub_preview)
        left.addWidget(self.preview_scrub)
        row = QHBoxLayout()
        self.region_mode = QComboBox()
        self.region_mode.addItems(["Preview only", "Draw slide area", "Draw ignore region"])
        self.region_mode.currentIndexChanged.connect(lambda i: setattr(self.preview, "mode", ["view", "roi", "mask"][i]))
        row.addWidget(self.region_mode, 1)
        row.addWidget(button("Reset regions", self.reset_regions))
        left.addLayout(row)
        left.addWidget(label("Green = detection area. Coral = ignored motion. Notes inside the exported image are always preserved.", "muted"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        left.addWidget(self.progress)
        self.progress_text = label("Ready to scan", "muted")
        left.addWidget(self.progress_text)
        actions = QHBoxLayout()
        self.start_btn = button("Start capturing", self.start, True)
        self.pause_btn = button("Pause", self.pause)
        self.cancel_btn = button("Cancel", self.cancel)
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        actions.addWidget(self.start_btn, 1)
        actions.addWidget(self.pause_btn)
        actions.addWidget(self.cancel_btn)
        left.addLayout(actions)
        layout.addLayout(left, 1)
        self.settings_card, right = card()
        self.settings_card.setFixedWidth(305)
        right.addWidget(label("Capture settings", "cardTitle"))
        right.addWidget(label("Choose what matters", "muted"))
        self.detect_combo = QComboBox()
        self.detect_combo.addItems(["Reveals, notes & slide changes", "Slides only · final annotated state"])
        right.addWidget(self.detect_combo)
        self.detect_combo.currentIndexChanged.connect(self.detection_changed)
        self.capture_combo = QComboBox()
        self.capture_combo.addItems(["Before & after", "Before only", "After only"])
        right.addWidget(label("Save on each change", "muted"))
        right.addWidget(self.capture_combo)
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["Every source frame · most thorough", "Fast · 0.5 FPS", "Balanced · 1 FPS", "Accurate · 5 FPS", "Custom FPS"])
        right.addWidget(label("Comparison rate", "muted"))
        right.addWidget(self.rate_combo)
        self.fps_input = QDoubleSpinBox()
        self.fps_input.setRange(.1, 120)
        self.fps_input.setValue(2)
        self.fps_input.setSuffix(" FPS")
        self.fps_input.setVisible(False)
        self.rate_combo.currentIndexChanged.connect(lambda i: self.fps_input.setVisible(i == 4))
        right.addWidget(self.fps_input)
        form = QFormLayout()
        self.group_input = QSpinBox()
        self.group_input.setRange(1, 60)
        self.group_input.setValue(5)
        self.group_input.setSuffix(" frames")
        self.group_input.setToolTip("Confirm a persistent changed state over this many original frames. Windows overlap; no frame is skipped inside a checked group.")
        form.addRow("Confirm group", self.group_input)
        self.gap_input = QDoubleSpinBox()
        self.gap_input.setRange(0, 60)
        self.gap_input.setValue(.25)
        self.gap_input.setSingleStep(.25)
        self.gap_input.setSuffix(" s")
        form.addRow("Minimum interval", self.gap_input)
        right.addLayout(form)
        self.sensitivity_label = label("Sensitivity   50 / 100", "muted")
        right.addWidget(self.sensitivity_label)
        self.sensitivity = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity.setRange(0, 100)
        self.sensitivity.setValue(50)
        self.sensitivity.valueChanged.connect(lambda v: self.sensitivity_label.setText(f"Sensitivity   {v} / 100"))
        right.addWidget(self.sensitivity)
        self.refine_check = QCheckBox("Precise transition refinement")
        self.refine_check.setChecked(True)
        right.addWidget(self.refine_check)
        self.crop_check = QCheckBox("Export only the slide area")
        right.addWidget(self.crop_check)
        self.auto_check = QCheckBox("Auto-export with Export settings")
        right.addWidget(self.auto_check)
        right.addWidget(label("Every-frame scanning catches brief changes. Lower FPS reduces comparisons but may miss short slides. Video decoding still takes time.", "muted"))
        right.addStretch()
        right.addWidget(label("NOTES STAY IN THE PICTURE", "eyebrow"))
        right.addWidget(label("Screenshots come directly from the video. Handwriting and solutions are never reconstructed or erased.", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.settings_card)
        scroll.setFixedWidth(321)
        layout.addWidget(scroll)
        return page

    def build_review(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.reader_mode = QComboBox()
        self.reader_mode.addItems(["Screenshots / study deck", "Saved PDF"])
        self.reader_mode.currentIndexChanged.connect(self.change_reader)
        toolbar.addWidget(self.reader_mode)
        toolbar.addWidget(button("−", lambda: self.zoom(.8)))
        toolbar.addWidget(button("+", lambda: self.zoom(1.25)))
        toolbar.addWidget(button("Fit page", self.fit_view))
        toolbar.addStretch()
        self.presentation_btn = button("Present fullscreen", self.present)
        toolbar.addWidget(button("Watch source video", self.watch_project))
        toolbar.addWidget(self.presentation_btn)
        layout.addLayout(toolbar)
        split = QSplitter()
        self.gallery = QListWidget()
        self.gallery.setIconSize(QSize(128, 75))
        self.gallery.setMinimumWidth(250)
        self.gallery.currentRowChanged.connect(self.show_capture)
        self.gallery.itemChanged.connect(self.check_changed)
        self.gallery.verticalScrollBar().valueChanged.connect(lambda: self.render_pdf_thumbnails())
        split.addWidget(self.gallery)
        self.viewer = QStackedWidget()
        self.image_reader = ZoomView()
        self.viewer.addWidget(self.image_reader)
        self.pdf_doc = QPdfDocument(self)
        self.pdf_reader = QPdfView()
        self.pdf_reader.setDocument(self.pdf_doc)
        self.pdf_reader.setPageMode(QPdfView.PageMode.SinglePage)
        self.pdf_reader.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.pdf_reader.pageNavigator().currentPageChanged.connect(self.pdf_page_changed)
        self.viewer.addWidget(self.pdf_reader)
        split.addWidget(self.viewer)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([270, 750])
        layout.addWidget(split, 1)
        row = QHBoxLayout()
        row.addWidget(button("Previous", lambda: self.navigate(-1)))
        self.page_spin = QSpinBox()
        self.page_spin.setPrefix("Page ")
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(self.go_page)
        row.addWidget(self.page_spin)
        self.page_count = label("/ 0", "muted")
        row.addWidget(self.page_count)
        row.addWidget(button("Next", lambda: self.navigate(1)))
        row.addStretch()
        self.capture_info = label("Select a project to read your captures.", "muted")
        row.addWidget(self.capture_info)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.edit_buttons = [button("Add a frame", self.add_frame), button("Replace with nearby frame", self.replace_frame),
                             button("Move up", lambda: self.move_capture(-1)), button("Move down", lambda: self.move_capture(1))]
        for b in self.edit_buttons:
            row.addWidget(b)
        row.addStretch()
        row.addWidget(button("Export notes", lambda: self.switch(3), True))
        layout.addLayout(row)
        layout.addWidget(label("Uncheck pages to exclude them from export. Reorder with Move up/down. Edits save automatically.", "muted"))
        return page

    def build_export(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, form_box = card()
        form_box.addWidget(label("Your notes, ready to keep", "cardTitle"))
        self.export_info = label("Open or capture a project first.", "muted")
        form_box.addWidget(self.export_info)
        form = QFormLayout()
        form.setSpacing(15)
        self.export_name = QLineEdit("Study notes")
        form.addRow("Document name", self.export_name)
        self.export_folder = QLineEdit(str(library_path() / "Exports"))
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.export_folder, 1)
        folder_row.addWidget(button("Browse", self.browse_output))
        form.addRow("Save location", folder_row)
        self.export_kind = QComboBox()
        self.export_kind.addItems(["PDF + Images", "PDF only", "Images only"])
        form.addRow("Export format", self.export_kind)
        self.image_format = QComboBox()
        self.image_format.addItems(["PNG", "JPEG"])
        form.addRow("Image format", self.image_format)
        self.paper = QComboBox()
        self.paper.addItems(["Original aspect ratio", "A4 landscape", "A4 portrait", "Letter landscape", "Letter portrait"])
        form.addRow("PDF page size", self.paper)
        self.quality = QComboBox()
        self.quality.addItems(["Maximum", "Balanced", "Small file"])
        form.addRow("Image quality", self.quality)
        self.captions = QCheckBox("Add timestamps below screenshots")
        form.addRow("PDF captions", self.captions)
        form_box.addLayout(form)
        form_box.addWidget(label("One screenshot per PDF page. Original aspect ratio and maximum quality keep small writing readable. New exports go into their own folder.", "muted"))
        row = QHBoxLayout()
        self.export_btn = button("Save PDF + Images", self.export, True)
        self.export_btn.setEnabled(False)
        self.export_kind.currentIndexChanged.connect(lambda i: self.export_btn.setText(["Save PDF + Images", "Save PDF", "Save Images"][i]))
        row.addWidget(self.export_btn)
        self.open_pdf_btn = button("Read saved PDF here", self.read_saved_pdf)
        self.open_pdf_btn.setEnabled(False)
        row.addWidget(self.open_pdf_btn)
        self.open_folder_btn = button("Open output folder", self.open_output)
        self.open_folder_btn.setEnabled(False)
        row.addWidget(self.open_folder_btn)
        row.addStretch()
        form_box.addLayout(row)
        self.export_progress = QProgressBar()
        form_box.addWidget(self.export_progress)
        self.export_result = label("", "muted")
        form_box.addWidget(self.export_result)
        layout.addWidget(panel)
        layout.addStretch()
        return page

    def switch(self, index):
        if index != 4 and hasattr(self, "watch"):
            self.watch.player.pause()
        self.pages.setCurrentIndex(index)
        titles = [("YOUR STUDY LIBRARY", "Pick up where you left off", "Your saved screenshots and PDFs, together in one place."),
                  ("01 / CAPTURE", "Capture every useful change", "Save the question, the answer, and every step of the solution."),
                  ("02 / REVIEW", "Your lecture, page by page", "Read, compare and refine your notes without leaving SlideSnap."),
                  ("03 / EXPORT", "Take your notes with you", "Save a PDF, individual images, or both."),
                  ("WATCH / MANUAL CAPTURE", "Watch it. Pause it. Keep it.", "Capture the exact question, handwritten note or worked solution you want.")]
        a, b, c = titles[index]
        self.eyebrow.setText(a)
        self.title.setText(b)
        self.subtitle.setText(c)
        for btn in self.nav_buttons:
            btn.setChecked(btn.property("page") == index)
        if index == 0:
            self.refresh_library()
        if index == 3:
            self.update_export_info()

    def refresh_library(self):
        self.library.clear()
        self.recents = recent_projects()
        for p in self.recents:
            n = len(p.selected())
            item = QListWidgetItem(f"{p.data['name']}\n{n} pages   ·   {p.data['status'].capitalize()}   ·   {p.data['created'][:10]}")
            if p.data["captures"]:
                thumb = QPixmap(str(p.image_path(p.data["captures"][-1]))).scaled(150, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                item.setIcon(QIcon(thumb))
            item.setSizeHint(QSize(400, 110))
            self.library.addItem(item)
        if not self.recents:
            item = QListWidgetItem("No projects yet. Import a lecture to create your first study deck.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.library.addItem(item)

    def open_recent(self, item):
        index = self.library.row(item)
        if index < len(self.recents):
            self.load_project(self.recents[index])

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SlideSnap project", str(library_path()), "SlideSnap project (project.json)")
        if path:
            try:
                self.load_project(Project.load(path))
            except Exception as exc:
                self.error(str(exc))

    def load_project(self, project):
        if self.busy:
            self.status.setText("Wait for the current capture or export to finish before switching projects.")
            return
        self.project = project
        self.last_export = next((e for e in reversed(project.data.get("exports", [])) if e.get("pdf") and Path(e["pdf"]).exists()), None)
        self.export_name.setText(project.data["name"])
        self.reader_mode.setCurrentIndex(0)
        self.refresh_gallery()
        self.open_pdf_btn.setEnabled(bool(self.last_export))
        self.open_folder_btn.setEnabled(bool(self.last_export))
        self.reader_mode.setCurrentIndex(0)
        self.update_export_info()
        self.switch(2)
        self.status.setText(f"Opened {project.data['name']}. Captures are saved locally.")
        self.watch.refresh_captures(project)

    def save_project(self):
        if self.project and not self.busy:
            self.project.save()
            self.status.setText("Project saved. Ctrl+S")

    def browse_video(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose lecture video", "", "Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All files (*)")
        if path:
            self.load_video(path)

    def load_video(self, path):
        if self.busy:
            return
        try:
            metadata = probe(path)
            im, t = read_at(path, min(.2, metadata["duration"]/2))
            self.source, self.metadata = path, metadata
            self.preview.set_image(image_pixmap(im))
            self.reset_regions()
            self.preview_scrub.setRange(0, round(metadata["duration"]*1000))
            self.preview_scrub.setValue(round(t*1000))
            self.file_info.setText(f"{Path(path).name}\n{timestamp(metadata['duration'])}   ·   {metadata['width']} × {metadata['height']}   ·   {metadata['fps']:.2f} FPS   ·   {metadata['size']/1048576:.1f} MB")
            self.start_btn.setEnabled(True)
            self.progress.setValue(0)
            self.progress_text.setText("Ready. Select the slide area to ignore webcam motion.")
            self.watch.load(path, metadata["duration"])
            self.watch.refresh_captures(self.project)
            self.switch(1)
        except Exception as exc:
            self.error(f"Could not open this video.\n{exc}")

    def scrub_preview(self):
        if self.source and not self.busy:
            try:
                im, t = read_at(self.source, self.preview_scrub.value()/1000)
                self.preview.set_image(image_pixmap(im))
                self.status.setText(f"Preview at {timestamp(t)}")
            except Exception as exc:
                self.error(str(exc))

    def reset_regions(self):
        self.preview.roi = [0, 0, 1, 1]
        self.preview.masks = []
        self.preview.update()

    def detection_changed(self, index):
        self.capture_combo.setCurrentIndex(1 if index else 0)

    def settings(self):
        index = self.rate_combo.currentIndex()
        return Settings(fps=[0, .5, 1, 5, self.fps_input.value()][index],
                        group_size=self.group_input.value(), sensitivity=self.sensitivity.value(),
                        minimum_gap=self.gap_input.value(), refine=self.refine_check.isChecked(),
                        detection="slides" if self.detect_combo.currentIndex() else "changes",
                        capture=["both", "before", "after"][self.capture_combo.currentIndex()],
                        roi=list(self.preview.roi), masks=copy.deepcopy(self.preview.masks), crop_export=self.crop_check.isChecked())

    def set_busy(self, busy, analysis=False):
        self.busy = busy
        self.settings_card.setEnabled(not busy)
        self.browse_btn.setEnabled(not busy)
        self.preview_scrub.setEnabled(not busy)
        self.region_mode.setEnabled(not busy)
        self.preview.editable = not busy
        self.start_btn.setEnabled(not busy and bool(self.source))
        self.pause_btn.setEnabled(busy and analysis)
        self.cancel_btn.setEnabled(busy and analysis)
        self.export_btn.setEnabled(not busy and bool(self.project and self.project.selected()))
        self.gallery.setEnabled(not busy)
        for b in self.edit_buttons:
            b.setEnabled(not busy)
        self.watch.capturing = busy
        self.watch.capture_btn.setEnabled(not busy and bool(self.watch.source))
        self.watch.choose_btn.setEnabled(not busy)

    def run_job(self, job):
        self.worker = job
        self.jobs.append(job)
        job.finished.connect(lambda: self.jobs.remove(job) if job in self.jobs else None)
        job.start()

    def start(self):
        if self.busy or not self.source:
            return
        try:
            settings = self.settings()
            settings.validate()
            self.project = Project.create(self.source, settings)
            self.last_export = None
            self.reader_mode.setCurrentIndex(0)
            self.open_pdf_btn.setEnabled(False)
            self.open_folder_btn.setEnabled(False)
            self.export_name.setText(self.project.data["name"])
            self.refresh_gallery()
            self.control = Control()
            project, control = self.project, self.control
            job = Job(lambda notify: Analyzer(project, notify, control).run())
            job.message.connect(self.analysis_message)
            job.failed.connect(self.job_error)
            self.set_busy(True, True)
            self.pause_btn.setText("Pause")
            self.progress.setValue(0)
            self.status.setText("Scanning locally. Captures save as they are found; instructor notes stay intact.")
            self.run_job(job)
        except Exception as exc:
            self.error(str(exc))

    def analysis_message(self, kind, data):
        if kind == "capture":
            self.append_capture(data)
        elif kind == "progress":
            self.last_progress = data
            self.progress.setValue(round(min(1, data["time"]/max(.01, data["duration"]))*1000))
            self.progress_text.setText(f"{timestamp(data['time'])} / {timestamp(data['duration'])}   ·   {data['captures']} captures   ·   {data['events']} changes\n{data['frames']:,} frames compared   ·   {data['speed']:.1f}× video speed   ·   about {round(data['eta'])} s left")
        elif kind == "result":
            self.set_busy(False)
            self.refresh_gallery()
            self.refresh_library()
            self.update_export_info()
            status = self.project.data["status"]
            self.status.setText(f"{status.capitalize()}: {len(self.project.data['captures'])} captures saved. Review notes and solutions before exporting.")
            if status == "complete":
                self.progress.setValue(1000)
                self.progress_text.setText(f"Complete · {len(self.project.data['events'])} changes · {len(self.project.data['captures'])} captures")
                self.switch(2)
                if self.auto_check.isChecked():
                    self.export()

    def pause(self):
        if self.control and self.busy:
            if self.control.running.is_set():
                self.control.running.clear()
                self.pause_btn.setText("Resume")
                self.status.setText("Paused. Your completed captures are saved.")
            else:
                self.control.running.set()
                self.pause_btn.setText("Pause")
                self.status.setText("Resuming local analysis…")

    def cancel(self):
        if self.control and self.busy:
            self.control.cancel.set()
            self.control.running.set()
            self.cancel_btn.setEnabled(False)
            self.status.setText("Cancelling… completed captures will remain in your project.")

    def append_capture(self, record):
        if not self.project:
            return
        self.gallery.blockSignals(True)
        item = QListWidgetItem(f"{self.gallery.count()+1:03}  {record['role']}\n{timestamp(record['time'])}")
        item.setData(Qt.ItemDataRole.UserRole, record["id"])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if record.get("included", True) else Qt.CheckState.Unchecked)
        pix = QPixmap(str(self.project.image_path(record))).scaled(128, 75, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        item.setIcon(QIcon(pix))
        item.setSizeHint(QSize(220, 94))
        self.gallery.addItem(item)
        self.gallery.blockSignals(False)

    def refresh_gallery(self, selected=0):
        self.gallery.blockSignals(True)
        self.gallery.clear()
        self.gallery.blockSignals(False)
        if self.project:
            for record in self.project.data["captures"]:
                self.append_capture(record)
        self.gallery.setCurrentRow(min(selected, self.gallery.count()-1))
        self.page_spin.setMaximum(max(1, self.gallery.count()))
        self.page_count.setText(f"/ {self.gallery.count()}")
        self.update_export_info()

    def record(self):
        row = self.gallery.currentRow()
        if self.project and 0 <= row < len(self.project.data["captures"]):
            return self.project.data["captures"][row]
        return None

    def show_capture(self, row):
        if self.reader_mode.currentIndex() == 1:
            if row >= 0:
                self.page_spin.setValue(row+1)
            return
        if not self.project or row < 0 or row >= len(self.project.data["captures"]):
            self.image_reader.set_image(None)
            return
        r = self.project.data["captures"][row]
        self.image_reader.set_image(self.project.image_path(r))
        if self.reader_mode.currentIndex() == 0:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(row+1)
            self.page_spin.blockSignals(False)
            self.capture_info.setText(f"{r['role']}   ·   {timestamp(r['time'])}")

    def check_changed(self, item):
        if not self.project or self.busy or self.reader_mode.currentIndex() == 1:
            return
        ident = item.data(Qt.ItemDataRole.UserRole)
        r = next(r for r in self.project.data["captures"] if r["id"] == ident)
        r["included"] = item.checkState() == Qt.CheckState.Checked
        self.project.save()
        self.update_export_info()

    def navigate(self, delta):
        self.page_spin.setValue(self.page_spin.value()+delta)

    def go_page(self, number):
        if self.reader_mode.currentIndex() == 1:
            self.pdf_reader.pageNavigator().jump(number-1, self.pdf_reader.pageNavigator().currentLocation())
        else:
            self.gallery.setCurrentRow(number-1)

    def pdf_page_changed(self, index):
        if self.reader_mode.currentIndex() == 1:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(index+1)
            self.page_spin.blockSignals(False)
            self.gallery.setCurrentRow(index)

    def render_pdf_thumbnails(self):
        if self.reader_mode.currentIndex() != 1 or not self.pdf_doc.pageCount():
            return
        # Render visible pages on demand; a long document does not need all
        # full-resolution page images in memory before it can be read.
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            if item.icon().isNull() and self.gallery.visualItemRect(item).intersects(self.gallery.viewport().rect()):
                rendered = self.pdf_doc.render(i, QSize(128, 85))
                item.setIcon(QIcon(QPixmap.fromImage(rendered)))

    def change_reader(self, index):
        if index == 1:
            if not self.last_export or not self.last_export.get("pdf") or not Path(self.last_export["pdf"]).exists():
                self.reader_mode.setCurrentIndex(0)
                self.status.setText("Export a PDF first. Your screenshots are already readable here.")
                return
            self.pdf_doc.close()
            error = self.pdf_doc.load(self.last_export["pdf"])
            if error != QPdfDocument.Error.None_:
                self.reader_mode.setCurrentIndex(0)
                self.error("Could not open the saved PDF. Try exporting it again.")
                return
            self.viewer.setCurrentIndex(1)
            self.gallery.blockSignals(True)
            self.gallery.clear()
            for i in range(self.pdf_doc.pageCount()):
                item = QListWidgetItem(f"Page {i+1}")
                item.setSizeHint(QSize(220, 94))
                self.gallery.addItem(item)
            self.gallery.blockSignals(False)
            self.page_spin.setMaximum(max(1, self.pdf_doc.pageCount()))
            self.page_spin.setValue(1)
            self.gallery.setCurrentRow(0)
            self.page_count.setText(f"/ {self.pdf_doc.pageCount()}")
            self.capture_info.setText("Saved PDF · export again to include newer edits")
            QTimer.singleShot(0, self.render_pdf_thumbnails)
        else:
            self.viewer.setCurrentIndex(0)
            self.refresh_gallery()
            self.page_spin.setMaximum(max(1, self.gallery.count()))
            self.page_count.setText(f"/ {self.gallery.count()}")
            self.show_capture(self.gallery.currentRow())
        for b in self.edit_buttons:
            b.setEnabled(index == 0 and not self.busy)

    def zoom(self, factor):
        if self.reader_mode.currentIndex():
            self.pdf_reader.setZoomMode(QPdfView.ZoomMode.Custom)
            self.pdf_reader.setZoomFactor(max(.1, min(5, self.pdf_reader.zoomFactor()*factor)))
        else:
            self.image_reader.zoom_by(factor)

    def fit_view(self):
        if self.reader_mode.currentIndex():
            self.pdf_reader.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self.image_reader.fit()

    def present(self):
        if self.project and self.project.selected():
            dialog = Presentation(self.project, self.gallery.currentRow(), self)
            dialog.showFullScreen()
            dialog.exec()

    def locate_source(self):
        if not self.project:
            return None
        path = self.project.data["source"]
        if Path(path).exists():
            return path
        path, _ = QFileDialog.getOpenFileName(self, "Locate this project's original video", "", "Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)")
        if path:
            try:
                meta = probe(path)
                old = self.project.data.get("metadata", {})
                if abs(meta["duration"]-old.get("duration", meta["duration"])) > 1 or meta["width"] != old.get("width", meta["width"]):
                    self.error("This video does not match the saved project's duration and dimensions.")
                    return None
                self.project.data["source"] = path
                self.project.save()
                return path
            except Exception as exc:
                self.error(str(exc))
        return None

    def pick_frame(self, replace):
        if self.busy or not self.project:
            return
        record = self.record()
        if replace and not record:
            return
        source = self.locate_source()
        if not source:
            return
        try:
            dialog = FramePicker(source, record["time"] if record else 0, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            im = dialog.result_image
            settings = Settings(**self.project.data["settings"])
            if settings.crop_export:
                x, y, w, h = settings.roi
                im = im.crop((round(x*im.width), round(y*im.height), round((x+w)*im.width), round((y+h)*im.height)))
            row = self.gallery.currentRow()
            ident = uuid.uuid4().hex
            relative = f"captures/{ident}.png"
            im.save(self.project.folder / relative)
            new = {"id": ident, "path": relative, "time": dialog.actual,
                   "role": "Adjusted" if replace else "Manual", "event": record.get("event") if replace else None,
                   "included": True}
            if replace:
                self.project.data["captures"][row] = new
            else:
                # Add by source time; existing manually chosen order is otherwise retained.
                captures = self.project.data["captures"]
                row = next((i for i, r in enumerate(captures) if r["time"] > dialog.actual), len(captures))
                captures.insert(row, new)
            self.project.note(f"[{timestamp(dialog.actual)}] {new['role']} capture selected manually")
            self.project.save()
            self.refresh_gallery(row)
            self.status.setText("Original frame saved in your project, including visible notes and solutions.")
        except Exception as exc:
            self.error(str(exc))

    def add_frame(self):
        self.pick_frame(False)

    def replace_frame(self):
        self.pick_frame(True)

    def move_capture(self, delta):
        if not self.project or self.busy:
            return
        row = self.gallery.currentRow()
        target = row+delta
        captures = self.project.data["captures"]
        if row >= 0 and 0 <= target < len(captures):
            captures[row], captures[target] = captures[target], captures[row]
            self.project.save()
            self.refresh_gallery(target)

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose export folder", self.export_folder.text())
        if folder:
            self.export_folder.setText(folder)

    def update_export_info(self):
        count = len(self.project.selected()) if self.project else 0
        self.export_info.setText(f"{self.project.data['name']}   ·   {count} selected pages" if self.project else "Open or capture a project first.")
        self.export_btn.setEnabled(bool(count) and not self.busy)

    def export(self):
        if self.busy or not self.project or not self.project.selected():
            return
        if not self.export_folder.text().strip():
            self.error("Choose a save location first.")
            return
        project = Project(self.project.folder, copy.deepcopy(self.project.data))
        destination, name = self.export_folder.text(), self.export_name.text()
        options = dict(kind=["both", "pdf", "images"][self.export_kind.currentIndex()],
                       image_format=self.image_format.currentText(), paper=self.paper.currentText(),
                       quality=self.quality.currentText(), captions=self.captions.isChecked())
        job = Job(lambda notify: export_project(project, destination, name, **options,
                  progress=lambda n, total: notify("export_progress", (n, total))))
        job.message.connect(self.export_message)
        job.failed.connect(self.job_error)
        self.set_busy(True)
        self.export_progress.setValue(0)
        self.export_result.setText("Saving your notes…")
        self.switch(3)
        self.run_job(job)

    def export_message(self, kind, data):
        if kind == "export_progress":
            self.export_progress.setValue(round(data[0]/data[1]*100))
        elif kind == "result":
            self.last_export = data
            self.project.data["exports"].append(data)
            self.project.save()
            self.set_busy(False)
            self.export_result.setText(f"Saved {data['pages']} pages.\n{data['folder']}")
            self.open_pdf_btn.setEnabled(bool(data["pdf"]))
            self.open_folder_btn.setEnabled(True)
            self.status.setText("Export complete. You can read the PDF here without opening another app.")

    def read_saved_pdf(self):
        self.switch(2)
        if self.reader_mode.currentIndex() == 1:
            self.change_reader(1)
        else:
            self.reader_mode.setCurrentIndex(1)

    def open_output(self):
        if self.last_export:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_export["folder"]))

    def job_error(self, message):
        self.set_busy(False)
        if self.project:
            self.refresh_gallery()
        self.error(message)

    def build_watch(self):
        self.watch = WatchPage()
        self.watch.fileChosen.connect(self.load_watch)
        self.watch.captureRequested.connect(self.manual_capture)
        self.watch.reviewRequested.connect(lambda: self.switch(2))
        self.watch.message.connect(lambda text: self.status.setText(text))
        return self.watch

    def load_watch(self, path):
        if self.busy:
            return
        self.load_video(path)
        if self.source and str(Path(self.source).resolve()) == str(Path(path).resolve()):
            self.switch(4)

    def watch_project(self):
        if not self.project:
            self.switch(4)
            return
        source = self.locate_source()
        if source:
            record = self.record()
            if self.watch.source != str(Path(source).resolve()):
                meta = self.project.data.get("metadata") or probe(source)
                self.watch.load(source, meta["duration"])
            self.watch.refresh_captures(self.project)
            self.switch(4)
            if record:
                self.watch.seek(round(record["time"]*1000))

    def manual_capture(self, seconds):
        if self.busy or not self.watch.source:
            return
        try:
            source = self.watch.source
            if not self.project or str(Path(self.project.data["source"]).resolve()) != source:
                self.project = Project.create(source, self.settings())
                self.project.data["metadata"] = probe(source)
                self.project.data["status"] = "manual"
                self.project.save()
                self.export_name.setText(self.project.data["name"])
                self.last_export = None
                self.open_pdf_btn.setEnabled(False)
                self.open_folder_btn.setEnabled(False)
                self.reader_mode.setCurrentIndex(0)
            project = self.project
            if any(abs(r["time"]-seconds) < .0005 for r in project.data["captures"]):
                self.status.setText(f"The frame at {timestamp(seconds)} is already saved in this project.")
                return
            def save_frame(notify):
                image, actual = read_at(source, seconds+.000001)
                settings = Settings(**project.data["settings"])
                if settings.crop_export:
                    x, y, w, h = settings.roi
                    image = image.crop((round(x*image.width), round(y*image.height), round((x+w)*image.width), round((y+h)*image.height)))
                ident = uuid.uuid4().hex
                relative = f"captures/{ident}.png"
                image.save(project.folder / relative, "PNG")
                return {"id": ident, "path": relative, "time": actual, "role": "Manual", "event": None, "included": True}
            job = Job(save_frame)
            job.message.connect(self.manual_message)
            job.failed.connect(self.job_error)
            self.set_busy(True)
            self.status.setText(f"Saving the original frame at {timestamp(seconds)}…")
            self.run_job(job)
        except Exception as exc:
            self.error(str(exc))

    def manual_message(self, kind, record):
        if kind != "result":
            return
        captures = self.project.data["captures"]
        row = next((i for i, r in enumerate(captures) if r["time"] > record["time"]), len(captures))
        captures.insert(row, record)
        self.project.note(f"[{timestamp(record['time'])}] Manually captured while watching; instructor notes preserved")
        self.project.save()
        self.set_busy(False)
        self.refresh_gallery(row)
        self.watch.refresh_captures(self.project)
        self.status.setText(f"Saved screenshot {len(captures)} at {timestamp(record['time'])}. Keep watching, or review your captures.")

    def error(self, message):
        self.status.setText(message.splitlines()[0])
        QMessageBox.warning(self, "SlideSnap", message)

    def closeEvent(self, event):
        active = [j for j in self.jobs if j.isRunning()]
        if active:
            if self.control:
                self.control.cancel.set()
                self.control.running.set()
            self.status.setText("Finishing the active operation safely. Close again when it has stopped.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SlideSnap")
    app.setOrganizationName("SlideSnap")
    assets = Path(__file__).resolve().parent / "assets"
    for font in assets.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Poppins", 10))
    app.setStyleSheet(STYLE)
    icon = assets / "slidesnap.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = Window()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        try:
            if path.suffix.lower() == ".json":
                window.load_project(Project.load(path))
            elif path.exists():
                window.load_video(str(path))
        except Exception as exc:
            window.status.setText(str(exc))
    window.show()
    return app.exec()
