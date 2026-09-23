"""Labelled timeline picture and the annotated copy of a published summary (`rotular`).

The published vN/resumen.mp4 is never touched: `rotular` writes a separate, derived MP4 in
vN-rotulado/, with the topic of every cut and both timelines (original and summary) burnt in.
"""

import json
import os
from pathlib import Path
import shutil
import tempfile

import common
import doc

BACKGROUND, BAR = (11, 18, 32), (30, 41, 59)
SOURCE, OUTPUT = (251, 191, 36), (56, 189, 248)
TEXT, SOFT, LINE = (241, 245, 249), (148, 163, 184), (71, 85, 105)
FONTS = {False: ("segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc",
                 "LiberationSans-Regular.ttf"),
         True: ("segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial_Bold.ttf",
                "LiberationSans-Bold.ttf")}
# Windows fonts live under %WINDIR%; no drive letter is written down here.
FONT_DIRS = (str(Path(os.environ.get("WINDIR", "")) / "Fonts"), "/usr/share/fonts/truetype/dejavu",
             "/usr/share/fonts/dejavu", "/usr/share/fonts/truetype/liberation", "/Library/Fonts",
             "/System/Library/Fonts", "/System/Library/Fonts/Supplemental")
COLUMNS = 3


def font(size, bold=False):
    """A scalable system font, or Pillow's own default at that size."""
    from PIL import ImageFont
    for name in FONTS[bold]:
        for folder in FONT_DIRS:
            path = Path(folder) / name
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: fixed bitmap font
        return ImageFont.load_default()


def factor(value):
    return f"×{value:g}".replace(".", ",")


def share(part, whole):
    return f"{100 * part / whole:.1f} %".replace(".", ",")


def fitted(draw, text, typeface, room):
    """`text` cut with an ellipsis so it never runs wider than `room` pixels."""
    if draw.textlength(text, font=typeface) <= room:
        return text
    while text and draw.textlength(text + "…", font=typeface) > room:
        text = text[:-1]
    return text.rstrip() + "…"


def cuts_of(spans, labels=None):
    """One row per cut: number, label, source interval and output interval."""
    labels = labels or {}
    return [{"n": n, "id": span["id"],
             "label": (labels.get(str(span["id"])) or span.get("title")
                       or f"Corte {span['id']}").strip(),
             "start": span["start"], "end": span["end"],
             "s": span["offset"], "e": span["offset"] + span["length"]}
            for n, span in enumerate(spans, start=1)]


