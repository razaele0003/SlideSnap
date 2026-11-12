"""Exercise the GUI worker pipeline: import -> capture -> save -> PDF reader."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SLIDESNAP_LIBRARY"] = str(ROOT / "qa" / "Workflow library")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from slidesnap.app import Window, STYLE

app = QApplication([])
for font in (ROOT / "slidesnap" / "assets").glob("*.ttf"):
    QFontDatabase.addApplicationFont(str(font))
app.setFont(QFont("Poppins", 10))
app.setStyleSheet(STYLE)
w = Window()
errors = []
w.error = lambda message: errors.append(message)
w.show()
w.load_video(str(ROOT / "qa" / "Annotated lecture demo.mkv"))
w.preview.roi = [0, 0, .85, 1]
w.export_folder.setText(str(ROOT / "qa" / "Workflow exports"))
w.start()
stage = ["scan"]
ok = []

def tick():
    if errors:
        app.quit()
    elif stage[0] == "scan" and not w.busy:
        assert w.project.data["status"] == "complete"
        assert len(w.project.data["events"]) == 5
        stage[0] = "export"
        w.export()
    elif stage[0] == "export" and not w.busy:
        assert w.last_export and Path(w.last_export["pdf"]).exists()
        w.read_saved_pdf()
        stage[0] = "read"
        QTimer.singleShot(1000, finish)

def finish():
    assert w.pdf_doc.pageCount() == len(w.project.selected())
    assert w.viewer.currentIndex() == 1
    w.grab().save(str(ROOT / "qa" / "workflow.png"))
    ok.append(True)
    print("GUI workflow passed:", w.pdf_doc.pageCount(), "PDF pages;", len(w.project.data["events"]), "changes")
    w.close()
    app.quit()

timer = QTimer()
timer.timeout.connect(tick)
timer.start(100)
QTimer.singleShot(30000, app.quit)
app.exec()
if errors or not ok:
    raise SystemExit("GUI workflow failed: " + repr(errors))
