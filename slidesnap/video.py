from __future__ import annotations

from pathlib import Path
import av
from PIL import Image


def frame_seconds(frame, stream, fallback=0.0):
    return float(frame.pts * frame.time_base) if frame.pts is not None and frame.time_base else fallback


def timeline_origin(container):
    # Use the media timeline, including any audio/video start offset, so manual
    # playback captures and automatic captures refer to the same source frame.
    return float((container.start_time or 0) / av.time_base)


def rotation(stream):
    try:
        return int(float(stream.metadata.get("rotate", 0))) % 360
    except (ValueError, TypeError):
        return 0


def as_image(frame, stream):
    im = frame.to_image().convert("RGB")
    # PyAV exposes display-matrix rotation on the decoded frame.
    frame_angle = round(getattr(frame, "rotation", 0))
    if frame_angle:
        return im.rotate(frame_angle, expand=True)
    angle = rotation(stream)
    return im.rotate(-angle, expand=True) if angle else im


def probe(path):
    with av.open(str(path)) as container:
        streams = list(container.streams.video)
        if not streams:
            raise ValueError("This file has no readable video track.")
        stream = streams[0]
        duration = float(container.duration / av.time_base) if container.duration is not None else float((stream.duration or 0) * stream.time_base)
        w, h = stream.width, stream.height
        if rotation(stream) in (90, 270):
            w, h = h, w
        return {"duration": duration, "width": w, "height": h,
                "fps": float(stream.average_rate or 30), "size": Path(path).stat().st_size}


def read_at(path, seconds):
    """Decode from the preceding keyframe; select the last frame at/before time."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        origin = timeline_origin(container)
        target = max(0.0, seconds) + origin
        container.seek(max(0, int(target / stream.time_base)), stream=stream, backward=True)
        previous = None
        for i, frame in enumerate(container.decode(stream)):
            t = frame_seconds(frame, stream, target) - origin
            if previous is None:
                previous = (as_image(frame, stream), t)
            if t > seconds + 1e-6:
                return previous
            previous = (as_image(frame, stream), t)
        if previous is None:
            raise ValueError("The video did not contain a decodable frame at this time.")
        return previous


def decode_interval(path, start, end):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        origin = timeline_origin(container)
        container.seek(max(0, int((start + origin) / stream.time_base)), stream=stream, backward=True)
        for frame in container.decode(stream):
            t = frame_seconds(frame, stream, start + origin) - origin
            if t < start - 1e-6:
                continue
            if t > end + 1e-6:
                break
            yield as_image(frame, stream), t
