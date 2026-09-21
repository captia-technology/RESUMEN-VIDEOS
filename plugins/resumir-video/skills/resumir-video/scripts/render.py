"""Cached, resumable montage of an accepted plan: budget, assembly, blocking validation and report."""

import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import wave

from common import (BLOCKING, DEFAULT_THREADS, ENERGY_STEP, MAX_SPANS, MEMORY_PATTERNS, energy,
                    ffmpeg, fingerprint, listing, output_interval, plan_sha256, positive, probe,
                    publish, require_encoders, run, save, seconds, seek_margin, stream_duration,
                    streams, timeline_start, video_stream, warning)


class Refused(ValueError):
    """Argument or plan the montage will not touch: exit code 2."""


class Invalid(ValueError):
    """The montage was produced but failed validation: exit code 4, nothing is published."""


class Pending(Exception):
    """The budget ran out; the call is resumable: exit code 3."""

    def __init__(self, done, total, blocks=()):
        super().__init__("Presupuesto agotado.")
        # `pending` is always an integer (§12); what is left is detailed in `bloques`.
        self.state = {"done": done, "total": total, "pending": total - done,
                      "bloques": list(blocks)}


def accepted(plan, accept, directo):
    """The plan only renders with a literal acceptance; blocking warnings stop --directo too (§9)."""
    blocking = [item for item in plan.get("warnings", []) if item.get("codigo") in BLOCKING]
    if blocking:
        detail = "; ".join(f"{item['codigo']}: {item['mensaje']}" for item in blocking)
        cuts = sorted({str(item["corte"]) for item in blocking if item.get("corte") is not None})
        where = f" Cortes afectados: {', '.join(cuts)}." if cuts else ""
        raise Refused(f"El plan tiene avisos bloqueantes ({detail}).{where} Corrige el plan con "
                      "plan y vuelve a pedir la aceptación del usuario; --directo no los anula.")
    if not accept and not directo:
        raise Refused('El plan requiere aceptación: repite con --accept "frase literal del usuario" '
                      "o con --directo.")
    return {"frase": accept, "directo": bool(directo), "sha256": plan_sha256(plan)}


def sources_agree(plan, video):
    """Same fingerprint: the plan is valid even if the file moved (§6). A different one is an error."""
    planned = plan.get("source")
    if not isinstance(planned, dict):
        raise Refused("El plan no trae source; cópialo de metadata.json.")
    current = fingerprint(video)
    differ = [key for key in ("size", "mtime_ns", "sha256") if planned.get(key) != current[key]]
    if differ:
        raise Refused(f"El plan no corresponde a este archivo (difiere: {', '.join(differ)}). "
                      "Vuelve a planificar sobre el medio actual.")
    if planned.get("path") != str(Path(video).resolve()):
        return [warning("origen_reasignado",
                        "El plan apunta a otra ruta pero la huella coincide: se actualiza source "
                        f"a {Path(video).resolve()}.")]
    return []


ENCODER = ("-bf", "0", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "fast")


def ffmpeg_release():
    """First line of `ffmpeg -version`: any change to it invalidates the cached cuts."""
    lines = run(["ffmpeg", "-hide_banner", "-version"]).splitlines()
    return lines[0] if lines else "desconocido"


def cadence_of(plan):
    """Constant output rate as a float, from the `settings.rate` fraction that plan.py fixed."""
    return 1 / output_interval(plan["settings"]["rate"])


def tempo_factors(speed):
    """atempo factors whose product is `speed`, each inside the filter's safe 0.5–2.0 range."""
    if abs(speed - 1.0) < 1e-9:
        return []
    steps = max(1, math.ceil(math.log2(speed))) if speed > 1 else 1
    return [speed ** (1 / steps)] * steps


