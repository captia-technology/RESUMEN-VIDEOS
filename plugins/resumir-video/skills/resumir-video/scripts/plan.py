"""Deterministic planning: spans, exact estimate, states, warnings and the proposal to review."""

import contextlib
import json
import math
from pathlib import Path
import sys

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


def load_draft(path):
    """The agent's draft; a file that is missing or unreadable is an invalid argument."""
    try:
        return load(path)
    except FileNotFoundError:
        raise ValueError(f"No existe el borrador: {path}") from None
    except OSError as exc:
        raise ValueError(f"No se puede leer el borrador {path}: {exc.strerror or exc}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"El borrador {Path(path).name} no es JSON válido: {exc}") from None


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
    excluded = draft.get("excluded", [])
    if not isinstance(excluded, list):
        raise ValueError("excluded debe ser una lista de objetos con title y reason.")
    for position, item in enumerate(excluded, start=1):
        # The proposal writes both fields into a table: anything else would break it after the
        # plan is already published.
        if not isinstance(item, dict) or any(not isinstance(item.get(field), str)
                                             or not item[field].strip()
                                             for field in ("title", "reason")):
            raise ValueError(f"La exclusión {position} de excluded necesita title y reason "
                             "de texto no vacío.")
    return segments


def check_parent(draft, work, kind):
    """`parent` is null or the number of a version this folder has already published."""
    parent = draft.get("parent")
    if parent is None:
        return
    prefix = "esquema" if kind == "audio" else "seleccion"
    if type(parent) is not int or parent < 1 or not (work / f"{prefix}-v{parent}.json").is_file():
        raise ValueError("parent debe ser nulo o el número de una versión ya publicada "
                         f"({prefix}-vN.json en la carpeta de trabajo); recibido {parent!r}.")


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


QUESTION_FIELDS = ("question", "answer", "audio_evidence")


def questions_of(draft, total):
    """The session's questions: the discipline of check_draft, without spans or priority."""
    rows = draft.get("questions") or []
    if not isinstance(rows, list):
        raise ValueError("El borrador de audio requiere una lista «questions».")
    seen, previous = set(), -1.0
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"La pregunta {number} debe ser un objeto.")
        key = row.get("id")
        if type(key) is not int or key < 1:
            raise ValueError(f"La pregunta {number} necesita un id entero positivo.")
        if key in seen:
            raise ValueError(f"El id {key} se repite entre las preguntas.")
        seen.add(key)
        start, end = row.get("start"), row.get("end")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)):
            raise ValueError(f"La pregunta {key} necesita start y end numéricos finitos.")
        if not 0 <= start < end <= total:
            raise ValueError(f"La pregunta {key} está fuera del medio o invertida (el medio termina "
                             f"en {total:.3f} s).")
        if start < previous:
            raise ValueError(f"La pregunta {key} rompe el orden cronológico.")
        previous = start
        for field in QUESTION_FIELDS:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Falta {field} en la pregunta {key}.")
    return [{"id": row["id"], "start": round(float(row["start"]), 6),
             "end": round(float(row["end"]), 6), "question": row["question"].strip(),
             "answer": row["answer"].strip(),
             "audio_evidence": row["audio_evidence"].strip()} for row in rows]


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
                                    f"{comma(row['output'])} s de salida; cuesta leerlo.", cut=key))
    elif not segment.get("visual_only") and row["output"] < SHORT_CUT:
        found.append(common.warning("corte_breve", f"El corte {key} dura {comma(row['output'])} s "
                                    "de salida; puede quedar descontextualizado.", cut=key))
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
        found.append(common.warning("velocidad_alta", f"Velocidad ×{comma(settings['speed'], 2)}: "
                                    "por encima de ×1,5 la voz técnica cuesta de seguir."))
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


def copies(rows):
    """Fresh rows for a what-if run: `measure` writes on the row, not on the segment."""
    return [{"segment": row["segment"], "a": row["a"], "b": row["b"], "note": row["note"]}
            for row in rows]


