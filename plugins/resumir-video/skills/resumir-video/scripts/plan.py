"""Deterministic planning: spans, exact estimate, states, warnings and the proposal to review."""

import json
import math
from pathlib import Path

import common

SHORT_CUT = 3.0
SHORT_VISUAL = 4.0
PAUSE_SHARE = 0.45
QUIET_MARGIN = 3.0
FAST_SPEED = 1.5
LOW_TARGET = 0.05
CODEC_MARGIN = 0.1
TEXT = ("title", "phrase", "reason", "audio_evidence")
BAR = 60


def load(path):
    """Read a JSON document written by the agent; BOM included, as in 0.1.0."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{Path(path).name} debe ser un objeto JSON.")
    return data


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} debe ser un número finito de segundos.")
    return float(value)


def flag(segment, key, default=False):
    value = segment.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"El corte {segment.get('id')} necesita {key} booleano.")
    return value


def check_draft(draft, total, kind):
    """Validate the agent's draft; every rejection happens before anything is written."""
    segments = draft.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("El borrador requiere segments con al menos un corte.")
    needed = TEXT + (("visual_evidence",) if kind == "video" else ())
    seen, previous = {}, 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Cada corte debe ser un objeto.")
        key = segment.get("id")
        if type(key) is not int or key < 1:
            raise ValueError(f"Identificador no válido: {key!r}; usa enteros estables desde 1.")
        if key in seen:
            raise ValueError(f"Identificador repetido: {key}.")
        start = number(segment.get("start"), f"start del corte {key}")
        end = number(segment.get("end"), f"end del corte {key}")
        # Touching cuts are legal, as in 0.1.0; only strict overlaps are refused.
        if not previous <= start < end <= total:
            raise ValueError(f"El corte {key} está desordenado, solapado o fuera del medio "
                             f"(termina en {total:.3f} s).")
        for field in needed:
            if not isinstance(segment.get(field), str) or not segment[field].strip():
                raise ValueError(f"Falta {field} en el corte {key}.")
        priority = segment.get("priority")
        if type(priority) is not int or priority not in (1, 2, 3):
            raise ValueError(f"La prioridad del corte {key} debe ser 1, 2 o 3.")
        for name in ("included", "pinned", "remove_pauses", "visual_only"):
            flag(segment, name, name == "remove_pauses")
        depends = segment.get("depends_on", [])
        if (not isinstance(depends, list) or any(type(x) is not int or x == key for x in depends)
                or len(depends) != len(set(depends))):
            raise ValueError(f"depends_on del corte {key} debe listar identificadores distintos.")
        seen[key], previous = segment, end
    for segment in segments:
        for other in segment.get("depends_on", []):
            if other not in seen:
                raise ValueError(f"El corte {segment['id']} depende de {other}, que no existe.")
    topics = draft.get("topics", [])
    if not isinstance(topics, list):
        raise ValueError("topics debe ser una lista de temas.")
    for topic in topics:
        if not isinstance(topic, dict):
            raise ValueError("Cada tema debe ser un objeto.")
        if not isinstance(topic.get("nombre"), str) or not topic["nombre"].strip():
            raise ValueError("Cada tema necesita un nombre.")
        cortes = topic.get("cortes", [])
        if (not isinstance(cortes, list) or any(type(x) is not int for x in cortes)
                or len(cortes) != len(set(cortes))):
            raise ValueError(f"cortes del tema «{topic['nombre']}» debe listar identificadores "
                             "enteros y distintos.")
        if any(x not in seen for x in cortes):
            raise ValueError(f"El tema «{topic['nombre']}» cita cortes que no existen.")
        if type(topic.get("imprescindible", False)) is not bool:
            raise ValueError(f"imprescindible del tema «{topic['nombre']}» debe ser booleano.")
    return segments


