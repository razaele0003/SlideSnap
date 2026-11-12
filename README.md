# SlideSnap

A local Windows app that turns lecture videos into saved study decks, PDFs and screenshots. Poppins typography, a built-in document reader, and no account or paid service required.

## Open the app

Double-click **Launch SlideSnap.cmd**. The portable build is at `dist/SlideSnap/SlideSnap.exe`; keep its complete folder together. Python and system FFmpeg are not needed for the portable build.

To run from source, install Python 3.12+, run `install.ps1` in PowerShell, and open the launcher. Alternatively run `.venv\Scripts\python.exe main.py`. You may pass a video path or a saved `project.json` as an argument.

## Capture a lecture

1. Choose **Import video** and browse for a local video, or drag it onto the drop area.
2. Scrub the preview to a representative slide. Choose **Draw slide area** and drag around the presentation. Use **Draw ignore region** to exclude webcams, timers, or overlays from detection.
3. Choose a detection preset:
   - **Reveals, notes & slide changes** saves stable before/after states when significant visual content changes, including answer highlights and written solutions.
   - **Slides only** defaults to before-only captures. It treats added writing and highlights as part of the current slide, then saves its latest annotated state before the next slide. It also saves the final slide.
4. Start capturing. Pause/resume or cancel whenever needed. Completed captures save automatically.
5. Review your study deck inside the app. Check the written notes and solutions. Uncheck unwanted screenshots, move pages, add a frame, or replace one with a nearby original frame.
6. Export a PDF, images, or both. Choose **Read saved PDF here** to view the actual exported document inside SlideSnap.

## Watch and capture manually

Open **Watch / capture** and choose a video. Watch with audio, scrub the timeline, jump to a time, or change playback speed. Click **Capture screenshot** or press **S** to save the displayed source frame without needing an automatic scan. **Space** plays or pauses. When paused, **Previous frame** and **Next frame** select exact original frames, including variable-frame-rate video.

Manual screenshots save automatically to the current matching video project, or a new project if you chose a different video. Recent captures appear below the player. **Review captures** opens the same saved study deck, where you can organize screenshots and export a PDF or images. **Watch source video** in Review jumps back to the source around the selected capture.

Real-footage validation used a 35-minute lecture recording. The app reads local videos and does not alter them.

## Handwriting, notes, and worked solutions

The screenshot is taken from the original video image. Instructor handwriting, annotations, highlights, equations, diagrams, and solution steps remain in it. The app does not use OCR to rewrite content and does not erase markings or watermarks.

In **Slides only**, small additions do not intentionally create a new slide; the app keeps moving its reference forward so the final annotated state can be captured before the page changes. In the default changes preset, a sufficiently large persistent addition can also create a before/after pair. Slow or very small writing may not create its own event, but visible writing remains in subsequent and final captures.

Use **Replace with nearby frame** if an automatic capture misses the desired state. Previous/next frame controls use original video timestamps, including variable-frame-rate sources. Cropping occurs only when **Export only the slide area** is explicitly checked. Ignore regions affect detection, not screenshot content.

If the instructor erases writing before moving to another slide, use the default **Reveals, notes & slide changes** preset to capture significant writing/erasing changes, or manually capture each step in **Watch / capture**. **Slides only** keeps the final visible state of a slide; earlier erased notes cannot remain in that final image.

## Speed and precision

- **Every source frame** is the thorough default.
- **Fast 0.5 FPS**, **Balanced 1 FPS**, **Accurate 5 FPS**, and custom FPS compare fewer frames. Lower rates can miss slides that appear entirely between samples. Video decoding still has a cost, so speedup is source-dependent.
- **Confirm group**, default 5 frames, confirms a persistent changed state using consecutive original frames. The confirmation windows overlap; this is separate from the comparison FPS setting.
- **Precise transition refinement** checks original frames near a detected change to find the last valid previous state. It does not invent missing frames.
- **Sensitivity**: increase it for missed small changes; decrease it for extra events caused by animation or writing.
- **Minimum interval**, default 0.25 seconds, suppresses closely spaced duplicate events. Lower it for rapid steps; raise it for animated presentations.

The detector uses pixel changes, structural similarity and removed/added text edges. Slide-only classification is heuristic: heavily overwritten notes, animated text, and nearly identical slides can require sensitivity adjustment or manual corrections. Preview the output before relying on it. Regression tests include synthetic lecture sequences; playback and manual captures are also checked against the supplied real lecture.

## Built-in reading and saving

**Projects** lists automatically saved decks. Each project contains a `project.json` manifest and original-resolution PNG captures. Captures remain readable without the source video; adding or replacing a frame needs that video. If it moves, the app asks you to locate it.

**Review & read** has thumbnails, zoom, fit-to-page, page navigation, and a fullscreen slide presentation. The **Saved PDF** selector reads a generated PDF inside the app. Export again after editing the deck to update the PDF. Existing unrelated PDF and PowerPoint imports are not part of this release.

By default, projects live under `Documents/SlideSnap/Projects`; exports live under `Documents/SlideSnap/Exports`. Set `SLIDESNAP_LIBRARY` before launching to use another library folder. No video is uploaded or copied to a server.

Exports use the current checked-page order, one screenshot per PDF page. Maximum-quality PNG export copies the saved screenshot losslessly. Original-aspect PDF pages preserve the complete image. A4 and Letter options fit it without stretching or cropping. Timestamps are optional captions below the image. Each export gets a separate folder containing its PDF/images, CSV timestamps, and detection log.

## Develop and build

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\build.ps1
```

The Poppins files are already bundled. `tools/prepare_assets.py` can restore them from the official Google Fonts repository. The build includes PyAV decoder libraries, Qt's PDF reader, and font assets. A dedicated GPU is unnecessary.

One video is processed per project. Long recordings are decoded incrementally and captures are disk-backed. Pause/resume applies during the current scan; a cancelled or interrupted scan preserves completed captures, but continuing the scan after restarting the app requires a new scan. Very long videos and large decks require enough disk space. No fixed hardware-independent processing-time promise is made.
