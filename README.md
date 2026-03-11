---
title: Video Frame Extractor
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Video Frame Extractor

A minimal web app that uploads a video and uniformly extracts N frames from it.

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg codecs (usually pre-installed; needed by OpenCV for some formats)

## Run Locally

```bash
uv run uvicorn app:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

## Run with Docker

```bash
docker build -t video-frame-extractor .
docker run -p 7860:7860 video-frame-extractor
```

Then open http://localhost:7860 in your browser.

## Usage

1. Select a video file (mp4 / mov / webm / mkv).
2. Enter the number of frames to extract (positive integer).
3. Click **Extract Frames**.
4. The extracted frames are displayed in a grid.

### Export Options

After extracting frames, select the ones you want and use the **Export Options** panel to configure and download:

**Supported formats:**

- **PNG** — Lossless horizontal grid of selected frames.
- **JPG** — Lossy horizontal grid with configurable quality (1–100).
- **SVG (Filmstrip)** — Self-contained filmstrip with sprocket holes and embedded images. Works in any browser or vector editor.

**Configurable options (PNG / JPG):**

- **Frame borders** — Toggle on/off, with adjustable width (1–10 px) and color.
- **Spacing** — Gap between frames (0–50 px) with configurable background color.
- **Quality** — JPG compression quality slider (1–100).

A live preview updates automatically as you change options. Right-click the preview to copy or save directly.

The layout adapts automatically to the number of selected frames (3–8 recommended, up to 20 supported).

### Download Selected Frames

Use **Download Selected Frames** to download the original extracted frame images individually (no ZIP packaging).

Note: your browser may ask permission for multiple file downloads.

## Tech Stack

- **Backend:** Python, FastAPI, OpenCV
- **Frontend:** Vanilla HTML / CSS / JavaScript
