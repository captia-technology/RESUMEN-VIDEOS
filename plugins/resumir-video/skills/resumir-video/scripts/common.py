"""Shared core: FFmpeg execution, atomic publishing, identity, timeline, energy and warnings."""

import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

MIN_PYTHON = (3, 10)
MAX_FRAMES = 600
HDR_TRANSFERS = ("smpte2084", "arib-std-b67")
SEEK_MARGIN = 3.0
# Demuxers without an index seek forward to the next keyframe, so they need a wider margin.
FORWARD_SEEK = ("mpegts", "mpegtsraw", "mpeg", "m2ts", "mts")
FORWARD_MARGIN = 10.0
DEFAULT_THREADS = min(4, os.cpu_count() or 1)
TOLERANCE_RATIO = 0.05
TOLERANCE_FLOOR = 10.0
CHUNK = 4 * 1024 * 1024
SILENCE_DB = -50.0
MIN_SILENCE = 0.30
ENERGY_STEP = 0.01
ENERGY_FLOOR = -120.0
ENERGY_BLOCK = 600
PAUSE_MARGIN = 0.08
MIN_ISLAND = 0.12
MIN_EDGE_ISLAND = 0.20
FULL_SCALE = 32768.0 * 32768.0
SQUARES = []

TARGET = re.compile(r"^(?:(?P<pct>\d+(?:[.,]\d+)?)\s*(?:%|por\s?ciento)"
                    r"|(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>s|seg|segundos?|m|min|minutos?|h|horas?)"
                    r"|(?P<clock>\d{1,2}(?::\d{2}){1,2}(?:[.,]\d+)?))$")
UNITS = {"s": 1, "seg": 1, "segundo": 1, "segundos": 1, "m": 60, "min": 60, "minuto": 60,
         "minutos": 60, "h": 3600, "hora": 3600, "horas": 3600}


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


def parse_target(text, total):
    """Target output length in seconds from '10%', '720s', '12min' or '0:12:00'; None when absent."""
    if text is None:
        return None
    clean = " ".join(str(text).split()).lower()
    if not clean or clean in ("ninguno", "sin objetivo"):
        return None
    match = TARGET.match(clean)
    if not match:
        raise ValueError(f"Objetivo ambiguo: «{text}». Indica un porcentaje (10%), una duración "
                         "(720s, 12min) o un tiempo (0:12:00).")
    if match["pct"] is not None:
        percent = float(match["pct"].replace(",", "."))
        if not 0 < percent < 100:
            raise ValueError("El porcentaje del objetivo debe estar entre 0 y 100 "
                             f"(recibido {percent:g}).")
        value = total * percent / 100
    elif match["num"] is not None:
        value = float(match["num"].replace(",", ".")) * UNITS[match["unit"]]
    else:
        value = 0.0
        for part in match["clock"].replace(",", ".").split(":"):
            value = value * 60 + float(part)
    value = round(value, 3)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Objetivo no válido: «{text}».")
    if value >= total:
        raise ValueError(f"El objetivo ({value:.1f} s) no es menor que el original ({total:.1f} s).")
    return value


def tolerance(target):
    """Half-width of the acceptance band around a target, never narrower than ten seconds."""
    return max(TOLERANCE_RATIO * target, TOLERANCE_FLOOR)


def fingerprint(path):
    """Identity that survives a move: size, mtime and a hash of the first and last 4 MiB."""
    path = Path(path).resolve(strict=True)
    info = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if info.st_size <= 2 * CHUNK:
            # Read whole below 8 MiB: hashing only the ends would skip the middle of these files.
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                digest.update(block)
        else:
            digest.update(stream.read(CHUNK))
            stream.seek(-CHUNK, os.SEEK_END)
            digest.update(stream.read(CHUNK))
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": digest.hexdigest()}


def squares():
    """Square of every 16-bit sample read as unsigned, so the RMS loop stays inside C calls."""
    if not SQUARES:
        SQUARES.extend(value * value for value in range(32768))
        SQUARES.extend((value - 65536) * (value - 65536) for value in range(32768, 65536))
    return SQUARES


def levels_of(sound, window):
    """dBFS of every `window` frames of an open mono 16-bit wave, read block by block."""
    table, levels, pending = squares().__getitem__, array.array("f"), b""
    while True:
        raw = sound.readframes(window * ENERGY_BLOCK)
        if not raw:
            return levels
        pending += raw
        # Whole windows only: the remainder is carried over so the grid never drifts.
        usable = len(pending) - len(pending) % (2 * window)
        block = array.array("H")
        block.frombytes(pending[:usable])
        if sys.byteorder == "big":
            block.byteswap()
        pending = pending[usable:]
        for start in range(0, len(block), window):
            mean = sum(map(table, block[start:start + window])) / window
            levels.append(ENERGY_FLOOR if mean <= 0
                          else max(ENERGY_FLOOR, 10 * math.log10(mean / FULL_SCALE)))


