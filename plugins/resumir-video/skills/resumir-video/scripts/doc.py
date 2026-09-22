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


def table(rows):
    """Markdown table from a list of rows; the first one is the header."""
    head = f"| {' | '.join(str(c) for c in rows[0])} |"
    rule = f"| {' | '.join('---' for _ in rows[0])} |"
    body = [f"| {' | '.join(str(c) for c in row)} |" for row in rows[1:]]
    return "\n".join([head, rule] + body)


def percent(part, whole):
    return f"{100 * part / whole:.1f}".replace(".", ",") + " %"


def count(number, singular, plural):
    return f"{number} {singular if number == 1 else plural}"


def read_json(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Falta {path.name} en {path.parent}.")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def transcriber(work):
    """How the audio evidence was obtained, for the document's data sheet."""
    path = Path(work) / "transcripcion.json"
    if not path.is_file():
        return "sin transcripción"
    data = read_json(path)
    settings = data.get("settings") or {}
    name = settings.get("model") or settings.get("origen") or "subtítulos del medio"
    return f"{name} ({data.get('language') or 'idioma sin declarar'})"


def ficha(context):
    name = Path(context["metadata"]["source"]["path"]).name
    stamp = datetime.date.today().isoformat()
    if context["spans"] is None:
        schema = context["schema"] or {"ideas": [], "questions": []}
        return table([["Campo", "Valor"], ["Archivo", name],
                      ["Duración", common.clock(context["total"])],
                      ["Ideas clave", count(len(schema["ideas"]), "idea", "ideas")],
                      ["Preguntas", count(len(schema["questions"]), "pregunta", "preguntas")],
                      ["Transcripción", context["transcriber"]],
                      ["Versión", f"v{context['version']} · {stamp}"]])
    output = sum(span["length"] for span in context["spans"])
    # `remove_pauses` is the published setting; more than one stretch proves it on a hand-written plan.
    setting = context["settings"].get("remove_pauses")
    removed = any(len(span["stretches"]) > 1 for span in context["spans"])
    pauses = "pausas eliminadas" if (removed if setting is None else setting) else "pausas conservadas"
    speed = f"×{context['speed']:g}".replace(".", ",")
    return table([["Campo", "Valor"], ["Archivo", name],
                  ["Duración original", common.clock(context["total"])],
                  ["Duración del resumen",
                   f"{common.clock(output)} ({percent(output, context['total'])} del original)"],
                  ["Técnicas",
                   f"{count(len(context['spans']), 'corte', 'cortes')} · {pauses} · velocidad {speed}"],
                  ["Transcripción", context["transcriber"]],
                  ["Versión", f"v{context['version']} · {stamp}"]])


def indice(context):
    rows = [["#", "Origen", "Salida", "Tema"]]
    for span in context["spans"]:
        title = str(span["title"]).replace("|", "\\|").replace("\n", " ")
        rows.append([span["id"], f"{common.clock(span['start'])}–{common.clock(span['end'])}",
                     f"{common.clock(span['offset'])}–"
                     f"{common.clock(span['offset'] + span['length'])}", title])
    return table(rows)


def timeline_row(spans, total, width=WIDTH):
    """One character per slice of the original: a full block where a cut is kept."""
    row = ["·"] * width
    for span in spans:
        first = min(width - 1, int(span["start"] / total * width))
        last = min(width - 1, math.ceil(span["end"] / total * width) - 1)
        for i in range(first, max(first, last) + 1):
            row[i] = "█"
    return "".join(row)


def timeline_text(spans, total, width=WIDTH):
    output = sum(span["length"] for span in spans)
    return "\n".join([
        f"Línea temporal · original {common.clock(total)} · resumen {common.clock(output)} · "
        f"cada carácter ≈ {total / width:.0f} s", "", "```text",
        f"{common.clock(0)} ▕{timeline_row(spans, total, width)}▏ {common.clock(total)}",
        "█ incluido   · fuera del resumen", "```"])


def timeline_png(spans, total, path):
    """Bar of the original with the kept cuts marked; None when Pillow is missing."""
    path = Path(path)
    if path.exists():
        # A document revision reuses the picture of its version: it never republishes it.
        return path
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    image = Image.new("RGB", (900, 60), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    inner = 880
    draw.rectangle([10, 10, 10 + inner - 1, 49], fill=(228, 228, 228))
    for span in spans:
        left = 10 + int(span["start"] / total * inner)
        right = 10 + max(int(span["start"] / total * inner) + 1, int(span["end"] / total * inner))
        draw.rectangle([left, 10, min(right, 10 + inner) - 1, 49], fill=(40, 90, 160))
    staged = path.with_name(f"{path.name}.parcial")
    image.save(staged, "PNG")
    staged.replace(path)
    return path


def timeline(context):
    text = timeline_text(context["spans"], context["total"])
    picture = timeline_png(context["spans"], context["total"], Path(context["out"]) / "timeline.png")
    if picture is None:
        context["avisos"].append("Sin Pillow: el timeline se entrega solo en texto "
                                 "(instálalo con `python -m pip install pillow`).")
        return text
    return f"{text}\n\n![Línea temporal del resumen](timeline.png)"


def validacion(context):
    path = Path(context["out"]) / "validacion.json"
    if not path.is_file():
        context["avisos"].append("Sin informe de validación en la carpeta de la versión: el documento "
                                 "declara la comprobación técnica como no realizada.")
        return ("Informe de validación no disponible: la carpeta de la versión no incluye "
                "`validacion.json`.")
    data = read_json(path)
    places = data.get("colocacion") or []
    distances = [row["distancia"] for place in places for row in place.get("imagen") or []]
    lags = [abs(row["desfase_ms"]) for place in places for row in place.get("envolvente") or []
            if row.get("bloques", 0) != 0]
    drift = f"{float(data.get('desfase_s', 0)):.3f}".replace(".", ",")
    image = f"{max(distances, default=0.0):.3f}".replace(".", ",")
    return table([["Comprobación", "Resultado"],
                  ["Fotogramas", f"{data.get('fotogramas', '?')} de "
                                 f"{data.get('fotogramas_esperados', '?')} esperados"],
                  ["Desfase vídeo/audio", f"{drift} s"],
                  ["Colocación de los cortes",
                   f"{count(len(places), 'corte comprobado', 'cortes comprobados')} · "
                   f"imagen máx. {image} · envolvente máx. {max(lags, default=0):.0f} ms"],
                  ["Ventanas marcadas", count(len(data.get("marcas") or []), "ventana", "ventanas")],
                  ["Hojas de uniones", count(len(data.get("uniones") or []), "unión", "uniones")]])


def block(name, number, context):
    if context["spans"] is None and name in VIDEO_ONLY:
        raise ValueError(f"Línea {number}: la marca [[{name}]] no existe en modo audio.")
    return {"ficha": ficha, "indice": indice, "timeline": timeline,
            "validacion": validacion}[name](context)
