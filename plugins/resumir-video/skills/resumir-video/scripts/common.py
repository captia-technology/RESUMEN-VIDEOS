"""Shared core: FFmpeg execution, atomic publishing, identity, timeline, energy and warnings."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 10)
MAX_FRAMES = 600
HDR_TRANSFERS = ("smpte2084", "arib-std-b67")
SEEK_MARGIN = 3.0
# Demuxers without an index seek forward to the next keyframe, so they need a wider margin.
FORWARD_SEEK = ("mpegts", "mpegtsraw", "mpeg", "m2ts", "mts")
FORWARD_MARGIN = 10.0
DEFAULT_THREADS = min(4, os.cpu_count() or 1)


def tool(name):
    """Absolute path of an FFmpeg program that can be started without a shell, or None."""
    # On Windows a .cmd/.bat shim cannot be launched safely without cmd.exe: only real executables count.
    return shutil.which(f"{name}.exe" if os.name == "nt" else name)


def run(args, cwd=None):
    args = [str(x) for x in args]
    if args[0] in ("ffmpeg", "ffprobe"):
        args[0] = tool(args[0]) or args[0]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd) as process:
        try:
            stdout, stderr = process.communicate()
        except BaseException:
            # Wait for the child so Windows releases its files before temporary folders are removed.
            process.kill()
            process.wait()
            raise
    if process.returncode:
        raise ValueError(f"{Path(args[0]).stem} falló (código {process.returncode}):\n{stderr[-4000:]}".rstrip())
    return stdout


def ffmpeg(*args, cwd=None):
    return run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", *args], cwd=cwd)


def save(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def seconds(value):
    # str(float) may produce exponents such as 1e-05, which ffmpeg rejects.
    return f"{value:.6f}"


def identity(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("La entrada debe ser un archivo local.")
    info = path.stat()
    return {"path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def probe(path):
    source = identity(path)
    data = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", source["path"]]))
    data["source"] = source
    return data


def duration(data):
    try:
        value = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Duración desconocida o no válida.") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Duración desconocida o no válida.")
    return value


def tag_seconds(stream):
    """Matroska/WebM expose a track length only as a DURATION tag (HH:MM:SS.nnnnnnnnn)."""
    for key, text in (stream.get("tags") or {}).items():
        if key.upper() == "DURATION" or key.upper().startswith("DURATION-"):
            try:
                hours, minutes, secs = str(text).strip().split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(secs)
            except ValueError:
                return None
    return None


def stream_duration(data, stream):
    """Duration of one stream, bounded by the container; falls back to the container."""
    total = duration(data)
    try:
        value = float(stream.get("duration"))
    except (TypeError, ValueError):
        value = tag_seconds(stream)
    if value is None or not math.isfinite(value) or value <= 0:
        return total
    return min(value, total)


def stream_end(data, stream):
    """Where one stream ends on the timeline used by `ffmpeg -ss` (relative to the container start)."""
    try:
        offset = float(stream.get("start_time") or 0) - float(data["format"].get("start_time") or 0)
    except (TypeError, ValueError):
        offset = 0.0
    if not math.isfinite(offset) or offset < 0:
        offset = 0.0
    return min(offset + stream_duration(data, stream), duration(data))


def timeline_start(data):
    """Absolute timestamp that `ffmpeg -ss 0` refers to: the container adds its own start."""
    try:
        value = float(data["format"].get("start_time"))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def seek_margin(data):
    """Seconds decoded before a target so the frame on screen at it is always available."""
    names = str(data["format"].get("format_name", "")).split(",")
    return FORWARD_MARGIN if any(name in FORWARD_SEEK for name in names) else SEEK_MARGIN


def landing(data, video, seek, threads=1):
    """Absolute time of the first frame decoded after seeking, or None if it cannot be read."""
    # showinfo logs to stderr, so this call cannot go through run().
    args = [tool("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin",
            "-threads", str(threads), "-ss", seconds(seek), "-noaccurate_seek", "-copyts",
            "-i", data["source"]["path"], "-map", f"0:{video['index']}", "-an", "-sn", "-dn",
            "-frames:v", "1", "-vf", "showinfo", "-f", "null", "-"]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for token in result.stderr.split():
        if token.startswith("pts_time:"):
            try:
                return float(token.partition(":")[2])
            except ValueError:
                return None
    return None


def rate_of(video, key):
    num, _, den = str(video.get(key, "")).partition("/")
    try:
        rate = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def frame_interval(video):
    rate = rate_of(video, "avg_frame_rate") or rate_of(video, "r_frame_rate")
    return 1 / rate if rate else 0.1


def output_rate(video):
    """Constant rate for rendered cuts: the stream's base rate when plausible."""
    for key in ("r_frame_rate", "avg_frame_rate"):
        rate = rate_of(video, key)
        if rate and rate <= 120:
            return video[key]
    return "30"


def output_interval(rate):
    """Seconds per frame of the constant rate that output_rate returned."""
    num, _, den = str(rate).partition("/")
    return float(den or 1) / float(num)


def video_stream(data):
    videos = [s for s in data["streams"] if s["codec_type"] == "video"
              and not s.get("disposition", {}).get("attached_pic")]
    if len(videos) != 1:
        raise ValueError("Se requiere exactamente una pista de vídeo; selecciona una fuente normalizada.")
    return videos[0]


def streams(data, audio_index=None):
    video = video_stream(data)
    audios = [s for s in data["streams"] if s["codec_type"] == "audio"]
    if audio_index is not None:
        audios = [s for s in audios if s["index"] == audio_index]
    if not audios:
        raise ValueError("No hay una pista de audio válida para analizar al ponente.")
    return video, audios[0]


def encoders():
    lines = run(["ffmpeg", "-hide_banner", "-encoders"]).splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("---")), -1)
    return {line.split()[1] for line in lines[start + 1:] if len(line.split()) > 1}


def require_encoders(*names):
    missing = [name for name in names if name not in encoders()]
    if missing:
        raise ValueError(f"FFmpeg no incluye {', '.join(missing)}; instala una compilación "
                         "con libx264 y AAC (ejecuta el subcomando check).")


def cache_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "resumir-video"


def new_dir(path):
    path = Path(path).resolve()
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError("La carpeta ya existe y no se sobrescribe; indica una carpeta nueva "
                         f"(p. ej., con el sufijo -2): {path}") from None
    return path


def frame_count(start, end, step):
    """Samples in the half-open range [start, end); rounding absorbs float noise such as 0.24 / 0.04."""
    return max(1, math.ceil(round((end - start) / step, 9)))


def stamp(value):
    millis = round(value * 1000)
    hours, rest = divmod(millis, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def listing(path, names):
    path.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("debe ser un entero positivo")
    return number
