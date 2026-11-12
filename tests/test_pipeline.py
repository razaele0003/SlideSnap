from __future__ import annotations
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from slidesnap.detection import Analyzer, Cancelled, Control, features, significant
from slidesnap.exporting import export_project
from slidesnap.project import Project, Settings
from slidesnap.video import probe, read_at
from fixtures import make_frame, make_video, write_frames


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    return make_video(tmp_path_factory.mktemp("media") / "lecture.mkv")


def analyze(video, root, **kwargs):
    settings = Settings(roi=[0, 0, .85, 1], group_size=3, **kwargs)
    project = Project.create(str(video), settings, root)
    Analyzer(project).run()
    return project


def test_notes_and_solutions_survive_before_next_slide(video, tmp_path):
    project = analyze(video, tmp_path)
    events = project.data["events"]
    # Highlight, handwriting, page change, second answer, second solution.
    assert len(events) == 5
    transition = next(e for e in events if 4.49 <= e["after"] < 4.7)
    record = next(r for r in project.data["captures"] if r["event"] == transition["id"] and r["role"] == "Before")
    assert 4.40 < record["time"] < 4.5
    expected, _ = read_at(video, record["time"])
    actual = Image.open(project.image_path(record)).convert("RGB")
    assert np.array_equal(np.asarray(expected), np.asarray(actual))
    # Green written solution is still present in the saved pixels.
    arr = np.asarray(actual)[145:195, 45:440]
    assert np.count_nonzero((arr[:,:,1] > 210) & (arr[:,:,0] < 160)) > 300
    assert project.data["captures"][-1]["role"] == "Final"
    assert project.data["captures"][-1]["time"] > 7.8


def test_slides_only_retains_final_annotated_state(video, tmp_path):
    project = analyze(video, tmp_path, detection="slides", capture="before")
    assert len(project.data["events"]) == 1
    assert len(project.data["captures"]) == 2
    assert 4.4 < project.data["captures"][0]["time"] < 4.5
    assert project.data["captures"][-1]["time"] > 7.8


def test_low_fps_refinement_uses_native_frame(video, tmp_path):
    project = analyze(video, tmp_path, fps=1, detection="slides", capture="before")
    assert len(project.data["events"]) == 1
    # At 15 FPS the cut at 4.5 seconds first appears at PTS 4.533;
    # the preceding source frame has the container timestamp 4.467.
    assert project.data["captures"][0]["time"] == pytest.approx(4.467, abs=.001)


def test_webcam_motion_masked_and_ink_is_not_rewritten():
    s = Settings(roi=[0, 0, .85, 1])
    a = features(make_frame(camera=0), s)
    b = features(make_frame(camera=210), s)
    assert not significant(a, b, s)
    assert significant(a, features(make_frame(notes=True), s), s)
    s.detection = "slides"
    assert not significant(a, features(make_frame(notes=True), s), s)
    assert not significant(a, features(make_frame(answer=True), s), s)
    assert significant(a, features(make_frame(question=2), s), s)


def test_export_persistence_inclusion_and_order(video, tmp_path):
    p = analyze(video, tmp_path / "projects", detection="slides", capture="before")
    p.data["captures"].reverse()
    p.data["captures"][1]["included"] = False
    p.save()
    p = Project.load(p.folder)
    result = export_project(p, tmp_path / "exports", "Notes", kind="both")
    reader = PdfReader(result["pdf"])
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.width)/float(reader.pages[0].mediabox.height) == pytest.approx(960/540)
    pngs = list((Path(result["folder"])/"Images").glob("*.png"))
    assert len(pngs) == 1
    assert pngs[0].read_bytes() == p.image_path(p.selected()[0]).read_bytes()


def test_cancellation_preserves_project(video, tmp_path):
    p = Project.create(str(video), Settings(), tmp_path)
    control = Control()
    control.cancel.set()
    Analyzer(p, control=control).run()
    assert Project.load(p.folder).data["status"] == "cancelled"


