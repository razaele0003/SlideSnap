from __future__ import annotations

import csv
import io
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .project import Project, timestamp


def export_project(project: Project, destination, name, kind="both", image_format="PNG",
                   paper="Original aspect ratio", quality="Maximum", captions=False,
                   checkpoint=None, progress=None):
    records = project.selected()
    if not records:
        raise ValueError("Select at least one screenshot before exporting.")
    name = "".join(c for c in name if c not in '<>:"/\\|?*').strip(" .") or "Study notes"
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    ident = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    final = destination / f"{name} - {ident}"
    staging = destination / f".slidesnap-{ident}"
    staging.mkdir()
    writer = None
    try:
        if kind in ("pdf", "both"):
            writer = canvas.Canvas(str(staging / f"{name}.pdf"), pageCompression=1)
            writer.setTitle(name)
            writer.setAuthor("SlideSnap")
        font = "Helvetica"
        fontfile = Path(__file__).resolve().parent / "assets" / "Poppins-Regular.ttf"
        if captions and fontfile.exists():
            if "Poppins" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Poppins", str(fontfile)))
            font = "Poppins"
        if kind in ("images", "both"):
            (staging / "Images").mkdir()
        for i, record in enumerate(records, 1):
            if checkpoint:
                checkpoint()
            source = project.image_path(record)
            with Image.open(source) as original:
                im = original.convert("RGB")
            if quality != "Maximum":
                limit = 1920 if quality == "Balanced" else 1280
                im.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            if kind in ("images", "both"):
                ext = "png" if image_format == "PNG" else "jpg"
                target = staging / "Images" / f"Slide_{i:03}.{ext}"
                if image_format == "PNG" and quality == "Maximum":
                    shutil.copyfile(source, target)
                else:
                    im.save(target, image_format, **({"quality": 95 if quality == "Maximum" else 85 if quality == "Balanced" else 72} if image_format == "JPEG" else {}))
            if writer:
                page = (im.width/2, im.height/2) if paper == "Original aspect ratio" else (
                    landscape(A4) if paper == "A4 landscape" else A4 if paper == "A4 portrait" else
                    landscape(LETTER) if paper == "Letter landscape" else LETTER)
                footer = 20 if captions else 0
                if paper == "Original aspect ratio":
                    page = (page[0], page[1] + footer)
                writer.setPageSize(page)
                margin = 0 if paper == "Original aspect ratio" else 18
                scale = min((page[0]-2*margin)/im.width, (page[1]-2*margin-footer)/im.height)
                w, h = im.width*scale, im.height*scale
                image = im
                if quality != "Maximum":
                    raw = io.BytesIO()
                    im.save(raw, "JPEG", quality=85 if quality == "Balanced" else 72)
                    raw.seek(0)
                    image = raw
                writer.drawImage(ImageReader(image), (page[0]-w)/2, footer+(page[1]-footer-h)/2,
                                 width=w, height=h)
                if captions:
                    writer.setFillColorRGB(.25, .28, .33)
                    writer.setFont(font, 8)
                    writer.drawString(12, 7, f"{i}   |   {timestamp(record['time'])}   |   {record['role']}")
                writer.showPage()
            if progress:
                progress(i, len(records))
        if writer:
            writer.save()
        with (staging / "timestamps.csv").open("w", encoding="utf-8-sig", newline="") as f:
            out = csv.writer(f)
            out.writerow(["Page", "Video timestamp", "Seconds", "Capture", "Change ID"])
            for i, record in enumerate(records, 1):
                out.writerow([i, timestamp(record["time"]), f"{record['time']:.6f}", record["role"], record.get("event")])
        (staging / "detection-log.txt").write_text("\n".join(project.data["log"]), encoding="utf-8")
        staging.rename(final)
    except BaseException:
        # Only remove the uniquely created staging directory owned by this export.
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"folder": str(final), "pdf": str(final / f"{name}.pdf") if kind in ("pdf", "both") else None,
            "pages": len(records), "created": datetime.now().isoformat(timespec="seconds")}