def labelled_timeline(cuts, original, speed, path, width=1800):
    """Where every kept cut comes from in the original and where it lands in the summary."""
    from PIL import Image, ImageDraw
    total = cuts[-1]["e"] if cuts else 0.0
    margin, height_bar, source_row, output_row = 60, 34, 150, 330
    rows = -(-len(cuts) // COLUMNS)
    legend = output_row + height_bar + 34
    image = Image.new("RGB", (width, legend + rows * 26 + 30), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title, body, small = font(34, True), font(20), font(16)
    inner = width - 2 * margin
    draw.text((margin, 36), "De dónde sale el resumen", font=title, fill=TEXT)
    draw.text((margin, 84), f"{len(cuts)} cortes · original {common.clock(original)} → resumen "
              f"{common.clock(total)} ({share(total, original)}) · {factor(speed)}",
              font=body, fill=SOFT)
    draw.text((margin, source_row - 28), f"ORIGINAL · {common.clock(original)}", font=small,
              fill=SOFT)
    draw.rounded_rectangle([margin, source_row, width - margin, source_row + height_bar], radius=8,
                           fill=BAR)
    for cut in cuts:
        a = margin + inner * cut["start"] / original
        b = max(a + 4, margin + inner * cut["end"] / original)
        draw.rounded_rectangle([a, source_row, b, source_row + height_bar], radius=5, fill=SOURCE)
        s = margin + inner * cut["s"] / total + 1
        e = max(s + 2, margin + inner * cut["e"] / total - 1)
        draw.rounded_rectangle([s, output_row, e, output_row + height_bar], radius=5, fill=OUTPUT)
        if e - s > 18:
            draw.text(((s + e) / 2, output_row + height_bar / 2), str(cut["n"]), font=small,
                      anchor="mm", fill=BACKGROUND)
        draw.line([((a + b) / 2, source_row + height_bar), ((s + e) / 2, output_row)], fill=LINE,
                  width=1)
        draw.text(((a + b) / 2, source_row - 8), str(cut["n"]), font=small, anchor="mb",
                  fill=SOURCE)
    # Drawn after the connecting lines so they never cross the label.
    caption = f"RESUMEN · {common.clock(total)}"
    draw.rectangle([margin - 4, output_row - 30, margin + draw.textlength(caption, font=small) + 8,
                    output_row - 6], fill=BACKGROUND)
    draw.text((margin, output_row - 28), caption, font=small, fill=SOFT)
    column = inner / COLUMNS
    for cut in cuts:
        x = margin + ((cut["n"] - 1) % COLUMNS) * column
        y = legend + ((cut["n"] - 1) // COLUMNS) * 26
        text = f"{cut['n']:>2}. {cut['label']}  ({common.clock(cut['start'])})"
        draw.text((x, y), fitted(draw, text, small, column - 16), font=small, fill=TEXT)
    staged = Path(path).with_name(f"{Path(path).name}.parcial")
    image.save(staged, "PNG")
    staged.replace(path)
    return Path(path)


def panel(cuts, current, original, speed, size, path):
    """Full-frame RGBA layer for one cut: caption plus both timelines, the cut highlighted."""
    from PIL import Image, ImageDraw
    width, height = size
    k = min(width / 1920, height / 1080)
    total = cuts[-1]["e"]
    tall, margin, label = round(176 * k), round(40 * k), round(150 * k)
    x0, x1 = margin + label, width - margin
    inner = x1 - x0
    top = height - tall
    source_row, output_row = top + round(92 * k), top + round(136 * k)
    bold, normal, small = font(max(12, round(30 * k)), True), font(max(10, round(22 * k))), \
        font(max(9, round(17 * k)))
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, top, width, height], fill=BACKGROUND + (244,))
    draw.rectangle([0, top, width, top + max(2, round(3 * k))], fill=OUTPUT + (255,))
    count = f"{current['n']}/{len(cuts)}"
    draw.text((margin, top + round(20 * k)), count, font=bold, fill=SOURCE)
    detail = (f"origen {common.clock(current['start'])}–{common.clock(current['end'])}  ·  resumen "
              f"{common.clock(current['s'])}–{common.clock(current['e'])}  ·  {factor(speed)}")
    right = draw.textlength(detail, font=normal)
    left = margin + draw.textlength(count, font=bold) + round(24 * k)
    draw.text((x1, top + round(28 * k)), detail, font=normal, fill=SOFT, anchor="ra")
    draw.text((left, top + round(20 * k)),
              fitted(draw, current["label"], bold, x1 - right - left - round(30 * k)),
              font=bold, fill=TEXT)
    thin, thick = round(14 * k), round(18 * k)
    draw.text((margin, source_row - round(4 * k)), f"Original {common.clock(original)}",
              font=small, fill=SOFT)
    draw.rounded_rectangle([x0, source_row, x1, source_row + thin], radius=max(1, thin // 2),
                           fill=BAR + (255,))
    for cut in cuts:
        a = x0 + inner * cut["start"] / original
        b = max(a + 3, x0 + inner * cut["end"] / original)
        draw.rounded_rectangle([a, source_row, b, source_row + thin], radius=max(1, round(4 * k)),
                               fill=SOURCE + ((255,) if cut is current else (95,)))
    draw.text((margin, output_row - round(2 * k)), f"Resumen {common.clock(total)}", font=small,
              fill=SOFT)
    for cut in cuts:
        a = x0 + inner * cut["s"] / total + 1
        b = max(a + 2, x0 + inner * cut["e"] / total - 1)
        mine = cut is current
        draw.rounded_rectangle([a, output_row, b, output_row + thick], radius=max(1, round(4 * k)),
                               fill=OUTPUT + ((255,) if mine else (80,)))
        if b - a > 22 * k:
            draw.text(((a + b) / 2, output_row + thick / 2), str(cut["n"]), font=small,
                      anchor="mm", fill=BACKGROUND if mine else TEXT)
    image.save(path, "PNG")
    return {"x0": x0, "inner": inner, "y": output_row - round(6 * k), "cursor": (
        max(2, round(4 * k)), thick + round(12 * k))}


def dimensions(path):
    report = json.loads(common.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height", "-of", "json",
                                    str(path)]))
    stream = report["streams"][0]
    return int(stream["width"]), int(stream["height"])


