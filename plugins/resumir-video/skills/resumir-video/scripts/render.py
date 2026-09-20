"""Cached, resumable montage of an accepted plan: budget, assembly, blocking validation and report."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from common import (BLOCKING, DEFAULT_THREADS, MAX_SPANS, fingerprint, output_interval, plan_sha256,
                    positive, run, warning)


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
