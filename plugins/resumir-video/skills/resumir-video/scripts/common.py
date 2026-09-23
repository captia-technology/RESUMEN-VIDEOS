"""Shared core: FFmpeg execution, atomic publishing, identity, timeline, energy and warnings."""

import argparse
import array
import contextlib
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
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
EDGE_LOOK = 0.08
EDGE_WINDOW = 0.60
EDGE_SILENCE = 0.10
WORD_MARGIN = 0.02
WORD_PAD = 0.15
WORD_SHIFT = 1.0
WORD_ONSET = 0.5
FULL_SCALE = 32768.0 * 32768.0
SQUARES = []

TARGET = re.compile(r"^(?:(?P<pct>\d+(?:[.,]\d+)?)\s*(?:%|por\s?ciento)"
                    r"|(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>s|seg|segundos?|m|min|minutos?|h|horas?)"
                    r"|(?P<clock>\d{1,2}(?::\d{2}){1,2}(?:[.,]\d+)?))$")
UNITS = {"s": 1, "seg": 1, "segundo": 1, "segundos": 1, "m": 60, "min": 60, "minuto": 60,
         "minutos": 60, "h": 3600, "hora": 3600, "horas": 3600}
MEMORY_PATTERNS = ("Cannot allocate memory", "Out of memory", "av_buffer_alloc() failed")
BLOCKING = ("esenciales_superan_objetivo", "dependencia_excluida", "tema_sin_cubrir", "corte_vacio")
MAX_SPANS = 40
HISTORY_LIMIT = 4096
HISTORY_TEXT = 300
VERSION_ATTEMPTS = 3


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


def pictures(data):
    """Picture tracks that are real video: cover art is metadata, not footage."""
    return [s for s in data["streams"] if s["codec_type"] == "video"
            and not s.get("disposition", {}).get("attached_pic")]


def kind(data):
    """`video` (one picture track and audio) or `audio` (no picture track and audio)."""
    videos = pictures(data)
    if not any(s["codec_type"] == "audio" for s in data["streams"]):
        raise ValueError("El medio no tiene pista de audio: una grabación muda no se puede resumir "
                         "con este flujo; extrae fotogramas aparte o aporta el audio.")
    if len(videos) > 1:
        raise ValueError(f"El medio tiene {len(videos)} pistas de vídeo; normaliza la fuente a una sola "
                         "antes de resumirla.")
    return "video" if videos else "audio"


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


def publish(staged, final):
    """Atomic rename that never replaces: the destination must not exist."""
    staged, final = Path(staged), Path(final)
    if final.exists():
        raise ValueError(f"Ya está publicado y no se sobrescribe: {final}")
    # Windows refuses an existing destination by itself; the check above covers POSIX.
    os.rename(staged, final)


