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
        if segment.get("priority") not in (1, 2, 3):
            raise ValueError(f"La prioridad del corte {key} debe ser 1, 2 o 3.")
        for name in ("included", "pinned", "remove_pauses", "visual_only"):
            flag(segment, name, name == "remove_pauses")
        depends = segment.get("depends_on", [])
        if not isinstance(depends, list) or any(type(x) is not int or x == key for x in depends):
            raise ValueError(f"depends_on del corte {key} debe listar identificadores distintos.")
        seen[key], previous = segment, end
    for segment in segments:
        for other in segment.get("depends_on", []):
            if other not in seen:
                raise ValueError(f"El corte {segment['id']} depende de {other}, que no existe.")
    for topic in draft.get("topics", []):
        if not isinstance(topic.get("nombre"), str) or not topic["nombre"].strip():
            raise ValueError("Cada tema necesita un nombre.")
        if any(x not in seen for x in topic.get("cortes", [])):
            raise ValueError(f"El tema «{topic['nombre']}» cita cortes que no existen.")
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
    speed = float(base.get("speed", 1.25))
    if not 1.0 <= speed <= 2.0:
        raise ValueError(f"La velocidad debe estar entre 1,0 y 2,0 (recibida {speed:g}).")
    target = common.parse_target(base.get("target"), total)
    return {"target": base.get("target"), "objetivo": target,
            "tolerance": common.tolerance(target) if target is not None else None,
            "speed": round(speed, 3), "remove_pauses": bool(base.get("remove_pauses", True)),
            "silence_db": float(base.get("silence_db", common.SILENCE_DB)),
            # render rebuilds the cadence from the plan alone, without opening metadata.json.
            "rate": grid["rate"], "sample_rate": grid["sample_rate"]}


def words_of(transcription):
    """Flat, ordered word marks; empty when the transcription comes from plain subtitles."""
    words = []
    for segment in (transcription or {}).get("segments", []):
        words.extend({"start": float(word["start"]), "end": float(word["end"])}
                     for word in segment.get("words", []) if word.get("start") is not None)
    return sorted(words, key=lambda word: word["start"])