def alternatives(rows, levels, grid, settings, included, total):
    """The four combinations of speed and pauses, each with its estimate and state."""
    speeds = sorted({1.0, settings["speed"]})
    if len(speeds) == 1:
        speeds = [1.0, 1.25]
    out = []
    for speed in speeds:
        for pauses in (True, False):
            variant = dict(settings, speed=speed, remove_pauses=pauses)
            report = estimate_of(measure(copies(rows), levels, grid, variant),
                                 included, variant, total, grid)
            out.append({"velocidad": speed, "pausas": pauses, "salida": report["salida"],
                        "porcentaje": report["porcentaje"], "estado": report["estado"]})
    return out


def movable(row, rows, included, *, essentials=False):
    """A cut can be freed only if it is not pinned and no included cut depends on it.

    Priority 1 stays protected too, unless `essentials` allows sacrificing one.
    """
    segment = row["segment"]
    if segment.get("pinned", False) or (not essentials and segment["priority"] == 1):
        return False
    return not any(segment["id"] in other["segment"].get("depends_on", [])
                   for other in rows if other["segment"]["id"] in included)


def suggestions(rows, included, settings, report):
    """Never applied alone: they respect priority 1, pinned cuts and dependencies."""
    out = []
    target = settings["objetivo"]
    if target is None:
        return out
    limits = report["banda"]
    kept = [row for row in rows if row["segment"]["id"] in included and not row["empty"]]
    if report["estado"] == "por_encima":
        excess, chosen = report["salida"] - limits[1], []
        for row in sorted(kept, key=lambda item: (-item["segment"]["priority"], -item["output"])):
            if excess <= 0:
                break
            if movable(row, rows, included):
                chosen.append(row["segment"]["id"])
                excess -= row["output"]
        if chosen:
            out.append({"tipo": "quitar", "cortes": chosen,
                        "texto": f"Pasa a reservas {', '.join(str(x) for x in chosen)} para entrar "
                                 f"en la banda (−{report['salida'] - limits[1]:.0f} s)."})
    if report["estado"] == "por_debajo":
        # A reserve whose dependency is still excluded (and not among the ones just chosen)
        # cannot be added on its own: it would trip `dependencia_excluida` once rendered.
        room, chosen = limits[1] - report["salida"], []
        for row in sorted(rows, key=lambda item: (item["segment"]["priority"], item["output"])):
            segment = row["segment"]
            if segment["id"] in included or row["empty"]:
                continue
            depends = segment.get("depends_on", [])
            if any(other not in included and other not in chosen for other in depends):
                continue
            if row["output"] <= room:
                chosen.append(segment["id"])
                room -= row["output"]
        if chosen:
            out.append({"tipo": "anadir", "cortes": chosen,
                        "texto": f"Recupera de reservas {', '.join(str(x) for x in chosen)}: caben "
                                 f"{limits[1] - report['salida']:.0f} s más."})
    if report["estado"] == "inviable":
        needed = settings["speed"] * report["esenciales"] / limits[1]
        has_speed = needed <= FAST_SPEED
        if has_speed:
            value = math.ceil(needed * 20) / 20
            out.append({"tipo": "velocidad", "valor": value,
                        "texto": f"Con velocidad ×{comma(value, 2)} los esenciales entran en la "
                                 "banda."})
        sacrifice, excess = [], report["esenciales"] - limits[1]
        essentials_kept = [item for item in kept if item["segment"]["priority"] == 1]
        for row in sorted(essentials_kept, key=lambda item: -item["output"]):
            if excess <= 0:
                break
            if movable(row, rows, included, essentials=True):
                sacrifice.append(row["segment"]["id"])
                excess -= row["output"]
        if sacrifice:
            # "O" only makes sense as a second option: it reads oddly on its own when no
            # speed change was offered first.
            prefix = "O renuncia" if has_speed else "Renuncia"
            out.append({"tipo": "sacrificar", "cortes": sacrifice,
                        "texto": f"{prefix} a los esenciales "
                                 f"{', '.join(str(x) for x in sacrifice)}."})
        out.append({"tipo": "porcentaje", "valor": report["minimo"],
                    "texto": f"El porcentaje mínimo razonable es {comma(report['minimo'])} % "
                             f"({report['esenciales']:.0f} s)."})
    if report["estado"] == "inalcanzable":
        out.append({"tipo": "objetivo", "valor": report["maximo"],
                    "texto": f"El objetivo máximo cumplible es {report['maximo']:.0f} s; no se "
                             "alarga el resumen con material prescindible."})
    return out