def settings_of(draft, args, total, grid):
    """Effective settings: the draft's, overridden by the options of this call."""
    base = dict(draft.get("settings") or {})
    if args.target is not None:
        base["target"] = args.target
    if args.speed is not None:
        base["speed"] = args.speed
    if args.pauses is not None:
        base["remove_pauses"] = args.pauses == "si"
    if args.silence_db is not None:
        base["silence_db"] = args.silence_db
    speed = base.get("speed", 1.25)
    if type(speed) not in (int, float) or not math.isfinite(speed):
        raise ValueError("speed debe ser un número finito.")
    speed = float(speed)
    if not 1.0 <= speed <= 2.0:
        raise ValueError(f"La velocidad debe estar entre 1,0 y 2,0 (recibida {speed:g}).")
    remove_pauses = base.get("remove_pauses", True)
    if type(remove_pauses) is not bool:
        raise ValueError("remove_pauses debe ser un valor booleano.")
    silence_db = base.get("silence_db", common.SILENCE_DB)
    if type(silence_db) not in (int, float) or not math.isfinite(silence_db):
        raise ValueError("silence_db debe ser un número finito.")
    target = common.parse_target(base.get("target"), total)
    return {"target": base.get("target"), "objetivo": target,
            "tolerance": common.tolerance(target) if target is not None else None,
            "speed": round(speed, 3), "remove_pauses": remove_pauses,
            "silence_db": float(silence_db),
            # render rebuilds the cadence from the plan alone, without opening metadata.json.
            "rate": grid["rate"], "sample_rate": grid["sample_rate"]}


def words_of(transcription):
    """Flat, ordered word marks; empty when the transcription comes from plain subtitles."""
    words = []
    for segment in (transcription or {}).get("segments", []):
        words.extend({"start": float(word["start"]), "end": float(word["end"])}
                     for word in segment.get("words", []) if word.get("start") is not None)
    return sorted(words, key=lambda word: word["start"])


def adjusted(segments, levels, words, threshold):
    """Chronological edge adjustment that never crosses a neighbour."""
    # `adjust_edges` only ever moves the start earlier and the end later, and a validated draft
    # (check_draft) already guarantees end <= next start, so a <= b holds after the clamp below
    # with no further fallback needed.
    rows, floor_ = [], 0.0
    for index, segment in enumerate(segments):
        roof = segments[index + 1]["start"] if index + 1 < len(segments) else float("inf")
        a, b, note = common.adjust_edges(segment["start"], segment["end"], levels, words,
                                         threshold=threshold)
        a, b = max(a, floor_), min(b, roof)
        rows.append({"segment": segment, "a": a, "b": b, "note": note})
        floor_ = b
    return rows


def join(one, other):
    """The cut that results from merging two neighbours: lowest id, highest priority."""
    ids = {one["id"], other["id"]}
    fused = dict(one)
    fused["id"] = min(ids)
    fused["priority"] = min(one["priority"], other["priority"])
    # `included` travels explicitly, never as a leftover of `dict(one)`: `fuse` pairs neighbours
    # that already share it, and a silent inheritance would drop a cut from the render.
    fused["included"] = one.get("included", False) and other.get("included", False)
    fused["pinned"] = one.get("pinned", False) or other.get("pinned", False)
    fused["visual_only"] = one.get("visual_only", False) and other.get("visual_only", False)
    fused["remove_pauses"] = one.get("remove_pauses", True) and other.get("remove_pauses", True)
    fused["depends_on"] = sorted({*one.get("depends_on", []), *other.get("depends_on", [])} - ids)
    fused["start"] = min(one["start"], other["start"])
    fused["end"] = max(one["end"], other["end"])
    for field in TEXT + ("visual_evidence",):
        if one.get(field) and other.get(field) and one[field] != other[field]:
            fused[field] = f"{one[field]} · {other[field]}"
    return fused


