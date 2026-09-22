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


def has_python_docx():
    try:
        import docx  # noqa: F401
    except Exception:
        return False
    return True


def engine():
    """Which converter will be used: Pandoc first, python-docx next, none last."""
    if common.tool("pandoc"):
        return "pandoc"
    return "python-docx" if has_python_docx() else None


def to_docx(markdown_path, target, base):
    """Publish the DOCX beside the Markdown; None means only Markdown is delivered."""
    target, staged = Path(target), Path(f"{target}.parcial")
    used = engine()
    if used is None:
        return None
    if used == "pandoc":
        common.run([common.tool("pandoc"), "--from=markdown", "--to=docx",
                    f"--resource-path={Path(base).resolve()}", "--output", str(staged),
                    str(markdown_path)])
    else:
        render_docx(Path(markdown_path).read_text(encoding="utf-8"), staged, Path(base))
    staged.replace(target)
    return used


INLINE = re.compile(r"(\*\*.+?\*\*|(?<!\*)\*[^*]+?\*|`[^`]+`)", re.S)
IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
ROW = re.compile(r"^\|(.+)\|\s*$")
RULE = re.compile(r"^\|[\s:|-]+\|\s*$")


def write_runs(paragraph, text):
    """Bold, italic and inline code of one line; anything else is plain text."""
    for piece in INLINE.split(text):
        if not piece:
            continue
        run = paragraph.add_run(piece.strip("*`"))
        run.bold = piece.startswith("**")
        run.italic = piece.startswith("*") and not piece.startswith("**")
        if piece.startswith("`"):
            run.font.name = "Consolas"


def arguments(**values):
    """Argument holder so the tests can call document() without going through argparse."""
    defaults = {"work": None, "version": 1, "source": None, "accept": None, "revision": None,
                "no_docx": False}
    return argparse.Namespace(**{**defaults, **values})


def context_of(work, number, out, metadata, schema=None):
    base = {"metadata": metadata, "total": common.duration(metadata), "version": number,
            "out": Path(out), "transcriber": transcriber(work), "avisos": [],
            "spans": None, "speed": 1.0, "settings": {}, "schema": schema}
    if metadata.get("kind") == "audio":
        return base
    plan = read_json(Path(out) / "seleccion.json")
    for key in ("segments", "settings"):
        if key not in plan:
            raise ValueError(f"El plan publicado no tiene «{key}»: {Path(out) / 'seleccion.json'}")
    speed = float(plan["settings"].get("speed", 1.0))
    # The montage's own F rules; metadata only answers when the plan does not carry it.
    rate = plan["settings"].get("rate")
    cadence = 1 / common.output_interval(rate) if rate else float(metadata["timeline"]["fps"])
    base.update(spans=placements(plan["segments"], speed, cadence), speed=speed,
                settings=plan["settings"])
    return base