def subcuts(segment, limit=MAX_SPANS):
    """Passes of one cut exactly as plan.py published them; render adds no arithmetic of its own."""
    declared = segment.get("subcuts")
    if not declared:
        raise Refused(f"El corte {segment['id']} no tiene tramos ni subcortes publicados: "
                      f"replanifica (aviso corte_vacio).")
    parts, joined = [], []
    for index, item in enumerate(declared):
        spans = [(float(start), float(end)) for start, end in item["spans"]]
        frames, samples = item["frames"], item["samples"]
        where = f"El corte {segment['id']} en el subcorte {index + 1}/{len(declared)}"
        if not spans or frames < 1 or samples < 1:
            raise Refused(f"{where} deja {len(spans)} tramos, {frames} fotogramas y {samples} "
                          f"muestras: replanifica (aviso corte_vacio).")
        if len(spans) > limit:
            raise Refused(f"{where} lleva {len(spans)} tramos y el máximo es {limit}: replanifica.")
        parts.append({"cut": segment["id"], "spans": spans, "frames": frames, "samples": samples,
                      "index": index, "total": len(declared)})
        joined.extend(spans)
    frames, samples = sum(part["frames"] for part in parts), sum(part["samples"] for part in parts)
    if (segment.get("frames"), segment.get("samples")) != (frames, samples):
        raise Refused(f"El corte {segment['id']} declara {segment.get('frames')} fotogramas y "
                      f"{segment.get('samples')} muestras, pero sus subcortes suman {frames} y "
                      f"{samples}; vuelve a ejecutar plan sobre este medio.")
    if joined != [(float(start), float(end)) for start, end in segment["spans"]]:
        raise Refused(f"El corte {segment['id']} publica unos subcortes cuyos tramos no son los del "
                      f"corte; vuelve a ejecutar plan sobre este medio.")
    return parts


def cut_key(plan, part, release):
    """sha256 of everything that changes a rendered cut (§6); the path deliberately stays out."""
    material = {"huella": {key: plan["source"][key] for key in ("size", "mtime_ns", "sha256")},
                "pista": plan["audio_stream"],
                "tramos": [[round(start, 3), round(end, 3)] for start, end in part["spans"]],
                "velocidad": round(float(plan["settings"]["speed"]), 6),
                "cadencia": str(plan["settings"]["rate"]),
                "codificador": " ".join(ENCODER),
                "subcorte": [part["index"], part["total"]],
                "ffmpeg": release}
    text = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def video_filter(spans, base, rate, speed, n_frames):
    """One pass per cut on the container's own timeline; every piece was measured on FFmpeg 8.0.1."""
    select = "+".join(f"(gte(t,{seconds(base + start)})*lt(t,{seconds(base + end)}))"
                      for start, end in spans)
    # Reading guard: `select` drops the frames past the cut instead of closing the chain, so
    # trim=end_frame never receives the frame N+1 that would end the pass and FFmpeg decodes the
    # medium whole (measured: 1000 of 1000 frames; 153 with this trim, same output). It cannot be
    # done with -t or -to: next to -copyts both count from the first packet read and leave the
    # chain at zero frames (measured). One frame of slack keeps everything the select needs.
    stop = seconds(base + spans[-1][1] + output_interval(rate))
    # The leading fps rebuilds held frames of variable-rate sources (without it the removed pause
    # freezes and the cut loses its tail); tpad needs stop=-1 to clone up to exactly N frames.
    return (f"fps={rate}:start_time={seconds(base + spans[0][0])},trim=end={stop},"
            f"select='{select}',settb=AVTB,"
            f"setpts=N/({rate})/{speed:.6f}/TB,fps={rate},tpad=stop=-1:stop_mode=clone,"
            f"trim=end_frame={n_frames},setpts=N/({rate})/TB,pad=ceil(iw/2)*2:ceil(ih/2)*2")


