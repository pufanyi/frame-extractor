# Video Frame Extractor

A minimal web app that uploads a video and uniformly extracts N frames from it.

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg codecs (usually pre-installed; needed by OpenCV for some formats)

## Run

```bash
uv run uvicorn app:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

## Usage

1. Select one or more video files (mp4 / mov / webm / mkv).
2. Enter the number of frames to extract (positive integer).
3. Click **Extract Frames** to preview and select frames from the first selected video.
4. The extracted frames are displayed in a grid.

### Export Filmstrip SVG

After extracting frames you can export selected frames as a filmstrip-style SVG:

1. Click on frames (or their checkboxes) to select the ones you want.
2. Click **Export Filmstrip SVG** (green button).
3. A `.svg` file will be downloaded. It contains a dark film-strip with sprocket holes and the selected frames embedded as base64 PNG images.
4. The SVG is self-contained — no external dependencies — and works in any browser or vector editor.

The layout adapts automatically to the number of selected frames (3–8 recommended, up to 20 supported).

### Batch Export Multiple SVGs

If you select multiple videos, you can export one filmstrip SVG per video in one go:

1. Select/drag multiple videos.
2. Set frame count `N`.
3. Click **Batch Export SVG ZIP**.
4. Download `filmstrips.zip` containing one `.svg` for each uploaded video.

## Tech Stack

- **Backend:** Python, FastAPI, OpenCV
- **Frontend:** Vanilla HTML / CSS / JavaScript