def next_revision(out):
    """Reserve the next resumen-rM number exclusively: same O_CREAT|O_EXCL principle as
    common.reserve_version (plan 1), adapted to the rM namespace of an already-published version —
    it does not reuse reserve_version itself, which reserves vN.json, not resumen-rM.md. This
    replaces a plain glob()+max(), which left a TOCTOU window where two concurrent `doc --revision`
    calls on the same vN could compute the same M. First revision is 2: the delivery without suffix
    is the first one; the reservation is the very `.md.parcial` staging file publish_document goes on
    to fill, so there is no separate sentinel and no throwaway write."""
    used = [int(p.stem.rsplit("-r", 1)[-1]) for p in Path(out).glob("resumen-r*.md")
            if p.stem.rsplit("-r", 1)[-1].isdigit()]
    first = max(used, default=1) + 1
    for number in range(first, first + common.VERSION_ATTEMPTS):
        staged = Path(out) / f"resumen-r{number}.md.parcial"
        try:
            os.close(os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return number
    raise ValueError(f"No se pudo reservar una revisión tras {common.VERSION_ATTEMPTS} intentos; "
                     "otra sesión está publicando una revisión en esta misma versión.")


def record_revision(out, number, reason, phrase, source):
    path = Path(out) / "revisiones.json"
    rows = read_json(path) if path.is_file() else []
    rows.append({"revision": number, "motivo": reason, "frase": phrase,
                 "fecha": datetime.date.today().isoformat(), "origen": Path(source).name})
    staged = Path(out) / "revisiones.json.parcial"
    staged.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    # The only index inside a published version that grows: replaced whole, never appended in place.
    os.replace(staged, path)
    return rows


def publish_document(text, out, name, base, skip_docx):
    markdown, staged = Path(out) / f"{name}.md", Path(out) / f"{name}.md.parcial"
    staged.write_text(text, encoding="utf-8")
    try:
        common.publish(staged, markdown)
    except (ValueError, OSError):
        # A refused publication must not leave a half-written file in a published version.
        staged.unlink(missing_ok=True)
        raise
    if skip_docx:
        return markdown, None
    return markdown, to_docx(markdown, Path(out) / f"{name}.docx", base)


def report_of(args):
    """Publish the document of one version and answer what was written; document() prints it."""
    work = Path(args.work).resolve()
    number = args.version
    metadata = read_json(work / "metadata.json")
    out = work / (f"documento-v{number}" if metadata.get("kind") == "audio" else f"v{number}")
    if not out.is_dir():
        raise ValueError(f"No existe la carpeta de la versión: {out}")
    source = Path(args.source) if args.source else work / f"documento-v{number}.md"
    if not source.is_file():
        raise ValueError(f"No existe el documento de partida: {source}")
    if args.revision and not (args.accept or "").strip():
        raise ValueError("Una revisión exige --accept con la frase literal del usuario.")
    context = context_of(work, number, out, metadata)
    text = expand(source.read_text(encoding="utf-8-sig"), context)
    revision = next_revision(out) if args.revision else None
    name = "resumen" if revision is None else f"resumen-r{revision}"
    markdown, used = publish_document(text, out, name, out, args.no_docx)
    if revision is not None:
        record_revision(out, revision, args.revision, args.accept, source)
    if used is None and not args.no_docx:
        context["avisos"].append("Sin Pandoc ni python-docx: la entrega es solo Markdown. Instala "
                                 "Pandoc (pandoc.org) o ejecuta `python -m pip install python-docx`.")
    # `doc` on every publication; `deliver` belongs to the final handover, not to this subcommand.
    common.history(work, "doc", {"version": number, "revision": revision, "motor": used,
                                 "archivo": markdown.name, "kind": metadata.get("kind")})
    return {"markdown": str(markdown),
            "docx": None if used is None else str(markdown.with_suffix(".docx")),
            "motor": used, "revision": revision, "avisos": context["avisos"]}


def document(args):
    """The subcommand: it prints its report and answers 0, like compare."""
    print(json.dumps(report_of(args), ensure_ascii=False, indent=2))
    return 0


def register(sub):
    p = sub.add_parser("doc", help="Expande las marcas del documento y publica Markdown y DOCX.")
    p.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    p.add_argument("--version", type=common.positive, required=True,
                   help="Número de versión: vN en vídeo, documento-vN en audio.")
    p.add_argument("--source", help="Documento con marcas (por defecto, documento-vN.md).")
    p.add_argument("--accept", help="Frase literal del usuario; obligatoria en audio y en revisiones.")
    p.add_argument("--revision", help="Motivo de la revisión; publica resumen-rM junto a la anterior.")
    p.add_argument("--no-docx", action="store_true", help="Entrega solo Markdown, sin convertir.")
    p.set_defaults(run=document)


def render_docx(markdown, target, base):
    """Headings, paragraphs, lists, tables, emphasis, code and images: the spec's subset."""
    from docx import Document
    from docx.shared import Inches
    document = Document()
    lines, i = markdown.splitlines(), 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            document.add_heading(line[level:].strip(), level=min(level, 4))
            i += 1
        elif line.startswith("```"):
            block, i = [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            document.add_paragraph().add_run("\n".join(block)).font.name = "Consolas"
            i += 1
        elif IMAGE.match(line):
            picture = Path(base) / IMAGE.match(line).group(2)
            if picture.is_file():
                document.add_picture(str(picture), width=Inches(6))
            i += 1
        elif line.lstrip().startswith(("- ", "* ")):
            write_runs(document.add_paragraph(style="List Bullet"), line.lstrip()[2:])
            i += 1
        elif ROW.match(line):
            rows = []
            while i < len(lines) and ROW.match(lines[i].rstrip()):
                if not RULE.match(lines[i].rstrip()):
                    rows.append([c.strip() for c in ROW.match(lines[i].rstrip()).group(1).split("|")])
                i += 1
            grid = document.add_table(rows=len(rows), cols=max(len(row) for row in rows))
            grid.style = "Table Grid"
            for row, values in zip(grid.rows, rows):
                for cell, text in zip(row.cells, values):
                    write_runs(cell.paragraphs[0], text)
        else:
            write_runs(document.add_paragraph(), line)
            i += 1
    document.save(str(target))
