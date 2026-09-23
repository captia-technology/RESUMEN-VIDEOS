"""Local evidence extraction and deterministic editing; editorial choices belong to the calling agent."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
import time

# Set before the sibling modules load: the skill folder may live in a read-only plugin cache.
sys.dont_write_bytecode = True

import common
import plan
import render
import doc
from common import (DEFAULT_THREADS, MAX_FRAMES, MIN_PYTHON, cache_dir, duration, encoders, ffmpeg,
                    frame_count, frame_interval, identity, new_dir, output_rate, positive, probe,
                    require_encoders, run, save, seconds, seek_margin, stream_duration, stream_end,
                    streams, tag_seconds, timeline_start, tool, video_stream)

__version__ = "0.1.0"

BLOCK = 600.0
SHEET = 5
SHEET_WIDTH = 160
INDEX_SIDE = 64


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


def block_name(start):
    """Folder of a sweep block, named after its first second."""
    return f"b{int(start):05d}"


def sheet_count(frames, side=SHEET):
    return max(1, math.ceil(frames / (side * side)))


def space_needed(frames):
    """Bytes to reserve for a sweep: 1 MB per view, the upper bound of the reference."""
    return frames * 1_000_000


def sweep_blocks(start, end, step, *, length=BLOCK):
    """Blocks of about `length` seconds aligned to the sampling grid: (start, end, frames)."""
    span = max(step, math.floor(length / step) * step)
    blocks, a = [], float(start)
    while a < end:
        b = min(float(end), a + span)
        blocks.append((round(a, 6), round(b, 6), frame_count(a, b, step)))
        a = b
    return blocks


def sweep_block(data, stream, folder, a, b, step, width, *, threads=1):
    """One FFmpeg process per block: JPEG views, gray index and contact sheets."""
    count = frame_count(a, b, step)
    base, margin = timeline_start(data), seek_margin(data)
    scale = f"scale=w='min({width},iw)':h=-2" if width else "null"
    # The rate has to stay an exact ratio and the rounding has to be `up`: 1/15 written as 0.066667
    # shifts the grid, and the default rounding returns the last frame of each bucket, about half a
    # step later. Both were measured against a source whose luminance encodes its own instant.
    graph = (f"[0:{stream['index']}]fps=1/{seconds(step)}:"
             f"start_time={seconds(base + a)}:round=up,split=3[j][g][t];"
             f"[j]{scale}[jo];"
             f"[g]scale={INDEX_SIDE}:{INDEX_SIDE},format=gray[go];"
             f"[t]scale={SHEET_WIDTH}:-2,tile={SHEET}x{SHEET}:padding=2:margin=2[to]")
    # No -t and no -to: with -copyts both cut the block short. The frame counts bound the work.
    ffmpeg("-threads", threads, "-ss", seconds(max(0.0, a - margin)),
           "-noaccurate_seek", "-copyts", "-i", data["source"]["path"],
           "-filter_complex", graph,
           "-map", "[jo]", "-frames:v", count, "-q:v", "2", "-start_number", "0",
           folder / "frame-%04d.jpg",
           "-map", "[go]", "-frames:v", count, "-f", "rawvideo", "-pix_fmt", "gray",
           folder / "indice.gray",
           "-map", "[to]", "-frames:v", sheet_count(count), "-q:v", "3", "-start_number", "0",
           folder / "hoja-%03d.jpg")
    images = sorted(folder.glob("frame-*.jpg"))
    index = folder / "indice.gray"
    # FFmpeg exits 0 when an instant falls past the last frame, so the count is checked here.
    if len(images) != count or index.stat().st_size != count * INDEX_SIDE * INDEX_SIDE:
        raise ValueError(f"El bloque {a:.3f}-{b:.3f} s produjo {len(images)} de {count} imágenes; "
                         "ajusta el intervalo al final real de la pista de vídeo.")
    return {"start": a, "end": b, "step": step,
            "frames": [{"time": round(a + i * step, 6), "file": image.name}
                       for i, image in enumerate(images)]}


def clear_partial(folder):
    """A block with a valid index.json is kept; anything else is set aside so it can be redone."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    marker = folder / "index.json"
    if marker.is_file():
        try:
            json.loads(marker.read_text(encoding="utf-8"))
            return folder
        except (OSError, ValueError):
            pass  # truncated or corrupt: treat as unfinished, fall through to reset
    # Nothing is deleted: the images already taken stay available to the agent.
    spare, number = folder.with_name(f"{folder.name}.parcial"), 1
    while spare.exists():
        number += 1
        spare = folder.with_name(f"{folder.name}.parcial-{number}")
    folder.rename(spare)
    return None