def audio_filter(spans, base, speed, m_samples, label="0:a"):
    """Same spans on the chosen track; aselect is useless here because it drops no samples."""
    # No reading guard here: the per-span `atrim=start=…:end=…` do end their branches and concat
    # closes the graph (measured: 8.02 s read of a 300 s medium), unlike the video `select`.
    count = len(spans)
    # §8 opens the chain with aresample. Measured on FFmpeg 8.0.1: the output is byte for byte the
    # same as without it (N and M included), because the atrim times are absolute; the only price
    # is that first_pts=0 pads with silence from 0 to the first instant read, so the pass takes
    # longer the further into the medium the cut is (1.35 s against 0.14 s at 3000 s).
    chain = [f"[{label}]aresample=async=1:first_pts=0,asplit={count}"
             + "".join(f"[s{i}]" for i in range(count))]
    for index, (start, end) in enumerate(spans):
        chain.append(f"[s{index}]atrim=start={seconds(base + start)}:end={seconds(base + end)},"
                     f"asetpts=N/SR/TB[t{index}]")
    tempo = "".join(f"atempo={factor:.6f}," for factor in tempo_factors(speed))
    chain.append("".join(f"[t{i}]" for i in range(count)) +
                 f"concat=n={count}:v=0:a=1,{tempo}apad=whole_len={m_samples},"
                 f"atrim=end_sample={m_samples}[a]")
    return ";".join(chain)


def counted_frames(path):
    """Frames actually decodable in a file; nb_frames of the header is not trustworthy enough."""
    report = json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                             "-show_entries", "stream=nb_read_frames", "-of", "json", str(path)]))
    return int(report["streams"][0]["nb_read_frames"])


def counted_samples(path, sample_rate, folder):
    """Samples of the audio track: ffprobe gives none for PCM in Matroska, so it is decoded."""
    with tempfile.TemporaryDirectory(prefix="muestras-", dir=folder) as temporary:
        # 24-bit PCM is WAVE_FORMAT_EXTENSIBLE and `wave` refuses it: decode to 16 bits first.
        copy = Path(temporary) / "cuenta.wav"
        ffmpeg("-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(sample_rate),
               "-c:a", "pcm_s16le", copy)
        with wave.open(str(copy)) as stream:
            return stream.getnframes()


