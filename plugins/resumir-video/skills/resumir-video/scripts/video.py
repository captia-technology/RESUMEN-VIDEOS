"""Local evidence extraction and deterministic editing; editorial choices belong to the calling agent."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

__version__ = "0.1.0"

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


def check(args):
    # Diagnostic entry point: always prints the report, even when something is broken.
    report = {"version": __version__, "python": platform.python_version(),
              "python_ok": sys.version_info >= MIN_PYTHON, "platform": platform.platform()}
    for name in ("ffmpeg", "ffprobe"):
        report[name] = tool(name)
    report["ffmpeg_version"] = report["error"] = None
    report["libx264"] = report["aac"] = False
    try:
        if report["ffprobe"]:
            run(["ffprobe", "-hide_banner", "-version"])
        if report["ffmpeg"]:
            lines = run(["ffmpeg", "-hide_banner", "-version"]).splitlines()
            report["ffmpeg_version"] = lines[0] if lines else None
            available = encoders()
            report["libx264"], report["aac"] = "libx264" in available, "aac" in available
    except (OSError, ValueError) as exc:
        report["error"] = str(exc)
    try:
        from faster_whisper import WhisperModel  # noqa: F401
        report["faster_whisper"] = True
    except Exception:
        report["faster_whisper"] = False
    report["transcription_venv"] = str(cache_dir() / "venv")
    try:
        report["disk_free_gb"] = round(shutil.disk_usage(os.getcwd()).free / 1e9, 1)
    except OSError:
        report["disk_free_gb"] = None
    report["ok"] = report["error"] is None and all(
        report[key] for key in ("python_ok", "ffmpeg", "ffprobe", "libx264", "aac"))
    order = ("version", "python", "python_ok", "platform", "ffmpeg", "ffprobe", "ffmpeg_version",
             "libx264", "aac", "faster_whisper", "transcription_venv", "disk_free_gb", "error", "ok")
    print(json.dumps({key: report[key] for key in order}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def prepare(args):
    data = probe(args.video)
    _, audio = streams(data, args.audio_stream)
    out = new_dir(args.work)
    # Job folders hold confidential frames and transcripts: keep them out of version control.
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    data["audio_stream"] = audio["index"]
    save(out / "metadata.json", data)
    ffmpeg("-i", data["source"]["path"], "-map", f"0:{audio['index']}",
           "-vn", "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1",
           "-c:a", "pcm_s16le", out / "audio.wav")
    print(out)


def frame_count(start, end, step):
    """Samples in the half-open range [start, end); rounding absorbs float noise such as 0.24 / 0.04."""
    return max(1, math.ceil(round((end - start) / step, 9)))


def frames(args):
    data = probe(args.video)
    video = video_stream(data)
    total = duration(data)
    end = total if args.end is None else args.end
    if not all(math.isfinite(x) for x in (args.start, end, args.step)):
        raise ValueError("Tiempos no finitos.")
    if not 0 <= args.start < end <= total or args.step <= 0 or args.width < 0:
        raise ValueError(f"Intervalo, paso o anchura no válidos (duración: {total:.3f} s).")
    count = frame_count(args.start, end, args.step)
    if count > MAX_FRAMES:
        raise ValueError(f"Extrae como máximo {MAX_FRAMES} imágenes por llamada; "
                         "divide el análisis en bloques.")
    # Seeking at or beyond the last frame yields no image; use the last decodable instant.
    last = round(max(0.0, stream_end(data, video) - frame_interval(video)), 6)
    base, margin = timeline_start(data), seek_margin(data)
    out = new_dir(args.out)
    index = []
    scale = f",scale=w='min({args.width},iw)':h=-2" if args.width else ""
    for i in range(count):
        time = min(round(args.start + i * args.step, 6), last)
        target = out / f"frame-{i:04d}-{time:.3f}.jpg"
        # Decoding from before the target and selecting on the container's own timeline yields the
        # frame on screen at `time`, also when a variable-rate recording holds one frame for seconds
        # or the demuxer can only seek forward.
        ffmpeg("-ss", seconds(max(0.0, time - margin)), "-noaccurate_seek", "-copyts",
               "-i", data["source"]["path"], "-map", f"0:{video['index']}", "-frames:v", "1",
               "-vf", f"fps=1000:start_time={seconds(base + time)}{scale}", "-q:v", "2", target)
        if not target.exists():
            raise ValueError(f"No se obtuvo imagen en {time:.3f} s.")
        index.append({"time": time, "file": target.name})
    save(out / "index.json", {"source": data["source"], "frames": index})
    print(out / "index.json")


def transcribe(args):
    target = Path(args.out).resolve()
    if target.exists():
        raise ValueError("La transcripción de salida ya existe.")
    if not target.parent.is_dir():
        raise ValueError(f"No existe la carpeta de salida: {target.parent}")
    audio = identity(args.audio)
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise ValueError("Falta faster-whisper. Usa subtítulos existentes o instálalo en un entorno local.") from exc
    try:
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type,
                             cpu_threads=args.threads, num_workers=1,
                             local_files_only=not args.allow_download)
    except (OSError, ValueError) as exc:
        if args.allow_download or Path(args.model).is_dir():
            raise
        raise ValueError(f"El modelo {args.model} no está en la caché local: repite la orden con "
                         f"--allow-download o indica en --model una carpeta CTranslate2 local.\n{exc}") from exc
    parts, info = model.transcribe(audio["path"], language=args.language,
                                   beam_size=args.beam_size, vad_filter=not args.no_vad,
                                   word_timestamps=True)
    segments = []
    for part in parts:
        segments.append({"start": part.start, "end": part.end, "text": part.text,
                         "words": [{"start": w.start, "end": w.end, "text": w.word}
                                   for w in (part.words or [])]})
        print(f"Transcrito hasta {part.end:.1f} s", flush=True)
    if not segments:
        raise ValueError("No se detectó habla; revisa el audio y el contenido visual.")
    settings = {"model": args.model, "device": args.device, "compute_type": args.compute_type,
                "beam_size": args.beam_size, "vad_filter": not args.no_vad}
    save(target, {"language": info.language, "settings": settings, "segments": segments})


def validate_plan(plan, source, total):
    if plan.get("source") != source:
        planned = plan.get("source") if isinstance(plan.get("source"), dict) else {}
        changed = [key for key in ("path", "size", "mtime_ns") if planned.get(key) != source[key]]
        raise ValueError(f"El plan no corresponde al archivo actual (difiere: {', '.join(changed) or 'source'}). "
                         "Copia source de metadata.json; si es el mismo vídeo pero movido, copiado o con otra "
                         "fecha de modificación, cópialo de un probe nuevo de ese archivo.")
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("El plan requiere segmentos.")
    previous = 0.0
    for number, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"El corte {number} debe ser un objeto.")
        start, end = segment.get("start"), segment.get("end")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)):
            raise ValueError(f"Los tiempos del corte {number} deben ser segundos numéricos finitos.")
        if not previous <= start < end <= total:
            raise ValueError(f"El corte {number} está desordenado, solapado o fuera de la pista de vídeo "
                             f"(termina en {total:.3f} s).")
        for key in ("title", "reason", "audio_evidence", "visual_evidence"):
            if not isinstance(segment.get(key), str) or not segment[key].strip():
                raise ValueError(f"Falta {key} en el corte {number}.")
        previous = end
    return segments


def stamp(value):
    millis = round(value * 1000)
    hours, rest = divmod(millis, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def listing(path, names):
    path.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")


def verify(path, expected, threads):
    result = probe(path)
    video, audio = streams(result)
    lengths = [stream_duration(result, video), stream_duration(result, audio)]
    if abs(lengths[0] - expected) > 0.25 or abs(lengths[0] - lengths[1]) > 0.1:
        raise ValueError(f"Duración final inesperada (vídeo {lengths[0]:.3f} s, audio "
                         f"{lengths[1]:.3f} s, esperado {expected:.3f} s).")
    ffmpeg("-xerror", "-threads", str(threads), "-i", path,
           "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")
    return duration(result)


def render(args):
    data = probe(args.video)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
    if not isinstance(plan, dict):
        raise ValueError("El plan debe ser un objeto JSON.")
    if type(plan.get("audio_stream")) is not int:
        raise ValueError("Selecciona audio_stream con el índice global de la pista de voz.")
    video, audio = streams(data, plan["audio_stream"])
    segments = validate_plan(plan, data["source"], stream_end(data, video))
    if video.get("color_transfer") in HDR_TRANSFERS:
        raise ValueError("Fuente HDR: requiere una ruta de color específica antes del montaje estándar.")
    require_encoders("libx264", "aac")
    source, threads, rate = data["source"]["path"], str(args.threads), output_rate(video)
    base, margin, interval = timeline_start(data), seek_margin(data), output_interval(rate)
    guarded = margin == FORWARD_MARGIN
    out = new_dir(args.out)
    save(out / "seleccion.json", plan)
    rows = []
    elapsed = 0.0
    try:
        # ignore_cleanup_errors: on Windows an interrupted child may still hold a file; keep the
        # KeyboardInterrupt instead of replacing it with a cleanup error.
        with tempfile.TemporaryDirectory(prefix="cortes-", dir=out, ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            names = [f"clip-{i:05d}" for i in range(len(segments))]
            for i, (segment, name) in enumerate(zip(segments, names)):
                clip = folder / f"{name}.mp4"
                length = segment["end"] - segment["start"]
                seek = max(0.0, segment["start"] - margin)
                landed = landing(data, video, seek, args.threads) if guarded else None
                if landed is not None and landed > base + segment["start"] + 1e-6:
                    raise ValueError(
                        f"El corte {i + 1} ({segment['start']:.3f}–{segment['end']:.3f} s) no se puede "
                        f"situar: tras buscar en {seek:.3f} s, el contenedor entrega el primer fotograma "
                        f"{landed - base - segment['start']:.3f} s más tarde (fotogramas clave muy "
                        "espaciados y búsqueda solo hacia delante). Convierte la fuente a MP4 o MKV.")
                # Constant-rate output from the frame closest to `start` (at most half a frame away),
                # decoding from before it and selecting on the container's own timeline: joins stay in
                # sync, held frames of variable-rate sources survive and forward-only demuxers work.
                ffmpeg("-threads", threads, "-ss", seconds(seek), "-noaccurate_seek", "-copyts",
                       "-i", source, "-t", seconds(length),
                       "-map", f"0:{video['index']}", "-an", "-sn", "-dn",
                       "-map_metadata", "-1", "-map_chapters", "-1",
                       "-vf", f"fps={rate}:start_time={seconds(base + segment['start'])},"
                              "setpts=PTS-STARTPTS,pad=ceil(iw/2)*2:ceil(ih/2)*2",
                       "-filter_threads", threads, "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                       # Without B-frames every clip has DTS == PTS, so the concatenation below stays
                       # monotonic: mixing reorder delays truncated short cuts.
                       "-bf", "0", "-pix_fmt", "yuv420p", "-threads", threads, clip)
                try:
                    actual = duration(probe(clip))
                except ValueError:
                    actual = 0.0
                if actual <= 0 or actual < length - 2 * interval:
                    raise ValueError(f"El corte {i + 1} ({segment['start']:.3f}–{segment['end']:.3f} s) "
                                     f"solo produjo {actual:.3f} s de vídeo.")
                # Audio is cut to the exact rendered video length and kept as PCM, so the
                # single AAC encode below has no per-clip priming overlap or drift at joins.
                ffmpeg("-ss", seconds(segment["start"]), "-i", source, "-t", seconds(actual),
                       "-map", f"0:{audio['index']}", "-vn", "-sn", "-dn", "-map_metadata", "-1",
                       "-af", "aresample=async=1:first_pts=0,apad", "-c:a", "pcm_s24le",
                       folder / f"{name}.wav")
                rows.append((segment, elapsed, elapsed + actual))
                elapsed += actual
                print(f"Corte {i + 1}/{len(segments)}", flush=True)
            listing(folder / "video.txt", [f"{name}.mp4" for name in names])
            listing(folder / "audio.txt", [f"{name}.wav" for name in names])
            staged = folder / "resumen.mp4"
            # Relative names run from the folder: the concat demuxer parses list paths as URLs ('#', '?').
            ffmpeg("-f", "concat", "-safe", "1", "-i", "video.txt",
                   "-f", "concat", "-safe", "1", "-i", "audio.txt",
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                   "-c:a", "aac", "-b:a", "192k", "-threads", threads,
                   "-movflags", "+faststart", staged.name, cwd=folder)
            final_duration = verify(staged, elapsed, args.threads)
            target = out / "resumen.mp4"
            staged.rename(target)
    except (ValueError, OSError) as exc:
        raise ValueError(f"{exc}\nSalida incompleta en {out}; corrige el motivo y usa otra carpeta.") from exc
    total = duration(data)
    lines = ["# Resumen de vídeo", "", f"Origen: `{Path(source).name}`", "",
             f"Duración original: {stamp(total)}. Final: {stamp(final_duration)}. "
             f"Reducción: {100 * (1 - final_duration / total):.1f}%. Cortes: {len(segments)}.", "",
             "| Origen | Salida | Tema |", "| --- | --- | --- |"]
    for segment, start, end in rows:
        title = segment["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {stamp(segment['start'])}–{stamp(segment['end'])} | "
                     f"{stamp(start)}–{stamp(end)} | {title} |")
    lines += ["", "Validación técnica: pistas presentes, duraciones de vídeo y audio coherentes "
              "y decodificación completa verificadas.", "",
              "Revisión editorial pendiente: completar tras revisar audio, imágenes, uniones y cobertura.",
              "Indicar aquí los temas conservados y las limitaciones reales de la revisión.", ""]
    (out / "resumen.md").write_text("\n".join(lines), encoding="utf-8")
    print(target)


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("debe ser un entero positivo")
    return number


def build_parser():
    parser = argparse.ArgumentParser(prog="video.py", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Comprueba Python, FFmpeg (libx264, AAC), faster-whisper y espacio libre; imprime JSON.")
    p = sub.add_parser("probe", help="Muestra en JSON todas las pistas y la identidad del archivo.")
    p.add_argument("video", help="Vídeo local.")
    p = sub.add_parser("prepare", help="Crea la carpeta de trabajo con metadata.json y audio.wav (16 kHz mono).")
    p.add_argument("video", help="Vídeo local.")
    p.add_argument("--work", required=True, help="Carpeta de trabajo nueva; se crea y no debe existir.")
    p.add_argument("--audio-stream", type=int,
                   help="Índice global de la pista de voz según probe (por defecto, la primera de audio).")
    p = sub.add_parser("frames", help="Extrae fotogramas JPEG en [start, end) cada step segundos, con index.json.")
    p.add_argument("video", help="Vídeo local.")
    p.add_argument("--out", required=True, help="Carpeta de salida nueva; se crea y no debe existir.")
    p.add_argument("--start", type=float, default=0, help="Inicio en segundos (por defecto 0).")
    p.add_argument("--end", type=float, help="Fin en segundos, excluido (por defecto, la duración).")
    p.add_argument("--step", type=float, default=15, help="Paso en segundos (por defecto 15).")
    p.add_argument("--width", type=int, default=1280,
                   help="Anchura máxima en píxeles; 0 conserva la resolución original (por defecto 1280).")
    p = sub.add_parser("transcribe", help="Transcribe con faster-whisper y marcas por palabra (opcional).")
    p.add_argument("audio", help="Audio local, normalmente audio.wav de prepare.")
    p.add_argument("--out", required=True, help="JSON de salida nuevo; su carpeta debe existir.")
    p.add_argument("--model", default="small",
                   help="Nombre de modelo o carpeta CTranslate2 local (por defecto small).")
    p.add_argument("--language", help="Código de idioma, p. ej. es (por defecto, detección automática).")
    p.add_argument("--allow-download", action="store_true",
                   help="Permite descargar el modelo; sin esta opción solo se usan modelos locales o cacheados.")
    p.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"),
                   help="Dispositivo de inferencia (por defecto cpu).")
    p.add_argument("--compute-type", default="int8",
                   help="Tipo de cálculo de CTranslate2, p. ej. int8 o float16 (por defecto int8).")
    p.add_argument("--beam-size", type=positive, default=1, help="Tamaño de haz (por defecto 1).")
    p.add_argument("--no-vad", action="store_true",
                   help="Desactiva el filtro VAD (útil para recuperar habla omitida).")
    p.add_argument("--threads", type=positive, default=DEFAULT_THREADS,
                   help=f"Hilos de CPU (por defecto {DEFAULT_THREADS}).")
    p = sub.add_parser("render", help="Monta resumen.mp4, seleccion.json y resumen.md a partir de un plan.")
    p.add_argument("video", help="Vídeo local original.")
    p.add_argument("--plan", required=True, help="seleccion.json con source, audio_stream y segments.")
    p.add_argument("--out", required=True, help="Carpeta de salida nueva; se crea y no debe existir.")
    p.add_argument("--threads", type=positive, default=DEFAULT_THREADS,
                   help=f"Hilos de codificación (por defecto {DEFAULT_THREADS}).")
    return parser


def main():
    for stream in (sys.stdout, sys.stderr):
        # Agents read piped output; the Windows default code page cannot encode every path.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            # Before the version guard, so the report can show python_ok: false.
            return check(args)
        if sys.version_info < MIN_PYTHON:
            raise ValueError("Se requiere Python 3.10 o superior.")
        if args.command in ("probe", "prepare", "frames", "render"):
            for executable in ("ffmpeg", "ffprobe"):
                if not tool(executable):
                    raise ValueError(f"Falta {executable} en PATH (se necesita el ejecutable, "
                                     "no un .cmd/.bat).")
        if args.command == "probe":
            print(json.dumps(probe(args.video), ensure_ascii=False, indent=2))
        else:
            {"prepare": prepare, "frames": frames, "transcribe": transcribe,
             "render": render}[args.command](args)
    except MemoryError:
        print("Error: memoria insuficiente; usa un modelo menor, menos hilos o divide el trabajo.",
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrumpido; revisa las carpetas de salida incompletas.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