def fuse(rows, interval):
    """Merge the cuts the adjustment left touching, and note every merge for `changes`."""
    merged, notes, follows = [], [], {}
    for row in rows:
        # Only neighbours with the same `included` merge: fusing a reserve into an included cut
        # would take the included one out of the render with no trace beyond the note.
        if (merged and row["a"] - merged[-1]["b"] < interval - 1e-9
                and merged[-1]["segment"].get("included", False)
                == row["segment"].get("included", False)):
            head = merged[-1]
            kept = min(head["segment"]["id"], row["segment"]["id"])
            discarded = max(head["segment"]["id"], row["segment"]["id"])
            notes.append(f"fusion: {head['segment']['id']} + {row['segment']['id']} "
                         f"-> {kept}")
            head["segment"] = join(head["segment"], row["segment"])
            head["b"] = max(head["b"], row["b"])
            head["note"] = head["note"] or row["note"]
            # `absorbed` travels with the surviving row so `topic_warnings` can still credit a
            # topic whose cited cut only rides inside another id's cut after the merge.
            head["absorbed"].append(discarded)
            follows[discarded] = kept
        else:
            merged.append(dict(row, absorbed=[]))
    if follows:
        # A cut that depended on an id now absorbed follows the surviving one instead: left
        # dangling, it would trip `dependency_warnings` (task 13) into a false `dependencia_excluida`.
        def settle(id_):
            while id_ in follows:
                id_ = follows[id_]
            return id_
        for row in merged:
            depends = row["segment"].get("depends_on")
            if depends:
                fixed = sorted({settle(other) for other in depends} - {row["segment"]["id"]})
                if fixed != depends:
                    row["segment"] = dict(row["segment"], depends_on=fixed)
    return merged, notes


def untouched(row):
    """True for the cuts whose audio is kept whole: visual ones and those that keep their pauses."""
    segment = row["segment"]
    return segment.get("visual_only", False) or not segment.get("remove_pauses", True)


def spans_of(row, levels, grid, settings):
    """Frame-aligned spans of one cut once its pauses are removed."""
    remove = settings["remove_pauses"] and not untouched(row)
    return common.islands(levels, row["a"], row["b"], interval=grid["interval"],
                          origin=grid["origin"], remove_pauses=remove,
                          threshold=settings["silence_db"])


def split(spans, frames, samples, grid, speed):
    """Subcuts of at most MAX_SPANS spans; N and M of the whole cut are shared out among them."""
    limit = common.MAX_SPANS
    rate, sample_rate = grid["fps"], grid["sample_rate"]
    groups = [spans[index:index + limit] for index in range(0, len(spans), limit)] or [[]]
    parts, frames_left, samples_left = [], frames, samples
    for index, group in enumerate(groups):
        length = sum(end - start for start, end in group)
        last = index == len(groups) - 1
        # Section 7.5: both totals belong to the whole cut, so the last subcut takes what is left
        # of each. Recomputing M here would lose samples whenever N / F * SR is not whole.
        count = (frames_left if last
                 else min(frames_left, common.frames_for(length, rate, speed)))
        share = (samples_left if last
                 else min(samples_left, common.samples_for(count, rate, sample_rate)))
        parts.append({"spans": group, "frames": count, "samples": share})
        frames_left -= count
        samples_left -= share
    return parts


def measure(rows, levels, grid, settings):
    """Spans, N, M and emptiness of every cut; an empty cut goes back to the reserves."""
    rate, speed, sample_rate = grid["fps"], settings["speed"], grid["sample_rate"]
    for row in rows:
        row["spans"] = spans_of(row, levels, grid, settings)
        row["length"] = round(sum(end - start for start, end in row["spans"]), 6)
        row["frames"] = common.frames_for(row["length"], rate, speed)
        row["output"] = row["frames"] / rate
        row["samples"] = common.samples_for(row["frames"], rate, sample_rate)
        # No spans leave L = 0, and N < 1 already implies L < 0.5 * v / F: the length test of
        # §7.4 alone covers every case, with no need for the two conditions it subsumes.
        row["empty"] = row["length"] < speed / rate - 1e-9
        row["subcuts"] = split(row["spans"], row["frames"], row["samples"], grid, speed)
        row["source"] = round(row["b"] - row["a"], 6)
    return rows


