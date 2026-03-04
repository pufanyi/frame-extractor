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

1. Select a video file (mp4 / mov / webm / mkv).
2. Enter the number of frames to extract (positive integer).
3. Click **Extract Frames**.
4. The extracted frames are displayed in a grid.

### Export Filmstrip SVG

After extracting frames you can export selected frames as a filmstrip-style SVG:

1. Click on frames (or their checkboxes) to select the ones you want.
2. Click **Export Filmstrip SVG** (green button).
3. A `.svg` file will be downloaded. It contains a dark film-strip with sprocket holes and the selected frames embedded as base64 PNG images.
4. The SVG is self-contained — no external dependencies — and works in any browser or vector editor.

The layout adapts automatically to the number of selected frames (3–8 recommended, up to 20 supported).

### Download Selected Images

After extraction, select the frames you want, then click **Download Selected Images** to download only the selected frames directly (no ZIP packaging).

Note: your browser may ask permission for multiple file downloads.

## Tech Stack

- **Backend:** Python, FastAPI, OpenCV
- **Frontend:** Vanilla HTML / CSS / JavaScript