@contextlib.contextmanager
def lock(path):
    """Exclusive marker for one job folder: a second process fails instead of waiting."""
    path = Path(path)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError(f"Otro proceso está trabajando en esta carpeta ({path}); espera a que "
                         "termine, o borra ese archivo si quedó de una interrupción.") from None
    try:
        os.write(handle, f"{os.getpid()}\n".encode("utf-8"))
    finally:
        # Closed before yielding: Windows cannot remove a file that is still open.
        os.close(handle)
    try:
        yield path
    finally:
        # A marker that will not go must not hide the error of the body: the next lock() reports it.
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def shorten(value):
    """Copy of a record with every text trimmed, however deep it sits inside the payload."""
    if isinstance(value, str):
        return value[:HISTORY_TEXT - 1] + "…" if len(value) > HISTORY_TEXT else value
    if isinstance(value, dict):
        return {key: shorten(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shorten(item) for item in value]
    return value


def history(work, event, payload):
    """One append-only line per call; a diary never undoes the work it was only writing down."""
    moment = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        # The payload goes first: it may add fields but never rewrite the moment or the event.
        record = shorten({**payload, "cuando": moment, "evento": event})
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if len(line.encode("utf-8")) >= HISTORY_LIMIT:
            line = json.dumps({"cuando": moment, "evento": event,
                               "nota": "registro recortado por exceder 4 KiB"},
                              ensure_ascii=False, sort_keys=True)
        with (Path(work) / "historial.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
    except Exception:
        # Losing a line of the log never justifies losing a montage or a version already published,
        # not even to a RecursionError from a payload too deep (or circular) to trim.
        pass


def reserve_version(work, prefix):
    """Reserve the next N by creating `<prefix>-vN.json` exclusively; three attempts."""
    work = Path(work)
    pattern = re.compile(rf"{re.escape(prefix)}-v(\d+)\.json")
    used = [int(match.group(1)) for match in
            (pattern.fullmatch(path.name) for path in work.glob(f"{prefix}-v*.json")) if match]
    first = max(used, default=0) + 1
    for number in range(first, first + VERSION_ATTEMPTS):
        path = work / f"{prefix}-v{number}.json"
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return number, path
    raise ValueError(f"No se pudo reservar una versión de {prefix} tras {VERSION_ATTEMPTS} "
                     "intentos; otra sesión está escribiendo en la misma carpeta.")


def write_reserved(path, text):
    """Fill a version reserved by reserve_version: staged beside it and replaced atomically."""
    path = Path(path)
    staged = path.with_name(path.name + ".parcial")
    staged.write_text(text, encoding="utf-8", newline="\n")
    os.replace(staged, path)


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
        staged = cache.with_name(f"{cache.name}.{os.getpid()}.parcial")
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


def spoken(gap, words):
    """Pieces of a pause gap that no word needs.

    A quiet word («Pero», «Y») can stay under the threshold and look like a pause. The first
    WORD_ONSET of every word is kept, plus WORD_MARGIN around it; only its onset, because the
    transcriber often stretches a word's end over the pause that follows it.
    """
    pieces = [gap]
    for word in words:
        low = word["start"] - WORD_MARGIN
        high = min(word["end"], word["start"] + WORD_ONSET) + WORD_MARGIN
        pieces = [part for start, end in pieces
                  for part in ((start, min(end, low)), (max(start, high), end))
                  if part[1] - part[0] > 0]
    return pieces


def islands(levels, a, b, *, interval, origin, remove_pauses=True, threshold=SILENCE_DB,
            min_silence=MIN_SILENCE, margin=PAUSE_MARGIN, words=None):
    """Spans of [a, b) that survive removing pauses, snapped to the frame grid."""
    if remove_pauses:
        spans, cursor = [], a
        inside = [word for word in words or () if word["end"] > a and word["start"] < b]
        for start, end in silences(levels, a, b, threshold, min_silence):
            for gap in spoken((start + margin, end - margin), inside):
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


def nearest_silence(levels, edge, direction, limit, threshold):
    """Closest edge of a silence within EDGE_WINDOW of `edge`, or None when nothing qualifies.

    `direction` is -1 to search backward from `edge` (adjusting a cut's start) or +1 to search
    forward (adjusting its end). `limit`, when not None, is the neighbouring word's edge on that
    side: the result never lands closer to `edge` than `limit` plus WORD_MARGIN would allow.
    """
    # The search window grows by EDGE_SILENCE so a pause that starts before it still shows 0.1 s.
    if direction < 0:
        gaps = reversed(silences(levels, max(0.0, edge - EDGE_WINDOW - EDGE_SILENCE), edge,
                                 threshold, EDGE_SILENCE))
    else:
        gaps = silences(levels, edge, edge + EDGE_WINDOW + EDGE_SILENCE, threshold, EDGE_SILENCE)
    for gap in gaps:
        near = gap[1] if direction < 0 else gap[0]
        if direction < 0 and near < edge - EDGE_WINDOW:
            continue
        if direction > 0 and near > edge + EDGE_WINDOW:
            continue
        if limit is None:
            candidate = near
        elif direction < 0:
            candidate = max(near, limit + WORD_MARGIN)
        else:
            candidate = min(near, limit - WORD_MARGIN)
        if direction < 0 and candidate < edge:
            return round(candidate, 6)
        if direction > 0 and candidate > edge:
            return round(candidate, 6)
    return None


def word_edge(edge, words, side):
    """Border moved to the gap between words when the audio has no usable silence.

    `side` is -1 for a start and +1 for an end. An edge inside a word keeps that word when most of
    it falls inside the cut and drops it otherwise; the new edge sits in the gap next to the word,
    at most WORD_PAD from it. Returns the edge unchanged when it already lies between words, and
    None when no option stays within WORD_SHIFT of the original edge.
    """
    inside = next((word for word in words if word["start"] < edge < word["end"]), None)
    if inside is None:
        return edge
    before = max((word["end"] for word in words if word["end"] <= inside["start"]), default=None)
    after = min((word["start"] for word in words if word["start"] >= inside["end"]), default=None)
    ahead = inside["start"] - WORD_PAD if before is None else max((before + inside["start"]) / 2,
                                                                  inside["start"] - WORD_PAD)
    behind = inside["end"] + WORD_PAD if after is None else min((inside["end"] + after) / 2,
                                                                inside["end"] + WORD_PAD)
    kept = inside["end"] - edge if side < 0 else edge - inside["start"]
    keep = 2 * kept >= inside["end"] - inside["start"]
    # Keeping the word widens the cut (start earlier, end later); dropping it narrows the cut.
    options = ((max(0.0, ahead), behind) if side < 0 else (behind, ahead))
    for candidate in (options if keep else options[::-1]):
        if abs(candidate - edge) <= WORD_SHIFT:
            return round(candidate, 6)
    return None


def adjust_edges(a, b, levels, words, *, threshold=SILENCE_DB):
    """Move both edges out of speech; returns the pair and `borde_en_voz` when no gap is near.

    The first choice is a silence in the audio; when the background never drops below the
    threshold (a call with constant noise), the word marks place the edge between two words.
    """
    words = words or []
    note, start, end, by_word = None, a, b, []
    if voiced(levels, max(0.0, a - EDGE_LOOK), a, threshold):
        limit = max((word["end"] for word in words if word["end"] <= a), default=None)
        candidate = nearest_silence(levels, a, -1, limit, threshold)
        if candidate is None and words:
            candidate = word_edge(a, words, -1)
            if candidate is not None and candidate != a:
                by_word.append("start")
        if candidate is None:
            note = "borde_en_voz"
        else:
            start = candidate
    if voiced(levels, b, b + EDGE_LOOK, threshold):
        limit = min((word["start"] for word in words if word["start"] >= b), default=None)
        candidate = nearest_silence(levels, b, 1, limit, threshold)
        if candidate is None and words:
            candidate = word_edge(b, words, 1)
            if candidate is not None and candidate != b:
                by_word.append("end")
        if candidate is None:
            note = "borde_en_voz"
        else:
            end = candidate
    if by_word and end - start < 2 * WORD_PAD:
        # Dropping words can close a short cut: undo only the moves the word marks made.
        start = a if "start" in by_word else start
        end = b if "end" in by_word else end
        note = "borde_en_voz"
    return start, end, note


def frames_for(length, rate, speed):
    """N = round(L * F / v); ties go up, so the same length always yields the same count."""
    return max(0, math.floor(length * rate / speed + 0.5))


def samples_for(n_frames, rate, sample_rate):
    """M = round(N / F * SR): the audio that exactly covers N frames."""
    return max(0, math.floor(n_frames / rate * sample_rate + 0.5))


def plan_sha256(plan):
    """Canonical digest of a plan: the same content always yields the same value."""
    body = {key: value for key, value in plan.items() if key != "sha256"}
    text = json.dumps(body, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def warning(code, message, *, cut=None):
    """One entry of the warnings list; `bloquea` comes from BLOCKING, never from the caller."""
    return {"codigo": code, "mensaje": message, "corte": cut, "bloquea": code in BLOCKING}


def strip_accents(text):
    """Accent-free copy for searching; ñ is a letter of its own in Spanish and survives."""
    guarded = unicodedata.normalize("NFC", text).replace("ñ", "\x00").replace("Ñ", "\x01")
    plain = "".join(ch for ch in unicodedata.normalize("NFD", guarded)
                    if not unicodedata.combining(ch))
    return plain.replace("\x00", "ñ").replace("\x01", "Ñ")


def clock(value):
    """Reading stamp, truncated to the second: 752.3 -> 12:32, 3725 -> 1:02:05."""
    hours, rest = divmod(int(value), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def timeline(data):
    """Container start, grid, cadence and sample rate that the whole job shares (sections 3, 5)."""
    sounds = [stream for stream in data["streams"] if stream["codec_type"] == "audio"]
    if not sounds:
        raise ValueError("El medio no tiene pista de audio: no se puede analizar al ponente.")
    chosen = next((s for s in sounds if s["index"] == data.get("audio_stream")), sounds[0])
    line = {"start": timeline_start(data), "origin": 0.0, "rate": None, "fps": None,
            "interval": None, "sample_rate": int(chosen.get("sample_rate") or 0)}
    # Audio-only media keep the same six keys with no grid to fill; cover art is not footage.
    if not any(stream["codec_type"] == "video"
               and not stream.get("disposition", {}).get("attached_pic")
               for stream in data["streams"]):
        return line
    video = video_stream(data)
    rate = output_rate(video)
    interval = output_interval(rate)
    try:
        offset = float(video.get("start_time") or 0) - timeline_start(data)
    except (TypeError, ValueError):
        offset = 0.0
    if not math.isfinite(offset) or offset < 0:
        offset = 0.0
    return {**line, "origin": round(math.fmod(offset, interval), 9), "rate": rate,
            "fps": round(1 / interval, 9), "interval": interval}