class Refused(ValueError):
    """Invalid arguments the caller must fix for `frames`: exit code 2, not the generic 1 of a
    controlled error."""


def frames(args):
    """Sequential sweep by blocks: one FFmpeg process each, resumable and bounded per call."""
    data = probe(args.video)
    # common.kind exige audio incluso para clasificar "video" (una grabación muda no pasa); el
    # barrido no necesita audio, así que aquí basta con comprobar la pista de imagen directamente
    # (docs/planes/2026-09-18-resumir-video-0.2.0-4-evidencia-empaquetado.md, tabla de dependencias).
    if not common.pictures(data):
        raise Refused("El barrido necesita una pista de vídeo; este medio es de solo audio.")
    stream = video_stream(data)
    total = min(duration(data), stream_end(data, stream))
    end = total if args.end is None else args.end
    if not all(math.isfinite(x) for x in (args.start, end, args.step, args.block)):
        raise Refused("Tiempos no finitos.")
    if not 0 <= args.start < end <= total or args.step <= 0 or args.width < 0 or args.block <= 0:
        raise Refused("Intervalo, paso, anchura o bloque no válidos "
                      f"(la pista de vídeo llega a {total:.3f} s).")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = sweep_blocks(args.start, end, args.step, length=args.block)
    todo = [row for row in plan if clear_partial(out / block_name(row[0])) is None]
    if todo and max(count for _, _, count in todo) > MAX_FRAMES:
        # El mensaje instruye a corregir --block/--step: es la misma categoría "bloque" que las
        # demás guardas de argumentos de esta función, así que también da código 2, no el 1 genérico.
        raise Refused(f"Un bloque supera las {MAX_FRAMES} imágenes por llamada; "
                      "reduce --block o aumenta --step.")
    needed = 2 * space_needed(sum(count for _, _, count in todo))
    free = shutil.disk_usage(out).free
    if free < needed:
        raise Refused(f"Espacio insuficiente para el barrido: hacen falta unos {needed / 1e9:.1f} "
                      f"GB y hay {free / 1e9:.1f} GB libres; reduce el intervalo o trabaja en "
                      "otra unidad.")
    done = sum(count for _, _, count in plan) - sum(count for _, _, count in todo)
    remaining = []
    for a, b, count in todo:
        if remaining or done + count > MAX_FRAMES:
            remaining.append(block_name(a))
            continue
        folder = new_dir(out / block_name(a))
        save(folder / "index.json",
             sweep_block(data, stream, folder, a, b, args.step, args.width, threads=args.threads))
        done += count
        print(f"Bloque {block_name(a)} ({a:.3f}-{b:.3f} s): {count} imágenes", flush=True)
    if remaining:
        # `pending` cuenta; `bloques` nombra. La forma del código 3 es la misma en toda la skill.
        # A diferencia del código 3 de `render` (que cuenta solo lo que esa llamada monta), aquí
        # `done`/`total` son acumulados de todo el intervalo pedido: es el criterio natural para
        # un barrido reanudable sobre un rango fijo.
        print(json.dumps({"done": done, "total": sum(count for _, _, count in plan),
                          "pending": len(remaining), "bloques": remaining}, ensure_ascii=False))
        print("Error: presupuesto agotado; repite la misma orden para continuar.", file=sys.stderr)
        return 3
    print(out)
    return 0


