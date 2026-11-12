from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


def library_path() -> Path:
    base = Path(os.environ.get("SLIDESNAP_LIBRARY", str(Path.home() / "Documents" / "SlideSnap")))
    base.mkdir(parents=True, exist_ok=True)
    return base


def timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


@dataclass
class Settings:
    fps: float = 0  # zero means every source frame
    group_size: int = 5
    sensitivity: int = 50
    minimum_gap: float = 0.25
    refine: bool = True
    detection: str = "changes"
    capture: str = "both"
    roi: list[float] = field(default_factory=lambda: [0, 0, 1, 1])
    masks: list[list[float]] = field(default_factory=list)
    crop_export: bool = False

    def validate(self):
        if not 0 <= self.fps <= 120:
            raise ValueError("Comparison FPS must be between 0 and 120 (0 = every frame).")
        if not 1 <= self.group_size <= 60:
            raise ValueError("Frame group size must be between 1 and 60.")
        if not 0 <= self.sensitivity <= 100 or not 0 <= self.minimum_gap <= 60:
            raise ValueError("Invalid sensitivity or minimum capture interval.")
        if self.detection not in ("changes", "slides") or self.capture not in ("both", "before", "after"):
            raise ValueError("Invalid detection or capture mode.")
        for rect in [self.roi, *self.masks]:
            x, y, w, h = rect
            if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00001 or y+h > 1.00001:
                raise ValueError("Detection rectangles must be inside the video.")


@dataclass
class Project:
    folder: Path
    data: dict

    @classmethod
    def create(cls, source: str, settings: Settings, parent: Path | None = None):
        parent = parent or library_path() / "Projects"
        folder = parent / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
        (folder / "captures").mkdir(parents=True)
        p = cls(folder, {
            "version": 1, "name": Path(source).stem, "source": str(Path(source).resolve()),
            "created": datetime.now().isoformat(timespec="seconds"), "status": "ready",
            "settings": asdict(settings), "captures": [], "events": [], "metadata": {},
            "exports": [], "log": [],
        })
        p.save()
        return p

    @classmethod
    def load(cls, path: str | Path):
        path = Path(path)
        if path.is_dir():
            path /= "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("This project was made with an unsupported version of SlideSnap.")
        return cls(path.parent, data)

    def save(self):
        temp = self.folder / "project.json.tmp"
        temp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        # OneDrive and antivirus can briefly hold an existing manifest open.
        # Keep the atomic write and retry a transient Windows sharing lock.
        for attempt in range(7):
            try:
                temp.replace(self.folder / "project.json")
                break
            except PermissionError:
                if attempt == 6:
                    raise
                time.sleep(.02 * 2**attempt)

    def image_path(self, record):
        return self.folder / record["path"]

    def selected(self):
        return [r for r in self.data["captures"] if r.get("included", True)]

    def note(self, text):
        self.data["log"].append(text)


def recent_projects():
    root = library_path() / "Projects"
    if not root.exists():
        return []
    result = []
    for path in sorted(root.glob("*/project.json"), reverse=True):
        try:
            result.append(Project.load(path))
        except (OSError, ValueError, KeyError):
            continue
    return result
