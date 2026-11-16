import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

app = FastAPI(title="Motion Graphics Studio")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_DURATION_SECONDS = 30
OUTPUT_PATTERN = re.compile(r"[0-9a-f]{32}_output\.(mp4|mov)")


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "motion-graphics-studio"}


def run_ffmpeg(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=210)
    if result.returncode:
        message = (result.stderr or "Video processing failed.")[-2200:]
        raise RuntimeError(message)


def probe_video(path):
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(path)],
        text=True,
        timeout=25,
    )
    data = json.loads(raw)
    stream = next((item for item in data.get("streams", []) if "width" in item), None)
    if stream is None:
        raise ValueError("The uploaded file does not contain a video stream.")
    return float(data["format"]["duration"]), int(stream["width"]), int(stream["height"])


def choose_style(style, prompt):
    if style != "auto":
        return style
    text = (prompt or "").lower()
    if any(word in text for word in ("corporate", "business", "clean", "minimal", "professional")):
        return "corporate"
    if any(word in text for word in ("3d", "three-dimensional", "depth", "rotate", "floating")):
        return "3d"
    if any(word in text for word in ("social", "tiktok", "reel", "bold", "playful", "energetic")):
        return "social"
    return "cinematic"


def style_color(style):
    return {
        "corporate": "0x27A6A1",
        "social": "0xFF4D8D",
        "3d": "0xA78BFA",
        "cinematic": "0xE6B85C",
    }.get(style, "0xE6B85C")


def graphic_filters(title_file, subtitle_file, style, position, duration, width, height):
    accent = style_color(style)
    y = str(height - 320) if position == "bottom" else "120"
    panel_width = width - 120
    title_size = max(34, int(height / 22))
    subtitle_size = max(22, int(height / 42))
    start = 0.2
    end = min(6.0, max(1.0, duration - 0.08))
    slide = "90*exp(-9*t)"
    filters = [
        f"drawbox=x='60+{slide}':y={y}:w={panel_width}:h=235:color=black@0.72:t=fill:enable='between(t,{start},{end})'",
        f"drawbox=x='60+{slide}':y={y}:w=12:h=235:color={accent}:t=fill:enable='between(t,{start},{end})'",
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile='{title_file}':expansion=none:fontcolor=white:fontsize={title_size}:x='112+{slide}':y={int(y)+42}:enable='between(t,{start},{end})'",
    ]
    if subtitle_file.read_text(encoding="utf-8").strip():
        filters.append(
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='{subtitle_file}':expansion=none:fontcolor=white:fontsize={subtitle_size}:x='114+{slide}':y={int(y)+128}:enable='between(t,{start + 0.05},{end})'"
        )
    filters.append(
        f"drawbox=x='112+{slide}':y={int(y)+194}:w={width-230}:h=5:color={accent}:t=fill:enable='between(t,{start + 0.1},{end})'"
    )
    return ",".join(filters)


def prompt_background(style):
    return {
        "cinematic": "0x101B31",
        "corporate": "0x0D2529",
        "social": "0x24101E",
        "3d": "0x15112B",
    }.get(style, "0x101B31")