LEVEL_STEP = 0.01
AUDIO_BLOCK = 600.0
BLOCK_SLACK = 60.0
GAP_MIN = 2.0


def quiet_cut(levels, low, high, *, window=common.MIN_SILENCE):
    """Instant of [low, high] whose `window` seconds carry the least energy."""
    width = max(1, round(window / LEVEL_STEP))
    first, last = max(0, round(low / LEVEL_STEP)), min(len(levels), round(high / LEVEL_STEP))
    if last - first < width:
        return round(min(high, len(levels) * LEVEL_STEP), 3)
    best, position, total = None, first, sum(levels[first:first + width])
    for index in range(first, last - width + 1):
        if index > first:
            total += levels[index + width - 1] - levels[index - 1]
        if best is None or total < best:
            best, position = total, index
    return round((position + width / 2) * LEVEL_STEP, 3)


def speech_blocks(levels, total, *, length=AUDIO_BLOCK, slack=BLOCK_SLACK):
    """Transcription blocks of about `length` seconds, each cut at its quietest window."""
    edges, start = [0.0], 0.0
    while total - start > length + slack:
        start = quiet_cut(levels, start + length - slack, start + length + slack)
        edges.append(start)
    return [(a, round(b, 3)) for a, b in zip(edges, edges[1:] + [total])]


def gaps(segments, levels, a, b, *, threshold=common.SILENCE_DB, minimum=GAP_MIN):
    """Stretches of [a, b) with sound and no transcribed word: the VAD may have dropped speech."""
    empty, edge = [], a
    for start, end in sorted((s["start"], s["end"]) for s in segments):
        if start - edge >= minimum:
            empty.append((edge, start))
        edge = max(edge, end)
    if b - edge >= minimum:
        empty.append((edge, b))
    loud = []
    for start, end in empty:
        window = levels[round(start / LEVEL_STEP):min(len(levels), round(end / LEVEL_STEP))]
        if sum(1 for level in window if level > threshold) * LEVEL_STEP >= minimum / 2:
            loud.append((round(start, 3), round(end, 3)))
    return loud


DOUBT_SILENCE = 0.6
DOUBT_LOGPROB = -1.0


def partial_dir(out):
    """Folder that holds the blocks already transcribed, next to the published file."""
    return Path(out).with_suffix(".parcial")


def block_cut(audio, target, a, b):
    """Sample-exact PCM slice: faster-whisper reads a file, not a range of one."""
    ffmpeg("-ss", seconds(a), "-t", seconds(b - a), "-i", audio, "-c:a", "pcm_s16le", target)
    return target


def transcribe_block(model, path, offset, language, args, *, vad=None):
    """One block, with its times moved back onto the original timeline."""
    parts, info = model.transcribe(str(path), language=language, beam_size=args.beam_size,
                                   vad_filter=not args.no_vad if vad is None else vad,
                                   word_timestamps=True)
    segments = []
    for part in parts:
        segment = {"start": round(part.start + offset, 3), "end": round(part.end + offset, 3),
                   "text": part.text,
                   "words": [{"start": round(w.start + offset, 3), "end": round(w.end + offset, 3),
                              "text": w.word} for w in (part.words or [])]}
        # Doubtful segments are marked, never dropped: the agent decides (spec §11).
        if (getattr(part, "no_speech_prob", 0.0) > DOUBT_SILENCE
                or getattr(part, "avg_logprob", 0.0) < DOUBT_LOGPROB):
            segment["dudoso"] = True
        segments.append(segment)
    return {"language": info.language, "segments": segments}