def test_invalid_settings_and_empty_export(tmp_path):
    with pytest.raises(ValueError):
        Settings(fps=-1).validate()
    with pytest.raises(ValueError):
        Settings(group_size=0).validate()
    p = Project.create("example.mp4", Settings(), tmp_path / "projects")
    with pytest.raises(ValueError):
        export_project(p, tmp_path / "exports", "Empty")


def test_pause_and_cancel_are_cooperative():
    control = Control()
    control.running.clear()
    result = []
    def wait():
        try:
            control.checkpoint()
        except Cancelled:
            result.append("cancelled")
    t = threading.Thread(target=wait)
    t.start()
    time.sleep(.1)
    assert t.is_alive()
    control.cancel.set()
    t.join(1)
    assert result == ["cancelled"]


def test_notes_revealed_immediately_before_next_slide(tmp_path):
    rows = []
    for i in range(65):
        # Instructor's solution appears for just TWO frames before the cut.
        rows.append((i/15, make_frame(question=1 if i < 32 else 2,
                                     answer=i < 32, notes=30 <= i < 32)))
    source = write_frames(tmp_path / "brief-notes.mkv", rows)
    p = Project.create(str(source), Settings(roi=[0, 0, .85, 1], group_size=5), tmp_path / "projects")
    Analyzer(p).run()
    target = next(r for r in p.data["captures"] if r["role"] == "Before" and 2 <= r["time"] < 2.15)
    expected, actual_t = read_at(source, 31/15 + .001)
    assert target["time"] == pytest.approx(actual_t)
    assert np.array_equal(np.asarray(Image.open(p.image_path(target))), np.asarray(expected))


def test_variable_timestamps_and_multi_hour_timeline(tmp_path):
    times = [0, .1, .2, 1, 1.6, 1.7, 1.8, 2.1, 7200, 7200.1, 7200.2]
    rows = [(t, make_frame(question=1 if t < 1.6 else 2, notes=t < 1.6)) for t in times]
    source = write_frames(tmp_path / "variable.mkv", rows, variable=True)
    _, t = read_at(source, 1.65)
    assert t == pytest.approx(1.6)
    p = Project.create(str(source), Settings(roi=[0, 0, .85, 1], group_size=2, capture="before"), tmp_path / "projects")
    Analyzer(p).run()
    assert len(p.data["events"]) == 1
    assert p.data["captures"][0]["time"] == pytest.approx(1)
    assert p.data["captures"][-1]["time"] == pytest.approx(7200.2)


def test_unchanged_video_and_temporary_blank(tmp_path):
    image = make_frame(notes=True)
    rows = [(i/15, Image.new("RGB", image.size) if 20 <= i <= 21 else image) for i in range(45)]
    source = write_frames(tmp_path / "unchanged.mkv", rows)
    p = analyze(source, tmp_path / "projects")
    assert p.data["events"] == []
    assert len(p.data["captures"]) == 1


def test_corrupted_video_does_not_silently_export(tmp_path):
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"not a video")
    p = Project.create(str(source), Settings(), tmp_path / "projects")
    with pytest.raises(Exception):
        Analyzer(p).run()
    assert p.data["captures"] == []


def test_default_mode_keeps_notes_before_instructor_erases_them(tmp_path):
    rows = [(i/15, make_frame(notes=15 <= i < 45)) for i in range(75)]
    source = write_frames(tmp_path / "erased-notes.mkv", rows)
    p = analyze(source, tmp_path / "projects")
    event = next(e for e in p.data["events"] if 2.9 < e["after"] < 3.2)
    # An identical preceding After image may be reused rather than duplicated.
    before = max((r for r in p.data["captures"] if r["time"] < event["after"]), key=lambda r: r["time"])
    arr = np.asarray(Image.open(p.image_path(before)))[145:195, 45:440]
    assert np.count_nonzero((arr[:,:,1] > 210) & (arr[:,:,0] < 160)) > 300