def comma(value, digits=1):
    """Spanish decimal notation, used by the suggestions and by the proposal."""
    return f"{value:.{digits}f}".replace(".", ",")


def cell(text):
    """One Markdown cell: a pipe, a stray CR or a newline would break the table."""
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def length(cut):
    """Output seconds of a published row."""
    return cut["salida"][1] - cut["salida"][0]


def cut_row(row, index, place, grid):
    """One cut of the published plan: origin, spans, exact N and M, and its place in the output."""
    segment = row["segment"]
    return {"id": segment["id"], "numero": index, "title": segment["title"],
            "phrase": segment["phrase"], "reason": segment["reason"],
            "audio_evidence": segment["audio_evidence"],
            "visual_evidence": segment.get("visual_evidence", ""),
            "priority": segment["priority"], "pinned": segment.get("pinned", False),
            "visual_only": segment.get("visual_only", False),
            "remove_pauses": segment.get("remove_pauses", True),
            "depends_on": sorted(segment.get("depends_on", [])),
            "start": round(row["a"], 6), "end": round(row["b"], 6),
            "spans": [[round(x, 6), round(y, 6)] for x, y in row["spans"]],
            "frames": row["frames"], "samples": row["samples"],
            "salida": [round(place, 6), round(place + row["frames"] / grid["fps"], 6)],
            "subcuts": [{"spans": [[round(x, 6), round(y, 6)] for x, y in part["spans"]],
                         "frames": part["frames"], "samples": part["samples"]}
                        for part in row["subcuts"]]}


def bar(rows, included, total, width=BAR):
    """Text timeline: one character per slice of the original, filled where a cut is kept."""
    slots = ["·"] * width
    for row in rows:
        if row["segment"]["id"] not in included or row["empty"]:
            continue
        first = max(0, min(width - 1, int(width * row["a"] / total)))
        last = max(first, min(width - 1, math.ceil(width * row["b"] / total) - 1))
        for index in range(first, last + 1):
            slots[index] = "#"
    return "".join(slots)


