from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, replace

import av
import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from .project import Project, Settings, timestamp
from .video import as_image, decode_interval, frame_seconds, probe, read_at, timeline_origin


@dataclass
class Features:
    rgb: np.ndarray
    gray: np.ndarray
    edges: np.ndarray
    valid: np.ndarray


def features(im: Image.Image, settings: Settings):
    w, h = im.size
    x, y, rw, rh = settings.roi
    box = (round(x*w), round(y*h), round((x+rw)*w), round((y+rh)*h))
    crop = im.crop(box)
    size = (480, max(40, round(crop.height * 480 / crop.width)))
    rgb = np.asarray(crop.resize(size, Image.Resampling.BILINEAR)).copy()
    rgb = cv2.GaussianBlur(rgb, (3, 3), 0)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    valid = np.ones(gray.shape, dtype=bool)
    for mx, my, mw, mh in settings.masks:
        l = max(0, round((mx-x)/rw*size[0])); r = min(size[0], round((mx+mw-x)/rw*size[0]))
        top = max(0, round((my-y)/rh*size[1])); bottom = min(size[1], round((my+mh-y)/rh*size[1]))
        if r > l and bottom > top:
            valid[top:bottom, l:r] = False
    if valid.mean() < 0.02:
        raise ValueError("The ignore regions cover the detection area. Leave some slide content visible.")
    rgb[~valid] = 0
    gray[~valid] = 0
    edges = cv2.Canny(gray, 60, 140)
    # Remove artificial mask boundaries as well as ignored interiors.
    safe = cv2.erode(valid.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    edges[~safe] = 0
    return Features(rgb, gray, edges, valid)


def blank(f):
    vals = f.gray[f.valid]
    return bool(vals.std() < 3 and (vals.mean() < 12 or vals.mean() > 245))


def metrics(a: Features, b: Features):
    mask = a.valid & b.valid
    delta = np.max(cv2.absdiff(a.rgb, b.rgb), axis=2)
    changed = float(np.mean(delta[mask] > 28))
    if changed < 0.001:
        return changed, 0.0, 0.0, 0.0
    _, smap = structural_similarity(a.gray, b.gray, data_range=255, full=True)
    structure = float(np.mean(1 - smap[mask]))
    kernel = np.ones((3, 3), np.uint8)
    new_edges = cv2.dilate(b.edges, kernel) > 0
    old_edges = cv2.dilate(a.edges, kernel) > 0
    lost = float(np.count_nonzero((a.edges > 0) & ~new_edges) / max(1, np.count_nonzero(a.edges)))
    added = float(np.count_nonzero((b.edges > 0) & ~old_edges) / max(1, np.count_nonzero(b.edges)))
    return changed, structure, lost, added


def significant(a, b, settings):
    changed, structure, lost, added = metrics(a, b)
    sens = settings.sensitivity / 100
    if settings.detection == "slides":
        # New ink mainly ADDS edges. Replaced question text removes old edges.
        # A color highlight mostly changes fill, while preserving text structure.
        return lost > max(.008, .095 - .10*sens) and added > 0.04 and structure > 0.008
    # A filled answer box can change color without moving a single text edge.
    return (changed > (0.022 - 0.019*sens) and structure > 0.002) or structure > (0.10 - 0.075*sens)


class Cancelled(Exception):
    pass


class Control:
    def __init__(self):
        self.cancel = threading.Event()
        self.running = threading.Event()
        self.running.set()

    def checkpoint(self):
        while not self.running.wait(0.05):
            if self.cancel.is_set():
                raise Cancelled()
        if self.cancel.is_set():
            raise Cancelled()


class Analyzer:
    def __init__(self, project: Project, notify=None, control=None):
        self.project = project
        self.settings = Settings(**project.data["settings"])
        self.settings.validate()
        self.notify = notify or (lambda kind, data: None)
        self.control = control or Control()
        self.source = project.data["source"]
        self.last_digest = None

    def capture(self, seconds, role, event=None):
        self.control.checkpoint()
        im, actual = read_at(self.source, seconds)
        if self.settings.crop_export:
            x, y, w, h = self.settings.roi
            im = im.crop((round(x*im.width), round(y*im.height), round((x+w)*im.width), round((y+h)*im.height)))
        digest = hashlib.sha256(im.tobytes()).hexdigest()
        # Only suppress consecutive exact images. Later revisits are meaningful.
        if digest == self.last_digest:
            return None
        self.last_digest = digest
        ident = uuid.uuid4().hex
        relative = f"captures/{ident}.png"
        im.save(self.project.folder / relative, "PNG")
        record = {"id": ident, "path": relative, "time": actual, "role": role,
                  "event": event, "included": True, "sha256": digest}
        self.project.data["captures"].append(record)
        self.project.note(f"[{timestamp(actual)}] Captured {role}; original video pixels preserved")
        self.project.save()
        self.notify("capture", record)
        return record

    def refine_pair(self, old_t, new_t, old_features, new_features):
        if not self.settings.refine:
            return old_t, new_t
        best = old_t
        first_new = None
        for im, t in decode_interval(self.source, old_t, new_t):
            self.control.checkpoint()
            f = features(im, self.settings)
            if blank(f):
                continue
            if first_new is None and not significant(old_features, f, self.settings):
                best = t
            if first_new is None and not significant(new_features, f, self.settings):
                first_new = t
        return best, first_new if first_new is not None else new_t

    def run(self):
        p, s = self.project, self.settings
        slide_rules = replace(s, detection="slides")
        try:
            metadata = probe(self.source)
        except Exception as exc:
            p.data["status"] = "error"
            p.note(f"Could not read video: {exc}")
            p.save()
            raise
        p.data.update(metadata=metadata, status="processing")
        p.save()
        self.notify("metadata", metadata)
        started = time.monotonic()
        compared = decoded = 0
        last_progress = 0
        last_t = 0.0
        last_valid_t = None
        anchor = None
        anchor_t = 0.0
        pending = None
        initial = None
        initialized = False
        next_sample = 0.0
        last_event = -1000.0
        try:
            with av.open(self.source) as container:
                stream = container.streams.video[0]
                stream.thread_type = "AUTO"
                origin = timeline_origin(container)
                for frame in container.decode(stream):
                    self.control.checkpoint()
                    decoded += 1
                    t = max(0.0, frame_seconds(frame, stream, origin + (decoded-1)/metadata["fps"]) - origin)
                    last_t = t
                    due = s.fps == 0 or t + 1e-6 >= next_sample
                    if not due and pending is None and initialized:
                        continue
                    im = as_image(frame, stream)
                    current = features(im, s)
                    compared += 1
                    if not blank(current):
                        last_valid_t = t
                        if not initialized:
                            if initial is None or significant(initial["f"], current, s):
                                initial = {"f": current, "t": t, "count": 1}
                            else:
                                initial["count"] += 1
                            if initial["count"] >= s.group_size:
                                anchor, anchor_t = current, t
                                initialized = True
                                if s.capture in ("after", "both"):
                                    self.capture(initial["t"], "Initial")
                        elif pending is not None:
                            if not significant(pending["old"], current, s):
                                # A transient flash returned to the previous state.
                                pending = None
                                anchor, anchor_t = current, t
                            else:
                                if significant(pending["new"], current, s):
                                    # If the page changes before fresh handwriting
                                    # has settled, retain the LAST written state,
                                    # rather than the frame before writing began.
                                    if significant(pending["previous"], current, slide_rules):
                                        pending["old"] = pending["previous"]
                                        pending["old_t"] = pending["previous_t"]
                                    pending["new"], pending["new_t"], pending["count"] = current, t, 1
                                else:
                                    pending["count"] += 1
                                if pending["count"] >= s.group_size:
                                    before, after = self.refine_pair(pending["old_t"], pending["new_t"], pending["old"], pending["new"])
                                    event_id = len(p.data["events"]) + 1
                                    event = {"id": event_id, "before": before, "after": after}
                                    p.data["events"].append(event)
                                    p.note(f"[{timestamp(after)}] Confirmed visual change #{event_id}")
                                    if s.capture in ("both", "before"):
                                        self.capture(before, "Before", event_id)
                                    if s.capture in ("both", "after"):
                                        self.capture(after, "After", event_id)
                                    last_event = after
                                    anchor, anchor_t = current, t
                                    pending = None
                                    p.save()
                                    self.notify("event", event)
                                if pending is not None:
                                    pending["previous"], pending["previous_t"] = current, t
                        elif due:
                            if significant(anchor, current, s):
                                if t - last_event >= s.minimum_gap:
                                    pending = {"old": anchor, "old_t": anchor_t,
                                               "new": current, "new_t": t, "count": 0,
                                               "previous": current, "previous_t": t}
                            else:
                                anchor, anchor_t = current, t
                    if due and s.fps:
                        next_sample = t + 1/s.fps
                    now = time.monotonic()
                    if now - last_progress > 0.15:
                        elapsed = now - started
                        speed = t / max(elapsed, 0.001)
                        self.notify("progress", {"time": t, "duration": metadata["duration"],
                                    "frames": compared, "decoded": decoded, "events": len(p.data["events"]),
                                    "captures": len(p.data["captures"]), "speed": speed,
                                    "eta": max(0, metadata["duration"]-t)/max(speed, 0.001)})
                        last_progress = now
            # Low-FPS analysis must still inspect the actual end, not just its last sample.
            if last_valid_t is not None:
                tail_start = max(last_valid_t, last_t - max(1, 2/max(s.fps, 1)))
                for tail_im, tail_t in decode_interval(self.source, tail_start, last_t):
                    self.control.checkpoint()
                    if not blank(features(tail_im, s)):
                        last_valid_t = tail_t
                self.capture(last_valid_t, "Final")
            if not p.data["captures"]:
                raise ValueError("No readable slide was found. Check your detection region or add a frame manually.")
            p.data["status"] = "complete"
        except Cancelled:
            p.data["status"] = "cancelled"
            p.note("Processing cancelled. Completed captures remain available for review.")
        except Exception as exc:
            p.data["status"] = "error"
            p.note(f"Processing error: {exc}")
            raise
        finally:
            p.save()
        self.notify("finished", p.data["status"])
        return p