def retention(rows, settings):
    """Audio kept after removing pauses, over every candidate: included cuts and reserves."""
    if not settings["remove_pauses"]:
        # Nothing is ever removed when pauses stay in globally: no frame-alignment overshoot to
        # correct for, so the ratio is exactly whole regardless of what the rows measured.
        return 1.0
    source = sum(row["source"] for row in rows)
    kept = sum(row["source"] if untouched(row) else row["length"] for row in rows)
    # max(1e-6, ...) keeps `presupuesto` finite instead of dividing by zero when every candidate
    # is empty; min(1.0, ...) caps the frame-alignment overshoot that can push the raw ratio
    # above one when an edge falls off the sampling grid.
    return 1.0 if source <= 0 else max(1e-6, min(1.0, round(kept / source, 6)))


def band(target):
    """Acceptance band of the target and its half-width."""
    margin = common.tolerance(target)
    return [max(0.0, target - margin), target + margin], margin


def state_of(estimate, essentials, target, top):
    """One of the six states of section 7.6, in the order that makes them exclusive."""
    if target is None:
        return "sin_objetivo"
    limits, margin = band(target)
    if target > top + margin:
        return "inalcanzable"
    if essentials > limits[1]:
        return "inviable"
    if estimate > limits[1]:
        return "por_encima"
    if estimate < limits[0]:
        return "por_debajo"
    return "ok"


def estimate_of(rows, included, settings, total, grid):
    """Everything the proposal shows about length: budget, retention, band and state."""
    kept = [row for row in rows if row["segment"]["id"] in included and not row["empty"]]
    output = sum(row["frames"] for row in kept) / grid["fps"]
    essentials = sum(row["frames"] for row in kept
                     if row["segment"]["priority"] == 1) / grid["fps"]
    share = retention(rows, settings)
    top = total * share / settings["speed"]
    target = settings["objetivo"]
    report = {"cortes": len(kept),
              "origen": round(sum((row["source"] for row in kept), 0.0), 3),
              "tras_pausas": round(sum((row["length"] for row in kept), 0.0), 3),
              "salida": round(output, 3), "margen": CODEC_MARGIN,
              "porcentaje": round(100 * output / total, 2), "objetivo": target,
              "banda": ([round(value, 3) for value in band(target)[0]]
                        if target is not None else None),
              "retencion": share, "esenciales": round(essentials, 3),
              "presupuesto": (round(target * settings["speed"] / share, 3)
                              if target is not None else None),
              "minimo": round(100 * essentials / total, 2), "maximo": round(top, 3)}
    report["estado"] = state_of(output, essentials, target, top)
    return report


def percentile(levels, a, b, share=0.10):
    """Level below which `share` of the cut sits; the tenth percentile spots a noisy floor."""
    first, last = common.bounds(levels, a, b)
    window = sorted(levels[first:last])
    if not window:
        return common.ENERGY_FLOOR
    return window[min(len(window) - 1, int(share * len(window)))]


