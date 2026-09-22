"""Local evidence extraction and deterministic editing; editorial choices belong to the calling agent."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys

# Set before the sibling modules load: the skill folder may live in a read-only plugin cache.
sys.dont_write_bytecode = True

import common
import plan
import render
from common import (DEFAULT_THREADS, MAX_FRAMES, MIN_PYTHON, cache_dir, duration, encoders, ffmpeg,
                    frame_count, frame_interval, identity, new_dir, output_rate, positive, probe,
                    require_encoders, run, save, seconds, seek_margin, stream_duration, stream_end,
                    streams, tag_seconds, timeline_start, tool, video_stream)

__version__ = "0.1.0"


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
    data = common.probe(args.video)
    data["kind"] = common.kind(data)
    common.duration(data)
    if data["kind"] == "video":
        reject_hdr(common.pictures(data)[0])
    sounds = [s for s in data["streams"] if s["codec_type"] == "audio"]
    if args.audio_stream is not None:
        sounds = [s for s in sounds if s["index"] == args.audio_stream]
        if not sounds:
            raise ValueError(f"No hay una pista de audio con el índice global {args.audio_stream}; "
                             "consulta probe.")
    audio = sounds[0]
    data["audio_stream"] = audio["index"]
    # Identity and fingerprint live together in `source`, the shape the published plan carries.
    data["source"] = {**data["source"], **common.fingerprint(data["source"]["path"])}
    # common.timeline answers both modes; in audio it leaves rate, fps and interval at null.
    data["timeline"] = common.timeline(data)
    if data["timeline"]["sample_rate"] <= 0:
        raise ValueError(f"La pista de audio {audio['index']} no declara una frecuencia de muestreo "
                         "válida; consulta probe y elige otra con --audio-stream.")
    data["avisos"] = packet_warnings(data)
    out = common.new_dir(args.work)
    # Job folders hold confidential frames and transcripts: keep them out of version control.
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    common.save(out / "metadata.json", data)
    common.ffmpeg("-i", data["source"]["path"], "-map", f"0:{audio['index']}",
                  "-vn", "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1",
                  "-c:a", "pcm_s16le", out / "audio.wav")
    common.energy(out / "audio.wav", out / "energia.f32")
    print(out)


PACKETS = 600
GAP_FACTOR = 1.5


def reject_hdr(picture):
    """HDR needs its own colour path: the standard montage would wash the picture out (section 12)."""
    transfer = picture.get("color_transfer")
    if transfer in common.HDR_TRANSFERS:
        raise ValueError(f"Fuente HDR ({transfer}): el montaje estándar no conserva su curva de "
                         "color. Convierte el original a SDR antes de resumirlo.")


def packet_times(path, index):
    """Presentation stamps of the first PACKETS packets of one track; the probe stops there."""
    report = json.loads(common.run(
        ["ffprobe", "-v", "error", "-select_streams", str(index), "-show_entries", "packet=pts_time",
         "-read_intervals", f"%+#{PACKETS}", "-of", "json", str(path)]))
    return sorted(float(packet["pts_time"]) for packet in report.get("packets") or []
                  if packet.get("pts_time") not in (None, "N/A"))


def packet_warnings(data):
    """Variable cadence and PTS gaps of the picture track, probed once and carried in metadata."""
    if data["kind"] == "audio":
        return []
    picture = common.pictures(data)[0]
    avisos = []
    if picture.get("avg_frame_rate") != picture.get("r_frame_rate"):
        avisos.append(common.warning(
            "fuente_vfr", f"La cadencia declarada no es constante (r_frame_rate "
            f"{picture.get('r_frame_rate')}, avg_frame_rate {picture.get('avg_frame_rate')}): el "
            "montaje fija F y normaliza con el filtro fps."))
    interval = data["timeline"]["interval"]
    times = packet_times(data["source"]["path"], picture["index"])
    # A gap of one interval is the normal spacing; 1,5 absorbs the rounding of the container.
    gaps = [round(b - a, 6) for a, b in zip(times, times[1:]) if b - a > GAP_FACTOR * interval]
    if gaps:
        avisos.append(common.warning(
            "huecos_pts", f"El sondeo de los primeros {len(times)} paquetes encuentra {len(gaps)} "
            f"saltos mayores de un fotograma (el mayor, {max(gaps):.3f} s): puede faltar imagen en "
            "el original."))
    return avisos


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


def show(args):
    """`probe`: every track and the file identity, as JSON on standard output."""
    print(json.dumps(probe(args.video), ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(prog="video.py", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="Comprueba Python, FFmpeg (libx264, AAC), faster-whisper y espacio libre; imprime JSON.")
    p.set_defaults(run=check)
    p = sub.add_parser("probe", help="Muestra en JSON todas las pistas y la identidad del archivo.")
    p.add_argument("video", help="Vídeo local.")
    p.set_defaults(run=show)
    p = sub.add_parser("prepare", help="Crea la carpeta de trabajo con metadata.json y audio.wav (16 kHz mono).")
    p.add_argument("video", help="Vídeo local.")
    p.add_argument("--work", required=True, help="Carpeta de trabajo nueva; se crea y no debe existir.")
    p.add_argument("--audio-stream", type=int,
                   help="Índice global de la pista de voz según probe (por defecto, la primera de audio).")
    p.set_defaults(run=prepare)
    p = sub.add_parser("frames", help="Extrae fotogramas JPEG en [start, end) cada step segundos, con index.json.")
    p.add_argument("video", help="Vídeo local.")
    p.add_argument("--out", required=True, help="Carpeta de salida nueva; se crea y no debe existir.")
    p.add_argument("--start", type=float, default=0, help="Inicio en segundos (por defecto 0).")
    p.add_argument("--end", type=float, help="Fin en segundos, excluido (por defecto, la duración).")
    p.add_argument("--step", type=float, default=15, help="Paso en segundos (por defecto 15).")
    p.add_argument("--width", type=int, default=1280,
                   help="Anchura máxima en píxeles; 0 conserva la resolución original (por defecto 1280).")
    p.set_defaults(run=frames)
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
    p.set_defaults(run=transcribe)
    plan.register(sub)
    render.register(sub)
    return parser


def main():
    for stream in (sys.stdout, sys.stderr):
        # Agents read piped output; the Windows default code page cannot encode every path.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    try:
        # check runs before the version guard, so its report can show python_ok: false.
        if args.command != "check" and sys.version_info < MIN_PYTHON:
            raise ValueError("Se requiere Python 3.10 o superior.")
        if args.command in ("probe", "prepare", "frames"):
            for executable in ("ffmpeg", "ffprobe"):
                if not tool(executable):
                    raise ValueError(f"Falta {executable} en PATH (se necesita el ejecutable, "
                                     "no un .cmd/.bat).")
        return args.run(args) or 0
    except MemoryError:
        print("Error: memoria insuficiente; usa un modelo menor, menos hilos o divide el trabajo.",
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrumpido; revisa las carpetas de salida incompletas.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, RuntimeError, AttributeError, TypeError,
            IndexError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
