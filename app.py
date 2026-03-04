import os
import uuid
import base64
import shutil
import tempfile
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


class FilmstripRequest(BaseModel):
    frames: list[str]  # e.g. ["/frames/abc123/frame_000000.jpg", ...]


def _build_filmstrip_svg(frame_paths: list[str]) -> str:
    """Generate a filmstrip-style SVG with embedded PNG frames."""
    n = len(frame_paths)

    # Read images and encode as base64 PNG
    encoded: list[tuple[str, int, int]] = []  # (data_uri, width, height)
    for fp in frame_paths:
        # Strip leading /frames/ to get relative path under FRAMES_DIR
        rel = fp.lstrip("/")
        if rel.startswith("frames/"):
            rel = rel[len("frames/"):]
        abs_path = FRAMES_DIR / rel
        if not abs_path.is_file():
            raise HTTPException(status_code=404, detail=f"Frame not found: {fp}")
        img = cv2.imread(str(abs_path))
        if img is None:
            raise HTTPException(status_code=400, detail=f"Cannot read image: {fp}")
        h, w = img.shape[:2]
        _, png_buf = cv2.imencode(".png", img)
        b64 = base64.b64encode(png_buf.tobytes()).decode()
        encoded.append((f"data:image/png;base64,{b64}", w, h))

    # Layout constants
    frame_display_h = 200  # height of each frame image area
    # Compute uniform display width preserving first image aspect ratio
    sample_w, sample_h = encoded[0][1], encoded[0][2]
    frame_display_w = int(frame_display_h * sample_w / sample_h)

    padding = 12  # padding around each frame
    perf_r = 8  # sprocket hole radius
    perf_margin = 18  # sprocket center distance from strip edge
    strip_h = frame_display_h + 2 * padding + 2 * perf_margin + 2 * perf_r
    cell_w = frame_display_w + 2 * padding
    total_w = cell_w * n
    img_y = perf_margin + perf_r + padding  # top of image area

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_w}" height="{strip_h}" '
        f'viewBox="0 0 {total_w} {strip_h}">'
    )
    # Background strip
    parts.append(f'<rect width="{total_w}" height="{strip_h}" rx="8" fill="#1a1a1a"/>')

    for i, (data_uri, orig_w, orig_h) in enumerate(encoded):
        x_off = i * cell_w

        # Sprocket holes (top and bottom)
        top_cy = perf_margin
        bot_cy = strip_h - perf_margin
        cx = x_off + cell_w // 2
        parts.append(f'<circle cx="{cx}" cy="{top_cy}" r="{perf_r}" fill="#333"/>')
        parts.append(f'<circle cx="{cx}" cy="{bot_cy}" r="{perf_r}" fill="#333"/>')

        # Frame border (slightly lighter)
        fx = x_off + padding
        fy = img_y
        parts.append(
            f'<rect x="{fx - 2}" y="{fy - 2}" width="{frame_display_w + 4}" '
            f'height="{frame_display_h + 4}" rx="3" fill="#444"/>'
        )

        # Embedded image
        parts.append(
            f'<image href="{data_uri}" x="{fx}" y="{fy}" '
            f'width="{frame_display_w}" height="{frame_display_h}" '
            f'preserveAspectRatio="xMidYMid slice"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


@app.post("/filmstrip")
async def filmstrip(req: FilmstripRequest):
    if not req.frames:
        raise HTTPException(status_code=400, detail="No frames selected.")
    if len(req.frames) > 20:
        raise HTTPException(status_code=400, detail="Too many frames (max 20).")
    svg_content = _build_filmstrip_svg(req.frames)
    return Response(content=svg_content, media_type="image/svg+xml",
                    headers={"Content-Disposition": "attachment; filename=filmstrip.svg"})


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("index.html").read_text()