def load_model(args):
    """Model loaded once per call; `auto` tries CUDA first and falls back to CPU."""
    for folder in args.dll_dir or ():
        path = Path(folder)
        if not path.is_dir():
            raise Refused(f"La carpeta de DLL no existe: {path}")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path.resolve()))
        else:
            print(f"Aviso: --dll-dir solo se aplica en Windows; se ignora {path}.", file=sys.stderr)
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise ValueError("Falta faster-whisper. Usa subtítulos existentes o instálalo en un entorno "
                         "local.") from exc
    order = ("cuda", "cpu") if args.device == "auto" else (args.device,)
    for device in order:
        compute = args.compute_type or ("float16" if device == "cuda" else "int8")
        try:
            return WhisperModel(args.model, device=device, compute_type=compute,
                                cpu_threads=args.threads, num_workers=1,
                                local_files_only=not args.allow_download), device
        except Exception as exc:
            if device != order[-1]:
                print(f"Aviso: CUDA no disponible ({exc}); se continúa en CPU.", file=sys.stderr)
                continue
            if not args.allow_download and not Path(args.model).is_dir():
                raise Refused(f"El modelo {args.model} no está en la caché local: repite la orden "
                              "con --allow-download o indica en --model una carpeta CTranslate2 "
                              f"local.\n{exc}") from exc
            raise ValueError(f"No se pudo cargar el modelo {args.model} en {device}: {exc}") from exc
    raise ValueError("Sin dispositivo de inferencia disponible.")


def recover(work, segments, levels, total, language, device, args):
    """Second pass, without VAD, over the stretches that have sound but no transcribed word."""
    model = None
    for number, (a, b) in enumerate(gaps(segments, levels, 0.0, total)):
        piece = work / f"hueco-{number:03d}.json"
        recorded = None
        if piece.is_file():
            try:
                recorded = json.loads(piece.read_text(encoding="utf-8"))
                recorded["segments"]  # validate shape before trusting the cache
            except (OSError, ValueError, KeyError):
                recorded = None  # truncated/corrupt: treat as unfinished
                # Cleared now, not left for save() below: its "x" mode never overwrites, so a
                # corrupt leftover would turn every retry into the same FileExistsError forever.
                piece.unlink(missing_ok=True)
        if recorded is None:
            if model is None:
                model, device = load_model(args)
            with tempfile.TemporaryDirectory(prefix="hueco-", dir=work) as tmp:
                cut = block_cut(args.audio, Path(tmp) / "hueco.wav", a, b)
                found = transcribe_block(model, cut, a, language, args, vad=False)
            recorded = {"start": a, "end": b, "device": device, **found}
            save(piece, recorded)
        # A hueco can also carry the device that produced it (same reasoning as bloque-NNN.json).
        device = recorded.get("device", device)
        for segment in recorded["segments"]:
            segments.append({**segment, "recuperado": True})
    return segments, device


CUE = re.compile(r"(?:(\d{1,2}):)?([0-5]\d):([0-5]\d)[.,](\d{1,3})\s*-->\s*"
                 r"(?:(\d{1,2}):)?([0-5]\d):([0-5]\d)[.,](\d{1,3})")
TAG = re.compile(r"</?[a-zA-Z][^>]*>|\{\\[^}]*\}")


def cue_time(hours, minutes, secs, millis):
    # WebVTT permite que un cue de menos de una hora omita las horas (`MM:SS.mmm`); cuenta como 0.
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs) + int(millis.ljust(3, "0")) / 1000


def subtitles(text):
    """Segments of an SRT or WebVTT file: no per-word marks, no styling tags."""
    segments = []
    lines = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for number, line in enumerate(lines):
        found = CUE.search(line)
        if not found:
            continue
        start, end = cue_time(*found.groups()[:4]), cue_time(*found.groups()[4:])
        body = []
        for offset, following in enumerate(lines[number + 1:]):
            index = number + 1 + offset
            if not following.strip() or CUE.search(following):
                break
            # A missing blank separator leaves the next cue's identifier line glued to this
            # cue's text; if the line right after `following` is itself a cue timing line,
            # `following` is that identifier, not this cue's text.
            if index + 1 < len(lines) and CUE.search(lines[index + 1]):
                break
            body.append(TAG.sub("", following).strip())
        said = " ".join(part for part in body if part).strip()
        if said and end > start:
            segments.append({"start": start, "end": end, "text": said, "words": []})
    segments.sort(key=lambda segment: (segment["start"], segment["end"]))
    return segments


