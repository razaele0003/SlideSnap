"""Build a reproducible annotated lecture and validate exports in the actual Qt reader."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fixtures import make_video
from slidesnap.detection import Analyzer
from slidesnap.exporting import export_project
from slidesnap.project import Project, Settings
from slidesnap.app import Window, STYLE
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import QSize, QPointF


def main():
    qa = ROOT / "qa"
    qa.mkdir(exist_ok=True)
    source = qa / "Annotated lecture demo.mkv"
    make_video(source)
    project = Project.create(str(source), Settings(detection="slides", capture="before", roi=[0, 0, .85, 1]), qa / "Projects")
    Analyzer(project).run()
    result = export_project(project, qa / "Exports", "Annotated study notes", kind="both")
    project.data["exports"].append(result)
    project.save()
    app = QApplication([])
    for path in (ROOT / "slidesnap" / "assets").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Poppins", 10))
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    w.load_project(project)
    app.processEvents()
    w.grab().save(str(qa / "review.png"))
    w.read_saved_pdf()
    app.processEvents()
    assert w.pdf_doc.pageCount() == 2
    w.pdf_doc.render(0, QSize(1440, 810)).save(str(qa / "pdf-page-1.png"))
    w.pdf_doc.render(1, QSize(1440, 810)).save(str(qa / "pdf-page-2.png"))
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1200, app.quit)
    app.exec()  # Qt renders document pages asynchronously.
    w.grab().save(str(qa / "pdf-reader.png"))
    w.navigate(1)
    app.processEvents()
    assert w.pdf_reader.pageNavigator().currentPage() == 1
    w.fit_view()
    w.zoom(1.25)
    w.reader_mode.setCurrentIndex(0)
    w.load_video(str(source))
    w.preview.roi = [.01, .01, .83, .96]
    app.processEvents()
    w.grab().save(str(qa / "import.png"))
    w.switch(3)
    app.processEvents()
    w.grab().save(str(qa / "export.png"))
    w.close()
    print("PROJECT", project.folder / "project.json")
    print("PDF", result["pdf"])
    print("Qt viewer: both PDF pages loaded, rendered, and navigated successfully.")


if __name__ == "__main__":
    main()
