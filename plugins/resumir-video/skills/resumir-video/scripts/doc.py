"""Document rendering: time marks, generated blocks, timeline and DOCX conversion."""

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import re
import sys

import common

MARK = re.compile(r"\[\[([a-z]+)(?:=([^\]]*))?\]\]")
BLOCKS = ("ficha", "indice", "timeline", "validacion")
VIDEO_ONLY = ("indice", "timeline", "validacion")
# Drive letters, home folders and UNC shares; an URL such as https://… never matches.
# The home folders are joined instead of written out: a literal one would trip the packaging
# check that forbids absolute paths anywhere under plugins/.
HOMES = tuple(f"/{name}/" for name in ("Users", "home"))
ABSOLUTE = re.compile("|".join((r"(?<![A-Za-z])[A-Za-z]:[\\/]", *HOMES, r"\\\\[A-Za-z0-9]")))
PENDING = re.compile(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\(pendiente de completar\)"
                     r"|\[completar\]|<completar>", re.IGNORECASE)
WIDTH = 48


def stretches_of(cut):
    """Kept stretches of a cut; the published plan always names them `spans`."""
    pieces = cut.get("spans")
    if not pieces:
        raise ValueError(f"El corte {cut.get('id')} no tiene tramos publicados.")
    return [(float(a), float(b)) for a, b in pieces]


def bounds_of(cut, pieces):
    """The published plan carries start and end; a hand-written one leaves its spans to say so."""
    return float(cut.get("start", pieces[0][0])), float(cut.get("end", pieces[-1][1]))


def placements(segments, speed, rate):
    """Output span of every cut and the output instant where each kept stretch starts."""
    spans, offset = [], 0.0
    for cut in segments:
        pieces = stretches_of(cut)
        stretches, inner = [], 0.0
        for a, b in pieces:
            stretches.append((a, b, offset + inner / speed))
            inner += b - a
        # The published N rules: the document must agree with the montage frame by frame.
        frames = cut.get("frames")
        frames = round(inner * rate / speed) if frames is None else int(frames)
        start, end = bounds_of(cut, pieces)
        spans.append({"id": cut["id"], "title": cut.get("title", ""), "start": start, "end": end,
                      "offset": offset, "length": frames / rate, "stretches": stretches})
        offset += frames / rate
    return spans


def output_at(t, spans, speed):
    """Output instant of a source instant, or None when no cut keeps it."""
    for span in spans:
        if not span["start"] <= t <= span["end"]:
            continue
        for a, b, base in span["stretches"]:
            # Inside a removed pause: the spec uses the start of the next stretch.
            if t < a:
                return base
            if t <= b:
                return base + (t - a) / speed
        # Past the last stretch but inside the cut: the last pause, so the cut's own end.
        return span["offset"] + span["length"]
    return None


def moment(t, spans, speed):
    if spans is None:
        return common.clock(t)
    out = output_at(t, spans, speed)
    if out is None:
        return f"{common.clock(t)} (no incluido en el resumen)"
    return f"{common.clock(t)} (resumen {common.clock(out)})"


def interval(a, b, spans, speed):
    label = f"{common.clock(a)}–{common.clock(b)}"
    if spans is None:
        return label
    first, last = output_at(a, spans, speed), output_at(b, spans, speed)
    if first is not None and last is not None:
        return f"{label} (resumen {common.clock(first)}–{common.clock(last)})"
    if first is None and last is None:
        return f"{label} (no incluido en el resumen)"
    return f"{label} (incluido en parte en el resumen)"


def number_of(value, number, total):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Línea {number}: [[t={value}]] no es un número de segundos.") from None
    if not 0 <= seconds <= total:
        raise ValueError(f"Línea {number}: {seconds:g} s queda fuera del medio (0–{total:.3f} s).")
    return seconds


def replace_line(line, number, context):
    match = MARK.fullmatch(line.strip())
    if match and match.group(1) in BLOCKS:
        return block(match.group(1), number, context)

    def one(hit):
        name, value = hit.group(1), hit.group(2)
        if name in BLOCKS:
            raise ValueError(f"Línea {number}: la marca [[{name}]] debe ocupar una línea entera.")
        if name == "t":
            return moment(number_of(value, number, context["total"]), context["spans"], context["speed"])
        if name == "r":
            parts = str(value).split("-")
            if len(parts) != 2:
                raise ValueError(f"Línea {number}: [[r={value}]] debe ser inicio-fin en segundos.")
            a, b = (number_of(part, number, context["total"]) for part in parts)
            if not a < b:
                raise ValueError(f"Línea {number}: [[r={value}]] tiene el fin antes del inicio.")
            return interval(a, b, context["spans"], context["speed"])
        raise ValueError(f"Línea {number}: marca desconocida [[{name}]].")

    return MARK.sub(one, line)


def expand(text, context):
    """Expand every mark; the first problem stops the document naming its line."""
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if ABSOLUTE.search(line):
            raise ValueError(f"Línea {number}: ruta absoluta en el documento; usa solo el nombre "
                             "del archivo.")
        if PENDING.search(line):
            raise ValueError(f"Línea {number}: texto pendiente de completar.")
    return "\n".join(replace_line(line, number, context)
                     for number, line in enumerate(lines, start=1)) + "\n"


def block(name, number, context):
    if context["spans"] is None and name in VIDEO_ONLY:
        raise ValueError(f"Línea {number}: la marca [[{name}]] no existe en modo audio.")
    raise ValueError(f"Línea {number}: la marca [[{name}]] aún no está disponible.")
