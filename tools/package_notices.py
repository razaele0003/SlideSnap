"""Copy installed runtime dependency licenses into the portable distribution."""
from importlib.metadata import distribution
from pathlib import Path
import re
import shutil

root = Path(__file__).resolve().parents[1]
target = root / "dist" / "SlideSnap"
for name in ["README.md", "THIRD_PARTY_NOTICES.md"]:
    shutil.copyfile(root / name, target / name)
packages = ["PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "av", "numpy", "opencv-python-headless",
            "scikit-image", "scipy", "Pillow", "reportlab", "lazy-loader", "imageio", "tifffile", "networkx", "packaging", "charset-normalizer"]
for name in packages:
    d = distribution(name)
    folder = target / "licenses" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "METADATA.txt").write_text(d.read_text("METADATA") or "", encoding="utf-8")
    for f in d.files or []:
        if not re.search(r"license|copying|notice", str(f), re.I):
            continue
        source = Path(d.locate_file(f))
        if not source.is_file():
            continue
        relative = Path(*[part for part in f.parts if part not in ("..", ".")])
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
print("Runtime dependency notices copied to", target / "licenses")