def proposal(plan, reserves, total, name):
    """propuesta-vN.md: what the user reads before accepting."""
    report, settings, clock = plan["estimate"], plan["settings"], common.clock
    head = [f"# Propuesta v{plan['version']} · resumen de «{name}»", "",
            f"Original {clock(total)} · " + (f"objetivo {clock(report['objetivo'])} "
            f"(banda {clock(report['banda'][0])}–{clock(report['banda'][1])}) · "
            if report["objetivo"] else "sin objetivo · ") +
            f"estimación {clock(report['salida'])} ({comma(report['porcentaje'])} %) · "
            f"estado **{report['estado']}**", "",
            f"{report['cortes']} cortes · {clock(report['origen'])} → sin pausas "
            f"{clock(report['tras_pausas'])} → ×{comma(settings['speed'], 2)} → "
            f"{clock(report['salida'])}", ""]
    head += ["## Cambios", ""] + [f"- {line}" for line in plan["changes"]] + [""]
    head += ["## Avisos", ""]
    head += [f"- {'**bloquea** · ' if item['bloquea'] else ''}`{item['codigo']}`"
             + (f" · corte {item['corte']}" if item["corte"] else "") + f" · {item['mensaje']}"
             for item in plan["warnings"]] or ["- ninguno"]
    head += ["", "## Cortes", "", "| # | Origen | Salida estimada | Prioridad | Qué se dice |",
             "| --- | --- | --- | --- | --- |"]
    for item in plan["segments"]:
        head.append(f"| {item['numero']} | {clock(item['start'])}–{clock(item['end'])} "
                    f"| {clock(item['salida'][0])}–{clock(item['salida'][1])} "
                    f"({length(item):.0f} s) | {item['priority']} | {cell(item['phrase'])} |")
    head += ["", "## Reservas", "", "| # | Origen | Qué aportaría |", "| --- | --- | --- |"]
    for item in reserves:
        head.append(f"| {item['numero']} | {clock(item['start'])}–{clock(item['end'])} | "
                    f"{cell(item['reason'])} |")
    head += ["", "## Exclusiones deliberadas", "", "| Qué | Por qué |", "| --- | --- |"]
    for item in plan["excluidos"]:
        head.append(f"| {cell(item.get('title', ''))} | {cell(item.get('reason', ''))} |")
    head += ["", "## Alternativas", "", "| Velocidad | Pausas | Salida | % | Estado |",
             "| --- | --- | --- | --- | --- |"]
    for item in plan["alternativas"]:
        head.append(f"| ×{comma(item['velocidad'], 2)} | {'sí' if item['pausas'] else 'no'} | "
                    f"{clock(item['salida'])} | {comma(item['porcentaje'])} % | {item['estado']} |")
    head += ["", "## Sugerencias", ""] + ([f"- {hint['texto']}" for hint in plan["sugerencias"]]
                                          or [("- ninguna: el plan está dentro de la banda"
                                               if report["estado"] == "ok" else
                                               "- ninguna aplicable: no hay ajuste disponible "
                                               f"para el estado «{report['estado']}».")])
    head += ["", "## Recorrido", "", f"`{plan['recorrido']}`", "",
             f"0:00 ← cada carácter son {comma(total / BAR)} s → {clock(total)}", "",
             "## Cómo responder", "",
             "- «acepta» o «móntalo» para montar esta versión.",
             "- El número es el de la columna # de esta propuesta, común a cortes y reservas.",
             "- «quita el 7 y el 9», «añade el 6», «alarga el 3 diez segundos».",
             "- «añade la parte donde habla de ATEX», «parte el 4», «une 4 y 5».",
             "- «súbelo al 15 %», «sin acelerar», «no quites pausas en el 12».",
             "- «vuelve a la v1» o «¿qué has dejado fuera?».", ""]
    return "\n".join(head)


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def source_of(data):
    """Identity and fingerprint of the medium in one place: path, size, mtime and sha256."""
    source = dict(data["source"])
    source.update(data.get("fingerprint") or {})
    if "sha256" not in source:
        source.update(common.fingerprint(source["path"]))
    return source


def discard(*paths):
    """Remove leftovers; a cleanup that fails never hides the error that made it necessary."""
    for path in paths:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def publish_version(work, prefix, body, extra=None):
    """Reserve N, then publish the plan and its companion Markdown: both, or nothing at all.

    `extra` takes no arguments: by the time it runs, N is already in `body["version"]`.
    """
    version, path = common.reserve_version(work, prefix)
    final = work / f"propuesta-v{version}.md"
    staged = work / f"propuesta-v{version}.md.parcial"
    try:
        body["version"] = version
        body["sha256"] = common.plan_sha256(body)
        if extra is not None:
            if final.exists():
                raise ValueError(f"Ya está publicado y no se sobrescribe: {final}")
            # Drafted before the reserve is filled: a Markdown that cannot be written must not
            # leave a plan without its proposal behind.
            staged.write_text(extra(), encoding="utf-8", newline="\n")
        common.write_reserved(path, dumps(body) + "\n")
        if extra is not None:
            common.publish(staged, final)
    except BaseException:
        discard(path, staged)
        raise
    return version, path


def changes(work, parent, cuts, notes):
    """Diff against the version this draft comes from: additions, removals, edits and merges.

    Section 9 asks for the three lines in seconds, so none of them goes through `common.clock`.
    """
    lines = list(notes)
    path = work / f"seleccion-v{parent}.json" if parent else None
    if path is None or not path.is_file():
        return lines or ["propuesta inicial"]
    before = {item["id"]: item for item in load(path).get("segments", [])}
    now = {item["id"]: item for item in cuts}
    for key in sorted(set(now) - set(before)):
        lines.append(f"alta: {key} · {now[key]['title']} · {comma(length(now[key]))} s")
    for key in sorted(set(before) - set(now)):
        lines.append(f"baja: {key} · {before[key]['title']}")
    for key in sorted(set(before) & set(now)):
        old, new = before[key], now[key]
        if (abs(length(old) - length(new)) > 0.05 or old["phrase"] != new["phrase"]
                or old["title"] != new["title"]):
            lines.append(f"cambio: {key} · {new['title']} · {comma(length(old))} s → "
                         f"{comma(length(new))} s · {new['phrase'][:60]}")
    return lines or ["sin cambios respecto a la versión anterior"]