def render_part(data, plan, part, target, threads):
    """Two FFmpeg passes (H.264 video and 24-bit PCM audio) remuxed without re-encoding."""
    spans, settings = part["spans"], plan["settings"]
    base, source = timeline_start(data), data["source"]["path"]
    # Only -ss: next to -copyts, -t and -to are counted from the first packet read and leave the
    # chain at zero frames (measured). The video filter carries its own reading guard and the audio
    # one closes on its own with the atrim of each span.
    seek = max(0.0, spans[0][0] - seek_margin(data))
    threading = ("-threads", str(threads), "-filter_threads", str(threads))
    folder = target.parent
    with tempfile.TemporaryDirectory(prefix="pasada-", dir=folder, ignore_cleanup_errors=True) as tmp:
        picture, sound = Path(tmp) / "v.mkv", Path(tmp) / "a.mkv"
        ffmpeg(*threading, "-ss", seconds(seek),
               "-noaccurate_seek", "-copyts", "-i", source,
               "-map", f"0:{video_stream(data)['index']}", "-an", "-sn", "-dn",
               "-map_metadata", "-1", "-map_chapters", "-1",
               "-vf", video_filter(spans, base, settings["rate"], float(settings["speed"]),
                                   part["frames"]),
               *ENCODER, picture)
        ffmpeg(*threading, "-ss", seconds(seek), "-noaccurate_seek", "-copyts",
               "-i", source,
               "-filter_complex", audio_filter(spans, base, float(settings["speed"]),
                                               part["samples"], f"0:{plan['audio_stream']}"),
               "-map", "[a]", "-vn", "-sn", "-dn", "-map_metadata", "-1",
               "-c:a", "pcm_s24le", sound)
        staged = Path(tmp) / "corte.mkv"
        ffmpeg("-i", picture, "-i", sound, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", staged)
        frames = counted_frames(staged)
        samples = counted_samples(staged, plan["settings"]["sample_rate"], tmp)
        if (frames, samples) != (part["frames"], part["samples"]):
            raise Invalid(f"El corte {part['cut']} subcorte {part['index'] + 1}/{part['total']} "
                          f"produjo {frames} fotogramas y {samples} muestras; se esperaban "
                          f"{part['frames']} y {part['samples']}.")
        publish(staged, target)


def cut_note(part, release):
    """What travels beside a cached cut: its numbers, so a later call can trust the file."""
    return {"cut": part["cut"], "index": part["index"], "total": part["total"],
            "spans": [[round(start, 3), round(end, 3)] for start, end in part["spans"]],
            "frames": part["frames"], "samples": part["samples"], "ffmpeg": release}


def is_cached(plan, part, cortes, release):
    """The one criterion for «already cached»: the cut, and a note whose counts are the part's."""
    target = cortes / f"{cut_key(plan, part, release)}.mkv"
    note = target.with_suffix(".json")
    if not (target.is_file() and note.is_file()):
        return False
    try:
        kept = json.loads(note.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(kept, dict) and (kept.get("frames"), kept.get("samples")) == (
        part["frames"], part["samples"])


def cached_part(data, plan, part, cortes, release, threads):
    """Render the part unless the cache already holds it with the right frame and sample counts."""
    target = cortes / f"{cut_key(plan, part, release)}.mkv"
    note = target.with_suffix(".json")
    if is_cached(plan, part, cortes, release):
        return target
    # A cut without its note, or with a note that disagrees, is not trustworthy: rebuild both.
    for path in (target, note):
        if path.exists():
            path.replace(path.with_suffix(path.suffix + ".parcial"))
    render_part(data, plan, part, target, threads)
    save(note, cut_note(part, release))
    for path in (target, note):
        leftover = path.with_suffix(path.suffix + ".parcial")
        if leftover.exists():
            leftover.unlink()
    return target


# The numeric half of §11's five memory cases; `common.MEMORY_PATTERNS` holds the three strings.
# Windows reports STATUS_NO_MEMORY (0xC0000017) as 3221225495, the OOM killer gives 137 and, on
# POSIX, a SIGKILLed child is -9.
MEMORY_CODES = (137, 3221225495, -9)


def exit_code(message):
    """The returncode that `common.run` writes at the head of its error as «(código N)»."""
    head, found, tail = message.partition("(código ")
    try:
        return int(tail.partition(")")[0]) if found else None
    except ValueError:
        return None


def retryable(message):
    """Only the memory failures listed in §11 deserve the single retry; an AVERROR does not."""
    return (any(pattern in message for pattern in MEMORY_PATTERNS)
            or exit_code(message) in MEMORY_CODES)


def part_label(part):
    """How a pass still to render is named in the resumable state of code 3."""
    return f"corte {part['cut']} subcorte {part['index'] + 1}/{part['total']}"


def all_parts(plan):
    """Every pass the plan needs, in order; `subcuts` refuses a cut whose numbers do not add up."""
    parts = []
    for segment in plan["segments"]:
        parts.extend(subcuts(segment))
    return parts


def build(data, plan, cortes, release, threads, budget):
    """Render every missing part, one retry on memory failures, honouring the time budget (§11)."""
    parts = all_parts(plan)
    fresh = [not is_cached(plan, part, cortes, release) for part in parts]
    # `done` and `total` count only what this call mounts: what was cached is neither.
    started, done, total, cuts = time.monotonic(), 0, sum(fresh), []
    for index, part in enumerate(parts):
        # `done` guards the first pass: a resumption always mounts one cut before it stops.
        if fresh[index] and budget and done and time.monotonic() - started >= budget:
            raise Pending(done, total, [part_label(item) for item, missing
                                        in zip(parts[index:], fresh[index:]) if missing])
        try:
            cuts.append(cached_part(data, plan, part, cortes, release, threads))
        except ValueError as exc:
            if not retryable(str(exc)):
                raise
            print(f"Falta de memoria en el {part_label(part)}; se repite con un solo hilo.",
                  file=sys.stderr, flush=True)
            # The one retry allowed by §11: -threads 1 and -filter_threads 1. A second failure
            # propagates. What the failed attempt set aside as `.parcial` goes before the retry.
            for leftover in cortes.glob(f"{cut_key(plan, part, release)}.*.parcial"):
                leftover.unlink()
            cuts.append(cached_part(data, plan, part, cortes, release, 1))
        if fresh[index]:
            done += 1
            # Stderr: stdout carries only the JSON state of code 3 (§12), never progress lines.
            print(f"Corte {done}/{total}", file=sys.stderr, flush=True)
    return cuts


def assemble(folder, cuts, staged, threads):
    """Two concat demuxers over the same list: video is copied and the audio is encoded once (D-006)."""
    require_encoders("libx264", "aac")
    names = [Path(cut).name for cut in cuts]
    # Relative names run from `folder`: the concat demuxer parses list paths as URLs ('#', '?').
    listing(folder / "cortes.txt", names)
    ffmpeg("-f", "concat", "-safe", "1", "-i", "cortes.txt",
           "-f", "concat", "-safe", "1", "-i", "cortes.txt",
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-af", "aresample=async=1:min_hard_comp=0.01",
           "-c:a", "aac", "-b:a", "192k", "-threads", str(threads),
           "-movflags", "+faststart", staged.name, cwd=folder)
    (folder / "cortes.txt").unlink()


SYNC = 0.1


def decode_check(path, threads):
    """Full decoding with -xerror: a montage that cannot be played whole is never published."""
    try:
        ffmpeg("-xerror", "-threads", str(threads), "-i", path,
               "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")
    except ValueError as exc:
        raise Invalid(f"El montaje no se decodifica completo: {exc}") from exc


def totals_check(path, parts):
    """Frames equal to Σ N and audio within 0.1 s of the video, both blocking in §8."""
    expected = sum(part["frames"] for part in parts)
    counted = counted_frames(path)
    data = probe(path)
    picture, sound = streams(data)
    lengths = (stream_duration(data, picture), stream_duration(data, sound))
    drift = abs(lengths[0] - lengths[1])
    if counted != expected:
        raise Invalid(f"El montaje tiene {counted} fotogramas y el plan suma {expected}.")
    if drift > SYNC:
        raise Invalid(f"Vídeo y audio difieren {drift:.3f} s (máximo {SYNC} s): "
                      f"vídeo {lengths[0]:.3f} s, audio {lengths[1]:.3f} s.")
    return {"fotogramas_esperados": expected, "fotogramas": counted,
            "video_s": round(lengths[0], 3), "audio_s": round(lengths[1], 3),
            "desfase_s": round(drift, 3)}


IMAGE_SIDE = 64
IMAGE_OK, IMAGE_MARK = 0.08, 0.15


def gray_frame(path, instant, base, margin, target, track="0:v:0"):
    """The frame on screen at `instant`, reduced to IMAGE_SIDE² luminance samples."""
    ffmpeg("-ss", seconds(max(0.0, instant - margin)), "-noaccurate_seek", "-copyts", "-i", path,
           "-map", track, "-frames:v", "1",
           "-vf", f"fps=1000:start_time={seconds(base + instant)},"
                  f"scale={IMAGE_SIDE}:{IMAGE_SIDE},format=gray",
           "-f", "rawvideo", target)
    return Path(target).read_bytes()


def image_distance(left, right):
    """Mean absolute luminance difference, normalised to 0…1."""
    if len(left) != len(right) or not left:
        raise ValueError(f"Las imágenes deben tener el mismo tamaño ({len(left)} y {len(right)}).")
    return sum(abs(one - two) for one, two in zip(left, right)) / (len(left) * 255)


def image_placement(data, final, spans, out_start, out_end, folder):
    """Compare the first and last frame of the cut against the source it claims to come from."""
    source, base = data["source"]["path"], timeline_start(data)
    margin = seek_margin(data)
    # `final` always carries a single video stream (assemble maps it to output 0), but the source
    # may not: pick the same track render_part read, never a stray attached_pic (§8, hallazgo 5).
    origin_track = f"0:{video_stream(data)['index']}"
    points = (("inicio", out_start, spans[0][0]), ("fin", max(out_start, out_end - 1e-3),
                                                   max(spans[-1][0], spans[-1][1] - 1e-3)))
    rows = []
    with tempfile.TemporaryDirectory(prefix="imagen-", dir=folder) as temporary:
        for name, moment, origin in points:
            produced = gray_frame(final, moment, 0.0, margin, Path(temporary) / f"{name}-s.gray")
            expected = gray_frame(source, origin, base, margin, Path(temporary) / f"{name}-o.gray",
                                  origin_track)
            rows.append({"punto": name, "salida_s": round(moment, 3), "origen_s": round(origin, 3),
                         "distancia": round(image_distance(produced, expected), 4)})
    return rows


# Its own name: video.BLOCK is the 600 s block of the sweep and this one is 10 ms of envelope.
# Alias, no literal: si common.ENERGY_STEP cambia, window_levels y desfase_ms siguen de acuerdo.
LEVEL_BLOCK = ENERGY_STEP
LEVEL_RATE = 16000
WINDOW = 1.0
# Provisional thresholds of §15, written down in docs/requisitos.md by the packaging plan.
ENVELOPE_OK, ENVELOPE_MARK = 4.0, 8.0
ENVELOPE_LAG = 4                 # blocks of 10 ms: 40 ms, inside the 45 ms of the specification
ENVELOPE_SPREAD = 6.0            # dB below which the envelope is flat and correlation says nothing
ENVELOPE_CORRELATION = 0.9


def window_levels(path, start, length, folder, name, track="0:a:0"):
    """RMS envelope of a window, always through a temporary mono 16-bit decode (§8)."""
    # Here -t is legitimate: there is no -copyts, so it is the plain duration after the seek, and
    # `start` is already in the s = pts − format.start_time convention of §3 (never `base + s`):
    # measured on a 12 s sine remuxed with `-output_ts_offset 7` (start_time = 7.000000), `-ss 1`
    # without -copyts gives the same wav as the unshifted original, and `-ss 8` a different one.
    copy = Path(folder) / f"{name}.wav"
    ffmpeg("-ss", seconds(max(0.0, start)), "-t", seconds(length), "-i", path, "-map", track,
           "-ac", "1", "-ar", str(LEVEL_RATE), "-c:a", "pcm_s16le", copy)
    return energy(copy)


def stretched(levels, speed, count):
    """The source envelope resampled by the speed, interpolating between blocks."""
    out = array.array("f")
    for index in range(count):
        position = index * speed
        lower = int(position)
        if lower >= len(levels) - 1:
            out.append(levels[-1])
            continue
        share = position - lower
        out.append(levels[lower] * (1 - share) + levels[lower + 1] * share)
    return out


def correlation(left, right):
    count = min(len(left), len(right))
    if count < 4:
        return 0.0
    first, second = left[:count], right[:count]
    mean_one, mean_two = sum(first) / count, sum(second) / count
    covariance = sum((a - mean_one) * (b - mean_two) for a, b in zip(first, second))
    spread_one = sum((a - mean_one) ** 2 for a in first)
    spread_two = sum((b - mean_two) ** 2 for b in second)
    if spread_one <= 0 or spread_two <= 0:
        return 0.0
    return covariance / math.sqrt(spread_one * spread_two)


def spread(levels):
    """Standard deviation of an envelope, in dB."""
    if len(levels) < 2:
        return 0.0
    mean = sum(levels) / len(levels)
    return math.sqrt(sum((value - mean) ** 2 for value in levels) / len(levels))


def align(produced, reference, span=ENVELOPE_LAG + 2):
    """Lag that minimises the mean absolute difference in dB, with its correlation.

    `lag` is positive when `produced` happens later than `reference` (produced is delayed) and
    negative when it happens earlier (produced is advanced); `validate` only reads `abs(lag)`, so
    the sign never changes which cuts are accepted.
    """
    best = (999.0, 0, 0.0)
    for lag in range(-span, span + 1):
        left, right = produced[max(0, lag):], reference[max(0, -lag):]
        count = min(len(left), len(right))
        if count < 4:
            continue
        difference = sum(abs(left[i] - right[i]) for i in range(count)) / count
        if difference < best[0]:
            best = (difference, lag, correlation(left, right))
    return best


def sound_placement(data, final, spans, out_start, out_end, speed, folder, track="0:a:0"):
    """Compare the envelope at both ends of the cut with the source, rescaled by the speed (§8)."""
    source = data["source"]["path"]
    first, last = spans[0], spans[-1]
    head = min(WINDOW, (first[1] - first[0]) / speed, out_end - out_start)
    tail = min(WINDOW, (last[1] - last[0]) / speed, out_end - out_start)
    # `first[0]` and `last[1] - tail * speed` are already `s` (§3): window_levels seeks with plain
    # -ss, no -copyts, so they must NOT be shifted by `base` — measured with a source of
    # start_time = 7 s: adding `base` here reads the wrong window (or none, past the end) even
    # though the montage is correct.
    points = (("inicio", head, out_start, first[0]),
              ("fin", tail, out_end - tail, last[1] - tail * speed))
    rows = []
    with tempfile.TemporaryDirectory(prefix="envolvente-", dir=folder) as temporary:
        for name, window, moment, origin in points:
            if window <= 4 * LEVEL_BLOCK:
                rows.append({"punto": name, "bloques": 0, "diferencia_db": 0.0, "desfase_ms": 0,
                             "correlacion": None, "modulacion_db": 0.0})
                continue
            produced = window_levels(final, moment, window, temporary, f"{name}-salida")
            original = window_levels(source, origin, window * speed, temporary, f"{name}-origen",
                                     track)
            reference = stretched(original, speed, len(produced))
            difference, lag, value = align(produced, reference)
            modulation = spread(reference)
            rows.append({"punto": name, "bloques": len(produced),
                         "diferencia_db": round(difference, 2),
                         "desfase_ms": lag * round(LEVEL_BLOCK * 1000),
                         "correlacion": None if modulation < ENVELOPE_SPREAD else round(value, 3),
                         "modulacion_db": round(modulation, 1)})
    return rows


def render(args):
    """Entry point of the subcommand; the montage itself arrives in Task 10."""
    raise RuntimeError("render aún no está implementado")


def register(sub):
    """Subcommand registration shared by the four modules: one subparser and its `run`."""
    parser = sub.add_parser("render", help="Monta vN/ desde un plan aceptado, con caché y validación.")
    parser.add_argument("video", help="Vídeo local original.")
    parser.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    parser.add_argument("--plan", required=True, help="seleccion-vN.json producido por plan.")
    parser.add_argument("--accept", help="Frase literal con la que el usuario aceptó la propuesta.")
    parser.add_argument("--directo", action="store_true",
                        help="Monta sin revisión previa; no anula los avisos bloqueantes.")
    parser.add_argument("--budget", type=float,
                        help="Segundos de montaje por llamada; al agotarse devuelve 3 y se reanuda.")
    parser.add_argument("--threads", type=positive, default=DEFAULT_THREADS,
                        help=f"Hilos de codificación (por defecto {DEFAULT_THREADS}).")
    parser.set_defaults(run=render)
