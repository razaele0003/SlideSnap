"""Video playback and precise, manually selected original-frame captures."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)
from .project import timestamp
from .video import decode_interval, read_at
from .widgets import ImageView


class WatchPage(QWidget):
    fileChosen = Signal(str)
    captureRequested = Signal(float)
    reviewRequested = Signal()
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.source = None
        self.displayed_time = 0.0
        self.forced_time = None
        self.capturing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        top = QHBoxLayout()
        self.filename = QLabel("Choose a video to watch and capture at your own pace.")
        self.filename.setWordWrap(True)
        self.filename.setObjectName("muted")
        top.addWidget(self.filename, 1)
        self.choose_btn = QPushButton("Choose video")
        self.choose_btn.clicked.connect(self.choose)
        top.addWidget(self.choose_btn)
        self.capture_btn = QPushButton("Capture screenshot  [S]")
        self.capture_btn.setObjectName("primary")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self.capture)
        top.addWidget(self.capture_btn)
        root.addLayout(top)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 180)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(lambda error, text: self.message.emit("Playback: " + text))
        self.video.videoSink().videoFrameChanged.connect(self.video_frame)
        self.frames = ImageView()
        self.visual = QStackedWidget()
        self.visual.addWidget(self.video)
        self.visual.addWidget(self.frames)
        root.addWidget(self.visual, 1)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderReleased.connect(lambda: self.seek(self.timeline.value()))
        root.addWidget(self.timeline)
        controls = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_btn)
        for text, callback in [("-5 s", lambda: self.seek(max(0, self.player.position()-5000))),
                               ("Previous frame", lambda: self.step(-1)),
                               ("Next frame", lambda: self.step(1)),
                               ("+5 s", lambda: self.seek(self.player.position()+5000))]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            controls.addWidget(b)
        self.clock = QLabel("00:00:00.000 / 00:00:00.000")
        self.clock.setObjectName("muted")
        controls.addWidget(self.clock, 1)
        self.speed = QComboBox()
        self.speed.addItems(["0.5x", "1x", "1.25x", "1.5x", "2x"])
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda i: self.player.setPlaybackRate([.5, 1, 1.25, 1.5, 2][i]))
        controls.addWidget(self.speed)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(80)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value/100))
        controls.addWidget(self.volume)
        root.addLayout(controls)
        jump = QHBoxLayout()
        jump.addWidget(QLabel("Jump to seconds"))
        self.jump_time = QDoubleSpinBox()
        self.jump_time.setDecimals(3)
        self.jump_time.setRange(0, 0)
        self.jump_time.setSuffix(" s")
        jump.addWidget(self.jump_time)
        jump_btn = QPushButton("Go")
        jump_btn.clicked.connect(lambda: self.seek(round(self.jump_time.value()*1000)))
        jump.addWidget(jump_btn)
        jump.addStretch()
        self.count = QLabel("0 saved screenshots")
        self.count.setObjectName("muted")
        jump.addWidget(self.count)
        review = QPushButton("Review captures")
        review.clicked.connect(self.reviewRequested)
        jump.addWidget(review)
        root.addLayout(jump)
        self.recent = QListWidget()
        self.recent.setFlow(QListWidget.Flow.LeftToRight)
        self.recent.setFixedHeight(103)
        from PySide6.QtCore import QSize
        self.recent.setIconSize(QSize(108, 60))
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.recent.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.recent)
        hint = QLabel("Press S to save the displayed frame while watching. Pause and step frame by frame to capture every written solution. Screenshots save automatically in your project.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        root.addWidget(hint)
        QShortcut(QKeySequence("S"), self, activated=self.capture, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_play, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a video to watch", "", "Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All files (*)")
        if path:
            self.fileChosen.emit(path)

    def load(self, source, duration):
        self.player.stop()
        self.source = str(Path(source).resolve())
        self.displayed_time = 0
        self.forced_time = None
        self.visual.setCurrentIndex(0)
        self.filename.setText(Path(source).name)
        self.timeline.setRange(0, round(duration*1000))
        self.jump_time.setMaximum(duration)
        self.clock.setText(f"{timestamp(0)} / {timestamp(duration)}")
        self.player.setSource(QUrl.fromLocalFile(self.source))
        self.capture_btn.setEnabled(True)
        self.recent.clear()

    def video_frame(self, frame):
        if frame.isValid() and frame.startTime() >= 0:
            self.displayed_time = frame.startTime()/1000000

    def position_changed(self, ms):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(ms)
        self.clock.setText(f"{timestamp(ms/1000)} / {timestamp(self.timeline.maximum()/1000)}")

    def duration_changed(self, duration):
        if duration > 0:
            self.timeline.setMaximum(duration)
            self.jump_time.setMaximum(duration/1000)

    def state_changed(self, state):
        self.play_btn.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def toggle_play(self):
        if not self.source:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.forced_time is not None:
                self.player.setPosition(round(self.forced_time*1000))
                self.forced_time = None
            self.visual.setCurrentIndex(0)
            self.player.play()

    def seek(self, ms):
        if not self.source:
            return
        self.forced_time = None
        self.visual.setCurrentIndex(0)
        self.player.setPosition(max(0, min(self.timeline.maximum(), ms)))

    def step(self, direction):
        if not self.source:
            return
        try:
            self.player.pause()
            t = self.forced_time if self.forced_time is not None else self.displayed_time
            times = [pts for _, pts in decode_interval(self.source, max(0, t-2), t+2)]
            options = [pts for pts in times if pts < t-1e-5] if direction < 0 else [pts for pts in times if pts > t+1e-5]
            if not options:
                return
            chosen = options[-1] if direction < 0 else options[0]
            image, actual = read_at(self.source, chosen+.0001)
            rgb = image.convert("RGB")
            qimage = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width*3, QImage.Format.Format_RGB888).copy()
            self.frames.set_image(QPixmap.fromImage(qimage))
            self.visual.setCurrentIndex(1)
            self.forced_time = actual
            self.player.setPosition(round(actual*1000))
            self.timeline.setValue(round(actual*1000))
            self.clock.setText(f"{timestamp(actual)} / {timestamp(self.timeline.maximum()/1000)}")
        except Exception as exc:
            self.message.emit(f"Could not step this video: {exc}")

    def capture(self):
        if self.source and not self.capturing:
            t = self.forced_time if self.forced_time is not None else self.displayed_time
            self.captureRequested.emit(max(0, t))

    def refresh_captures(self, project):
        from PySide6.QtCore import QSize
        self.recent.clear()
        records = project.data["captures"] if project and str(Path(project.data["source"]).resolve()) == self.source else []
        self.count.setText(f"{len(records)} saved screenshots")
        for r in records[-12:]:
            icon = QPixmap(str(project.image_path(r))).scaled(108, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            item = QListWidgetItem(QIcon(icon), timestamp(r["time"]))
            item.setSizeHint(QSize(215, 78))
            self.recent.addItem(item)
        self.recent.scrollToBottom()
