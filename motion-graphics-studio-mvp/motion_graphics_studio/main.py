
import os, uuid, subprocess, json, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)
app = FastAPI(title="Motion Graphics Studio")
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")

@app.get("/")
def home():
    return FileResponse(BASE/"static"/"index.html")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or "FFmpeg failed")[-3000:])

def probe(path):
    raw = subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=width,height","-of","json",str(path)])
    data = json.loads(raw)
    v = next((s for s in data.get("streams",[]) if "width" in s), None)
    if not v: raise ValueError("Uploaded file has no video stream.")
    return float(data["format"]["duration"]), int(v["width"]), int(v["height"])

def esc(s):
    return s.replace("\\","\\\\").replace(":","\\:").replace("'","\\'").replace("%","\\%").replace(",","\\,")

@app.post("/api/render")
async def render(
    video: UploadFile = File(...),
    headline: str = Form("YOUR HEADLINE"),
    subheading: str = Form("Add your supporting message"),
    style: str = Form("cinematic"),
    resolution: str = Form("1080p"),
    output_mode: str = Form("composite"),
    position: str = Form("bottom")
):
    if not video.filename or not video.filename.lower().endswith((".mp4",".mov",".m4v",".webm",".mkv")):
        raise HTTPException(400, "Please upload an MP4, MOV, M4V, WebM or MKV video.")
    if len(headline)>90 or len(subheading)>140:
        raise HTTPException(400, "Keep the headline under 90 characters and subheading under 140.")
    job = uuid.uuid4().hex
    src = WORK/f"{job}_source{Path(video.filename).suffix.lower()}"
    await video.seek(0)
    src.write_bytes(await video.read())
    try:
        duration, w, h = probe(src)
        target_w, target_h = (3840,2160) if resolution=="4K" else (1920,1080)
        # Preserve source aspect ratio; scale to fit target canvas.
        scale = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        pad = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        title, sub = esc(headline.strip() or " "), esc(subheading.strip() or " ")
        if style == "corporate":
            accent = "0x27A6A1"
        elif style == "social":
            accent = "0xFF4D8D"
        elif style == "3d":
            accent = "0xA78BFA"
        else:
            accent = "0xE6B85C"
        y = "h-300" if position=="bottom" else "150"
        # Animated title card: soft panel, accent rail, fade/slide entrance.
        alpha = "if(lt(t\\,0.45)\\,t/0.45\\,1)"
        overlay_filter = (
            f"drawbox=x=90:y={y}:w=iw-180:h=220:color=black@0.66:t=fill:"
            f"enable='between(t,0.15,5.8)',"
            f"drawbox=x=90:y={y}:w=12:h=220:color={accent}@1:t=fill:"
            f"enable='between(t,0.15,5.8)',"
            f"drawtext=fontfile='{font}':text='{title}':fontcolor=white:fontsize=h/23:"
            f"x=135:y={y}+48:alpha='{alpha}':enable='between(t,0.15,5.8)',"
            f"drawtext=fontfile='{font_reg}':text='{sub}':fontcolor=white@0.92:fontsize=h/42:"
            f"x=137:y={y}+125:alpha='{alpha}':enable='between(t,0.25,5.8)',"
            f"drawbox=x=135:y={y}+185:w=iw-270:h=5:color={accent}:t=fill:"
            f"enable='between(t,0.35,5.8)'"
        )
        out = WORK/f"{job}_output"
        if output_mode == "overlay":
            # Transparent ProRes 4444 overlay, designed to sit above the original in CapCut.
            out = out.with_suffix(".mov")
            cmd = ["ffmpeg","-y","-f","lavfi","-i",f"color=c=black@0.0:s={target_w}x{target_h}:r=30:d={duration}",
                   "-vf",f"format=rgba,{overlay_filter}","-c:v","qtrle","-pix_fmt","argb",str(out)]
        else:
            out = out.with_suffix(".mp4")
            cmd = ["ffmpeg","-y","-i",str(src),"-vf",f"{scale},{pad},{overlay_filter}",
                   "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
                   "-c:a","aac","-b:a","192k","-movflags","+faststart",str(out)]
        run(cmd)
        return {"download_url":f"/api/download/{out.name}","filename":out.name,
                "mode":output_mode,"resolution":resolution,
                "note":"This MVP creates prompt-directed animated title graphics. Generative AI scene transformation, object tracking and complex 3D animation are not connected yet."}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        try: src.unlink(missing_ok=True)
        except: pass

@app.get("/api/download/{name}")
def download(name: str):
    if not re.fullmatch(r"[a-f0-9]{32}_output\.(mp4|mov)", name):
        raise HTTPException(404, "File not found")
    path = WORK/name
    if not path.exists(): raise HTTPException(404, "Render expired or not found")
    return FileResponse(path, filename=name, media_type="video/quicktime" if name.endswith(".mov") else "video/mp4")
