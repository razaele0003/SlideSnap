"""Run the real packaged app with an isolated PATH and exact Windows arguments."""
import json
import os
import subprocess
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
exe = root / "dist" / "SlideSnap" / "SlideSnap.exe"
environment = os.environ.copy()
environment["PATH"] = str(Path(os.environ["WINDIR"]) / "System32") + ";" + os.environ["WINDIR"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manual-video", type=Path, help="Optional lecture with content around seven minutes for manual playback checks")
args = parser.parse_args()
checks = [("auto", root / "qa" / "Annotated lecture demo.mkv")]
if args.manual_video:
    checks.append(("manual", args.manual_video.resolve()))
for mode, source in checks:
    folder = root / "qa" / f"Portable {mode} check"
    completed = subprocess.run([str(exe), "--self-test", str(source), str(folder), mode],
                               cwd=str(root), env=environment, timeout=110,
                               capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    result = json.loads((folder / "smoke-result.json").read_text())
    print(json.dumps(result, indent=2), flush=True)
    if completed.returncode or not result.get("passed") or not result.get("frozen"):
        raise SystemExit(f"Portable {mode} check failed: {completed.stderr}")
print("Portable executable checks passed without Python or FFmpeg on PATH:", ", ".join(mode for mode, _ in checks))
