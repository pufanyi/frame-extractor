import os
import uuid
import base64
import shutil
import tempfile
import zipfile
import io
import re
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
FRAMES_DIR = Path("frames")
FRAMES_DIR.mkdir(exist_ok=True)
MAX_BATCH_VIDEOS = 20

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


def _validate_video_extension(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'. Allowed: {allowed}")
    return ext


def _safe_svg_stem(filename: str | None, idx: int) -> str:
    stem = Path(filename or "").stem.strip()
    if not stem:
        stem = f"video_{idx:02d}"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return stem or f"video_{idx:02d}"


def _extract_upload(video: UploadFile, n: int, output_dir: Path) -> list[str]:
    ext = _validate_video_extension(video.filename)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(video.file, tmp)
        filenames = extract_frames(tmp_path, n, output_dir)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return filenames


@app.post("/extract")
async def extract(video: UploadFile = File(...), n: int = Form(...)):
    if n < 1:
        raise HTTPException(status_code=400, detail="Number of frames must be a positive integer.")

    job_id = uuid.uuid4().hex[:12]
    output_dir = FRAMES_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    filenames = _extract_upload(video, n, output_dir)

    if not filenames:
        raise HTTPException(status_code=500, detail="Failed to extract any frames from the video.")

    return {"job_id": job_id, "frames": [f"/frames/{job_id}/{f}" for f in filenames]}


class FilmstripRequest(BaseModel):
    frames: list[str]  # e.g. ["/frames/abc123/frame_000000.jpg", ...]
    add_border: bool = False


class ExportConfig(BaseModel):
    frames: list[str]
    format: str = "png"  # svg, png, jpg
    add_border: bool = True
    border_width: int = 1
    border_color: str = "#c8c8c8"
    spacing: int = 0
    background_color: str = "#ffffff"
    quality: int = 90  # JPG only


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color like '#c8c8c8' to BGR tuple for OpenCV."""
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            raise ValueError
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except (ValueError, IndexError):
        return (200, 200, 200)


def _load_frame_images(frame_paths: list[str]) -> list:
    """Load frame images from paths, returning list of cv2 images."""
    images = []
    for fp in frame_paths:
        rel = fp.lstrip("/")
        if rel.startswith("frames/"):
            rel = rel[len("frames/"):]
        abs_path = FRAMES_DIR / rel
        if not abs_path.is_file():
            raise HTTPException(status_code=404, detail=f"Frame not found: {fp}")
        img = cv2.imread(str(abs_path))
        if img is None:
            raise HTTPException(status_code=400, detail=f"Cannot read image: {fp}")
        images.append(img)
    if not images:
        raise HTTPException(status_code=400, detail="No valid images.")
    return images


def _build_raster_export(images: list, config: ExportConfig) -> tuple[bytes, str, str]:
    """Build horizontal grid image. Returns (bytes, media_type, file_extension)."""
    target_h = images[0].shape[0]
    bw = max(0, min(config.border_width, 10))
    spacing = max(0, min(config.spacing, 50))
    quality = max(1, min(config.quality, 100))
    border_bgr = _hex_to_bgr(config.border_color)
    bg_bgr = _hex_to_bgr(config.background_color)

    processed = []
    for img in images:
        h, w = img.shape[:2]
        if h != target_h:
            new_w = int(w * target_h / h)
            img = cv2.resize(img, (new_w, target_h))
        if config.add_border and bw > 0:
            img = cv2.copyMakeBorder(
                img, bw, bw, bw, bw, cv2.BORDER_CONSTANT, value=border_bgr
            )
        processed.append(img)

    if spacing > 0 and len(processed) > 1:
        final_h = processed[0].shape[0]
        spacer = np.full((final_h, spacing, 3), bg_bgr, dtype=np.uint8)
        parts = [processed[0]]
        for p in processed[1:]:
            parts.append(spacer)
            parts.append(p)
        stitched = cv2.hconcat(parts)
    else:
        stitched = cv2.hconcat(processed)

    fmt = config.format.lower()
    if fmt in ("jpg", "jpeg"):
        _, buf = cv2.imencode(".jpg", stitched, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes(), "image/jpeg", "jpg"
    else:
        _, buf = cv2.imencode(".png", stitched, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        return buf.tobytes(), "image/png", "png"


def _build_filmstrip_svg(frame_paths: list[str]) -> str:
    """Generate a realistic 35mm filmstrip-style SVG with embedded PNG frames."""
    n = len(frame_paths)

    # Read images and encode as base64 PNG
    encoded: list[tuple[str, int, int]] = []  # (data_uri, width, height)
    for fp in frame_paths:
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

    # Layout constants — modelled after 35mm film proportions
    frame_display_h = 200
    sample_w, sample_h = encoded[0][1], encoded[0][2]
    frame_display_w = int(frame_display_h * sample_w / sample_h)

    # Sprocket hole dimensions (rectangular with rounded corners, like real film)
    perf_w = 20        # width of each sprocket hole
    perf_h = 14        # height of each sprocket hole
    perf_r = 4         # corner radius of sprocket holes
    perf_band = 28     # height of the sprocket band (top/bottom)
    perf_gap = 18      # gap between adjacent sprocket holes

    frame_pad = 14     # padding between frame image and sprocket band
    cell_gap = 8       # gap between adjacent frames (the "cut line")
    cell_w = frame_display_w + 2 * frame_pad
    film_w = cell_w * n + cell_gap * (n - 1) if n > 1 else cell_w
    film_h = frame_display_h + 2 * frame_pad + 2 * perf_band

    film_x = 0
    film_y = 0

    # How many sprocket holes fit per frame cell
    perf_count = max(1, int((cell_w - perf_gap) / (perf_w + perf_gap)))
    perf_total = perf_count * perf_w + (perf_count - 1) * perf_gap

    # Precompute all sprocket-hole positions so we can cut them out as transparent holes.
    hole_positions: list[tuple[float, float]] = []
    for i in range(n):
        x_off = film_x + i * (cell_w + cell_gap)
        perf_start_x = x_off + (cell_w - perf_total) / 2
        top_perf_y = film_y + (perf_band - perf_h) / 2
        bot_perf_y = film_y + film_h - perf_band + (perf_band - perf_h) / 2
        for j in range(perf_count):
            px = perf_start_x + j * (perf_w + perf_gap)
            hole_positions.append((px, top_perf_y))
            hole_positions.append((px, bot_perf_y))

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{film_w}" height="{film_h}" '
        f'viewBox="0 0 {film_w} {film_h}">'
    )

    # Mask: white keeps film body visible, black punches transparent sprocket holes.
    parts.append('<defs>')
    parts.append('<mask id="film-cutouts">')
    parts.append(
        f'<rect x="{film_x}" y="{film_y}" width="{film_w}" height="{film_h}" fill="#fff"/>'
    )
    for px, py in hole_positions:
        parts.append(
            f'<rect x="{px:.1f}" y="{py:.1f}" '
            f'width="{perf_w}" height="{perf_h}" '
            f'rx="{perf_r}" fill="#000"/>'
        )
    parts.append("</mask>")
    parts.append("</defs>")

    # Background strip — dark brown film base
    parts.append(
        f'<rect x="{film_x}" y="{film_y}" width="{film_w}" height="{film_h}" '
        # f'fill="#2a2520" mask="url(#film-cutouts)"/>'
        f'fill="#ded8f6" mask="url(#film-cutouts)"/>'
    )
    # Subtle edge lines along top and bottom of the strip
    parts.append(
        f'<rect x="{film_x}" y="{film_y}" width="{film_w}" height="2" fill="#3a3530"/>'
    )
    parts.append(
        f'<rect x="{film_x}" y="{film_y + film_h - 2}" width="{film_w}" height="2" fill="#3a3530"/>'
    )

    for i, (data_uri, orig_w, orig_h) in enumerate(encoded):
        x_off = film_x + i * (cell_w + cell_gap)

        # --- Frame area ---
        fx = x_off + frame_pad
        fy = film_y + perf_band + frame_pad

        # Thin bright border around the image (exposure window)
        parts.append(
            f'<rect x="{fx - 2}" y="{fy - 2}" '
            f'width="{frame_display_w + 4}" height="{frame_display_h + 4}" '
            f'fill="none" stroke="#333" stroke-width="1"/>'
        )

        # Embedded image
        parts.append(
            f'<image href="{data_uri}" x="{fx}" y="{fy}" '
            f'width="{frame_display_w}" height="{frame_display_h}" '
            f'preserveAspectRatio="xMidYMid slice"/>'
        )

        # Frame number label (like real film edge markings)
        label_x = fx + frame_display_w - 4
        label_y = fy + frame_display_h + frame_pad - 4
        parts.append(
            f'<text x="{label_x}" y="{label_y}" '
            f'font-family="monospace" font-size="10" fill="#bbb" font-weight="bold" '
            f'text-anchor="end">{i + 1}</text>'
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


@app.post("/export-png")
async def export_png(req: FilmstripRequest):
    if not req.frames:
        raise HTTPException(status_code=400, detail="No frames selected.")
    
    images = []
    for fp in req.frames:
        rel = fp.lstrip("/")
        if rel.startswith("frames/"):
            rel = rel[len("frames/"):]
        abs_path = FRAMES_DIR / rel
        if not abs_path.is_file():
            raise HTTPException(status_code=404, detail=f"Frame not found: {fp}")
        img = cv2.imread(str(abs_path))
        if img is None:
            raise HTTPException(status_code=400, detail=f"Cannot read image: {fp}")
        images.append(img)

    if not images:
        raise HTTPException(status_code=400, detail="No valid images to export.")

    target_h = images[0].shape[0]
    resized_images = []
    
    # We want a 1px gray border on all sides for each frame if add_border is True
    # (or perhaps just right/left to act as separator, but all sides is consistent and fine)
    for img in images:
        h, w = img.shape[:2]
        if h != target_h:
            new_w = int(w * target_h / h)
            img = cv2.resize(img, (new_w, target_h))
            
        if req.add_border:
            # Add a 1px thin gray border around each sub-image
            img = cv2.copyMakeBorder(
                img, 
                1, 1, 1, 1, 
                cv2.BORDER_CONSTANT, 
                value=(200, 200, 200) # Light gray in BGR
            )
            
        resized_images.append(img)

    stitched = cv2.hconcat(resized_images)

    # Use PNG compression level 0 (no compression, maximum quality/lossless)
    _, png_buf = cv2.imencode(".png", stitched, [cv2.IMWRITE_PNG_COMPRESSION, 0])

    return Response(content=png_buf.tobytes(), media_type="image/png",
                    headers={"Content-Disposition": "attachment; filename=horizontal_grid.png"})


@app.post("/export")
async def unified_export(req: ExportConfig):
    if not req.frames:
        raise HTTPException(status_code=400, detail="No frames selected.")
    if len(req.frames) > 20:
        raise HTTPException(status_code=400, detail="Too many frames (max 20).")

    fmt = req.format.lower()
    if fmt not in ("svg", "png", "jpg", "jpeg"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {req.format}")

    if fmt == "svg":
        svg_content = _build_filmstrip_svg(req.frames)
        return Response(
            content=svg_content,
            media_type="image/svg+xml",
            headers={"Content-Disposition": "attachment; filename=filmstrip.svg"},
        )

    images = _load_frame_images(req.frames)
    data, media_type, ext = _build_raster_export(images, req)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=export.{ext}"},
    )


@app.post("/batch-filmstrip")
async def batch_filmstrip(videos: list[UploadFile] = File(...), n: int = Form(...)):
    if n < 1:
        raise HTTPException(status_code=400, detail="Number of frames must be a positive integer.")
    if not videos:
        raise HTTPException(status_code=400, detail="No videos uploaded.")
    if len(videos) > MAX_BATCH_VIDEOS:
        raise HTTPException(status_code=400, detail=f"Too many videos (max {MAX_BATCH_VIDEOS}).")

    zip_buffer = io.BytesIO()
    used_names: set[str] = set()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, video in enumerate(videos, start=1):
            job_id = uuid.uuid4().hex[:12]
            output_dir = FRAMES_DIR / job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            filenames = _extract_upload(video, n, output_dir)
            if not filenames:
                raise HTTPException(status_code=500, detail=f"Failed to extract frames from: {video.filename or f'video {idx}'}")

            frame_paths = [f"/frames/{job_id}/{f}" for f in filenames]
            svg_content = _build_filmstrip_svg(frame_paths)

            base_stem = _safe_svg_stem(video.filename, idx)
            svg_name = f"{base_stem}.svg"
            suffix = 2
            while svg_name in used_names:
                svg_name = f"{base_stem}_{suffix}.svg"
                suffix += 1
            used_names.add(svg_name)
            zf.writestr(svg_name, svg_content)

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=filmstrips.zip"},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("index.html").read_text()