def video_plan(args, work, data, draft, settings, segments, total, levels, words, grid):
    """The whole section 7 pipeline for a video job."""
    rows, notes = fuse(adjusted(segments, levels, words, settings["silence_db"]), grid["interval"])
    rows = measure(rows, levels, grid, settings)
    included = {row["segment"]["id"] for row in rows
                if row["segment"].get("included", False) and not row["empty"]}
    # Section 7.4: a cut the agent wanted and the discards emptied goes back to reserves, and that
    # move is a change of this version, not only a warning.
    notes += [f"corte vacío: {row['segment']['id']} · {row['segment']['title']} · sin tramos tras "
              "quitar pausas: vuelve a reservas (corte_vacio)"
              for row in rows if row["empty"] and row["segment"].get("included", False)]
    report = estimate_of(rows, included, settings, total, grid)
    cuts, place = [], 0.0
    for row in [item for item in rows if item["segment"]["id"] in included]:
        cuts.append(cut_row(row, len(cuts) + 1, place, grid))
        place += row["frames"] / grid["fps"]
    left = [row for row in rows if row["segment"]["id"] not in included]
    # One numbering for the whole proposal (section 9): the reserves go on where the cuts stop.
    reserves = [cut_row(row, len(cuts) + number, 0.0, grid)
                for number, row in enumerate(left, start=1)]
    warnings = global_warnings(report, settings, total, bool(words))
    warnings += dependency_warnings(rows, included) + topic_warnings(draft, rows, included)
    for row in rows:
        # `included` already leaves the empty ones out, so `row["empty"]` brings them back for their
        # warning — but only if the agent wanted the cut: an empty reserve is material nobody
        # mounts, and its blocking `corte_vacio` would return 2 for nothing.
        if row["segment"].get("included", False) and (row["segment"]["id"] in included
                                                      or row["empty"]):
            warnings += cut_warnings(row, levels, settings)
    # prepare records huecos_pts and fuente_vfr of the packet probe; plan only carries them on.
    warnings += [common.warning(item["codigo"], item["mensaje"], cut=item.get("corte"))
                 for item in data.get("avisos", [])]
    # A draft born from --import carries its own warnings (identidad_parcial): the same queue
    # carries them into the published plan and its proposal, instead of stopping at the draft.
    warnings += [common.warning(item["codigo"], item["mensaje"], cut=item.get("corte"))
                 for item in draft.get("warnings", [])]
    body = {"version": 0, "parent": draft.get("parent"), "kind": "video",
            "request": draft.get("request", ""), "source": source_of(data),
            "audio_stream": data["audio_stream"],
            "settings": settings, "timeline": grid,
            "segments": cuts, "reserves": reserves, "excluidos": draft.get("excluded", []),
            "changes": [], "estimate": report,
            "alternativas": alternatives(rows, levels, grid, settings, included, total),
            "sugerencias": suggestions(rows, included, settings, report),
            "warnings": warnings, "recorrido": bar(rows, included, total)}
    body["changes"] = changes(work, draft.get("parent"), cuts, notes)
    blocking = any(item["bloquea"] for item in warnings)
    if args.dry_run:
        body["sha256"] = common.plan_sha256(body)
        print(dumps(body))
        return 2 if blocking else 0
    name = Path(data["source"]["path"]).name
    version, path = publish_version(work, "seleccion", body,
                                    lambda: proposal(body, reserves, total, name))
    common.history(work, "edit" if draft.get("parent") else "init",
                   {"tipo": "seleccion", "version": version, "segments": len(cuts),
                    "estado": report["estado"], "salida": report["salida"],
                    "sha256": body["sha256"], "peticion": draft.get("request", "")})
    print(path)
    return 2 if blocking else 0