def import_subtitles(args):
    """Normalize the medium's own subtitles instead of transcribing (spec §5)."""
    target = Path(args.out).resolve()
    if target.exists():
        raise Refused("La transcripción de salida ya existe.")
    if not target.parent.is_dir():
        raise Refused(f"No existe la carpeta de salida: {target.parent}")
    source = Path(identity(args.subtitles)["path"])
    segments = subtitles(source.read_text(encoding="utf-8-sig", errors="replace"))
    if not segments:
        raise Refused(f"{source.name} no contiene ningún bloque con tiempos válidos; "
                      "comprueba que es SRT o WebVTT.")
    note = common.warning("sin_marcas_por_palabra",
                          "La transcripción procede de subtítulos: sin marcas por palabra, los "
                          "bordes usan los límites de cada segmento.")
    save(target, {"language": args.language,
                  "settings": {"origen": "subtitulos", "archivo": source.name},
                  "blocks": [], "segments": segments, "warnings": [note]})
    print(target)
    return 0


def transcribe(args):
    """Resumable transcription: one saved block at a time, published only when every block is in."""
    if args.subtitles:
        return import_subtitles(args)
    target = Path(args.out).resolve()
    if target.exists():
        raise Refused("La transcripción de salida ya existe.")
    if not target.parent.is_dir():
        raise Refused(f"No existe la carpeta de salida: {target.parent}")
    audio = identity(args.audio)
    work = partial_dir(target)
    work.mkdir(exist_ok=True)
    levels = common.energy(audio["path"], target.parent / "energia.f32")
    total = round(len(levels) * LEVEL_STEP, 3)
    plan = speech_blocks(levels, total, length=args.block, slack=args.slack)
    settings = {"model": args.model, "compute_type": args.compute_type, "beam_size": args.beam_size,
                "vad_filter": not args.no_vad, "language": args.language}
    fingerprint = {"settings": settings, "source": audio, "blocks": [[a, b] for a, b in plan]}
    stored = work / "ajustes.json"
    if stored.is_file():
        if json.loads(stored.read_text(encoding="utf-8")) != fingerprint:
            raise Refused("Los ajustes de transcripción no coinciden con los de la parte ya "
                          "hecha; repite la orden con los mismos o elige otra salida.")
    else:
        save(stored, fingerprint)
    # `device` starts unknown; each bloque-NNN.json records the device that produced it, so a
    # resumption that finds every block already done still ends up with the real device (below),
    # instead of publishing settings.device as null.
    model, device, language = None, None, args.language
    started, done = time.monotonic(), 0
    for number, (a, b) in enumerate(plan):
        piece = work / f"bloque-{number:03d}.json"
        if piece.is_file():
            try:
                recorded = json.loads(piece.read_text(encoding="utf-8"))
                language = language or recorded["language"]
            except (OSError, ValueError, KeyError):
                recorded = None  # truncated/corrupt: treat as unfinished
                # Cleared now, not left for save() below: its "x" mode never overwrites, so a
                # corrupt leftover would turn every retry into the same FileExistsError forever.
                piece.unlink(missing_ok=True)
            if recorded is not None:
                device = recorded.get("device", device)
                done += 1
                continue
        if args.budget is not None and done and time.monotonic() - started >= args.budget:
            left = [f"bloque-{i:03d}" for i in range(number, len(plan))]
            print(json.dumps({"done": done, "total": len(plan), "pending": len(left),
                              "bloques": left}, ensure_ascii=False))
            return 3
        if model is None:
            model, device = load_model(args)
        with tempfile.TemporaryDirectory(prefix="bloque-", dir=work) as tmp:
            cut = block_cut(audio["path"], Path(tmp) / "bloque.wav", a, b)
            result = transcribe_block(model, cut, a, language, args)
        # The language is fixed with the first block so the rest cannot drift (spec §11).
        language = language or result["language"]
        save(piece, {"index": number, "start": a, "end": b, "device": device, **result})
        done += 1
        print(f"Bloque {number + 1}/{len(plan)} hasta {b:.1f} s", flush=True)
    segments = [segment for number in range(len(plan))
                for segment in json.loads((work / f"bloque-{number:03d}.json")
                                          .read_text(encoding="utf-8"))["segments"]]
    segments, device = recover(work, segments, levels, total, language, device, args)
    segments.sort(key=lambda segment: (segment["start"], segment["end"]))
    staged = work / "transcripcion.json"
    # A previous attempt may have written this and then failed to publish it: "x" mode would
    # otherwise turn every retry into the same FileExistsError. `target` is what publish() must
    # never overwrite; `staged` lives inside the resumable `work` area, so redoing it is safe.
    staged.unlink(missing_ok=True)
    save(staged, {"language": language, "settings": {**settings, "device": device},
                  "blocks": [{"start": a, "end": b} for a, b in plan],
                  "segments": segments, "warnings": []})
    common.publish(staged, target)
    shutil.rmtree(work)
    print(target)
    return 0


