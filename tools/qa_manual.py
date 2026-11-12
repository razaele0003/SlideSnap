"""Verify watching and manual capture against the user's actual lecture."""
import os
import sys
import argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SLIDESNAP_LIBRARY"] = str(ROOT / "qa" / "Manual library")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QFont
from slidesnap.app import Window, STYLE
from slidesnap.video import read_at
import numpy as np
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("video", type=Path, help="Path to a lecture with content around seven minutes")
source = str(parser.parse_args().video.resolve())

app = QApplication([])
for font in (ROOT / "slidesnap" / "assets").glob("*.ttf"):
    QFontDatabase.addApplicationFont(str(font))
app.setFont(QFont("Poppins", 10))
app.setStyleSheet(STYLE)
w = Window()
w.show()
errors, passed = [], []
w.error = lambda text: errors.append(text)
w.load_watch(source)
w.watch.audio.setMuted(True)
w.watch.player.play()
stage = ["playing"]
ticks = [0]

def tick():
    ticks[0] += 1
    try:
        if errors:
            raise RuntimeError(repr(errors))
        if stage[0] == "playing" and w.watch.displayed_time > .3:
            w.watch.seek(420000)
            stage[0] = "seek"
        elif stage[0] == "seek" and w.watch.displayed_time >= 420:
            w.watch.player.pause()
            w.watch.capture()
            stage[0] = "capture"
        elif stage[0] == "capture" and not w.busy:
            assert len(w.project.data["captures"]) == 1
            w.watch.step(1)
            assert w.watch.forced_time is not None
            w.watch.capture()
            stage[0] = "step"
        elif stage[0] == "step" and not w.busy:
            assert len(w.project.data["captures"]) == 2
            for r in w.project.data["captures"]:
                original, actual = read_at(w.watch.source, r["time"]+.000001)
                saved = Image.open(w.project.image_path(r)).convert("RGB")
                assert np.array_equal(np.asarray(original), np.asarray(saved))
            w.grab().save(str(ROOT / "qa" / "watch-manual.png"))
            print("Manual playback and two source-frame captures passed:", [r["time"] for r in w.project.data["captures"]])
            print("PROJECT", w.project.folder / "project.json")
            passed.append(True)
            w.close()
            app.quit()
    except Exception as exc:
        errors.append(str(exc))
        app.quit()

timer = QTimer()
timer.timeout.connect(tick)
timer.start(100)
QTimer.singleShot(30000, app.quit)
app.exec()
if errors or not passed:
    raise SystemExit("Manual playback test failed: " + repr(errors) + f"; displayed time={w.watch.displayed_time}")
