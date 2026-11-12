from pathlib import Path
import av
from PIL import Image, ImageDraw, ImageFont


def make_frame(question=1, answer=False, notes=False, camera=0):
    im = Image.new("RGB", (960, 540), "#101c2c")
    d = ImageDraw.Draw(im)
    regular = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 25)
    bold = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 31)
    note_font = ImageFont.truetype("C:/Windows/Fonts/segoepr.ttf", 26)
    d.text((35, 25), f"Question {question}", font=bold, fill="#ff944b")
    title = "Why is narrowband FM chosen?" if question == 1 else "What changes when modulation increases?"
    d.text((35, 85), title, font=bold, fill="white")
    choices = ["Better noise immunity", "No carrier required", "Higher audio fidelity", "Less bandwidth"] if question == 1 else ["Power becomes zero", "Power falls sharply", "Power remains constant", "Power grows rapidly"]
    for i, text in enumerate(choices):
        x = 35+(i%2)*380
        y = 220+(i//2)*112
        fill = "#f48030" if answer and i == (3 if question == 1 else 2) else "#c5c9ce"
        d.rounded_rectangle((x, y, x+355, y+88), radius=12, fill=fill)
        d.text((x+14, y+29), text, font=regular, fill="#121820")
    if notes:
        d.text((45, 145), "Solution: BW = 2 (df + fm)", font=note_font, fill="#7ff4c7")
        d.line([(48, 192),(360, 192),(366, 189)], fill="#7ff4c7", width=4)
        d.line([(650, 438),(690, 465),(740, 423)], fill="#ffcf76", width=6)
    d.rectangle((825, 0, 959, 105), fill=(camera % 255, 60, 150))
    d.ellipse((850+camera%18, 15, 915+camera%18, 80), fill="#c49e82")
    d.text((35, 495), "Lecture example - original instructor markings", font=regular, fill="#8492a7")
    return im


def make_video(path: Path, fps=15):
    stages = [(0, 1.5, 1, False, False), (1.5, 2.5, 1, True, False),
              (2.5, 4.5, 1, True, True), (4.5, 6, 2, False, False),
              (6, 7, 2, True, False), (7, 8, 2, True, True)]
    with av.open(str(path), "w") as out:
        stream = out.add_stream("ffv1", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 960, 540, "bgr0"
        for i in range(8*fps):
            t = i/fps
            _, _, q, a, n = next(x for x in stages if x[0] <= t < x[1])
            image = make_frame(q, a, n, camera=i*13)
            frame = av.VideoFrame.from_image(image)
            frame.pts = i
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path


def write_frames(path, rows, fps=15, variable=False):
    from fractions import Fraction
    with av.open(str(path), "w") as out:
        stream = out.add_stream("ffv1", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 960, 540, "bgr0"
        if variable:
            stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
        for i, (seconds, image) in enumerate(rows):
            frame = av.VideoFrame.from_image(image)
            frame.pts = round(seconds*1000) if variable else i
            if variable:
                frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path