def audio_plan(args, work, data, draft, settings, segments, total, levels, words, grid):
    """Audio jobs publish an outline: ideas and questions with times, no spans and no speed."""
    included = {segment["id"] for segment in segments if segment.get("included", False)}
    ideas = [{"numero": number, "id": segment["id"], "priority": segment["priority"],
              "title": segment["title"], "phrase": segment["phrase"], "reason": segment["reason"],
              "audio_evidence": segment["audio_evidence"],
              "start": round(segment["start"], 6), "end": round(segment["end"], 6)}
             for number, segment in enumerate([item for item in segments
                                               if item["id"] in included], start=1)]
    if not ideas:
        raise ValueError("El esquema necesita al menos una idea clave incluida en el borrador.")
    questions = questions_of(draft, total)
    warnings = dependency_warnings([{"segment": item} for item in segments], included)
    warnings += topic_warnings(draft, [{"segment": item} for item in segments], included)
    if not words:
        warnings.append(common.warning(
            "sin_marcas_por_palabra", "La transcripción no trae marcas por palabra: los tiempos "
            "del esquema son los de cada segmento."))
    # prepare records huecos_pts and fuente_vfr of the packet probe; the outline only carries them on.
    warnings += [common.warning(item["codigo"], item["mensaje"], cut=item.get("corte"))
                 for item in data.get("avisos", [])]
    body = {"version": 0, "parent": draft.get("parent"), "kind": "audio",
            "request": draft.get("request", ""), "source": data["source"],
            "audio_stream": data["audio_stream"],
            # No montage in audio: target, speed and pauses are published neutralised (section 4).
            "settings": {"target": None, "speed": 1.0, "remove_pauses": False,
                         "silence_db": settings["silence_db"], "rate": None,
                         "sample_rate": grid["sample_rate"], "tolerance": None},
            "ideas": ideas, "questions": questions, "excluded": draft.get("excluded", []),
            "changes": [] if draft.get("parent") else ["propuesta inicial"],
            "warnings": warnings}
    blocking = any(item["bloquea"] for item in warnings)
    if args.dry_run:
        body["sha256"] = common.plan_sha256(body)
        print(dumps(body))
        return 2 if blocking else 0
    name = Path(data["source"]["path"]).name
    version, path = publish_version(work, "esquema", body,
                                    lambda: audio_proposal(body, total, name, body["version"]))
    common.history(work, "edit" if draft.get("parent") else "init",
                   {"version": version, "ideas": len(ideas), "preguntas": len(questions),
                    "sha256": body["sha256"], "peticion": draft.get("request", "")})
    print(path)
    return 2 if blocking else 0


def audio_proposal(body, total, name, version):
    """The outline the user accepts before the document is written."""
    lines = [f"# Esquema v{version} · documento de «{name}»", "",
             f"Original {common.clock(total)} · {len(body['ideas'])} ideas · "
             f"{len(body['questions'])} preguntas · sin montaje (entrada de solo audio)", "",
             "En modo audio se ignoran objetivo, velocidad y pausas: la entrega es el documento.",
             "", "## Avisos", ""]
    lines += [f"- {'**bloquea** · ' if item['bloquea'] else ''}`{item['codigo']}` · "
              f"{item['mensaje']}" for item in body["warnings"]] or ["- ninguno"]
    lines += ["", "## Ideas", "", "| # | Origen | Prioridad | Qué se dice |",
              "| --- | --- | --- | --- |"]
    for idea in body["ideas"]:
        lines.append(f"| {idea['numero']} | {common.clock(idea['start'])}–"
                     f"{common.clock(idea['end'])} | {idea['priority']} | {cell(idea['phrase'])} |")
    lines += ["", "## Preguntas", "", "| # | Origen | Pregunta | Respuesta |",
              "| --- | --- | --- | --- |"]
    for item in body["questions"]:
        lines.append(f"| {item['id']} | {common.clock(item['start'])}–"
                     f"{common.clock(item['end'])} | {cell(item['question'])} | "
                     f"{cell(item['answer'])} |")
    if not body["questions"]:
        lines.append("| — | — | No se registraron preguntas en la sesión. | — |")
    lines += ["", "## Exclusiones deliberadas", "", "| Qué | Por qué |", "| --- | --- |"]
    for item in body["excluded"]:
        lines.append(f"| {cell(item.get('title', ''))} | {cell(item.get('reason', ''))} |")
    lines += ["", "## Cómo responder", "",
              "- «acepta» o «adelante» para redactar el documento con este esquema.",
              "- «quita la 3», «añade lo de ATEX», «junta la 1 y la 2» para cambiarlo.",
              "- «¿qué has dejado fuera?» para ver lo descartado sin crear una versión.", ""]
    return "\n".join(lines)