def energy(wav_path, cache_path=None):
    """RMS level in dBFS every 10 ms; cached, and never loading the whole recording."""
    cache = Path(cache_path) if cache_path is not None else None
    with wave.open(str(wav_path), "rb") as sound:
        if sound.getsampwidth() != 2 or sound.getnchannels() != 1:
            raise ValueError("La energía se calcula sobre el audio de análisis mono PCM de 16 bits "
                             "que crea prepare.")
        window = max(1, round(sound.getframerate() * ENERGY_STEP))
        expected = sound.getnframes() // window
        if cache is not None and cache.is_file():
            cached, data = array.array("f"), cache.read_bytes()
            if len(data) == expected * cached.itemsize:
                cached.frombytes(data)
                return cached
        levels = levels_of(sound, window)
    if cache is not None:
        # os.replace (not os.rename) also repairs a wrong-size cache: on Windows, rename
        # fails with FileExistsError when the destination is already there.
        staged = cache.with_name(cache.name + ".parcial")
        staged.write_bytes(levels.tobytes())
        os.replace(staged, cache)
    return levels


def bounds(levels, a, b):
    """[a, b) seconds as indices of the 10 ms grid, clipped to what `levels` actually covers."""
    # The epsilons keep 1.16 s (115.999… steps) from opening a window one index too early or wide.
    first = max(0, int(a / ENERGY_STEP + 1e-9))
    last = min(len(levels), math.ceil(b / ENERGY_STEP - 1e-9))
    return first, last


def silences(levels, a, b, threshold=SILENCE_DB, min_silence=MIN_SILENCE):
    """Stretches of [a, b) whose level never reaches `threshold` and last at least `min_silence`."""
    first, last = bounds(levels, a, b)
    runs, start = [], None
    for index in range(first, last):
        if levels[index] < threshold:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, last))
    found = []
    for x, y in runs:
        low, high = max(a, x * ENERGY_STEP), min(b, y * ENERGY_STEP)
        if high - low >= min_silence - 1e-9:
            # max/min return the int operand unchanged on a tie with a/b; force float,
            # since the declared contract is list[tuple[float, float]] and this reaches JSON.
            found.append((round(float(low), 6), round(float(high), 6)))
    return found


def voiced(levels, a, b, threshold=SILENCE_DB):
    """True when any 10 ms window of [a, b) reaches `threshold`."""
    first, last = bounds(levels, a, b)
    return any(levels[index] >= threshold for index in range(first, last))


def snap(t, interval, origin):
    """Nearest instant of the frame grid; ties go up so the same value always lands the same way."""
    steps = math.floor((t - origin) / interval + 0.5)
    return round(origin + steps * interval, 6)


def islands(levels, a, b, *, interval, origin, remove_pauses=True, threshold=SILENCE_DB,
            min_silence=MIN_SILENCE, margin=PAUSE_MARGIN):
    """Spans of [a, b) that survive removing pauses, snapped to the frame grid."""
    if remove_pauses:
        spans, cursor = [], a
        for start, end in silences(levels, a, b, threshold, min_silence):
            gap = (start + margin, end - margin)
            if gap[1] - gap[0] <= 0:
                continue
            if gap[0] > cursor:
                spans.append([cursor, gap[0]])
            cursor = max(cursor, gap[1])
        if b > cursor:
            spans.append([cursor, b])
        spans = [span for span in spans if span[1] - span[0] >= MIN_ISLAND - 1e-9]
        while spans and spans[0][1] - spans[0][0] < MIN_EDGE_ISLAND - 1e-9:
            spans.pop(0)
        while spans and spans[-1][1] - spans[-1][0] < MIN_EDGE_ISLAND - 1e-9:
            spans.pop()
    else:
        # §7.4: a visual_only cut keeps its pauses, so nothing is dropped for being short here.
        spans = [[a, b]]
    grid = []
    for start, end in spans:
        low, high = snap(start, interval, origin), snap(end, interval, origin)
        if high - low < interval - 1e-9:
            continue
        if grid and low - grid[-1][1] < interval - 1e-9:
            grid[-1][1] = high
        else:
            grid.append([low, high])
    return grid
