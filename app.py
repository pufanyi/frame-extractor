import os
import uuid
import shutil
import tempfile
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
FRAMES_DIR = Path("frames")
FRAMES_DIR.mkdir(exist_ok=True)

app = FastAPI()
app.mount("/frames", StaticFiles(directory=str(FRAMES_DIR)), name="frames")


def extract_frames(video_path: str, n: int, output_dir: Path) -> list[str]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Video file could not be opened. It may be corrupted or in an unsupported codec.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 1:
        cap.release()
        raise HTTPException(status_code=400, detail="Video has no readable frames.")

    n = min(n, total_frames)
    indices = [int(i * (total_frames - 1) / (n - 1)) if n > 1 else 0 for i in range(n)]

    filenames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        fname = f"frame_{idx:06d}.jpg"
        cv2.imwrite(str(output_dir / fname), frame)
        filenames.append(fname)

    cap.release()
    return filenames


@app.post("/extract")
async def extract(video: UploadFile = File(...), n: int = Form(...)):
    # Validate extension
    ext = Path(video.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    # Validate N
    if n < 1:
        raise HTTPException(status_code=400, detail="Number of frames must be a positive integer.")

    # Save upload to temp file
    job_id = uuid.uuid4().hex[:12]
    output_dir = FRAMES_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(video.file, tmp)

        filenames = extract_frames(tmp_path, n, output_dir)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not filenames:
        raise HTTPException(status_code=500, detail="Failed to extract any frames from the video.")

    return {"job_id": job_id, "frames": [f"/frames/{job_id}/{f}" for f in filenames]}


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("index.html").read_text()
