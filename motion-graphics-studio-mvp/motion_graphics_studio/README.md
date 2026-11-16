# Motion Graphics Studio — MVP

A small web application for creating animated title-card graphics over a video, or exporting those graphics as a transparent ProRes 4444 MOV overlay for use above the original footage in CapCut.

## Run locally
1. Install Python 3.11+, FFmpeg, and DejaVu fonts.
2. In this folder run:
   ```bash
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. Open http://127.0.0.1:8000

## Run with Docker
```bash
docker build -t motion-graphics-studio .
docker run --rm -p 8000:8000 motion-graphics-studio
```

## Current scope and limitations
This is a functional starter MVP for animated title-card overlays and composited exports at 1080p or 4K. It does **not** yet connect to a generative AI video model. It does not currently perform full-scene stylization, subject/object tracking, arbitrary text-to-animation, or sophisticated 3D motion design. Those require integration with a selected AI video/graphics provider and API credentials.

The transparent overlay is exported as ProRes 4444 MOV. Alpha-channel import support can vary by CapCut version/device; if it does not import correctly, export a finished composite instead.

## Before public cloud deployment
- Add authentication and per-user storage.
- Add upload-size limits, quotas, job queue and automatic cleanup.
- Store API keys as server-side environment secrets, never in browser code.
- Use private object storage and signed download URLs.
- Add rate limiting, malware scanning, monitoring and privacy/retention controls.
- Use a GPU-backed provider only when adding generative video features.
