"""Analyze the supplied real lecture using a practical low-FPS review preset."""
import sys
import argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slidesnap.project import Project, Settings
from slidesnap.detection import Analyzer

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("video", type=Path, help="Path to a local lecture recording")
source = str(parser.parse_args().video.resolve())
p = Project.create(source, Settings(fps=1, group_size=5, detection="slides", capture="before",
                                  roi=[0, 0, .87, .98]), ROOT / "qa" / "Real lecture projects")
checkpoint = [-1]
def notify(kind, data):
    if kind == "progress":
        part = int(data["time"] / data["duration"] * 10)
        if part > checkpoint[0]:
            checkpoint[0] = part
            print(f"{part*10}%: {data['captures']} captures; {data['speed']:.1f}x speed", flush=True)
Analyzer(p, notify).run()
print("PROJECT", p.folder / "project.json", flush=True)
print("EVENTS", p.data["events"][:6], flush=True)
print("CAPTURES", len(p.data["captures"]), flush=True)