def cut_warnings(row, levels, settings):
    """Warnings that belong to one cut."""
    found, segment = [], row["segment"]
    key = segment["id"]
    if row["empty"]:
        found.append(common.warning("corte_vacio", f"El corte {key} se queda sin tramos tras "
                                    "quitar pausas; vuelve a las reservas.", cut=key))
        return found
    if row["note"]:
        found.append(common.warning("borde_en_voz", f"El corte {key} no encuentra silencio en los "
                                    "0,6 s del borde: la unión puede partir una palabra.", cut=key))
    if segment.get("visual_only") and row["output"] < SHORT_VISUAL:
        found.append(common.warning("visual_breve", f"El corte visual {key} dura "
                                    f"{row['output']:.1f} s de salida; cuesta leerlo.", cut=key))
    elif not segment.get("visual_only") and row["output"] < SHORT_CUT:
        found.append(common.warning("corte_breve", f"El corte {key} dura {row['output']:.1f} s de "
                                    "salida; puede quedar descontextualizado.", cut=key))
    # Both pause warnings only make sense where pauses are actually removed: a cut that keeps them,
    # by its own mark or by the job's, has nothing to measure.
    # `source` is always positive here: `check_draft` requires start < end, and neither
    # `adjusted` nor `fuse` ever shrink a cut to zero width.
    if settings["remove_pauses"] and not untouched(row):
        removed = 1 - row["length"] / row["source"]
        if removed > PAUSE_SHARE:
            found.append(common.warning("pausas_excesivas", f"En el corte {key} se elimina el "
                                        f"{100 * removed:.0f} % por pausas.", cut=key))
        # The quiet floor follows --silence-db: −53 dBFS with the default −50, as section 7.7 sets.
        quiet = settings["silence_db"] - QUIET_MARGIN
        if percentile(levels, row["a"], row["b"]) > quiet:
            shown = f"{quiet:.0f}".replace("-", "−")
            found.append(common.warning("sin_pausas_detectadas", f"El fondo del corte {key} supera "
                                        f"{shown} dBFS: revisa el umbral de silencio.", cut=key))
    return found


def global_warnings(estimate, settings, total, has_words):
    """Warnings about the job as a whole."""
    found, target = [], settings["objetivo"]
    if settings["speed"] > FAST_SPEED:
        found.append(common.warning("velocidad_alta", f"Velocidad ×{settings['speed']:g}: por "
                                    "encima de ×1,5 la voz técnica cuesta de seguir."))
    if target is not None and target < LOW_TARGET * total:
        found.append(common.warning("objetivo_muy_bajo", f"El objetivo ({target:.0f} s) es menor "
                                    f"que el 5 % del original ({LOW_TARGET * total:.0f} s)."))
    if estimate["estado"] == "inalcanzable":
        found.append(common.warning("objetivo_muy_alto", "Ni conservando todo el material se llega "
                                    f"a {target:.0f} s: el máximo es {estimate['maximo']:.0f} s."))
    if estimate["estado"] == "inviable":
        found.append(common.warning("esenciales_superan_objetivo", "Los cortes de prioridad 1 suman "
                                    f"{estimate['esenciales']:.0f} s, por encima de la banda."))
    if not has_words:
        found.append(common.warning("sin_marcas_por_palabra", "La transcripción procede de "
                                    "subtítulos sin palabras: los bordes usan límites de segmento."))
    return found


def dependency_warnings(rows, included):
    """An included cut that leans on an excluded one blocks the render."""
    found = []
    for row in rows:
        segment = row["segment"]
        if segment["id"] not in included:
            continue
        for other in segment.get("depends_on", []):
            if other not in included:
                found.append(common.warning("dependencia_excluida", f"El corte {segment['id']} "
                                            f"depende del {other}, que no está incluido.",
                                            cut=segment["id"]))
    return found


def topic_warnings(draft, rows, included):
    """A topic the inventory marked essential must have at least one included cut."""
    # A cut absorbed by an included one still rides inside it in the render, so it counts as
    # covered even though its own id never reaches `included`.
    covered = set(included)
    for row in rows:
        if row["segment"]["id"] in included:
            covered.update(row.get("absorbed", []))
    found = []
    for topic in draft.get("topics", []):
        if topic.get("imprescindible") and not set(topic.get("cortes", [])) & covered:
            found.append(common.warning("tema_sin_cubrir", f"El tema «{topic['nombre']}» se marcó "
                                        "imprescindible y no tiene ningún corte incluido."))
    return found
