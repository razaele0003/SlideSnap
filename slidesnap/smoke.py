"""Offline end-to-end check used to validate the frozen portable distribution."""
import json
import os
import sys
import traceback
from pathlib import Path


def main(args):
    source, output = map(Path, args[:2])
    mode = args[2] if len(args) > 2 else "auto"
    output.mkdir(parents=True, exist_ok=True)
    report = output / "smoke-result.json"
    try:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["SLIDESNAP_LIBRARY"] = str(output / "Library")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtCore import QTimer
        from .app import Window, STYLE
        from .project import timestamp
        from .video import read_at
        import numpy as np
        from PIL import Image

        app = QApplication([])
        for font in (Path(__file__).parent / "assets").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Poppins", 10))
        app.setStyleSheet(STYLE)
        window = Window()
        errors = []
        window.error = lambda text: errors.append(text)
        window.show()
        if mode == "manual":
            window.load_watch(str(source))
            window.watch.audio.setMuted(True)
            window.watch.player.play()
        else:
            window.load_video(str(source))
            window.preview.roi = [0, 0, .85, 1]
        window.export_folder.setText(str(output / "Exports"))
        if mode != "manual":
            window.start()
        stage = ["playing" if mode == "manual" else "scan"]
        passed = []
        def finish():
            try:
                assert window.pdf_doc.pageCount() == len(window.project.selected())
                assert window.pdf_doc.pageCount() > 1
                window.pdf_doc.render(0, window.image_reader.size()).save(str(output / "pdf-page.png"))
                window.grab().save(str(output / "portable-reader.png"))
                if mode == "manual":
                    capture = window.project.data["captures"][-1]
                    assert len(window.project.data["captures"]) == 2
                else:
                    event = next(e for e in window.project.data["events"] if 4.49 < e["after"] < 4.7)
                    capture = next(r for r in window.project.data["captures"] if r["event"] == event["id"] and r["role"] == "Before")
                original, actual = read_at(source, capture["time"])
                saved = Image.open(window.project.image_path(capture)).convert("RGB")
                assert np.array_equal(np.asarray(saved), np.asarray(original))
                if mode != "manual":
                    ink = np.asarray(saved)[145:195, 45:440]
                    assert np.count_nonzero((ink[:,:,1]>210) & (ink[:,:,0]<160)) > 300
                report.write_text(json.dumps({"passed": True, "frozen": bool(getattr(sys, "frozen", False)),
                                  "mode": mode, "pdf_pages": window.pdf_doc.pageCount(), "events": len(window.project.data["events"]),
                                  "notes_preserved_at": timestamp(actual), "pdf": window.last_export["pdf"]}, indent=2))
                passed.append(True)
            except Exception:
                errors.append(traceback.format_exc())
            window.close()
            app.quit()
        def tick():
            try:
                if errors:
                    app.quit()
                elif stage[0] == "playing" and window.watch.displayed_time > .3:
                    window.watch.seek(420000)
                    stage[0] = "seek"
                elif stage[0] == "seek" and window.watch.displayed_time >= 420:
                    window.watch.player.pause()
                    window.watch.capture()
                    stage[0] = "manual_capture"
                elif stage[0] == "manual_capture" and not window.busy:
                    assert len(window.project.data["captures"]) == 1
                    window.watch.step(1)
                    window.watch.capture()
                    stage[0] = "second_capture"
                elif stage[0] == "second_capture" and not window.busy:
                    window.grab().save(str(output / "portable-watch.png"))
                    stage[0] = "export"
                    window.export()
                elif stage[0] == "scan" and not window.busy:
                    assert window.project.data["status"] == "complete"
                    assert len(window.project.data["events"]) == 5
                    stage[0] = "export"
                    window.export()
                elif stage[0] == "export" and not window.busy:
                    assert window.last_export and Path(window.last_export["pdf"]).exists()
                    window.read_saved_pdf()
                    stage[0] = "read"
                    QTimer.singleShot(1200, finish)
            except Exception:
                errors.append(traceback.format_exc())
                app.quit()
        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(100)
        QTimer.singleShot(90000, app.quit)
        app.exec()
        if errors or not passed:
            raise RuntimeError("\n".join(errors) or "Portable self-test timed out")
        return 0
    except BaseException:
        report.write_text(json.dumps({"passed": False, "error": traceback.format_exc()}, indent=2))
        return 1
