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

ALLOWED = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 45
OUTPUT_PATTERN = re.compile(r"[0-9a-f]{32}_output[.](mp4|mov)")


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


def run_ffmpeg(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError((result.stderr or "FFmpeg failed")[-2200:])


def probe(path):
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=width,height", "-of", "json", str(path)],
        text=True, timeout=30
    )
    data = json.loads(raw)
    stream = next((s for s in data.get("streams", []) if "width" in s), None)
    if stream is None:
        raise ValueError("Uploaded file has no video stream.")
    return float(data["format"]["duration"])


def resolve_style(style, prompt):
    if style in {"cinematic", "corporate", "social", "3d"}:
        return style
    text = (prompt or "").lower()
    if any(x in text for x in ("corporate", "business", "clean", "minimal", "professional")):
        return "corporate"
    if any(x in text for x in ("3d", "depth", "rotate", "floating", "three-dimensional")):
        return "3d"
    if any(x in text for x in ("social", "tiktok", "reel", "bold", "playful", "energetic")):
        return "social"
    return "cinematic"


def accent_for(style):
    return {"corporate":"0x27A6A1", "social":"0xFF4D8D", "3d":"0xA78BFA"}.get(style, "0xE6B85C")


def graphics_filter(title_path, subtitle_path, style, position, duration):
    accent = accent_for(style)
    y_box = "ih-330" if position == "bottom" else "150"
    y_title = "main_h-282" if position == "bottom" else "198"
    y_sub = "main_h-195" if position == "bottom" else "285"
    y_line = "ih-125" if position == "bottom" else "355"
    start = 0.25
    end = max(1.0, min(6.0, duration - 0.1))
    fade_end = max(start + 0.25, end - 0.4)
    alpha = (
        f"if(lt(t\\,{start + 0.4})\\,max(0\\,(t-{start})/0.4)\\,"
        f"if(gt(t\\,{fade_end})\\,max(0\\,({end}-t)/0.4)\\,1))"
    )
    return (
        f"drawbox=x=60:y={y_box}:w=iw-120:h=250:color=black@0.70:t=fill:enable='between(t,{start},{end})',"
        f"drawbox=x=60:y={y_box}:w=14:h=250:color={accent}:t=fill:enable='between(t,{start},{end})',"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile='{title_path}':reload=0:fontcolor=white:fontsize=main_h/22:x=112:y={y_title}:alpha='{alpha}':enable='between(t,{start},{end})',"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='{subtitle_path}':reload=0:fontcolor=white:fontsize=main_h/42:x=114:y={y_sub}:alpha='{alpha}':enable='between(t,{start},{end})',"
        f"drawbox=x=112:y={y_line}:w=iw-230:h=5:color={accent}:t=fill:enable='between(t,{start+0.1},{end})'"
    )


def prompt_backdrop(style):
    accent = accent_for(style)
    bg = {"3d":"0x15112B", "social":"0x24101E", "corporate":"0x0D2529"}.get(style, "0x101B31")
    filters = (
        f"drawbox=x='mod(t*230,iw+240)-120':y=0:w=120:h=ih:color={accent}@0.22:t=fill,"
        "drawbox=x=70:y=70:w=iw-140:h=ih-140:color=white@0.035:t=8"
    )
    return bg, filters


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
    position = position if position in {"top", "bottom"} else "bottom"
    if len(prompt) > 700 or len(headline) > 90 or len(subheading) > 140:
        raise HTTPException(400, "Please shorten the prompt, headline or supporting text.")
    if mode == "video" and video is None:
        raise HTTPException(400, "Choose a video clip first.")
    if mode == "prompt" and not prompt.strip() and not headline.strip():
        raise HTTPException(400, "Describe the animation or enter a headline.")

    job = uuid.uuid4().hex
    source = None
    title_path = WORK / f"{job}_title.txt"
    sub_path = WORK / f"{job}_subtitle.txt"
    output = WORK / f"{job}_output.{'mov' if output_mode == 'overlay' else 'mp4'}"
    try:
        chosen_style = resolve_style(style, prompt)
        if not headline.strip():
            headline = (re.sub(r"\\s+", " ", prompt).strip()[:64].rstrip(" .,:;!?") or "YOUR NEXT BIG IDEA").upper()
        if not subheading.strip() and mode == "prompt":
            subheading = " ".join(re.sub(r"\\s+", " ", prompt).split()[8:])[:110]
        title_path.write_text(headline.strip() or " ", encoding="utf-8")
        sub_path.write_text(subheading.strip() or " ", encoding="utf-8")
        width, height = (3840, 2160) if resolution == "4K" else (1920, 1080)

        if mode == "video":
            ext = Path(video.filename or "").suffix.lower()
            if ext not in ALLOWED:
                raise HTTPException(400, "Use MP4, MOV, M4V, WebM or MKV video.")
            source = WORK / f"{job}_source{ext}"
            content = await video.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise HTTPException(413, "This starter version accepts videos up to 100 MB.")
            source.write_bytes(content)
            duration = probe(source)
            if duration > MAX_SECONDS:
                raise HTTPException(400, f"Use a video clip no longer than {MAX_SECONDS} seconds on this free-hosted version.")
            if duration <= 0:
                raise HTTPException(400, "Could not read the video's duration.")
            graphic = graphics_filter(title_path, sub_path, chosen_style, position, duration)
            if output_mode == "overlay":
                command = [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"color=c=black@0.0:s={width}x{height}:r=30:d={duration}",
                    "-vf", f"format=rgba,{graphic}", "-c:v", "qtrle", "-pix_fmt", "argb", str(output)
                ]
            else:
                scale_pad = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                command = [
                    "ffmpeg", "-y", "-i", str(source), "-vf", f"{scale_pad},{graphic}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(output)
                ]
        else:
            duration = 7.0
            graphic = graphics_filter(title_path, sub_path, chosen_style, position, duration)
            if output_mode == "overlay":
                background = f"color=c=black@0.0:s={width}x{height}:r=30:d={duration}"
                filters = f"format=rgba,{graphic}"
                codec = ["-c:v", "qtrle", "-pix_fmt", "argb"]
            else:
                bg, shapes = prompt_backdrop(chosen_style)
                background = f"color=c={bg}:s={width}x{height}:r=30:d={duration}"
                filters = f"{shapes},{graphic}"
                codec = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p"]
            command = ["ffmpeg", "-y", "-f", "lavfi", "-i", background, "-vf", filters, *codec, "-movflags", "+faststart", str(output)]

        run_ffmpeg(command)
        return {
            "download_url": f"/api/download/{output.name}",
            "filename": output.name,
            "mode": mode,
            "resolution": resolution,
            "style": chosen_style,
            "note": "This version creates prompt-directed motion-graphics templates. Full AI-generated scenes, custom 3D object animation and subject tracking still require a connected AI generation provider."
        }
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Rendering timed out. Try a shorter clip or select 1080p.")
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {str(exc)[-1400:]}")
    finally:
        for path in (source, title_path, sub_path):
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
        raise HTTPException(404, "This render is no longer available. Please generate it again.")
    media_type = "video/quicktime" if name.endswith(".mov") else "video/mp4"
    return FileResponse(path, filename=name, media_type=media_type)
