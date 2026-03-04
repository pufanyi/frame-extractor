# VBVR Frame Extractor (Angular)

Pure frontend video frame extractor built with Angular.

- No Python backend
- No file upload to server
- Video decoding, frame extraction, and SVG generation all run in the browser

## Requirements

- Node.js 22+
- pnpm 10+

## Install

```bash
pnpm install
```

## Run (Angular Host)

```bash
pnpm start
```

Default URL: `http://localhost:4200`

## Build

```bash
pnpm build
```

## Deploy (Cloudflare Workers Static Assets)

1. Authenticate once:

```bash
pnpm wrangler login
```

2. Deploy:

```bash
pnpm deploy
```

This project deploys `dist/app` as static assets with SPA fallback via [`wrangler.jsonc`](/mnt/umm/users/pufanyi/workspace/vbvr-frame-extractor/wrangler.jsonc).

## Usage

1. Select a video file (`.mp4/.mov/.webm/.mkv`).
2. Set frame count.
3. Click **Extract Frames**.
4. Select frames from the grid.
5. Click **Export Filmstrip SVG**.

## Notes

- Extraction uses browser video seeking + canvas snapshots, so sampled frames are based on timeline positions.
- Very large videos or very high frame count may be slower due to browser memory limits.