def publish_draft(work, body, event, payload, dry_run):
    """The shared ending of --import and --revert: a new draft, never a plan."""
    if dry_run:
        print(dumps(body))
        return 0
    version, path = common.reserve_version(work, "borrador")
    body["version"] = version
    common.write_reserved(path, dumps(body) + "\n")
    # `version` numbers a draft here, a selection in the lines of `video_plan`: `tipo` says which.
    common.history(work, event, {"tipo": "borrador", "version": version, **payload})
    print(path)
    return 0


def import_plan(args, work, data, total):
    """Convert a 0.1 plan into a draft that still needs review and acceptance."""
    old = load(args.import_from)
    identity = old.get("source") if isinstance(old.get("source"), dict) else {}
    current = data["source"]
    # A 0.1 plan has no fingerprint: only size and mtime can be contrasted.
    differing = [key for key in ("size", "mtime_ns") if identity.get(key) != current.get(key)]
    if differing:
        raise ValueError("El plan importado no corresponde a este medio "
                         f"(difiere: {', '.join(differing)}).")
    old_segments = old.get("segments")
    if not isinstance(old_segments, list) or not old_segments:
        raise ValueError("El plan importado no tiene cortes.")
    segments, previous = [], 0.0
    for index, segment in enumerate(old_segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"El corte {index} del plan importado debe ser un objeto.")
        start = number(segment.get("start"), f"start del corte {index}")
        end = number(segment.get("end"), f"end del corte {index}")
        if not previous <= start < end <= total:
            raise ValueError(f"El corte {index} del plan importado está desordenado, solapado o "
                             f"fuera del medio (termina en {total:.3f} s).")
        title = segment.get("title", f"Corte {index}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"El título del corte {index} del plan importado debe ser texto.")
        segments.append({"id": index, "start": start, "end": end, "title": title, "phrase": title,
                         "reason": segment.get("reason", "Importado de un plan 0.1"),
                         "audio_evidence": segment.get("audio_evidence", "Importado de un plan 0.1"),
                         "visual_evidence": segment.get("visual_evidence",
                                                        "Importado de un plan 0.1"),
                         "priority": 1, "included": True, "pinned": False, "depends_on": [],
                         "remove_pauses": False, "visual_only": False})
        previous = end
    body = {"parent": None, "request": f"Importado de {Path(args.import_from).name}",
            # The fingerprint is recomputed from the file itself, never copied from the 0.1 plan.
            "source": dict(current, **common.fingerprint(current["path"])),
            "settings": {"target": None, "speed": 1.0, "remove_pauses": False,
                         "silence_db": common.SILENCE_DB},
            "segments": segments, "excluded": [], "topics": [],
            "warnings": [common.warning("identidad_parcial", "Plan 0.1 sin huella: se contrastaron "
                                        "tamaño y fecha y se completó desde el archivo actual.")]}
    return publish_draft(work, body, "init",
                         {"segments": len(segments), "importado": Path(args.import_from).name},
                         args.dry_run)


def revert(args, work):
    """«Vuelve a la vN»: copy that published plan into a new draft."""
    source = work / f"seleccion-v{args.revert}.json"
    if not source.is_file():
        raise ValueError(f"No existe {source.name} en la carpeta de trabajo.")
    old = load(source)
    published = old.get("segments", [])
    kept = {item["id"] for item in published}
    segments = []
    # `cut_row` always writes these keys for both `segments` and `reserves`: no default is needed.
    for item in published + old.get("reserves", []):
        segments.append({"id": item["id"], "start": item["start"], "end": item["end"],
                         "title": item["title"], "phrase": item["phrase"], "reason": item["reason"],
                         "audio_evidence": item["audio_evidence"],
                         "visual_evidence": item["visual_evidence"],
                         "priority": item["priority"], "included": item["id"] in kept,
                         "pinned": item["pinned"], "depends_on": item["depends_on"],
                         "remove_pauses": item["remove_pauses"],
                         "visual_only": item["visual_only"]})
    segments.sort(key=lambda item: item["start"])
    body = {"parent": old["version"], "request": f"Vuelve a la v{old['version']}",
            "source": old["source"],
            "settings": {key: old["settings"][key] for key in
                         ("target", "speed", "remove_pauses", "silence_db")},
            "segments": segments, "excluded": old.get("excluidos", []), "topics": []}
    return publish_draft(work, body, "edit", {"desde": old["version"]}, args.dry_run)


def run(args):
    """Entry point registered by `register`; video.py reaches it through args.run."""
    work = Path(args.work).resolve()
    if not work.is_dir():
        raise ValueError(f"No existe la carpeta de trabajo: {work}")
    data = load(work / "metadata.json")
    total = common.duration(data)
    if args.import_from or args.revert is not None:
        # Section 12: these options shape a video job's settings, and neither --import nor
        # --revert runs one; silently ignoring them would hide a request the caller made.
        if any(value is not None for value in
               (args.target, args.speed, args.pauses, args.silence_db)):
            print("Error: --target, --speed, --pauses y --silence-db no se aplican con --import "
                 "ni --revert.", file=sys.stderr)
            return 2
        return import_plan(args, work, data, total) if args.import_from else revert(args, work)
    if not args.draft:
        # Section 12: a draft that is missing is as invalid an argument as one that is wrong, so it
        # leaves by the same door as `check_draft` below, with code 2 and without writing anything.
        print("Error: indica --draft con el borrador del agente.", file=sys.stderr)
        return 2
    # prepare writes `kind`; a job that does not declare it is a video job, as in 0.1.0.
    kind = args.kind or data.get("kind") or "video"
    grid = data.get("timeline") or common.timeline(data)
    try:
        draft = load_draft(args.draft)
        settings = settings_of(draft, args, total, grid)
        segments = check_draft(draft, total, kind)
        check_parent(draft, work, kind)
    except ValueError as exc:
        # The same door: a draft the agent has to fix (or cannot even give us) is an invalid
        # argument, not a controlled failure.
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    transcript = work / "transcripcion.json"
    words = words_of(load(transcript)) if transcript.is_file() else []
    levels = common.energy(work / "audio.wav", work / "energia.f32")
    if kind == "audio":
        return audio_plan(args, work, data, draft, settings, segments, total, levels, words, grid)
    return video_plan(args, work, data, draft, settings, segments, total, levels, words, grid)


def register(sub):
    """Add the `plan` subcommand and leave its entry point in the parsed arguments."""
    parser = sub.add_parser("plan",
                            help="Calcula tramos, estimación, avisos y propuesta desde un borrador.")
    parser.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    # Exactly one way to get a video job's segments: a draft to plan, a 0.1 plan to import, or a
    # published version to copy back into a new draft. argparse itself refuses any other pair.
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--draft", help="Borrador del agente (JSON) con segments y settings.")
    source.add_argument("--import", dest="import_from",
                        help="Convierte un plan 0.1 en un borrador nuevo.")
    source.add_argument("--revert", type=common.positive,
                        help="Copia seleccion-vN.json a un borrador nuevo.")
    parser.add_argument("--target",
                        help="Objetivo: 10%%, 720s, 12min o 0:12:00 (prevalece sobre el borrador).")
    parser.add_argument("--speed", type=float, help="Velocidad de 1,0 a 2,0 (por defecto 1,25).")
    parser.add_argument("--pauses", choices=("si", "no"), help="Eliminación global de pausas.")
    parser.add_argument("--silence-db", type=float,
                        help="Umbral de silencio en dBFS (por defecto -50).")
    parser.add_argument("--kind", choices=("video", "audio"),
                        help="Modo; por defecto, el de metadata.json.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calcula e imprime el plan sin publicar versión.")
    parser.set_defaults(run=run)
    return parser