@app.post("/api/render")
async def render(
    video: Optional[UploadFile] = File(None),
    mode: str = Form("video"),
    prompt: str = Form(""),
    headline: str = Form(""),
    subheading: str = Form(""),
    style: str = Form("auto"),
    resolution: str = Form("1080p"),
    output_mode: str = Form("composite"),
    position: str = Form("bottom"),
):
    mode = mode if mode in {"video", "prompt"} else "video"
    output_mode = output_mode if output_mode in {"composite", "overlay"} else "composite"
    resolution = resolution if resolution in {"1080p", "4K"} else "1080p"
    position = position if position in {"bottom", "top"} else "bottom"
    if len(prompt) > 700 or len(headline) > 90 or len(subheading) > 140:
        raise HTTPException(400, "Please shorten the prompt, headline or supporting text.")
    if mode == "video" and video is None:
        raise HTTPException(400, "Upload a video clip first.")
    if mode == "prompt" and not prompt.strip() and not headline.strip():
        raise HTTPException(400, "Describe the animation you want, or enter a headline.")

    job = uuid.uuid4().hex
    src = None
    title_file = WORK / f"{job}_title.txt"
    subtitle_file = WORK / f"{job}_subtitle.txt"
    out = WORK / f"{job}_output.{'mov' if output_mode == 'overlay' else 'mp4'}"

    try:
        chosen_style = choose_style(style, prompt)
        if not headline.strip():
            words = re.sub(r"\s+", " ", prompt).strip().split()
            headline = " ".join(words[:7]).strip(" .,:;!?")[:64].upper() or "YOUR NEXT BIG IDEA"
        if not subheading.strip() and mode == "prompt":
            words = re.sub(r"\s+", " ", prompt).strip().split()
            subheading = " ".join(words[7:])[:110]

        title_file.write_text(headline.strip() or " ", encoding="utf-8")
        subtitle_file.write_text(subheading.strip() or " ", encoding="utf-8")
        width, height = (3840, 2160) if resolution == "4K" else (1920, 1080)

        if mode == "video":
            extension = Path(video.filename or "").suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(400, "Use MP4, MOV, M4V, WebM or MKV video.")
            src = WORK / f"{job}_source{extension}"
            contents = await video.read(MAX_UPLOAD_BYTES + 1)
            if len(contents) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "This starter version accepts videos up to 80 MB.")
            src.write_bytes(contents)
            duration, _, _ = probe_video(src)
            if duration > MAX_DURATION_SECONDS:
                raise HTTPException(400, f"For the current free server, use a clip no longer than {MAX_DURATION_SECONDS} seconds.")
            if duration <= 0:
                raise HTTPException(400, "The uploaded video's duration could not be read.")
            overlays = graphic_filters(title_file, subtitle_file, chosen_style, position, duration, width, height)
            if output_mode == "overlay":
                command = [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"color=c=black@0.0:s={width}x{height}:r=30:d={duration}",
                    "-vf", f"format=rgba,{overlays}", "-c:v", "qtrle", "-pix_fmt", "argb", str(out)
                ]
            else:
                scale_pad = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                command = [
                    "ffmpeg", "-y", "-i", str(src), "-vf", f"{scale_pad},{overlays}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "1",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)
                ]
        else:
            duration = 7.0
            overlays = graphic_filters(title_file, subtitle_file, chosen_style, position, duration, width, height)
            if output_mode == "overlay":
                source = f"color=c=black@0.0:s={width}x{height}:r=30:d={duration}"
                filters = f"format=rgba,{overlays}"
                codecs = ["-c:v", "qtrle", "-pix_fmt", "argb"]
            else:
                bg = prompt_background(chosen_style)
                source = f"color=c={bg}:s={width}x{height}:r=30:d={duration}"
                shape_color = style_color(chosen_style)
                moving = f"drawbox=x='mod(t*240\\,{width}+200)-100':y=0:w=100:h={height}:color={shape_color}@0.22:t=fill,drawbox=x=70:y=70:w={width-140}:h={height-140}:color=white@0.04:t=8"
                filters = f"{moving},{overlays}"
                codecs = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "1", "-pix_fmt", "yuv420p"]
            command = ["ffmpeg", "-y", "-f", "lavfi", "-i", source, "-vf", filters, *codecs, "-movflags", "+faststart", str(out)]

        run_ffmpeg(command)
        return {
            "download_url": f"/api/download/{out.name}",
            "filename": out.name,
            "mode": mode,
            "resolution": resolution,
            "style": chosen_style,
            "note": "Prompt-directed motion-graphics templates are available. Generative AI scene creation and true object tracking still require a connected AI video provider."
        }
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Rendering timed out. Try a shorter clip or select 1080p.")
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {str(exc)[-1400:]}")
    finally:
        for path in (src, title_file, subtitle_file):
            if path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


@app.get("/api/download/{name}")
def download(name: str):
    if not OUTPUT_PATTERN.fullmatch(name):
        raise HTTPException(404, "File not found.")
    path = WORK / name
    if not path.is_file():
        raise HTTPException(404, "This render is no longer available. Please create it again.")
    media_type = "video/quicktime" if name.endswith(".mov") else "video/mp4"
    return FileResponse(path, filename=name, media_type=media_type)
