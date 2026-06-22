"""
Free, low-RAM video renderer for YouTube Shorts — ffmpeg CLI only.

Unlike MoviePy (which decodes whole clips into numpy arrays in RAM and was the
cause of the 512 MB crashes on Render), this builds ONE streaming ffmpeg command
and lets the ffmpeg child process do the work frame-by-frame. Output is a
vertical 720x1280 H.264 short with:

  • an animated branded intro card
  • Ken-Burns (slow zoom) on each scene image, with cross-fades
  • an animated call-to-action outro card
  • a corner watermark + optional sponsor banner

Text is passed via drawtext `textfile=` (with `expansion=none`) so French accents
and punctuation need no escaping. If the rich command fails, it retries without
the zoom effect, then gives up gracefully (returns None) — the pipeline never
crashes the app.
"""
import os
import shutil
import subprocess
from functools import lru_cache

W, H, FPS = 720, 1280, 24
INTRO, OUTRO = 2.5, 3.0
_BG = "0x050d05"          # near-black green, matches the CRT aesthetic
_GREEN = "0x39ff14"
_AMBER = "0xffb000"


@lru_cache(maxsize=8)
def _has_filter(ffmpeg: str, name: str) -> bool:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=20).stdout
        return any(line.split()[1:2] == [name]
                   for line in out.splitlines() if len(line.split()) > 1)
    except Exception:
        return False


def _ffmpeg_bin() -> str | None:
    if os.environ.get("FFMPEG_BIN"):
        return os.environ["FFMPEG_BIN"]
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:                                  # bundled static binary, last resort
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _font() -> str:
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(p):
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _textfile(work_dir: str, name: str, text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    path = os.path.join(work_dir, f"_txt_{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _drawtext(font: str, textfile: str, *, size: int, color: str, x: str, y: str,
              box: bool = False, shadow: bool = False) -> str:
    parts = [
        f"drawtext=fontfile={font}",
        f"textfile={textfile}",
        "expansion=none",
        f"fontcolor={color}",
        f"fontsize={size}",
        "line_spacing=14",
        f"x={x}", f"y={y}",
    ]
    if box:
        parts += ["box=1", "boxcolor=0x000000@0.45", "boxborderw=24"]
    if shadow:
        parts += ["shadowcolor=black@0.6", "shadowx=2", "shadowy=2"]
    return ":".join(parts)


def _build_cmd(ffmpeg, font, image_paths, durations, output_path, *,
               voice_path, music_path, texts, use_zoom) -> list[str]:
    inputs: list[str] = []
    for img, d in zip(image_paths, durations):
        inputs += ["-loop", "1", "-t", f"{d:.2f}", "-i", img]
    n = len(image_paths)
    voice_idx = music_idx = None
    ai = n
    if voice_path:
        inputs += ["-i", voice_path]; voice_idx = ai; ai += 1
    if music_path:
        inputs += ["-stream_loop", "-1", "-i", music_path]; music_idx = ai; ai += 1

    fc: list[str] = []
    vlabels: list[str] = []

    # ── intro card ──
    intro = f"color=c={_BG}:s={W}x{H}:r={FPS}:d={INTRO},format=yuv420p,setsar=1"
    if texts.get("title"):
        intro += "," + _drawtext(font, texts["title"], size=60, color=_GREEN,
                                 x="(w-text_w)/2", y="(h-text_h)/2", box=True)
    intro += f",fade=t=in:st=0:d=0.6,fade=t=out:st={INTRO-0.6:.2f}:d=0.6[v0]"
    fc.append(intro); vlabels.append("[v0]")

    # ── scene images ──
    for i, (img, d) in enumerate(zip(image_paths, durations)):
        s = (f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H},setsar=1")
        if use_zoom:
            frames = max(1, int(d * FPS))
            s += (f",zoompan=z='min(zoom+0.0006,1.12)':d={frames}"
                  f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
        fo = max(0.0, d - 0.4)
        s += f",format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={fo:.2f}:d=0.4[v{i+1}]"
        fc.append(s); vlabels.append(f"[v{i+1}]")

    # ── outro / CTA card ──
    oi = n + 1
    outro = f"color=c={_BG}:s={W}x{H}:r={FPS}:d={OUTRO},format=yuv420p,setsar=1"
    if texts.get("cta"):
        outro += "," + _drawtext(font, texts["cta"], size=50, color=_AMBER,
                                 x="(w-text_w)/2", y="(h-text_h)/2")
    outro += f",fade=t=in:st=0:d=0.6,fade=t=out:st={OUTRO-0.8:.2f}:d=0.8[v{oi}]"
    fc.append(outro); vlabels.append(f"[v{oi}]")

    # ── concat all video segments ──
    fc.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vc]")

    # ── watermark + sponsor banner overlays ──
    chain: list[str] = []
    if texts.get("watermark"):
        chain.append(_drawtext(font, texts["watermark"], size=26, color="white@0.5",
                               x="w-text_w-22", y="26", shadow=True))
    if texts.get("sponsor"):
        chain.append(f"drawbox=x=0:y=h-96:w=iw:h=96:color=0x000000@0.55:t=fill")
        chain.append(_drawtext(font, texts["sponsor"], size=30, color=_GREEN,
                               x="(w-text_w)/2", y="h-66"))
    if chain:
        fc.append("[vc]" + ",".join(chain) + "[vout]")
    else:
        fc.append("[vc]null[vout]")
    vout = "[vout]"

    # ── audio: voice + looped, ducked music ──
    alabels: list[str] = []
    if voice_idx is not None:
        fc.append(f"[{voice_idx}:a]aresample=44100[av]"); alabels.append("[av]")
    if music_idx is not None:
        fc.append(f"[{music_idx}:a]aresample=44100,volume=0.12[am]"); alabels.append("[am]")
    aout = None
    if len(alabels) == 2:
        fc.append("[av][am]amix=inputs=2:duration=longest:dropout_transition=0[aout]")
        aout = "[aout]"
    elif len(alabels) == 1:
        fc.append(f"{alabels[0]}anull[aout]"); aout = "[aout]"

    # Hard-cap the output to the exact video length. This is the authority on
    # duration: it guarantees termination even though the looped music is an
    # infinite input (`-shortest` proved unreliable with filtergraphs here).
    total = INTRO + OUTRO + sum(durations)

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(fc), "-map", vout]
    if aout:
        cmd += ["-map", aout]
    cmd += ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "28", "-pix_fmt", "yuv420p", "-threads", "1"]
    if aout:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd += ["-t", f"{total:.2f}", "-movflags", "+faststart", output_path]
    return cmd