def load_labels(path):
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError("--labels debe ser un objeto JSON {\"id del corte\": \"rótulo\"}.")
    return {str(key): value for key, value in data.items()}


def annotate(args):
    """vN-rotulado/: derived MP4 with topic and timelines, the labelled graphic and the labels."""
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("rotular necesita Pillow: python -m pip install pillow") from None
    work = Path(args.work).resolve()
    version = work / f"v{args.version}"
    video = version / "resumen.mp4"
    if not video.is_file():
        raise ValueError(f"No hay resumen montado en {version.name}/: monta antes con render.")
    target = work / f"v{args.version}-rotulado"
    if target.exists():
        raise ValueError(f"Ya existe {target.name}/ y no se sobrescribe.")
    common.require_encoders("libx264")
    metadata = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
    context = doc.context_of(work, args.version, version, metadata)
    cuts = cuts_of(context["spans"], load_labels(args.labels))
    original, speed = context["total"], context["speed"]
    size = dimensions(video)
    staged = work / f"v{args.version}-rotulado.parcial"
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir()
    with tempfile.TemporaryDirectory(prefix="rotulos-", dir=staged,
                                     ignore_cleanup_errors=True) as temporary:
        layers = []
        for cut in cuts:
            layer = Path(temporary) / f"panel-{cut['n']:02d}.png"
            place = panel(cuts, cut, original, speed, size, layer)
            layers.append(layer)
        cursor = Path(temporary) / "cursor.png"
        Image.new("RGBA", place["cursor"], (255, 255, 255, 255)).save(cursor)
        total = cuts[-1]["e"]
        command = ["-i", str(video)]
        for layer in layers:
            command += ["-i", str(layer)]
        command += ["-i", str(cursor)]
        graph, previous = [], "[0:v]"
        for k, cut in enumerate(cuts, start=1):
            # The last layer stays up to the very end, whatever the container rounding leaves.
            end = cut["e"] if k < len(cuts) else cut["e"] + 1
            graph.append(f"{previous}[{k}:v]overlay=0:0:enable='gte(t,{cut['s']:.4f})*"
                         f"lt(t,{end:.4f})'[v{k}]")
            previous = f"[v{k}]"
        half = place["cursor"][0] // 2
        graph.append(f"{previous}[{len(cuts) + 1}:v]overlay=x='{place['x0']:.1f}+"
                     f"{place['inner']:.1f}*t/{total:.4f}-{half}':y={place['y']}:eval=frame,"
                     "format=yuv420p[fin]")
        command += ["-filter_complex", ";".join(graph), "-map", "[fin]", "-map", "0:a:0?",
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-threads",
                    str(args.threads), "-c:a", "copy", "-movflags", "+faststart",
                    str(staged / "resumen-rotulado.mp4")]
        common.ffmpeg(*command)
    labelled_timeline(cuts, original, speed, staged / "linea-tiempo.png")
    common.save(staged / "rotulos.json",
                {"version": args.version, "original_s": round(original, 3), "speed": speed,
                 "cortes": [{"numero": c["n"], "id": c["id"], "rotulo": c["label"],
                             "origen": [round(c["start"], 3), round(c["end"], 3)],
                             "resumen": [round(c["s"], 3), round(c["e"], 3)]} for c in cuts]})
    common.publish(staged, target)
    common.history(work, "annotate", {"version": args.version, "cortes": len(cuts)})
    print(target / "resumen-rotulado.mp4")
    return 0


def register(sub):
    p = sub.add_parser("rotular", help="Copia derivada de vN/resumen.mp4 con el tema de cada corte "
                                       "y las líneas temporales; no toca vN/.")
    p.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    p.add_argument("--version", type=common.positive, required=True, help="Versión montada (vN).")
    p.add_argument("--labels", help="JSON {\"id\": \"rótulo\"}; por defecto, el título de cada corte.")
    p.add_argument("--threads", type=common.positive, default=common.DEFAULT_THREADS,
                   help=f"Hilos de codificación (por defecto {common.DEFAULT_THREADS}).")
    p.set_defaults(run=annotate)