def show(args):
    """`probe`: every track and the file identity, as JSON on standard output."""
    print(json.dumps(probe(args.video), ensure_ascii=False, indent=2))


SPACES = re.compile(r"\s+")


def normal(text):
    return SPACES.sub(" ", common.strip_accents(text).casefold()).strip()


def haystack(segment):
    """Normalised text of a segment and, per character, the word it belongs to."""
    words = segment.get("words") or []
    if not words:
        text = normal(segment.get("text", ""))
        return text, [None] * len(text)
    pieces, owners = [], []
    for index, word in enumerate(words):
        piece = normal(word.get("text", ""))
        if not piece:
            continue
        if pieces:
            pieces.append(" ")
            owners.append(index)
        pieces.append(piece)
        owners.extend([index] * len(piece))
    return "".join(pieces), owners


def find(data, query, context=1, limit=20):
    needle = normal(query)
    if not needle:
        raise ValueError("Indica un texto de búsqueda no vacío.")
    segments, hits = data.get("segments") or [], []
    for number, segment in enumerate(segments):
        text, owners = haystack(segment)
        words = segment.get("words") or []
        position = text.find(needle)
        while position >= 0 and len(hits) < limit:
            owner = owners[position] if position < len(owners) else None
            start = words[owner]["start"] if owner is not None and owner < len(words) else segment["start"]
            around = segments[max(0, number - context):number + context + 1]
            hits.append({"segmento": number, "inicio": round(float(start), 3),
                         "fin": round(float(segment["end"]), 3),
                         "texto": str(segment.get("text", "")).strip(),
                         "contexto": " ".join(str(s.get("text", "")).strip() for s in around)})
            position = text.find(needle, position + len(needle))
    return {"consulta": query, "normalizada": needle, "total": len(hits), "coincidencias": hits}


