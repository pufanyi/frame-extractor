# Video Frame Extractor

A minimal web app that uploads a video and uniformly extracts N frames from it.

## Requirements

- Python 3.9+
- FFmpeg codecs (usually pre-installed; needed by OpenCV for some formats)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

## Usage

1. Select a video file (mp4 / mov / webm / mkv).
2. Enter the number of frames to extract (positive integer).
3. Click **Extract Frames**.
4. The extracted frames are displayed in a grid.

## Tech Stack

- **Backend:** Python, FastAPI, OpenCV
- **Frontend:** Vanilla HTML / CSS / JavaScript