def render_short(image_paths, durations, output_path, *, voice_path=None,
                 music_path=None, title="", cta="", watermark="", sponsor="",
                 work_dir=None) -> str | None:
    """Render a branded vertical Short. Returns output_path or None on failure."""
    image_paths = [p for p in (image_paths or []) if p and os.path.exists(p)]
    if not image_paths:
        return None
    durations = list(durations or [])[: len(image_paths)]
    while len(durations) < len(image_paths):
        durations.append(12.0)

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return None

    work_dir = work_dir or os.path.dirname(output_path) or "."
    os.makedirs(work_dir, exist_ok=True)
    font = _font()
    if _has_filter(ffmpeg, "drawtext"):
        texts = {
            "title": _textfile(work_dir, "title", title),
            "cta": _textfile(work_dir, "cta", cta),
            "watermark": _textfile(work_dir, "watermark", watermark),
            "sponsor": _textfile(work_dir, "sponsor", sponsor),
        }
    else:
        # ffmpeg built without freetype — render the video without text overlays
        print("[ffmpeg_render] drawtext unavailable; skipping text branding")
        texts = {"title": None, "cta": None, "watermark": None, "sponsor": None}

    # Ken Burns (zoompan) is gorgeous but CPU-heavy — opt in via BRAND_KENBURNS=1.
    # Default is the fast, reliable still+fade path so the free tier stays snappy.
    kb = os.environ.get("BRAND_KENBURNS", "").lower() in ("1", "true", "yes")
    attempts = (True, False) if kb else (False,)
    last_err = ""
    for use_zoom in attempts:
        cmd = _build_cmd(ffmpeg, font, image_paths, durations, output_path,
                         voice_path=voice_path, music_path=music_path,
                         texts=texts, use_zoom=use_zoom)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and os.path.exists(output_path) \
                    and os.path.getsize(output_path) > 0:
                return output_path
            last_err = r.stderr[-800:]
        except Exception as exc:
            last_err = str(exc)
    print(f"[ffmpeg_render] failed: {last_err}")
    return None