def search(args):
    path = Path(args.transcription)
    if not path.is_file():
        raise ValueError(f"No existe la transcripción: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    print(json.dumps(find(data, args.query, args.context, args.max), ensure_ascii=False, indent=2))


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
    p = sub.add_parser("frames", help="Barre [start, end) por bloques: vistas JPEG, índice gris y "
                                      "hojas de contacto; reanudable.")
    p.set_defaults(run=frames)
    p.add_argument("video", help="Vídeo local.")
    p.add_argument("--out", required=True,
                   help="Carpeta de fotogramas (normalmente TRABAJO/fotogramas); se crea si falta y "
                        "se reutiliza para reanudar.")
    p.add_argument("--start", type=float, default=0, help="Inicio en segundos (por defecto 0).")
    p.add_argument("--end", type=float,
                   help="Fin en segundos, excluido (por defecto, el final de la pista de vídeo).")
    p.add_argument("--step", type=float, default=15, help="Paso en segundos (por defecto 15).")
    p.add_argument("--width", type=int, default=1280,
                   help="Anchura máxima en píxeles; 0 conserva la resolución (por defecto 1280).")
    p.add_argument("--block", type=float, default=BLOCK,
                   help=f"Segundos por bloque, un proceso cada uno (por defecto {BLOCK:.0f}).")
    p.add_argument("--threads", type=positive, default=1,
                   help="Hilos de decodificación por bloque (por defecto 1).")
    p = sub.add_parser("transcribe", help="Transcribe por bloques reanudables con faster-whisper, "
                                          "o normaliza subtítulos existentes.")
    p.set_defaults(run=transcribe)
    p.add_argument("audio", help="Audio local, normalmente audio.wav de prepare.")
    p.add_argument("--out", required=True, help="JSON de salida nuevo; su carpeta debe existir.")
    p.add_argument("--model", default="small",
                   help="Nombre de modelo o carpeta CTranslate2 local (por defecto small).")
    p.add_argument("--language", help="Código de idioma, p. ej. es (por defecto, detección automática).")
    p.add_argument("--allow-download", action="store_true",
                   help="Permite descargar el modelo; sin esta opción solo se usan modelos locales.")
    p.add_argument("--device", default="auto", choices=("cpu", "cuda", "auto"),
                   help="Dispositivo de inferencia; auto prueba CUDA y vuelve a CPU (por defecto auto).")
    p.add_argument("--dll-dir", action="append", metavar="CARPETA",
                   help="Carpeta de DLL de CUDA/cuDNN en Windows; repetible.")
    p.add_argument("--compute-type",
                   help="Tipo de cálculo de CTranslate2 (por defecto int8 en CPU y float16 en CUDA).")
    p.add_argument("--beam-size", type=positive, default=1, help="Tamaño de haz (por defecto 1).")
    p.add_argument("--no-vad", action="store_true", help="Desactiva el filtro VAD en todos los bloques.")
    p.add_argument("--threads", type=positive, default=DEFAULT_THREADS,
                   help=f"Hilos de CPU (por defecto {DEFAULT_THREADS}).")
    p.add_argument("--block", type=float, default=AUDIO_BLOCK,
                   help=f"Segundos por bloque (por defecto {AUDIO_BLOCK:.0f}).")
    p.add_argument("--slack", type=float, default=BLOCK_SLACK,
                   help=f"Margen para buscar el corte silencioso (por defecto {BLOCK_SLACK:.0f}).")
    p.add_argument("--budget", type=float,
                   help="Segundos como máximo por llamada; al agotarse devuelve 3 y se reanuda.")
    p.add_argument("--subtitles", metavar="RUTA",
                   help="Normaliza un SRT o WebVTT en vez de transcribir (tarea 7).")
    p = sub.add_parser("search", help="Busca en la transcripción sin distinguir tildes ni mayúsculas.")
    p.add_argument("transcription", help="transcripcion.json de la carpeta de trabajo.")
    p.add_argument("query", help="Texto buscado; se comparan minúsculas y sin tildes.")
    p.add_argument("--context", type=int, default=1,
                   help="Segmentos de contexto a cada lado (por defecto 1).")
    p.add_argument("--max", type=common.positive, default=20,
                   help="Coincidencias como máximo (por defecto 20).")
    p.set_defaults(run=search)
    plan.register(sub)
    render.register(sub)
    doc.register(sub)
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
        if args.command in ("probe", "prepare", "frames", "transcribe"):
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
    except Refused as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, RuntimeError, AttributeError, TypeError,
            IndexError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
