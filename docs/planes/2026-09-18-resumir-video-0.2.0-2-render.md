# Montaje 0.2.0 con caché, presupuesto y validación · Plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usa `superpowers:subagent-driven-development`
> (recomendada) o `superpowers:executing-plans` para implementar este plan tarea a tarea. Los pasos
> usan casillas (`- [ ]`) para el seguimiento.

**Goal:** reescribir `render` en un módulo propio `scripts/render.py` que monte un plan aceptado por
cortes cacheados, respete un presupuesto de tiempo reanudable, ensamble una sola vez el audio y no
publique `vN/` hasta superar una validación bloqueante contra el original.

**Architecture:** `render.py` no decide nada editorial: recibe `seleccion-vN.json` (lo produce
`plan.py`), exige aceptación literal, descompone cada corte en subcortes de 40 tramos como máximo,
renderiza cada subcorte con **dos pasadas de FFmpeg** (vídeo H.264 y audio PCM de 24 bits) que se
remultiplexan sin recodificar en `cortes/<clave>.mkv`, ensambla con dos *concat demuxer* copiando el
vídeo y codificando AAC una sola vez (invariante D-006), valida el resultado frente al medio original
por recuento de fotogramas, imagen y envolvente, y solo entonces publica `vN/`. El estado vive en el
sistema de archivos —caché por clave de huella, `historial.jsonl`, cerrojo exclusivo—, de modo que una
llamada interrumpida o agotada por presupuesto se reanuda sin repetir trabajo. Esa misma caché le
permite responder, sin montar nada, cuánto costaría el montaje (`render --dry-run`), que es el dato que
la propuesta de §9 muestra tras cada edición.

**Tech Stack:** Python 3.10–3.13 (solo biblioteca estándar: `array`, `hashlib`, `json`, `math`, `os`,
`pathlib`, `re`, `shutil`, `subprocess`, `sys`, `tempfile`, `time`, `wave`, `unittest`), FFmpeg 8.0.1
(`libx264`, `aac`, filtros `fps`, `select`, `settb`, `setpts`, `tpad`, `trim`, `pad`, `showinfo`,
`asplit`, `atrim`, `asetpts`, `concat`, `atempo`, `apad`, `tile`), `ffprobe`.

**Spec:** [`docs/especificaciones/2026-09-18-resumir-video-0.2.0.md`](../especificaciones/2026-09-18-resumir-video-0.2.0.md)
— este plan cubre §8 (montaje y validación), §9 (aceptación y coste de montaje), §11 (montaje y
protección) y §12 (códigos de error). El presupuesto, los bordes, los tramos y los avisos los calcula
`plan.py`; el documento y la cobertura, `doc.py`.

## Global Constraints

- **Alcance del plan:** `scripts/render.py` y `scripts/test_render.py`, ambos nuevos. De
  `scripts/video.py` se tocan exclusivamente dos líneas —`import render` y `render.register(sub)`
  (Tarea 1, paso 9)—. Ningún otro archivo del repositorio: **`scripts/test_video.py` no lo toca este
  plan**. Lo reordena el Plan 1 en su Tarea 1, al retirar de `video.py` el `render` de la 0.1.0, y es
  él quien retira las pruebas que se quedan sin sujeto y reescribe las demás para conservar su
  cobertura de `prepare`, `frames` y `probe` (§13).
- **Sin dependencias fuera de la biblioteca estándar.** Nada de `numpy`, `PIL`, `pydub` ni similares.
- **FFmpeg siempre con listas de argumentos, nunca por shell.** Se usa `common.ffmpeg(...)`, que ya
  añade `-hide_banner -loglevel error -nostdin -n`.
- **Estilo de 0.1.0:** docstring de módulo y de función en inglés; mensajes de error y de ayuda en
  español y con el prefijo `Error: ` que pone `video.main()`; funciones cortas; comentarios solo donde
  el porqué no es obvio.
- **Nada se sobrescribe.** JSON con `common.save` (modo `"x"`), carpetas nuevas con `common.new_dir`,
  publicación con `common.publish` (renombrado atómico). `cortes/` sí puede existir: es la caché
  reanudable de §6.
- **No se escribe dentro de la carpeta de la skill.** `video.py` fija `sys.dont_write_bytecode = True`
  y las pruebas se ejecutan con `python -B`.
- **Códigos de salida (§12):** 0 correcto · 1 error controlado · 2 argumentos inválidos o plan con
  aviso bloqueante · 3 pendiente y reanudable con `{done, total, pending, bloques}`, donde `pending`
  es **siempre un entero** y el detalle va en la lista `bloques` · 4 validación fallida ·
  130 interrupción.
- **Constantes de la especificación que no se negocian:** máximo **40 tramos** por pasada, que vive en
  `common.MAX_SPANS` y `render.py` importa sin redefinir (§8); umbrales de imagen **0,08** (acepta) y
  **0,15** (falla) (§8); diferencia audio-vídeo **≤ 0,1 s** (§8); fotogramas totales **iguales a Σ N**
  (§8); un solo reintento ante `MEMORY_PATTERNS` con `-threads 1 -filter_threads 1` (§11); PCM de
  24 bits **nunca leído desde Python** (§8).
- **Umbrales provisionales de la envolvente (§15):** desfase máximo **40 ms** (cuatro bloques de
  10 ms, dentro de los 45 ms que cita §8), guarda de modulación **6 dB** por debajo de la cual la
  correlación no dice nada, y bloqueo por diferencia media **8 dB**. Se declaran en «Desviaciones y
  umbrales declarados»; el Plan 4 los escribe en `docs/requisitos.md`.
- **La lectura de la entrada no se acota con `-t` ni con `-to`.** Medido hoy: junto a `-copyts` ambas
  se cuentan desde el primer paquete leído, no desde el instante pedido, y dejan la cadena en **cero
  fotogramas** (véase la tabla de recetas). La pasada de audio se cierra sola por sus `atrim` de
  tiempo; la de vídeo necesita la guarda `trim=end=…` de la Tarea 3.
- **Versión:** `render.py` no declara versión propia; `__version__` vive solo en `video.py` y lo
  actualiza el plan de empaquetado.
- **Órdenes de comprobación** (desde la raíz del repositorio):

  ```text
  python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"
  python -B -m unittest discover -s tests
  ```

## Contrato con `common.py` (Plan 1) y con `plan.py` (Plan 1)

`render.py` **consume** de `common.py`, sin redefinir nada: `BLOCKING`, `MAX_SPANS`,
`MEMORY_PATTERNS`, `energy`, `ffmpeg`, `fingerprint`, `frames_for`, `history`, `listing`, `lock`,
`new_dir`, `output_interval`, `plan_sha256`, `positive`, `probe`, `publish`, `require_encoders`,
`run`, `samples_for`, `save`, `seconds`, `seek_margin`, `stamp`, `stream_duration`, `streams`,
`timeline_start`, `video_stream`, `warning`.

No usa `parse_target`, `tolerance`, `silences`, `snap`, `islands`, `adjust_edges`, `reserve_version`,
`clock` ni `strip_accents`: son de `plan.py` y `doc.py`.

Forma de `seleccion-vN.json` fijada para los cuatro planes (la produce `plan.py`; las claves de datos
van en inglés y los avisos conservan las que ya estaban contratadas):

```json
{
  "version": 1,
  "parent": null,
  "kind": "video",
  "source": {"path": "…", "size": 123, "mtime_ns": 456, "sha256": "…"},
  "audio_stream": 1,
  "timeline": {"start": 0.0, "origin": 0.032, "rate": "25/1", "fps": 25.0,
               "interval": 0.04, "sample_rate": 48000},
  "settings": {"target": "10%", "objetivo": 96.0, "tolerance": 10.0, "speed": 1.25,
               "remove_pauses": true, "silence_db": -50.0, "rate": "25/1", "sample_rate": 48000},
  "segments": [{"id": 1, "numero": 1, "title": "…", "phrase": "…", "reason": "…",
                "audio_evidence": "…", "visual_evidence": "…", "priority": 1,
                "pinned": false, "visual_only": false, "remove_pauses": true,
                "start": 12.3, "end": 24.8, "spans": [[12.3, 18.4], [19.0, 24.8]],
                "frames": 122, "samples": 234240,
                "subcuts": [{"spans": [[12.3, 18.4], [19.0, 24.8]],
                             "frames": 122, "samples": 234240}]}],
  "reserves": [], "estimate": {}, "alternativas": [], "sugerencias": [],
  "warnings": [{"codigo": "corte_breve", "mensaje": "…", "corte": 1, "bloquea": false}],
  "changes": [],
  "sha256": "…"
}
```

De ese esquema `render` **lee** `version`, `source`, `audio_stream`, `settings.{speed,rate,sample_rate}`,
`segments[].{id,title,spans,frames,samples,subcuts}` y `warnings`; copia el documento entero a
`vN/seleccion.json` y calcula su `sha256` con `common.plan_sha256`, que ignora la clave `sha256`. El
resto de claves —`parent`, `kind`, `request`, `timeline`, `reserves`, `excluidos`, `estimate`,
`alternativas`, `sugerencias`, `recorrido`, `changes` y los campos editoriales de cada corte
(`depends_on`, `salida` y las evidencias)— viajan sin que `render` los interprete: son del agente, de
`plan.py` y de `doc.py`. `timeline.rate` y `settings.rate` son la misma fracción y `timeline.fps` su
valor en coma flotante; `render` usa la de `settings` y no depende de `timeline`.
`settings.objetivo` son los segundos del objetivo ya resueltos y **`settings.tolerance` es un número
en segundos**: la semianchura de la banda `[max(0, T_obj − d), T_obj + d]` de A-5, no un par de
factores. `render` no lee ninguno de los dos, pero el esquema es el mismo para los cuatro planes y las
pruebas de este lo copian tal cual.

---

## Estructura de archivos

| Archivo | Responsabilidad |
| --- | --- |
| `plugins/resumir-video/skills/resumir-video/scripts/render.py` | **Nuevo.** Aceptación, subcortes, claves de caché, filtros, montaje por corte, presupuesto, ensamblado, validación bloqueante, hojas de uniones, informe y estimación del coste (`--dry-run`). |
| `plugins/resumir-video/skills/resumir-video/scripts/test_render.py` | **Nuevo.** Pruebas rápidas (sin FFmpeg) y de integración (con FFmpeg) sobre una fuente sintética cuya luminancia codifica el instante de origen. |
| `plugins/resumir-video/skills/resumir-video/scripts/video.py` | **Modificado, dos líneas.** `import render` y `render.register(sub)`; el despacho ya es `return args.run(args) or 0`. |

Salidas dentro de la carpeta de trabajo (§6): `cortes/<clave>.mkv` y `cortes/<clave>.json` (caché),
`historial.jsonl` (registro), `vN/resumen.mp4`, `vN/seleccion.json`, `vN/validacion.json`,
`vN/uniones/union-NN.jpg` y `vN/montaje.md` (publicación inmutable). El `vN/resumen.md` de §6 es el
documento y lo escribe `doc.py`: este plan no lo toca.

---

## Recetas verificadas en esta máquina (FFmpeg 8.0.1-full_build, Windows 11)

Comprobadas con una fuente sintética de 320×180 cuya luminancia del píxel (0,0) es el índice de
fotograma y cuyo audio es la rampa `t/10`, de modo que cada muestra identifica su instante de origen:

```text
ffmpeg -f lavfi -i "color=c=black:s=320x180:r=25:d=10" \
       -f lavfi -i "aevalsrc=exprs='t/10':sample_rate=48000:duration=10" \
       -vf "geq=lum='N':cb=128:cr=128,format=yuv420p" \
       -c:v libx264 -crf 12 -preset ultrafast -bf 0 -c:a pcm_s16le fuente.mkv
```

| Comprobación | Resultado medido |
| --- | --- |
| Corte de tramos `[4,5)` y `[7,8)` a ×1,25 con `-ss 1 -noaccurate_seek -copyts`, sin acotar la lectura | 40 fotogramas exactos, luminancias `100…124` y `175…199`: solo el contenido pedido |
| Lo mismo con `rate = "25/1"` y con `rate = "30000/1001"` | 40 y 48 fotogramas exactos |
| Audio del mismo corte | 76 800 muestras exactas (76 877 a 29,97 fps); primera muestra en 3,9998 s, última en 7,9998 s |
| **`-t` como opción de entrada junto a `-copyts`** (`-ss 5 -t 5` sobre un corte en `[8,9)` de un medio de 10 s) | El archivo de salida **no tiene ni un fotograma** (578 bytes, sin pista de vídeo): `-t` se cuenta desde el primer paquete leído, así que cierra la lectura antes del corte |
| **`-to` como opción de entrada junto a `-copyts`** | `-to 5` con `-ss 5` aborta (`-to value smaller than -ss; aborting.`); con valores mayores se comporta como una duración desde el primer paquete, no como un instante absoluto. Ninguna de las dos acota la lectura de forma fiable |
| La misma orden **sin** `-t` ni `-to` | 25 fotogramas exactos: lo pedido |
| Fotogramas que llegan al grafo (`showinfo`) con la cadena del §8 sobre un medio de 40 s (1 000 fotogramas), corte en `[4,6)` | **1 000**: el `select` descarta los fotogramas posteriores en vez de cerrar la cadena, así que `trim=end_frame=N` nunca recibe el fotograma `N + 1` que la cerraría y FFmpeg decodifica el medio entero |
| La misma cadena con la guarda `trim=end=<base + fin + 1/F>` tras el `fps` inicial | **153** fotogramas leídos, misma salida exacta (40 fotogramas, mismas luminancias); sobre la fuente de cadencia variable, los mismos 70 fotogramas con el retenido intacto |
| Pasada de audio sobre un medio de 300 s, tramos `[4,5)` y `[7,8)` | **385 024 muestras leídas (8,02 s)**: los `atrim=start=…:end=…` de cada tramo sí cierran el grafo; el audio no necesita guarda |
| Control negativo sin el `fps` inicial sobre fuente de cadencia variable | El fotograma retenido de `[3,5)` **se pierde por completo**: la salida empieza en el segundo tramo y se congela |
| `trim=end_frame=0` y `atrim=end_sample=0` | FFmpeg devuelve **0** y escribe un archivo vacío: hay que comprobar `N ≥ 1` y `M ≥ 1` en Python |
| Corte que termina en el último fotograma del medio (`[9,10)` de un medio de 10 s) | 25 fotogramas exactos con luminancias `225…249` y 48 000 muestras: no se trunca ni hace falta clonar |
| Medio desfasado (`format.start_time = 7 s`), corte en `s ∈ [3,4)` | 25 fotogramas con luminancias `75…99` y 48 000 muestras de 0,2999 a 0,3999 de la rampa: la convención `base + s` es correcta sobre un contenedor real desplazado |
| Ensamblado de dos cortes con dos *concat demuxer* | 70 fotogramas (= Σ N), vídeo 2,800 s, audio 2,800 s según `ffprobe` |
| Distancia de luminancia 64×64 entre salida y original en el mismo instante | 0,0000; contra un instante ajeno, 0,5720 |
| Envolvente de 10 ms, ventanas de inicio y fin del corte | diferencia media 0,81 dB y 3,08 dB; contra una ventana desplazada 0,75 s, **54,22 dB** |
| `wave.open()` sobre PCM de 24 bits | `Error unknown format: 65534` — hay que decodificar a `pcm_s16le` |
| Código de salida de Windows para `STATUS_NO_MEMORY` (0xC0000017) | Python lo comunica como **3221225495** |

---

## Tarea 1: Esqueleto de `render.py`, aceptación obligatoria y avisos bloqueantes

**Files:**
- Create: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Create: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/video.py`

**Interfaces:**
- Consumes: de `common.py` → `BLOCKING: tuple[str, ...]`, `plan_sha256(plan) -> str`,
  `fingerprint(path) -> dict` con claves `size`, `mtime_ns`, `sha256`, `warning(code, message, *, cut=None) -> dict`.
- Produces: `render.Refused(ValueError)`, `render.Invalid(ValueError)`, `render.Pending(Exception)` con
  atributo `state: dict` de claves `done`, `total`, `pending` (entero) y `bloques` (lista);
  `render.accepted(plan, accept, directo) -> dict` con claves `frase`, `directo`, `sha256`;
  `render.sources_agree(plan, video) -> list[dict]`; `render.render(args) -> int`;
  `render.register(sub) -> None`, que crea el subparser y fija `set_defaults(run=render)`.
- Requisito previo del Plan 1: `video.py` ya no define `render`, `verify` ni `validate_plan` (los retira
  su Tarea 1 al repartir el núcleo en `common.py`), ya trae `import common` y su `main()` despacha con
  `return args.run(args) or 0`.

- [ ] **Paso 1: Escribe la prueba que falla**

Crea `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`:

```python
"""Checks for the montage: fast ones first, then integration over generated media."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import common
import render


def sample_segment(**changes):
    """One cut exactly as plan.py publishes it; `subcuts` mirrors its own split of the spans."""
    segment = {"id": 1, "numero": 1, "title": "Requisito", "phrase": "el requisito obliga a…",
               "reason": "Fija el requisito", "audio_evidence": "Lo enuncia el ponente",
               "visual_evidence": "Tabla en pantalla", "priority": 1, "pinned": False,
               "visual_only": False, "remove_pauses": True, "start": 1.0, "end": 3.0,
               "spans": [[1.0, 3.0]], "frames": 40, "samples": 76800}
    segment.update(changes)
    segment.setdefault("subcuts", [{"spans": segment["spans"], "frames": segment["frames"],
                                    "samples": segment["samples"]}])
    return segment


def sample_plan(**changes):
    """The published seleccion-vN.json; render only reads a few keys but must tolerate them all."""
    plan = {"version": 1, "parent": None, "kind": "video",
            "source": {"path": "fuente.mkv", "size": 10, "mtime_ns": 20, "sha256": "ab"},
            "audio_stream": 1,
            "timeline": {"start": 0.0, "origin": 0.0, "rate": "25/1", "fps": 25.0,
                         "interval": 0.04, "sample_rate": 48000},
            # `tolerance` is the half-width of the target band in seconds, not a pair of factors.
            "settings": {"target": "10%", "objetivo": 96.0, "tolerance": 10.0, "speed": 1.25,
                         "remove_pauses": True, "silence_db": -50.0, "rate": "25/1",
                         "sample_rate": 48000},
            "segments": [sample_segment()],
            "reserves": [], "estimate": {}, "alternativas": [], "sugerencias": [],
            "warnings": [], "changes": []}
    plan.update(changes)
    return plan


class AcceptanceTest(unittest.TestCase):
    def test_a_plan_without_acceptance_is_refused(self):
        with self.assertRaisesRegex(render.Refused, "--accept"):
            render.accepted(sample_plan(), None, False)

    def test_blocking_warnings_stop_even_with_directo(self):
        plan = sample_plan(warnings=[{"codigo": "dependencia_excluida", "corte": 7,
                                      "mensaje": "El 7 depende del 6, excluido.", "bloquea": True}])
        for accept, directo in (("vale, móntalo", False), (None, True)):
            with self.subTest(directo=directo):
                with self.assertRaisesRegex(render.Refused, "dependencia_excluida") as caught:
                    render.accepted(plan, accept, directo)
                self.assertIn("7", str(caught.exception))

    def test_the_acceptance_records_the_literal_phrase_and_the_plan_hash(self):
        plan = sample_plan()
        record = render.accepted(plan, "vale, móntalo", False)
        self.assertEqual(record["frase"], "vale, móntalo")
        self.assertFalse(record["directo"])
        self.assertEqual(record["sha256"], common.plan_sha256(plan))
        self.assertEqual(render.accepted(plan, None, True)["directo"], True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"`
Esperado: `ModuleNotFoundError: No module named 'render'`.

- [ ] **Paso 3: Escribe la implementación mínima**

Crea `plugins/resumir-video/skills/resumir-video/scripts/render.py`:

```python
"""Cached, resumable montage of an accepted plan: budget, assembly, blocking validation and report."""

import argparse
import json
from pathlib import Path
import sys

from common import BLOCKING, fingerprint, plan_sha256, positive


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
    return []


def render(args):
    raise NotImplementedError


def register(sub):
    raise NotImplementedError
```

- [ ] **Paso 4: Ejecuta la prueba y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"`
Esperado: `Ran 3 tests … OK`.

- [ ] **Paso 5: Escribe la prueba que falla de la reasignación por huella**

Añade a `test_render.py`, dentro de `AcceptanceTest`:

```python
    def test_the_plan_survives_a_move_but_not_another_file(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            original = root / "uno.bin"
            original.write_bytes(b"contenido de prueba")
            moved = root / "dos.bin"
            shutil.copy2(original, moved)
            plan = sample_plan(source={"path": str(original), **common.fingerprint(original)})
            avisos = render.sources_agree(plan, moved)
            self.assertEqual([a["codigo"] for a in avisos], ["origen_reasignado"])
            self.assertFalse(avisos[0]["bloquea"])
            otro = root / "tres.bin"
            otro.write_bytes(b"contenido distinto")
            with self.assertRaisesRegex(render.Refused, "sha256"):
                render.sources_agree(plan, otro)
```

- [ ] **Paso 6: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k test_the_plan_survives_a_move`
Esperado: FALLA con `AssertionError: [] != ['origen_reasignado']`.

- [ ] **Paso 7: Completa `sources_agree`**

En `render.py`, sustituye el `return []` final de `sources_agree` por:

```python
    if planned.get("path") != str(Path(video).resolve()):
        return [warning("origen_reasignado",
                        "El plan apunta a otra ruta pero la huella coincide: se actualiza source "
                        f"a {Path(video).resolve()}.")]
    return []
```

y añade `warning` a la importación de `common`:

```python
from common import BLOCKING, fingerprint, plan_sha256, positive, warning
```

- [ ] **Paso 8: Ejecuta las pruebas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"`
Esperado: `Ran 4 tests … OK`.

- [ ] **Paso 9: Engancha `render` en `video.py`**

Requisito previo (Tarea 1 del Plan 1): `video.py` ya no define `render`, `verify` ni `validate_plan`,
ya trae `import common` y su `main()` despacha con `return args.run(args) or 0`. Si alguna de las tres
funciones sigue ahí, bórrala en este mismo paso: el `import render` chocaría con el nombre de la
función.

Dentro de `build_parser()`, donde estaba el bloque del subcomando `render` de la 0.1.0 (desde
`p = sub.add_parser("render", …)` hasta `help=f"Hilos de codificación (por defecto {DEFAULT_THREADS}).")`),
deja una sola línea, junto a los `register` de los demás módulos hermanos:

```python
    render.register(sub)
```

El registro es el convenido para los cuatro módulos: cada uno expone `register(sub)`, crea su
subparser y fija `parser.set_defaults(run=<función>)`; `video.main()` hace `return args.run(args) or 0`
y no conoce ningún diccionario de despacho. Si en `main()` queda el diccionario de la 0.1.0, retira de
él la entrada `"render"`.

Añade arriba, junto a las demás importaciones de módulos hermanos:

```python
import render
```

- [ ] **Paso 10: Comprueba que la ayuda se genera**

Ejecuta: `python -B plugins/resumir-video/skills/resumir-video/scripts/video.py render --help`
Esperado: FALLA con `NotImplementedError` procedente de `register`; eso confirma que el enganche
llega al módulo nuevo. Se completará en la Tarea 10.

- [ ] **Paso 11: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py \
        plugins/resumir-video/skills/resumir-video/scripts/video.py
git commit -m "feat(render): exige aceptación literal y rechaza avisos bloqueantes" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 2: Reparto en subcortes y clave de caché

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.Refused`; de `common.py` → `MAX_SPANS: int` (= 40, §8; vive en `common.py` porque
  `plan.py` reparte los mismos subcortes), `frames_for(length, rate, speed) -> int`,
  `samples_for(n_frames, rate, sample_rate) -> int`, `output_interval(rate) -> float`,
  `run(args, cwd=None) -> str`.
- Produces: `render.ENCODER: tuple[str, ...]`;
  `render.cadence_of(plan) -> float`; `render.tempo_factors(speed) -> list[float]`;
  `render.subcuts(segment, cadence, speed, sample_rate, limit=MAX_SPANS) -> list[dict]` donde cada
  parte es `{"cut": int, "spans": list[tuple[float, float]], "frames": int, "samples": int,
  "index": int, "total": int}`; `render.cut_key(plan, part, release) -> str` (32 caracteres
  hexadecimales); `render.ffmpeg_release() -> str`.

- [ ] **Paso 1: Escribe la prueba que falla**

Añade a `test_render.py`:

```python
class SubcutTest(unittest.TestCase):
    def test_one_pass_keeps_the_whole_cut(self):
        segment = {"id": 3, "spans": [[1.0, 2.0], [4.0, 5.0]]}
        parts = render.subcuts(segment, 25.0, 1.25, 48000)
        self.assertEqual(len(parts), 1)
        self.assertEqual((parts[0]["frames"], parts[0]["samples"]), (40, 76800))
        self.assertEqual((parts[0]["index"], parts[0]["total"], parts[0]["cut"]), (0, 1, 3))

    def test_the_split_shares_out_n_and_m_without_losing_a_frame(self):
        segment = {"id": 1, "spans": [[float(i), i + 0.5] for i in range(85)]}
        parts = render.subcuts(segment, 25.0, 1.25, 48000)
        self.assertEqual([len(part["spans"]) for part in parts], [40, 40, 5])
        self.assertEqual([part["total"] for part in parts], [3, 3, 3])
        whole = common.frames_for(85 * 0.5, 25.0, 1.25)
        self.assertEqual(sum(part["frames"] for part in parts), whole)
        self.assertEqual(sum(part["samples"] for part in parts),
                         common.samples_for(whole, 25.0, 48000))

    def test_a_cut_that_yields_no_frame_is_refused_before_ffmpeg(self):
        # FFmpeg answers 0 to trim=end_frame=0 and writes an empty file: the guard lives in Python.
        with self.assertRaisesRegex(render.Refused, "fotogramas"):
            render.subcuts({"id": 9, "spans": [[1.0, 1.01]]}, 25.0, 1.25, 48000)

    def test_the_fractional_rate_is_exact(self):
        segment = {"id": 1, "spans": [[4.0, 5.0], [7.0, 8.0]]}
        parts = render.subcuts(segment, 1 / common.output_interval("30000/1001"), 1.25, 48000)
        self.assertEqual((parts[0]["frames"], parts[0]["samples"]), (48, 76877))

    def test_tempo_factors_multiply_back_to_the_speed(self):
        self.assertEqual(render.tempo_factors(1.0), [])
        self.assertEqual(render.tempo_factors(1.25), [1.25])
        factors = render.tempo_factors(2.5)
        self.assertEqual(len(factors), 2)
        self.assertAlmostEqual(factors[0] * factors[1], 2.5)
        self.assertTrue(all(0.5 <= factor <= 2.0 for factor in factors))


class KeyTest(unittest.TestCase):
    def test_every_ingredient_of_the_key_changes_it(self):
        plan = sample_plan()
        part = render.subcuts(plan["segments"][0], 25.0, 1.25, 48000)[0]
        base = render.cut_key(plan, part, "8.0.1")
        self.assertEqual(len(base), 32)
        self.assertTrue(all(letter in "0123456789abcdef" for letter in base))
        self.assertEqual(base, render.cut_key(sample_plan(), part, "8.0.1"))
        self.assertNotEqual(base, render.cut_key(plan, part, "7.1"))
        moved = dict(part, spans=[[1.0, 3.001]])
        self.assertNotEqual(base, render.cut_key(plan, moved, "8.0.1"))
        self.assertNotEqual(base, render.cut_key(plan, dict(part, index=1, total=2), "8.0.1"))
        other = sample_plan()
        other["settings"] = dict(other["settings"], speed=1.0)
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["source"] = dict(other["source"], sha256="cd")
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["source"] = dict(other["source"], path="otra/ruta.mkv")
        self.assertEqual(base, render.cut_key(other, part, "8.0.1"))
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k Subcut`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'subcuts'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, amplía la importación y añade las constantes y funciones:

```python
import hashlib
import math

from common import (BLOCKING, MAX_SPANS, fingerprint, frames_for, output_interval, plan_sha256,
                    positive, run, samples_for, warning)

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


def subcuts(segment, cadence, speed, sample_rate, limit=MAX_SPANS):
    """Passes of at most `limit` spans that share out N and M of the whole cut, §7.5 and §8."""
    spans = [(float(start), float(end)) for start, end in segment["spans"]]
    if not spans:
        raise Refused(f"El corte {segment['id']} no tiene tramos.")
    total_frames = frames_for(sum(end - start for start, end in spans), cadence, speed)
    total_samples = samples_for(total_frames, cadence, sample_rate)
    groups = [spans[i:i + limit] for i in range(0, len(spans), limit)]
    parts, frames, samples = [], 0, 0
    for index, group in enumerate(groups):
        if index == len(groups) - 1:
            count, length = total_frames - frames, total_samples - samples
        else:
            count = frames_for(sum(end - start for start, end in group), cadence, speed)
            length = samples_for(count, cadence, sample_rate)
        if count < 1 or length < 1:
            raise Refused(f"El corte {segment['id']} deja {count} fotogramas y {length} muestras en "
                          f"el subcorte {index + 1}/{len(groups)}: replanifícalo (aviso corte_vacio).")
        parts.append({"cut": segment["id"], "spans": group, "frames": count, "samples": length,
                      "index": index, "total": len(groups)})
        frames, samples = frames + count, samples + length
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
```

- [ ] **Paso 4: Ejecuta las pruebas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"`
Esperado: `Ran 10 tests … OK`.

- [ ] **Paso 5: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): reparte cada corte en subcortes de 40 tramos con clave de caché por huella" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 3: Filtros de FFmpeg por corte, con control negativo

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.tempo_factors`, `render.subcuts`; de `common.py` → `seconds(value) -> str`,
  `output_interval(rate) -> float`, `ffmpeg(*args, cwd=None)`, `timeline_start(data) -> float`.
- Produces: `render.video_filter(spans, base, rate, speed, n_frames) -> str`, que incluye la guarda de
  lectura `trim=end=<base + fin + 1/F>`; `render.audio_filter(spans, base, speed, m_samples, label="0:a") -> str`.

- [ ] **Paso 1: Escribe la prueba rápida que falla**

Añade a `test_render.py`:

```python
class FilterTest(unittest.TestCase):
    def test_the_video_filter_carries_the_whole_verified_chain(self):
        text = render.video_filter([(4.0, 5.0), (7.0, 8.0)], 0.0, "25/1", 1.25, 40)
        # The reading guard closes one frame after the LAST span; without it FFmpeg decodes the
        # whole medium, because select drops frames instead of ending the chain.
        self.assertTrue(text.startswith("fps=25/1:start_time=4.000000,trim=end=8.040000,select='"))
        self.assertIn("(gte(t,4.000000)*lt(t,5.000000))+(gte(t,7.000000)*lt(t,8.000000))", text)
        # The leading fps is what keeps a held frame alive; tpad needs stop=-1 to clone up to N.
        self.assertIn("settb=AVTB,setpts=N/(25/1)/1.250000/TB,fps=25/1", text)
        self.assertIn("tpad=stop=-1:stop_mode=clone,trim=end_frame=40", text)
        self.assertTrue(text.endswith("setpts=N/(25/1)/TB,pad=ceil(iw/2)*2:ceil(ih/2)*2"))

    def test_the_container_offset_moves_every_boundary(self):
        text = render.video_filter([(4.0, 5.0)], 12.5, "25/1", 1.0, 25)
        self.assertIn("fps=25/1:start_time=16.500000,trim=end=17.540000", text)
        self.assertIn("(gte(t,16.500000)*lt(t,17.500000))", text)

    def test_the_audio_filter_forces_the_exact_sample_count(self):
        text = render.audio_filter([(4.0, 5.0), (7.0, 8.0)], 0.0, 1.25, 76800)
        self.assertTrue(text.startswith("[0:a]asplit=2[s0][s1];"))
        self.assertIn("[s0]atrim=start=4.000000:end=5.000000,asetpts=N/SR/TB[t0];", text)
        self.assertIn("[s1]atrim=start=7.000000:end=8.000000,asetpts=N/SR/TB[t1];", text)
        self.assertIn("[t0][t1]concat=n=2:v=0:a=1,atempo=1.250000,", text)
        self.assertTrue(text.endswith("apad=whole_len=76800,atrim=end_sample=76800[a]"))

    def test_speed_one_leaves_no_atempo(self):
        self.assertNotIn("atempo", render.audio_filter([(0.0, 1.0)], 0.0, 1.0, 48000))

    def test_the_chosen_track_replaces_the_default_label(self):
        text = render.audio_filter([(0.0, 1.0)], 0.0, 1.0, 48000, label="0:3")
        self.assertTrue(text.startswith("[0:3]asplit=1[s0];"))
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k Filter`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'video_filter'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade `seconds` a la importación de `common` y las dos funciones:

```python
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
    chain = [f"[{label}]asplit=" + str(count) + "".join(f"[s{i}]" for i in range(count))]
    for index, (start, end) in enumerate(spans):
        chain.append(f"[s{index}]atrim=start={seconds(base + start)}:end={seconds(base + end)},"
                     f"asetpts=N/SR/TB[t{index}]")
    tempo = "".join(f"atempo={factor:.6f}," for factor in tempo_factors(speed))
    chain.append("".join(f"[t{i}]" for i in range(count)) +
                 f"concat=n={count}:v=0:a=1,{tempo}apad=whole_len={m_samples},"
                 f"atrim=end_sample={m_samples}[a]")
    return ";".join(chain)
```

- [ ] **Paso 4: Ejecuta las pruebas rápidas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k FilterTest`
Esperado: `Ran 5 tests … OK`.

- [ ] **Paso 5: Escribe la prueba de integración que falla**

Añade a `test_render.py`, antes de `if __name__`:

```python
def coded(path, length=10, rate=25):
    """Source whose luminance is the frame index and whose audio ramps with time."""
    common.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=320x180:r={rate}:d={length}",
                  "-f", "lavfi", "-i", f"aevalsrc=exprs='t/{length}':sample_rate=48000:"
                                       f"duration={length}",
                  "-vf", "geq=lum='N':cb=128:cr=128,format=yuv420p",
                  "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast", "-bf", "0",
                  "-c:a", "pcm_s16le", path)


def held(path):
    """Variable-rate recording: 25 fps until 2 s, one frame held until 8 s, then 25 fps again."""
    common.ffmpeg("-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=10",
                  "-f", "lavfi", "-i", "aevalsrc=exprs='t/10':sample_rate=48000:duration=10",
                  "-vf", r"geq=lum='N':cb=128:cr=128,format=yuv420p,"
                         r"select='lt(t\,2)+eq(n\,50)+gte(t\,8)'",
                  "-fps_mode", "vfr", "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast",
                  "-bf", "0", "-c:a", "pcm_s16le", path)


def shifted(path, source, ahead=7):
    """Copy whose container starts at `ahead` seconds, like a real recording with an offset."""
    common.ffmpeg("-i", source, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                  "-output_ts_offset", str(ahead), "-muxdelay", "0", "-muxpreload", "0", path)


def luminances(path, width=320, height=180):
    """Top-left luminance sample of every frame, read straight from the Y plane."""
    with tempfile.TemporaryDirectory(prefix="resumir-video-y-") as folder:
        plane = Path(folder) / "y.raw"
        common.ffmpeg("-i", path, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", plane)
        data = plane.read_bytes()
    size = width * height * 3 // 2
    return [data[index * size] for index in range(len(data) // size)]


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class FilterOnMediaTest(unittest.TestCase):
    def test_the_cut_holds_only_its_spans_at_the_asked_speed(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)
            clip = root / "corte.mkv"
            common.ffmpeg("-ss", "1.000000", "-noaccurate_seek", "-copyts",
                          "-i", source, "-map", "0:v:0", "-an", "-sn", "-dn",
                          "-map_metadata", "-1", "-map_chapters", "-1",
                          "-vf", render.video_filter([(4.0, 5.0), (7.0, 8.0)], 0.0, "25/1", 1.25, 40),
                          *render.ENCODER, clip)
            values = luminances(clip)
            self.assertEqual(len(values), 40)
            # Frame 100 is second 4.0 and frame 175 is second 7.0 of the source.
            self.assertEqual(values[:2], [100, 101])
            self.assertEqual(values[20:22], [175, 176])
            self.assertEqual(values[-1], 199)
            self.assertTrue(all(100 <= value <= 124 for value in values[:20]))
            self.assertTrue(all(175 <= value <= 199 for value in values[20:]))

    def test_without_the_leading_fps_a_held_frame_disappears(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "pantalla.mkv"
            held(source)
            good, bad = root / "bien.mkv", root / "mal.mkv"
            chain = render.video_filter([(3.0, 5.0), (8.2, 9.0)], 0.0, "25/1", 1.0, 70)
            common.ffmpeg("-ss", "0", "-noaccurate_seek", "-copyts", "-i", source,
                          "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", chain, *render.ENCODER, good)
            # Drop only the leading fps, keeping the reading guard that follows it.
            common.ffmpeg("-ss", "0", "-noaccurate_seek", "-copyts", "-i", source,
                          "-map", "0:v:0", "-an", "-sn", "-dn",
                          "-vf", chain.split(",", 1)[1], *render.ENCODER, bad)
            kept, lost = luminances(good), luminances(bad)
            self.assertEqual(len(kept), 70)
            # The slide held from 2 s to 8 s is frame 50 and must fill the first 50 output frames.
            self.assertEqual(set(kept[:50]), {50})
            self.assertEqual(kept[50], 205)
            self.assertNotIn(50, lost)

    def test_a_shifted_container_keeps_the_absolute_times(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, moved = root / "fuente.mkv", root / "desfasada.mkv"
            coded(source)
            shifted(moved, source)
            data = common.probe(moved)
            base = common.timeline_start(data)
            self.assertAlmostEqual(base, 7.0, places=3)
            clip = root / "corte.mkv"
            common.ffmpeg("-ss", "0.000000", "-noaccurate_seek", "-copyts", "-i", moved,
                          "-map", "0:v:0", "-an", "-sn", "-dn",
                          "-map_metadata", "-1", "-map_chapters", "-1",
                          "-vf", render.video_filter([(3.0, 4.0)], base, "25/1", 1.0, 25),
                          *render.ENCODER, clip)
            # s = 3.0 of the medium is frame 75: the container offset must not move the content.
            self.assertEqual(luminances(clip), list(range(75, 100)))
```

- [ ] **Paso 6: Ejecuta la prueba de integración y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k FilterOnMedia`
Esperado: `Ran 3 tests … OK` (unos 15 s). Medido en esta máquina: 40 fotogramas con luminancias
`100…124` y `175…199`; 70 con el retenido intacto; y 25 con luminancias `75…99` sobre el contenedor
desplazado 7 s.

- [ ] **Paso 7: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): filtros por corte con fps inicial, guarda de lectura y tpad stop=-1" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 4: Montaje de un subcorte, recuento y caché

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.video_filter`, `render.audio_filter`, `render.cut_key`, `render.ENCODER`,
  `render.Invalid`; de `common.py` → `ffmpeg`, `run`, `save`, `seconds`, `publish(staged, final)`,
  `seek_margin(data) -> float`, `timeline_start(data) -> float`.
- Produces: `render.counted_frames(path) -> int`;
  `render.counted_samples(path, sample_rate, folder) -> int`;
  `render.render_part(data, plan, part, target, threads) -> None`, **sin acotar la lectura con `-t`
  ni con `-to`** (la guarda va en el filtro, Tarea 3);
  `render.cached_part(data, plan, part, cortes, release, threads) -> Path`.

- [ ] **Paso 1: Escribe la prueba que falla**

Añade `import re` a la cabecera de `test_render.py` (entre `from pathlib import Path` y
`import shutil`) y a continuación, al final del archivo:

```python
def graph_frames(source, chain, target):
    """Frames that actually reach the filter graph, counted by a leading showinfo on stderr."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin", "-n",
                             "-ss", "1.000000", "-noaccurate_seek", "-copyts", "-i", str(source),
                             "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", chain,
                             *map(str, render.ENCODER), str(target)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise AssertionError(result.stderr[-2000:])
    return len(re.findall(r"\] n: *\d+ pts:", result.stderr))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class PartTest(unittest.TestCase):
    def prepared(self, root):
        source = root / "fuente.mkv"
        coded(source)
        plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                           segments=[sample_segment(title="Prueba", start=4.0, end=8.0,
                                                    spans=[[4.0, 5.0], [7.0, 8.0]],
                                                    frames=40, samples=76800)])
        plan["audio_stream"] = 1
        return source, plan

    def test_the_reading_stops_at_the_end_of_the_cut(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "largo.mkv"
            coded(source, length=40)                       # 1000 frames
            chain = render.video_filter([(4.0, 6.0)], 0.0, "25/1", 1.25, 40)
            head, guard, rest = chain.split(",", 2)
            self.assertTrue(guard.startswith("trim=end="), chain)
            guarded = graph_frames(source, f"showinfo,{chain}", root / "con.mkv")
            whole = graph_frames(source, f"showinfo,{head},{rest}", root / "sin.mkv")
            # Measured here: 153 frames with the guard and the whole 1000 without it. Neither -t
            # nor -to can replace it next to -copyts: both leave the chain at zero frames.
            self.assertLess(guarded, 300, guarded)
            self.assertGreater(whole, 900, whole)
            self.assertEqual(render.counted_frames(root / "con.mkv"), 40)
            self.assertEqual(render.counted_frames(root / "sin.mkv"), 40)

    def test_a_cut_that_ends_on_the_last_frame_of_the_medium_is_whole(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)                                  # 10 s: frames 0…249
            plan = sample_plan(source={"path": str(source.resolve()),
                                       **common.fingerprint(source)},
                               segments=[sample_segment(title="Cierre", start=9.0, end=10.0,
                                                        spans=[[9.0, 10.0]], frames=25,
                                                        samples=48000)])
            plan["settings"]["speed"] = 1.0
            plan["audio_stream"] = 1
            data = common.probe(source)
            part = render.subcuts(plan["segments"][0], 25.0, 1.0, 48000)[0]
            target = root / "cierre.mkv"
            render.render_part(data, plan, part, target, 1)
            self.assertEqual(render.counted_frames(target), 25)
            self.assertEqual(render.counted_samples(target, 48000, root), 48000)
            # Frames 225…249: the last frame of the medium is kept and tpad clones nothing.
            self.assertEqual(luminances(target), list(range(225, 250)))

    def test_a_rendered_part_has_exactly_n_frames_and_m_samples(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, plan = self.prepared(root)
            data = common.probe(source)
            part = render.subcuts(plan["segments"][0], 25.0, 1.25, 48000)[0]
            target = root / "corte.mkv"
            render.render_part(data, plan, part, target, 1)
            self.assertEqual(render.counted_frames(target), 40)
            self.assertEqual(render.counted_samples(target, 48000, root), 76800)
            self.assertEqual(luminances(target)[:2], [100, 101])

    def test_the_cache_is_reused_and_a_damaged_entry_is_rebuilt(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, plan = self.prepared(root)
            data = common.probe(source)
            cortes = root / "cortes"
            cortes.mkdir()
            part = render.subcuts(plan["segments"][0], 25.0, 1.25, 48000)[0]
            release = render.ffmpeg_release()
            first = render.cached_part(data, plan, part, cortes, release, 1)
            stamp = first.stat().st_mtime_ns
            again = render.cached_part(data, plan, part, cortes, release, 1)
            self.assertEqual(again, first)
            self.assertEqual(again.stat().st_mtime_ns, stamp)
            first.with_suffix(".json").unlink()
            third = render.cached_part(data, plan, part, cortes, release, 1)
            self.assertEqual(third, first)
            self.assertTrue(third.with_suffix(".json").is_file())
            note = json.loads(third.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual((note["frames"], note["samples"]), (40, 76800))
            self.assertFalse(list(cortes.glob("*.parcial")))
```

- [ ] **Paso 2: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k PartTest`
Esperado: FALLA cuatro veces con `AttributeError: module 'render' has no attribute 'counted_frames'`
o `… 'render_part'`, según la prueba.

- [ ] **Paso 3: Escribe los recuentos**

En `render.py`, añade `tempfile` y `wave` a las importaciones y:

```python
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
```

- [ ] **Paso 4: Escribe el montaje de un subcorte**

En `render.py`, añade:

```python
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
```

Añade `video_stream` a la importación de `common`:

```python
from common import (BLOCKING, ffmpeg, fingerprint, frames_for, output_interval, plan_sha256,
                    positive, publish, run, samples_for, save, seconds, seek_margin,
                    timeline_start, video_stream, warning)
```

- [ ] **Paso 5: Escribe la caché**

En `render.py`, añade:

```python
def cached_part(data, plan, part, cortes, release, threads):
    """Render the part unless the cache already holds it with the right frame and sample counts."""
    target = cortes / f"{cut_key(plan, part, release)}.mkv"
    note = target.with_suffix(".json")
    if target.is_file() and note.is_file():
        try:
            kept = json.loads(note.read_text(encoding="utf-8"))
        except ValueError:
            kept = {}
        if (kept.get("frames"), kept.get("samples")) == (part["frames"], part["samples"]):
            return target
    # A cut without its note, or with a note that disagrees, is not trustworthy: rebuild both.
    for path in (target, note):
        if path.exists():
            path.replace(path.with_suffix(path.suffix + ".parcial"))
    render_part(data, plan, part, target, threads)
    save(note, {"cut": part["cut"], "index": part["index"], "total": part["total"],
                "spans": [[round(start, 3), round(end, 3)] for start, end in part["spans"]],
                "frames": part["frames"], "samples": part["samples"], "ffmpeg": release})
    for path in (target, note):
        leftover = path.with_suffix(path.suffix + ".parcial")
        if leftover.exists():
            leftover.unlink()
    return target
```

- [ ] **Paso 6: Ejecuta las pruebas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k PartTest`
Esperado: `Ran 4 tests … OK` (unos 30 s).

- [ ] **Paso 7: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): monta cada subcorte con recuento forzado y caché por clave" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 5: Presupuesto reanudable y reintento único ante falta de memoria

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.cached_part`, `render.Pending`, `render.render_part`; de `common.py` →
  `MEMORY_PATTERNS: tuple[str, ...]`.
- Produces: `render.MEMORY_CODES: tuple[str, ...]`; `render.retryable(message) -> bool`;
  `render.part_label(part) -> str`; `render.all_parts(plan, cadence) -> list[dict]`, que además
  comprueba los `subcuts` publicados por `plan.py`;
  `render.build(data, plan, cortes, release, threads, budget) -> list[Path]`.

- [ ] **Paso 1: Escribe la prueba rápida que falla**

Añade a `test_render.py`:

```python
class BudgetTest(unittest.TestCase):
    def test_only_recognised_memory_failures_are_retried(self):
        for text in ("ffmpeg falló (código 1):\nCannot allocate memory",
                     "ffmpeg falló (código 1):\nOut of memory",
                     "ffmpeg falló (código 1):\nav_buffer_alloc() failed",
                     "ffmpeg falló (código 137):\nmatado",
                     "ffmpeg falló (código 3221225495):\n"):
            with self.subTest(text=text):
                self.assertTrue(render.retryable(text))
        for text in ("ffmpeg falló (código 1):\nInvalid data found when processing input",
                     "ffmpeg falló (código 2):\nNo such file or directory"):
            with self.subTest(text=text):
                self.assertFalse(render.retryable(text))

    def test_the_pending_state_counts_what_is_done(self):
        pending = render.Pending(4, 11, ["corte 5 subcorte 1/1", "corte 6 subcorte 1/2"])
        self.assertEqual(pending.state, {"done": 4, "total": 11, "pending": 7,
                                         "bloques": ["corte 5 subcorte 1/1",
                                                     "corte 6 subcorte 1/2"]})
        # `pending` is always an integer and `bloques` always a list, even without detail (§12).
        self.assertIsInstance(render.Pending(0, 2).state["pending"], int)
        self.assertEqual(render.Pending(0, 2).state["bloques"], [])

    def test_all_parts_expands_every_cut_in_order(self):
        plan = sample_plan(segments=[sample_segment(id=1, numero=1, title="A", start=1.0, end=3.0,
                                                    spans=[[1.0, 3.0]], frames=40, samples=76800),
                                     sample_segment(id=4, numero=2, title="B", start=5.0, end=9.0,
                                                    spans=[[5.0, 6.0], [8.0, 9.0]],
                                                    frames=40, samples=76800)])
        parts = render.all_parts(plan, 25.0)
        self.assertEqual([part["cut"] for part in parts], [1, 4])
        self.assertEqual(sum(part["frames"] for part in parts), 80)

    def test_a_plan_whose_estimate_disagrees_is_refused(self):
        plan = sample_plan(segments=[sample_segment(spans=[[1.0, 3.0]], frames=41, samples=76800)])
        with self.assertRaisesRegex(render.Refused, "41"):
            render.all_parts(plan, 25.0)
        # The subcuts published by plan.py must match the ones render recomputes from the spans.
        moved = sample_plan(segments=[sample_segment(
            spans=[[1.0, 3.0]], frames=40, samples=76800,
            subcuts=[{"spans": [[1.0, 2.0]], "frames": 20, "samples": 38400},
                     {"spans": [[2.0, 3.0]], "frames": 20, "samples": 38400}])])
        with self.assertRaisesRegex(render.Refused, "subcortes"):
            render.all_parts(moved, 25.0)
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k BudgetTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'retryable'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade `time` a las importaciones, `MEMORY_PATTERNS` a las de `common` y:

```python
# Python reports STATUS_NO_MEMORY (0xC0000017) as 3221225495 on Windows and the OOM killer as 137.
MEMORY_CODES = ("código 137", "código 3221225495")


def retryable(message):
    """Only the memory failures listed in §11 deserve the single retry; an AVERROR does not."""
    return any(pattern in message for pattern in MEMORY_PATTERNS + MEMORY_CODES)


def part_label(part):
    """How a pass still to render is named in the resumable state of code 3."""
    return f"corte {part['cut']} subcorte {part['index'] + 1}/{part['total']}"


def all_parts(plan, cadence):
    """Every pass the plan needs, in order, checking the numbers that plan wrote for each cut."""
    settings = plan["settings"]
    parts = []
    for segment in plan["segments"]:
        pieces = subcuts(segment, cadence, float(settings["speed"]), settings["sample_rate"])
        frames, samples = sum(p["frames"] for p in pieces), sum(p["samples"] for p in pieces)
        if (segment.get("frames"), segment.get("samples")) != (frames, samples):
            raise Refused(f"El corte {segment['id']} declara {segment.get('frames')} fotogramas y "
                          f"{segment.get('samples')} muestras, pero sus tramos dan {frames} y "
                          f"{samples}; vuelve a ejecutar plan sobre este medio.")
        declared = segment.get("subcuts")
        if isinstance(declared, list) and declared:
            mine = [(len(piece["spans"]), piece["frames"], piece["samples"]) for piece in pieces]
            theirs = [(len(piece.get("spans") or []), piece.get("frames"), piece.get("samples"))
                      for piece in declared]
            if mine != theirs:
                raise Refused(f"El corte {segment['id']} publica unos subcortes que no cuadran con "
                              f"sus tramos ({theirs} frente a {mine}); vuelve a ejecutar plan.")
        parts.extend(pieces)
    return parts


def build(data, plan, cortes, release, threads, budget):
    """Render every missing part, one retry on memory failures, honouring the time budget (§11)."""
    parts = all_parts(plan, cadence_of(plan))
    started, done, cuts = time.monotonic(), 0, []
    for index, part in enumerate(parts):
        target = cortes / f"{cut_key(plan, part, release)}.mkv"
        fresh = not (target.is_file() and target.with_suffix(".json").is_file())
        # `done` guards the first pass: a budget smaller than one cut must still make progress.
        if fresh and budget and done and time.monotonic() - started >= budget:
            raise Pending(done, len(parts), [part_label(item) for item in parts[index:]])
        try:
            cuts.append(cached_part(data, plan, part, cortes, release, threads))
        except ValueError as exc:
            if not retryable(str(exc)):
                raise
            print(f"Falta de memoria en el corte {part['cut']}; se repite con un solo hilo.",
                  flush=True)
            # The one retry allowed by §11: -threads 1 and -filter_threads 1, never a second one.
            render_part(data, plan, part, target, 1)
            save(target.with_suffix(".json"),
                 {"cut": part["cut"], "index": part["index"], "total": part["total"],
                  "spans": [[round(a, 3), round(b, 3)] for a, b in part["spans"]],
                  "frames": part["frames"], "samples": part["samples"], "ffmpeg": release})
            cuts.append(target)
        done += 1
        print(f"Corte {done}/{len(parts)}", flush=True)
    return cuts
```

`render_part` ya aplica `-threads N -filter_threads N` a sus dos pasadas, así que el reintento solo
necesita pasar `1`. Comprobado en esta máquina que el audio acepta ambas opciones antes de `-i` y
sigue dando las 76 800 muestras exactas.

- [ ] **Paso 4: Ejecuta las pruebas rápidas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k BudgetTest`
Esperado: `Ran 4 tests … OK`.

- [ ] **Paso 5: Escribe la prueba de integración de reanudación**

Añade a `test_render.py`:

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class ResumeTest(unittest.TestCase):
    def test_an_exhausted_budget_leaves_the_done_cuts_in_the_cache(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)
            plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                               segments=[sample_segment(id=1, numero=1, title="A", start=1.0,
                                                        end=3.0, spans=[[1.0, 3.0]],
                                                        frames=40, samples=76800),
                                         sample_segment(id=2, numero=2, title="B", start=5.0,
                                                        end=7.0, spans=[[5.0, 7.0]],
                                                        frames=40, samples=76800)])
            plan["audio_stream"] = 1
            data = common.probe(source)
            cortes = root / "cortes"
            cortes.mkdir()
            release = render.ffmpeg_release()
            with self.assertRaises(render.Pending) as caught:
                # A microscopic budget still renders the first part and stops before the second.
                render.build(data, plan, cortes, release, 1, 1e-9)
            self.assertEqual(caught.exception.state, {"done": 1, "total": 2, "pending": 1,
                                                      "bloques": ["corte 2 subcorte 1/1"]})
            self.assertEqual(len(list(cortes.glob("*.mkv"))), 1)
            cuts = render.build(data, plan, cortes, release, 1, None)
            self.assertEqual(len(cuts), 2)
            self.assertEqual(len(list(cortes.glob("*.mkv"))), 2)
            self.assertTrue(all(render.counted_frames(cut) == 40 for cut in cuts))
```

- [ ] **Paso 6: Ejecuta la prueba de integración y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k ResumeTest`
Esperado: `Ran 1 test … OK` (unos 10 s).

- [ ] **Paso 7: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): presupuesto reanudable y reintento único ante falta de memoria" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 6: Ensamblado con audio codificado una sola vez

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.build`, `render.counted_frames`; de `common.py` → `ffmpeg`, `listing(path, names)`,
  `require_encoders(*names)`.
- Produces: `render.assemble(folder, cuts, staged, threads) -> None`, que escribe `staged` (un MP4)
  dentro de `folder` a partir de los MKV de `cuts`.

- [ ] **Paso 1: Escribe la prueba que falla**

Añade a `test_render.py`:

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class AssemblyTest(unittest.TestCase):
    def test_the_montage_keeps_every_frame_and_stays_in_sync(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)
            plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                               segments=[sample_segment(id=1, numero=1, title="A", start=1.0,
                                                        end=5.0, spans=[[1.0, 2.0], [4.0, 5.0]],
                                                        frames=40, samples=76800),
                                         sample_segment(id=2, numero=2, title="B", start=7.0,
                                                        end=8.5, spans=[[7.0, 8.5]],
                                                        frames=30, samples=57600)])
            plan["audio_stream"] = 1
            data = common.probe(source)
            cortes = root / "cortes"
            cortes.mkdir()
            cuts = render.build(data, plan, cortes, render.ffmpeg_release(), 1, None)
            # The list and the cuts share a folder: the concat demuxer resolves names from the cwd.
            staged = cortes / "resumen.mp4"
            render.assemble(cortes, cuts, staged, 1)
            self.assertEqual(render.counted_frames(staged), 70)
            final = common.probe(staged)
            picture, sound = common.streams(final)
            self.assertAlmostEqual(common.stream_duration(final, picture), 70 / 25, delta=0.02)
            self.assertLessEqual(abs(common.stream_duration(final, picture)
                                     - common.stream_duration(final, sound)), 0.1)
            self.assertEqual(sound["codec_name"], "aac")
            # The cuts keep their content: source frames 25…49, 100…124 and 175…211.
            values = luminances(staged)
            self.assertEqual((values[0], values[20], values[40], values[-1]), (25, 100, 175, 211))
```

- [ ] **Paso 2: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k AssemblyTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'assemble'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade `listing` y `require_encoders` a la importación de `common` y:

```python
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
```

**Invariante de `assemble`:** los MKV de `cuts`, la lista `cortes.txt` y `staged` viven en `folder`.
En la Tarea 10, `montage` copia allí los cortes cacheados antes de llamar; en esta prueba `build` ya
los ha dejado en `cortes/`, que es la carpeta que se pasa.

- [ ] **Paso 4: Ejecuta la prueba y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k AssemblyTest`
Esperado: `Ran 1 test … OK` (unos 15 s).

- [ ] **Paso 5: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): ensambla con dos concat demuxer y una sola codificación AAC" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 7: Validación bloqueante de decodificación y recuentos

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.counted_frames`, `render.Invalid`; de `common.py` → `ffmpeg`, `probe`, `streams`,
  `stream_duration`.
- Produces: `render.SYNC = 0.1`; `render.decode_check(path, threads) -> None`;
  `render.totals_check(path, parts, threads) -> dict` con claves `fotogramas_esperados`,
  `fotogramas`, `video_s`, `audio_s`, `desfase_s`.

- [ ] **Paso 1: Escribe la prueba que falla**

Añade a `test_render.py`:

```python
def assembled(root):
    """Two cuts of the coded source, already rendered and assembled; reused by several checks."""
    source = root / "fuente.mkv"
    coded(source)
    plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                       segments=[sample_segment(id=1, numero=1, title="A", start=1.0, end=5.0,
                                                spans=[[1.0, 2.0], [4.0, 5.0]],
                                                frames=40, samples=76800),
                                 sample_segment(id=2, numero=2, title="B", start=7.0, end=8.5,
                                                spans=[[7.0, 8.5]], frames=30, samples=57600)])
    plan["audio_stream"] = 1
    data = common.probe(source)
    cortes = root / "cortes"
    cortes.mkdir()
    cuts = render.build(data, plan, cortes, render.ffmpeg_release(), 1, None)
    staged = cortes / "resumen.mp4"
    render.assemble(cortes, cuts, staged, 1)
    return source, plan, data, staged


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class TotalsTest(unittest.TestCase):
    def test_the_totals_match_the_plan(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, plan, _, staged = assembled(root)
            render.decode_check(staged, 1)
            report = render.totals_check(staged, render.all_parts(plan, 25.0), 1)
            self.assertEqual(report["fotogramas"], 70)
            self.assertEqual(report["fotogramas_esperados"], 70)
            self.assertLessEqual(report["desfase_s"], render.SYNC)

    def test_a_montage_short_of_frames_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, plan, _, staged = assembled(root)
            parts = render.all_parts(plan, 25.0)
            parts[0] = dict(parts[0], frames=parts[0]["frames"] + 5)
            with self.assertRaisesRegex(render.Invalid, "75"):
                render.totals_check(staged, parts, 1)

    def test_a_truncated_file_fails_the_decoding(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, _, _, staged = assembled(root)
            broken = root / "roto.mp4"
            broken.write_bytes(staged.read_bytes()[: staged.stat().st_size // 3])
            with self.assertRaises(render.Invalid):
                render.decode_check(broken, 1)

    def test_short_cuts_leave_no_packet_under_a_millisecond(self):
        # The check that `test_short_cuts_are_not_truncated_by_the_concatenation` used to make in
        # test_video.py: one-frame cuts next to longer ones must not squash the muxed timeline.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)
            plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                               segments=[sample_segment(id=1, numero=1, title="Breve", start=1.0,
                                                        end=1.04, spans=[[1.0, 1.04]],
                                                        frames=1, samples=1920),
                                         sample_segment(id=2, numero=2, title="Larga", start=3.0,
                                                        end=3.6, spans=[[3.0, 3.6]],
                                                        frames=15, samples=28800),
                                         sample_segment(id=3, numero=3, title="Otra breve",
                                                        start=5.0, end=5.04, spans=[[5.0, 5.04]],
                                                        frames=1, samples=1920)])
            plan["settings"]["speed"] = 1.0
            plan["audio_stream"] = 1
            data = common.probe(source)
            cortes = root / "cortes"
            cortes.mkdir()
            cuts = render.build(data, plan, cortes, render.ffmpeg_release(), 1, None)
            staged = cortes / "resumen.mp4"
            render.assemble(cortes, cuts, staged, 1)
            report = render.totals_check(staged, render.all_parts(plan, 25.0), 1)
            self.assertEqual(report["fotogramas"], 17)
            packets = json.loads(common.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                             "-show_packets", "-show_entries",
                                             "packet=duration_time", "-of", "json", str(staged)]))
            self.assertFalse([item for item in packets["packets"]
                              if float(item["duration_time"]) < 0.001])
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k TotalsTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'decode_check'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade `probe`, `streams` y `stream_duration` a la importación de `common` y:

```python
SYNC = 0.1


def decode_check(path, threads):
    """Full decoding with -xerror: a montage that cannot be played whole is never published."""
    try:
        ffmpeg("-xerror", "-threads", str(threads), "-i", path,
               "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")
    except ValueError as exc:
        raise Invalid(f"El montaje no se decodifica completo: {exc}") from exc


def totals_check(path, parts, threads):
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
```

- [ ] **Paso 4: Ejecuta las pruebas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k TotalsTest`
Esperado: `Ran 4 tests … OK` (unos 45 s). La cuarta es la de los paquetes cortos: a ×1 un corte de
0,04 s da exactamente un fotograma (`N = round(0,04 · 25 / 1)`) y 1 920 muestras, y el montaje de los
tres cortes suma 17 fotogramas.

- [ ] **Paso 5: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): validación bloqueante de decodificación, fotogramas y sincronía" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 8: Colocación de cada corte por imagen, frente al original

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.Invalid`; de `common.py` → `ffmpeg`, `seconds`, `seek_margin`, `timeline_start`,
  `video_stream`.
- Produces: `render.IMAGE_SIDE = 64`, `render.IMAGE_OK = 0.08`, `render.IMAGE_MARK = 0.15`;
  `render.gray_frame(path, instant, base, margin, target) -> bytes`;
  `render.image_distance(left, right) -> float`;
  `render.image_placement(data, final, spans, out_start, out_end, folder) -> list[dict]` con un
  registro `{"punto", "salida_s", "origen_s", "distancia"}` por ventana.

- [ ] **Paso 1: Escribe la prueba rápida que falla**

Añade a `test_render.py`:

```python
class ImageDistanceTest(unittest.TestCase):
    def test_the_distance_is_normalised_and_symmetric(self):
        black, white = bytes(4096), bytes([255]) * 4096
        self.assertEqual(render.image_distance(black, black), 0.0)
        self.assertEqual(render.image_distance(black, white), 1.0)
        self.assertEqual(render.image_distance(white, black), 1.0)
        half = bytes([128]) * 4096
        self.assertAlmostEqual(render.image_distance(black, half), 128 / 255)

    def test_frames_of_different_sizes_are_refused(self):
        with self.assertRaisesRegex(ValueError, "tamaño"):
            render.image_distance(bytes(4096), bytes(16))
```

- [ ] **Paso 2: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k ImageDistance`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'image_distance'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade:

```python
IMAGE_SIDE = 64
IMAGE_OK, IMAGE_MARK = 0.08, 0.15


def gray_frame(path, instant, base, margin, target):
    """The frame on screen at `instant`, reduced to IMAGE_SIDE² luminance samples."""
    ffmpeg("-ss", seconds(max(0.0, instant - margin)), "-noaccurate_seek", "-copyts", "-i", path,
           "-map", "0:v:0", "-frames:v", "1",
           "-vf", f"fps=1000:start_time={seconds(base + instant)},"
                  f"scale={IMAGE_SIDE}:{IMAGE_SIDE},format=gray",
           "-f", "rawvideo", target)
    return Path(target).read_bytes()


def image_distance(left, right):
    """Mean absolute luminance difference, normalised to 0…1."""
    if len(left) != len(right) or not left:
        raise ValueError(f"Las imágenes deben tener el mismo tamaño ({len(left)} y {len(right)}).")
    return sum(abs(one - two) for one, two in zip(left, right)) / (len(left) * 255)
```

- [ ] **Paso 4: Ejecuta la prueba rápida y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k ImageDistance`
Esperado: `Ran 2 tests … OK`.

- [ ] **Paso 5: Escribe la prueba de integración que falla**

Añade a `test_render.py`:

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class ImagePlacementTest(unittest.TestCase):
    def test_the_first_and_last_frame_of_every_cut_match_the_source(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, _, data, staged = assembled(root)
            rows = render.image_placement(data, staged, [(1.0, 2.0), (4.0, 5.0)], 0.0, 1.6, root)
            self.assertEqual([row["punto"] for row in rows], ["inicio", "fin"])
            self.assertTrue(all(row["distancia"] <= render.IMAGE_OK for row in rows), rows)

    def test_a_displaced_map_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, _, data, staged = assembled(root)
            # Same cut, wrong source times: the montage holds seconds 1 and 4, not 6 and 9.
            rows = render.image_placement(data, staged, [(6.0, 7.0), (9.0, 9.5)], 0.0, 1.6, root)
            self.assertTrue(any(row["distancia"] > render.IMAGE_MARK for row in rows), rows)
```

- [ ] **Paso 6: Escribe `image_placement`**

En `render.py`, añade:

```python
def image_placement(data, final, spans, out_start, out_end, folder):
    """Compare the first and last frame of the cut against the source it claims to come from."""
    source, base = data["source"]["path"], timeline_start(data)
    margin = seek_margin(data)
    points = (("inicio", out_start, spans[0][0]), ("fin", max(out_start, out_end - 1e-3),
                                                   max(spans[-1][0], spans[-1][1] - 1e-3)))
    rows = []
    with tempfile.TemporaryDirectory(prefix="imagen-", dir=folder) as temporary:
        for name, moment, origin in points:
            produced = gray_frame(final, moment, 0.0, margin, Path(temporary) / f"{name}-s.gray")
            expected = gray_frame(source, origin, base, margin, Path(temporary) / f"{name}-o.gray")
            rows.append({"punto": name, "salida_s": round(moment, 3), "origen_s": round(origin, 3),
                         "distancia": round(image_distance(produced, expected), 4)})
    return rows
```

- [ ] **Paso 7: Ejecuta las pruebas de integración y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k ImagePlacement`
Esperado: `Ran 2 tests … OK` (unos 30 s). Medido en esta máquina: la distancia del caso correcto es
0,0000 y la del mapa desplazado, 0,5720.

- [ ] **Paso 8: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): valida por imagen la colocación de cada corte contra el original" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 9: Colocación de cada corte por envolvente de audio

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: de `common.py` → `energy(wav_path, cache_path=None) -> array('f')` (RMS en dBFS cada
  10 ms), `ffmpeg`, `seconds`, `timeline_start`.
- Produces: `render.LEVEL_BLOCK = 0.010`, `render.LEVEL_RATE = 16000`, `render.WINDOW = 1.0`,
  `render.ENVELOPE_OK = 4.0`, `render.ENVELOPE_MARK = 8.0`, `render.ENVELOPE_LAG = 4`,
  `render.ENVELOPE_SPREAD = 6.0`, `render.ENVELOPE_CORRELATION = 0.9`. El bloque de la envolvente se
  llama `LEVEL_BLOCK` —y la rejilla de las hojas de uniones y sus medidas, `JOIN_SHEET`, `JOIN_WIDTH`
  y `JOIN_GAP` (Tarea 10)— para no chocar con `video.BLOCK` (600 s del barrido) ni con `video.SHEET`,
  que define el plan de evidencia.
  `ENVELOPE_LAG`, `ENVELOPE_SPREAD` y `ENVELOPE_MARK` son los tres umbrales provisionales que se
  declaran al final de este plan y que el Plan 4 escribe en `docs/requisitos.md`: 40 ms de desfase,
  6 dB de guarda de modulación y 8 dB de bloqueo;
  `render.window_levels(path, start, length, folder, name) -> array('f')`;
  `render.stretched(levels, speed, count) -> array('f')`;
  `render.correlation(left, right) -> float`; `render.spread(levels) -> float`;
  `render.align(produced, reference) -> tuple[float, int, float]` → `(diferencia_db, desfase_bloques, correlación)`;
  `render.sound_placement(data, final, spans, out_start, out_end, speed, folder) -> list[dict]`.

- [ ] **Paso 1: Escribe la prueba rápida que falla**

Añade `import array` a la cabecera de `test_render.py` (primera línea de importaciones, antes de
`import json`) y al final del archivo:

```python
class EnvelopeTest(unittest.TestCase):
    def test_the_reference_is_stretched_by_the_speed(self):
        levels = array.array("f", [float(value) for value in range(10)])
        stretched = render.stretched(levels, 1.25, 8)
        self.assertEqual(len(stretched), 8)
        self.assertAlmostEqual(stretched[0], 0.0)
        self.assertAlmostEqual(stretched[4], 5.0)
        self.assertAlmostEqual(stretched[1], 1.25, places=5)
        self.assertAlmostEqual(render.stretched(levels, 4.0, 6)[-1], 9.0)

    def test_the_alignment_finds_the_shift_and_the_difference(self):
        shape = [-60.0] * 6 + [-10.0] * 20 + [-60.0] * 6
        produced = array.array("f", shape)
        reference = array.array("f", shape)
        difference, lag, value = render.align(produced, reference)
        self.assertEqual(lag, 0)
        self.assertAlmostEqual(difference, 0.0)
        self.assertAlmostEqual(value, 1.0)
        moved = array.array("f", shape[3:] + [-60.0] * 3)
        difference, lag, value = render.align(produced, moved)
        self.assertEqual(lag, -3)
        self.assertLess(difference, 1.0)

    def test_a_flat_envelope_says_nothing_about_correlation(self):
        flat = array.array("f", [-9.0] * 40)
        self.assertLess(render.spread(flat), render.ENVELOPE_SPREAD)
        shaped = array.array("f", [-60.0] * 20 + [-9.0] * 20)
        self.assertGreater(render.spread(shaped), render.ENVELOPE_SPREAD)
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k EnvelopeTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'stretched'`.

- [ ] **Paso 3: Escribe la implementación mínima**

En `render.py`, añade `array` y `energy` a las importaciones y:

```python
# Its own name: video.BLOCK is the 600 s block of the sweep and this one is 10 ms of envelope.
LEVEL_BLOCK = 0.010
LEVEL_RATE = 16000
WINDOW = 1.0
# Provisional thresholds of §15, written down in docs/requisitos.md by the packaging plan.
ENVELOPE_OK, ENVELOPE_MARK = 4.0, 8.0
ENVELOPE_LAG = 4                 # blocks of 10 ms: 40 ms, inside the 45 ms of the specification
ENVELOPE_SPREAD = 6.0            # dB below which the envelope is flat and correlation says nothing
ENVELOPE_CORRELATION = 0.9


def window_levels(path, start, length, folder, name):
    """RMS envelope of a window, always through a temporary mono 16-bit decode (§8)."""
    # Here -t is legitimate: there is no -copyts, so it is the plain duration after the seek.
    copy = Path(folder) / f"{name}.wav"
    ffmpeg("-ss", seconds(max(0.0, start)), "-t", seconds(length), "-i", path, "-map", "0:a:0",
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
    """Lag that minimises the mean absolute difference in dB, with its correlation."""
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
```

- [ ] **Paso 4: Ejecuta las pruebas rápidas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k EnvelopeTest`
Esperado: `Ran 3 tests … OK`.

- [ ] **Paso 5: Escribe `sound_placement`**

En `render.py`, añade:

```python
def sound_placement(data, final, spans, out_start, out_end, speed, folder):
    """Compare the envelope at both ends of the cut with the source, rescaled by the speed (§8)."""
    source, base = data["source"]["path"], timeline_start(data)
    first, last = spans[0], spans[-1]
    head = min(WINDOW, (first[1] - first[0]) / speed, out_end - out_start)
    tail = min(WINDOW, (last[1] - last[0]) / speed, out_end - out_start)
    points = (("inicio", head, out_start, base + first[0]),
              ("fin", tail, out_end - tail, base + last[1] - tail * speed))
    rows = []
    with tempfile.TemporaryDirectory(prefix="envolvente-", dir=folder) as temporary:
        for name, window, moment, origin in points:
            if window <= 4 * LEVEL_BLOCK:
                rows.append({"punto": name, "bloques": 0, "diferencia_db": 0.0, "desfase_ms": 0,
                             "correlacion": None, "modulacion_db": 0.0})
                continue
            produced = window_levels(final, moment, window, temporary, f"{name}-salida")
            original = window_levels(source, origin, window * speed, temporary, f"{name}-origen")
            reference = stretched(original, speed, len(produced))
            difference, lag, value = align(produced, reference)
            modulation = spread(reference)
            rows.append({"punto": name, "bloques": len(produced),
                         "diferencia_db": round(difference, 2),
                         "desfase_ms": lag * round(LEVEL_BLOCK * 1000),
                         "correlacion": None if modulation < ENVELOPE_SPREAD else round(value, 3),
                         "modulacion_db": round(modulation, 1)})
    return rows
```

- [ ] **Paso 6: Escribe la prueba de integración que falla**

Añade a `test_render.py`:

```python
def spoken(path, length=12):
    """Source with 1 s of tone and 0.5 s of silence in turns: an envelope with real modulation."""
    common.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=320x180:r=25:d={length}",
                  "-f", "lavfi", "-i", "aevalsrc=exprs='0.5*sin(2*PI*440*t)*"
                                       r"lt(mod(t\,1.5)\,1.0)':sample_rate=48000:"
                                       f"duration={length}",
                  "-vf", "geq=lum='N':cb=128:cr=128,format=yuv420p",
                  "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast", "-bf", "0",
                  "-c:a", "pcm_s16le", path)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class SoundPlacementTest(unittest.TestCase):
    def built(self, root):
        source = root / "voz.mkv"
        spoken(source)
        spans = [[0.0, 1.08], [1.42, 2.58], [2.92, 4.08]]
        plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                           segments=[sample_segment(id=1, numero=1, title="A", start=0.0, end=4.08,
                                                    spans=spans, frames=68, samples=130560)])
        plan["audio_stream"] = 1
        data = common.probe(source)
        cortes = root / "cortes"
        cortes.mkdir()
        cuts = render.build(data, plan, cortes, render.ffmpeg_release(), 1, None)
        staged = cortes / "resumen.mp4"
        render.assemble(cortes, cuts, staged, 1)
        return data, staged, [(a, b) for a, b in spans]

    def test_a_well_placed_cut_matches_its_source(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            data, staged, spans = self.built(root)
            rows = render.sound_placement(data, staged, spans, 0.0, 68 / 25, 1.25, root)
            self.assertEqual([row["punto"] for row in rows], ["inicio", "fin"])
            # Measured here: 0.81 dB at the start and 3.08 dB at the end, both inside the gate.
            for row in rows:
                with self.subTest(row=row):
                    self.assertLessEqual(row["diferencia_db"], render.ENVELOPE_MARK, row)
                    self.assertLessEqual(abs(row["desfase_ms"]), render.ENVELOPE_LAG * 10, row)
                    self.assertGreater(row["bloques"], 80, row)

    def test_a_cut_claimed_from_the_wrong_place_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            data, staged, _ = self.built(root)
            moved = [(0.75, 1.83), (2.17, 3.33), (3.67, 4.83)]
            rows = render.sound_placement(data, staged, moved, 0.0, 68 / 25, 1.25, root)
            self.assertTrue(any(row["diferencia_db"] > render.ENVELOPE_MARK for row in rows), rows)
```

- [ ] **Paso 7: Ejecuta las pruebas de integración y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k SoundPlacement`
Esperado: `Ran 2 tests … OK` (unos 25 s). Medido en esta máquina: 0,81 dB y 3,08 dB en el caso
correcto, frente a 54,22 dB con la ventana desplazada 0,75 s.

- [ ] **Paso 8: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): valida por envolvente la colocación de cada corte, con guarda de modulación" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 10: Hojas de uniones, informe, publicación de `vN/` y línea de órdenes

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: todo lo anterior; de `common.py` → `lock(path)` (gestor de contexto, error 1 si está
  tomado), `history(work, event, payload)` —que recorta los textos largos de forma recursiva y nunca
  aborta un montaje ya hecho—, `new_dir(path) -> Path`, `publish(staged, final)`,
  `save(path, data)`, `stamp(value) -> str`, `positive(value) -> int`. El `DEFAULT_THREADS` de
  `video.py` no se importa: `render.py` define el suyo con la misma fórmula.
- Produces: `render.JOIN_SHEET = (5, 2)`, `render.JOIN_WIDTH = 160`, `render.JOIN_GAP = 4`,
  `render.DEFAULT_THREADS: int`;
  `render.sheets(final, joins, folder, cadence) -> list[str]`;
  `render.validate(data, plan, parts, final, folder, threads) -> dict` con claves
  `fotogramas_esperados`, `fotogramas`, `video_s`, `audio_s`, `desfase_s`, `colocacion`, `marcas` y
  `uniones`; `render.report(plan, checks, avisos, cadence) -> str`;
  `render.montage(args) -> int`; `render.render(args) -> int`; `render.register(sub) -> None`.
- **Eventos de `historial.jsonl`** que escribe este plan, de los siete del contrato
  (`init, edit, accept, render, verify, doc, deliver`): `accept` con la frase literal aceptada,
  `render` con los cortes montados y `verify` con el resultado de la validación. Cada carga es plana
  —nada de diccionarios anidados—, así que el recorte de `common.history` la deja legible.

- [ ] **Paso 1: Escribe la prueba de las hojas que falla**

Añade a `test_render.py`:

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class SheetTest(unittest.TestCase):
    def test_every_join_gets_one_contact_sheet(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, _, _, staged = assembled(root)
            uniones = root / "uniones"
            uniones.mkdir()
            names = render.sheets(staged, [40], uniones, 25.0)
            self.assertEqual(names, ["union-01.jpg"])
            sheet = common.probe(uniones / "union-01.jpg")
            picture = common.video_stream(sheet)
            columns = render.JOIN_SHEET[0]
            self.assertEqual(picture["width"],
                             2 * render.JOIN_GAP + columns * render.JOIN_WIDTH
                             + (columns - 1) * render.JOIN_GAP)
            self.assertGreater((uniones / "union-01.jpg").stat().st_size, 1000)

    def test_a_join_at_the_very_start_is_clamped(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, _, _, staged = assembled(root)
            uniones = root / "uniones"
            uniones.mkdir()
            self.assertEqual(render.sheets(staged, [2], uniones, 25.0), ["union-01.jpg"])
            self.assertTrue((uniones / "union-01.jpg").is_file())
```

- [ ] **Paso 2: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k SheetTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'sheets'`.

- [ ] **Paso 3: Escribe `sheets`**

En `render.py`, añade:

```python
JOIN_SHEET = (5, 2)
JOIN_WIDTH = 160
JOIN_GAP = 4


def sheets(final, joins, folder, cadence):
    """One contact sheet per join, half before and half after, for the agent's visual review."""
    columns, rows = JOIN_SHEET
    tiles = columns * rows
    total = counted_frames(final)
    names = []
    for number, join in enumerate(joins, start=1):
        first = max(0, min(total - tiles, join - tiles // 2))
        name = f"union-{number:02d}.jpg"
        # Accurate input seeking: without it every join would decode the montage from the start.
        # The tpad clone fills the grid when the montage is shorter than one sheet.
        ffmpeg("-ss", seconds(first / cadence), "-i", final, "-map", "0:v:0",
               "-vf", f"trim=end_frame={tiles},setpts=N/({cadence:.6f})/TB,"
                      f"tpad=stop=-1:stop_mode=clone,trim=end_frame={tiles},"
                      f"setpts=N/({cadence:.6f})/TB,scale={JOIN_WIDTH}:-2,"
                      f"tile={columns}x{rows}:margin={JOIN_GAP}:padding={JOIN_GAP}:color=gray",
               "-frames:v", "1", "-q:v", "2", folder / name)
        names.append(name)
    return names
```

- [ ] **Paso 4: Ejecuta la prueba y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k SheetTest`
Esperado: `Ran 2 tests … OK` (unos 25 s).

- [ ] **Paso 5: Escribe `validate` y `report`**

En `render.py`, añade:

```python
def validate(data, plan, parts, final, folder, threads):
    """Every blocking check of §8; returns the content of validacion.json."""
    decode_check(final, threads)
    checks = totals_check(final, parts, threads)
    cadence, speed = cadence_of(plan), float(plan["settings"]["speed"])
    placements, joins, elapsed = [], [], 0.0
    for segment in plan["segments"]:
        spans = [(float(start), float(end)) for start, end in segment["spans"]]
        length = segment["frames"] / cadence
        images = image_placement(data, final, spans, elapsed, elapsed + length, folder)
        sounds = sound_placement(data, final, spans, elapsed, elapsed + length, speed, folder)
        placements.append({"corte": segment["id"], "titulo": segment["title"],
                           "salida_s": [round(elapsed, 3), round(elapsed + length, 3)],
                           "imagen": images, "envolvente": sounds})
        elapsed += length
        joins.append(round(elapsed * cadence))
    checks["colocacion"] = placements
    failures, marks = [], []
    for entry in placements:
        for row in entry["imagen"]:
            if row["distancia"] > IMAGE_MARK:
                failures.append(f"corte {entry['corte']} ({row['punto']}): imagen a "
                                f"{row['distancia']:.4f} del original")
            elif row["distancia"] > IMAGE_OK:
                marks.append(f"corte {entry['corte']} ({row['punto']}): imagen a "
                             f"{row['distancia']:.4f}, revísala en la hoja de uniones")
        for row in entry["envolvente"]:
            if ENVELOPE_OK < row["diferencia_db"] <= ENVELOPE_MARK:
                marks.append(f"corte {entry['corte']} ({row['punto']}): envolvente a "
                             f"{row['diferencia_db']:.2f} dB, escúchala")
            if row["diferencia_db"] > ENVELOPE_MARK:
                failures.append(f"corte {entry['corte']} ({row['punto']}): envolvente a "
                                f"{row['diferencia_db']:.2f} dB del original")
            if abs(row["desfase_ms"]) > ENVELOPE_LAG * round(LEVEL_BLOCK * 1000):
                failures.append(f"corte {entry['corte']} ({row['punto']}): desfase de "
                                f"{row['desfase_ms']} ms")
            if row["correlacion"] is not None and row["correlacion"] < ENVELOPE_CORRELATION:
                failures.append(f"corte {entry['corte']} ({row['punto']}): correlación "
                                f"{row['correlacion']:.3f}")
    if failures:
        raise Invalid("La colocación no coincide con el original: " + "; ".join(failures) + ".")
    checks["marcas"] = marks
    checks["uniones"] = joins[:-1]
    return checks


def report(plan, checks, avisos, cadence):
    """The report that travels with the montage; the agent adds the editorial review."""
    total = checks["fotogramas"] / cadence
    lines = ["# Montaje", "",
             f"Versión: v{plan['version']}. Cortes: {len(plan['segments'])}. "
             f"Velocidad: ×{float(plan['settings']['speed']):g}. Cadencia: {plan['settings']['rate']}.",
             "", f"Duración de salida: {stamp(total)} ({checks['fotogramas']} fotogramas). "
                 f"Desfase vídeo-audio: {checks['desfase_s']:.3f} s.", "",
             "| # | Origen | Salida | Imagen | Envolvente | Tema |",
             "| --- | --- | --- | --- | --- | --- |"]
    for entry, segment in zip(checks["colocacion"], plan["segments"]):
        spans = segment["spans"]
        origin = f"{stamp(float(spans[0][0]))}–{stamp(float(spans[-1][1]))}"
        output = f"{stamp(entry['salida_s'][0])}–{stamp(entry['salida_s'][1])}"
        image = max(row["distancia"] for row in entry["imagen"])
        sound = max(row["diferencia_db"] for row in entry["envolvente"])
        title = str(segment["title"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {entry['corte']} | {origin} | {output} | {image:.4f} | "
                     f"{sound:.2f} dB | {title} |")
    lines += ["", f"Hojas de uniones: `uniones/` ({len(checks['uniones'])}).", ""]
    if checks.get("marcas"):
        lines += ["Marcas de colocación que conviene revisar a mano:", ""]
        lines += [f"- {text}" for text in checks["marcas"]] + [""]
    if avisos:
        lines += ["Avisos del montaje:", ""]
        lines += [f"- {item['codigo']}: {item['mensaje']}" for item in avisos] + [""]
    lines += ["Validación técnica: decodificación completa, fotogramas iguales a la suma del plan, "
              "sincronía y colocación de cada corte contra el original.", "",
              "Revisión editorial pendiente: completar tras revisar uniones, cobertura y documento.",
              ""]
    return "\n".join(lines)
```

Añade `stamp` a la importación de `common`.

- [ ] **Paso 6: Escribe la prueba de extremo a extremo que falla**

Añade a `test_render.py`:

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class CommandTest(unittest.TestCase):
    def work(self, root):
        source = root / "voz.mkv"
        spoken(source)
        trabajo = root / "trabajo"
        trabajo.mkdir()
        plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                           segments=[sample_segment(id=1, numero=1, title="Primera idea",
                                                    start=0.0, end=2.58,
                                                    spans=[[0.0, 1.08], [1.42, 2.58]],
                                                    frames=45, samples=86400),
                                     sample_segment(id=2, numero=2, title="Segunda idea",
                                                    start=4.42, end=5.58, spans=[[4.42, 5.58]],
                                                    frames=23, samples=44160)])
        common.save(trabajo / "seleccion-v1.json", plan)
        return source, trabajo, plan

    def invoke(self, *arguments, ok=True):
        result = subprocess.run([sys.executable, "-B", str(Path(render.__file__).parent / "video.py"),
                                 *map(str, arguments)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_the_montage_publishes_only_after_validation(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, trabajo, _ = self.work(root)
            refused = self.invoke("render", source, "--work", trabajo,
                                  "--plan", trabajo / "seleccion-v1.json", ok=False)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("--accept", refused.stderr)
            self.assertFalse((trabajo / "v1").exists())
            done = self.invoke("render", source, "--work", trabajo,
                               "--plan", trabajo / "seleccion-v1.json",
                               "--accept", "vale, móntalo", "--threads", "1")
            final = trabajo / "v1" / "resumen.mp4"
            self.assertIn(str(final), done.stdout)
            self.assertTrue(final.is_file())
            self.assertEqual(render.counted_frames(final), 68)
            checks = json.loads((trabajo / "v1" / "validacion.json").read_text(encoding="utf-8"))
            self.assertEqual(checks["fotogramas"], checks["fotogramas_esperados"])
            self.assertEqual(checks["uniones"], [45])
            self.assertEqual(len(list((trabajo / "v1" / "uniones").glob("union-*.jpg"))), 1)
            self.assertIn("Primera idea", (trabajo / "v1" / "montaje.md").read_text(encoding="utf-8"))
            published = json.loads((trabajo / "v1" / "seleccion.json").read_text(encoding="utf-8"))
            self.assertEqual(published["version"], 1)
            self.assertEqual(published["aceptacion"]["frase"], "vale, móntalo")
            # The record layout belongs to common.history; only the three events are checked here.
            log = (trabajo / "historial.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log), 3)
            self.assertEqual([json.loads(line)["evento"] for line in log],
                             ["accept", "render", "verify"])
            # The acceptance travels with its literal phrase, flat, in the accept event.
            self.assertEqual(json.loads(log[0])["frase"], "vale, móntalo")
            self.assertTrue(all(len(line.encode("utf-8")) < 4096 for line in log))
            repeated = self.invoke("render", source, "--work", trabajo,
                                   "--plan", trabajo / "seleccion-v1.json",
                                   "--accept", "otra vez", ok=False)
            self.assertEqual(repeated.returncode, 1)
            self.assertIn("ya existe", repeated.stderr)

    def test_an_exhausted_budget_answers_with_code_three(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, trabajo, _ = self.work(root)
            pending = self.invoke("render", source, "--work", trabajo,
                                  "--plan", trabajo / "seleccion-v1.json",
                                  "--accept", "vale", "--budget", "0.000001", ok=False)
            self.assertEqual(pending.returncode, 3)
            self.assertEqual(json.loads(pending.stdout),
                             {"done": 1, "total": 2, "pending": 1,
                              "bloques": ["corte 2 subcorte 1/1"]})
            self.assertFalse((trabajo / "v1").exists())
            self.invoke("render", source, "--work", trabajo,
                        "--plan", trabajo / "seleccion-v1.json", "--accept", "vale", "--threads", "1")
            self.assertTrue((trabajo / "v1" / "resumen.mp4").is_file())

    def test_a_new_version_reuses_the_cuts_already_rendered(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, trabajo, plan = self.work(root)
            self.invoke("render", source, "--work", trabajo, "--plan", trabajo / "seleccion-v1.json",
                        "--accept", "vale, móntalo", "--threads", "1")
            cortes = trabajo / "cortes"
            before = {path.name: path.stat().st_mtime_ns for path in cortes.glob("*.mkv")}
            self.assertEqual(len(before), 2)
            second = dict(plan, version=2, parent=1,
                          segments=[plan["segments"][0],
                                    sample_segment(id=3, numero=2, title="Tercera idea", start=7.42,
                                                   end=8.58, spans=[[7.42, 8.58]], frames=23,
                                                   samples=44160)])
            common.save(trabajo / "seleccion-v2.json", second)
            self.invoke("render", source, "--work", trabajo, "--plan", trabajo / "seleccion-v2.json",
                        "--accept", "vale", "--threads", "1")
            after = {path.name: path.stat().st_mtime_ns for path in cortes.glob("*.mkv")}
            # Only the new cut is rendered: the key of the untouched one does not change.
            self.assertEqual(len(after), 3)
            self.assertEqual({name: after[name] for name in before}, before)
            part = render.subcuts(second["segments"][0], 25.0, 1.25, 48000)[0]
            reused = f"{render.cut_key(second, part, render.ffmpeg_release())}.mkv"
            self.assertIn(reused, before)
            self.assertTrue((trabajo / "v2" / "resumen.mp4").is_file())
            self.assertTrue((trabajo / "v1" / "resumen.mp4").is_file())

    def test_the_lock_stops_a_second_montage(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, trabajo, _ = self.work(root)
            (trabajo / "montaje.lock").write_text("12345\n", encoding="utf-8")
            blocked = self.invoke("render", source, "--work", trabajo,
                                  "--plan", trabajo / "seleccion-v1.json",
                                  "--accept", "vale", ok=False)
            self.assertEqual(blocked.returncode, 1)
            self.assertIn("Otro proceso", blocked.stderr)
            self.assertFalse((trabajo / "v1").exists())
            # The acceptance is recorded inside the lock: a blocked call writes no history.
            self.assertFalse((trabajo / "historial.jsonl").exists())
            (trabajo / "montaje.lock").unlink()
            self.invoke("render", source, "--work", trabajo, "--plan", trabajo / "seleccion-v1.json",
                        "--accept", "vale", "--threads", "1")
            self.assertTrue((trabajo / "v1" / "resumen.mp4").is_file())
```

- [ ] **Paso 7: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k CommandTest`
Esperado: FALLA con `NotImplementedError` de `register`.

- [ ] **Paso 8: Escribe `montage`, `render` y `register`**

En `render.py`, sustituye los dos `raise NotImplementedError` por:

```python
DEFAULT_THREADS = min(4, os.cpu_count() or 1)


def montage(args):
    """Render, assemble, validate and publish; everything staged and renamed at the end (§11)."""
    work = Path(args.work).resolve(strict=True)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
    if not isinstance(plan, dict) or type(plan.get("version")) is not int:
        raise Refused("El plan debe ser un objeto JSON con version entera.")
    data = probe(args.video)
    avisos = sources_agree(plan, args.video)
    record = accepted(plan, args.accept, args.directo)
    if avisos:
        plan["source"] = {"path": str(Path(args.video).resolve()), **fingerprint(args.video)}
    require_encoders("libx264", "aac")
    release = ffmpeg_release()
    published = work / f"v{plan['version']}"
    if published.exists():
        raise ValueError(f"La versión v{plan['version']} ya existe y no se sobrescribe: {published}")
    cortes = work / "cortes"
    cortes.mkdir(exist_ok=True)
    with lock(work / "montaje.lock"):
        # Flat payloads: the acceptance is three fields, not a nested record (§9 and common.history).
        history(work, "accept", {"version": plan["version"], "frase": record["frase"],
                                 "directo": record["directo"], "sha256": record["sha256"]})
        cuts = build(data, plan, cortes, release, args.threads, args.budget)
        history(work, "render", {"version": plan["version"], "cortes": len(cuts),
                                 "avisos": ", ".join(a["codigo"] for a in avisos)})
        with tempfile.TemporaryDirectory(prefix="montaje-", dir=work,
                                         ignore_cleanup_errors=True) as temporary:
            folder = Path(temporary)
            for cut in cuts:
                (folder / cut.name).write_bytes(cut.read_bytes())
            staged = folder / "resumen.mp4"
            assemble(folder, [folder / cut.name for cut in cuts], staged, args.threads)
            uniones = folder / "uniones"
            uniones.mkdir()
            try:
                checks = validate(data, plan, all_parts(plan, cadence_of(plan)), staged, folder,
                                  args.threads)
            except Invalid:
                kept = new_dir(work / f"fallo-v{plan['version']}-{int(time.time())}")
                staged.replace(kept / "resumen.mp4")
                raise
            checks["uniones_hojas"] = sheets(staged, checks["uniones"], uniones, cadence_of(plan))
            save(folder / "validacion.json", checks)
            save(folder / "seleccion.json", dict(plan, aceptacion=record))
            (folder / "montaje.md").write_text(report(plan, checks, avisos, cadence_of(plan)),
                                               encoding="utf-8")
            target = new_dir(published)
            publish(uniones, target / "uniones")
            for name in ("resumen.mp4", "seleccion.json", "validacion.json", "montaje.md"):
                publish(folder / name, target / name)
        history(work, "verify", {"version": plan["version"], "fotogramas": checks["fotogramas"],
                                 "desfase_s": checks["desfase_s"]})
    for aviso in avisos:
        print(f"Aviso: {aviso['mensaje']}", file=sys.stderr)
    print(published / "resumen.mp4")
    return 0


def render(args):
    """Entry point of the subcommand: maps every failure onto the exit codes of §12."""
    try:
        return montage(args)
    except Pending as exc:
        print(json.dumps(exc.state, ensure_ascii=False))
        print("Error: presupuesto agotado; repite la misma orden para continuar.", file=sys.stderr)
        return 3
    except Invalid as exc:
        print(f"Error: {exc}\nNo se ha publicado nada; la evidencia queda en la carpeta fallo-*.",
              file=sys.stderr)
        return 4
    except Refused as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def register(sub):
    """Subcommand registration shared by the four modules: one subparser and its `run`."""
    parser = sub.add_parser("render", help="Monta vN/ desde un plan aceptado, con caché y validación.")
    parser.set_defaults(run=render)
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
```

Añade `os` a las importaciones y `history`, `lock`, `new_dir`, `probe` y `stamp` a las de `common`. La
cabecera de importaciones queda así:

```python
import array
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import wave

from common import (BLOCKING, MAX_SPANS, MEMORY_PATTERNS, energy, ffmpeg, fingerprint, frames_for,
                    history, listing, lock, new_dir, output_interval, plan_sha256, positive, probe,
                    publish, require_encoders, run, samples_for, save, seconds, seek_margin, stamp,
                    stream_duration, streams, timeline_start, video_stream, warning)
```

El `import argparse` que la Tarea 1 dejó en la cabecera ya no hace falta: `positive` viene de
`common` y el subparser lo crea `register`. Bórralo.

- [ ] **Paso 9: Ejecuta la prueba de extremo a extremo y comprueba que pasa**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k CommandTest`
Esperado: `Ran 4 tests … OK` (unos 150 s: cuatro montajes completos).

- [ ] **Paso 10: Ejecuta toda la batería**

Ejecuta:

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
python -B -m unittest discover -s tests
```

Esperado: `Ran 47 tests … OK` en la primera (4 + 6 + 8 + 4 + 5 + 1 + 4 + 4 + 5 + 6 por tareas) y `OK`
en la segunda, con las pruebas que el Plan 1 haya dejado en `test_video.py` más las de `common` y las
de los demás módulos que ya existan. En `tests/` (23 pruebas) puede fallar
`test_versions_agree_everywhere` mientras `video.py` siga declarando `__version__ = "0.1.0"`: ese
literal lo actualiza el plan de empaquetado, no este. Ninguna otra prueba de `tests/` debe romperse; si
alguna lo hace, es una regresión de esta tarea. Comprueba también que `test_render.py` no contiene
ninguna ruta absoluta —`tests/test_packaging.py` las prohíbe en todo `plugins/`— y que no ha aparecido
ningún `__pycache__`.

- [ ] **Paso 11: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): hojas de uniones, informe y publicación atómica de vN/ tras validar" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Tarea 11: Coste de montaje con `render --dry-run`

§9 pide que tras cada edición se muestre «el coste de montaje ("reutiliza 36 de 38 · 2 cortes nuevos ·
≈2 min")». Ese dato no lo puede dar `plan.py`, que no conoce ni la caché ni la versión de FFmpeg con la
que se montó: lo calcula `render --dry-run`, que no monta nada, y lo cita la propuesta (Plan 1).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/render.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_render.py`

**Interfaces:**
- Consumes: `render.all_parts`, `render.cadence_of`, `render.cut_key`, `render.ffmpeg_release`; de
  `common.py` → `save`. Modifica `render.cached_part` (Tarea 4), `render.build` (Tarea 5), y
  `render.montage` y `render.register` (Tarea 10).
- Produces: `render.COST_GUESS = 0.5` y `render.ASSEMBLY_SHARE = 0.25` (ambos provisionales, declarados
  al final de este plan); `render.cut_note(part, release, seconds=None) -> dict`, la nota que acompaña
  a cada corte cacheado, ahora con el tiempo que costó; `render.cut_cost(cortes) -> float | None`
  (segundos de montaje por fotograma medidos sobre esas notas); `render.estimate(plan, cortes, release)
  -> dict` con **exactamente** las claves `reused`, `new` y `eta_s`; la opción `--dry-run` del
  subparser y la salida temprana de `montage`, **antes de exigir la aceptación**: la propuesta necesita
  el coste justo cuando el usuario todavía no ha aceptado nada.
- `reused` y `new` cuentan **pasadas** (los subcortes que monta `build`), que coinciden con los cortes
  salvo en los que pasan de 40 tramos.

- [ ] **Paso 1: Escribe la prueba rápida que falla**

Añade a `test_render.py`, antes de `if __name__`:

```python
class CostTest(unittest.TestCase):
    def test_the_cost_per_frame_comes_from_the_notes_the_cache_already_has(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary)
            self.assertIsNone(render.cut_cost(cortes))
            common.save(cortes / "uno.json", {"frames": 40, "samples": 76800, "segundos": 8.0})
            common.save(cortes / "dos.json", {"frames": 60, "samples": 115200, "segundos": 12.0})
            self.assertAlmostEqual(render.cut_cost(cortes), 0.2)
            # A note from an older cache, without its seconds, neither counts nor breaks the mean.
            common.save(cortes / "tres.json", {"frames": 25, "samples": 48000})
            self.assertAlmostEqual(render.cut_cost(cortes), 0.2)

    def test_the_estimate_separates_the_cached_passes_from_the_new_ones(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary) / "cortes"
            cortes.mkdir()
            plan = sample_plan(segments=[sample_segment(id=1, numero=1, title="A",
                                                        spans=[[1.0, 3.0]], frames=40,
                                                        samples=76800),
                                         sample_segment(id=2, numero=2, title="B", start=5.0,
                                                        end=7.0, spans=[[5.0, 7.0]], frames=40,
                                                        samples=76800)])
            part = render.subcuts(plan["segments"][0], 25.0, 1.25, 48000)[0]
            key = render.cut_key(plan, part, "8.0.1")
            (cortes / f"{key}.mkv").write_bytes(b"")
            common.save(cortes / f"{key}.json", {"frames": 40, "samples": 76800, "segundos": 10.0})
            report = render.estimate(plan, cortes, "8.0.1")
            self.assertEqual(sorted(report), ["eta_s", "new", "reused"])
            self.assertEqual((report["reused"], report["new"]), (1, 1))
            # 40 new frames at the measured 0.25 s each, plus the assembly over the whole montage.
            self.assertAlmostEqual(report["eta_s"],
                                   round(40 * 0.25 + 80 / 25.0 * render.ASSEMBLY_SHARE, 1))

    def test_without_a_measured_cache_the_provisional_cost_is_used(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary) / "cortes"          # the folder does not even exist yet
            report = render.estimate(sample_plan(), cortes, "8.0.1")
            self.assertEqual((report["reused"], report["new"]), (0, 1))
            self.assertAlmostEqual(report["eta_s"],
                                   round(40 / 25.0 * (render.COST_GUESS + render.ASSEMBLY_SHARE), 1))
```

- [ ] **Paso 2: Ejecuta las pruebas y comprueba que fallan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k CostTest`
Esperado: FALLA con `AttributeError: module 'render' has no attribute 'cut_cost'`.

- [ ] **Paso 3: Escribe la implementación mínima y anota el tiempo en la caché**

En `render.py`, añade:

```python
# Provisional, hasta que la caché de la máquina lo mida: segundos de montaje por segundo de salida.
COST_GUESS = 0.5
# El ensamblado y la validación recorren el montaje entero, también los cortes reutilizados.
ASSEMBLY_SHARE = 0.25


def cut_note(part, release, seconds=None):
    """What travels beside a cached cut: its numbers and, when known, what it cost to render."""
    note = {"cut": part["cut"], "index": part["index"], "total": part["total"],
            "spans": [[round(start, 3), round(end, 3)] for start, end in part["spans"]],
            "frames": part["frames"], "samples": part["samples"], "ffmpeg": release}
    if seconds is not None:
        note["segundos"] = round(float(seconds), 3)
    return note


def cut_cost(cortes):
    """Seconds of montage per output frame, measured over the notes already in the cache."""
    spent, frames = 0.0, 0
    for note in sorted(Path(cortes).glob("*.json")):
        try:
            kept = json.loads(note.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(kept.get("segundos"), (int, float)) and kept.get("frames"):
            spent, frames = spent + float(kept["segundos"]), frames + int(kept["frames"])
    return spent / frames if frames and spent > 0 else None


def estimate(plan, cortes, release):
    """What `render --dry-run` answers: cached passes, new ones and the seconds they will cost."""
    cadence = cadence_of(plan)
    parts = all_parts(plan, cadence)
    per_frame = cut_cost(cortes) or COST_GUESS / cadence
    fresh = []
    for part in parts:
        target = Path(cortes) / f"{cut_key(plan, part, release)}.mkv"
        if not (target.is_file() and target.with_suffix(".json").is_file()):
            fresh.append(part)
    total = sum(part["frames"] for part in parts)
    seconds = sum(part["frames"] for part in fresh) * per_frame + total / cadence * ASSEMBLY_SHARE
    return {"reused": len(parts) - len(fresh), "new": len(fresh), "eta_s": round(seconds, 1)}
```

Y sustituye por `cut_note` las dos notas que se escribían a mano, cronometrando lo que tarda cada
pasada. En `cached_part` (Tarea 4), las líneas `render_part(...)` y `save(note, {...})` —las de justo
antes del barrido de `*.parcial`— pasan a ser:

```python
    started = time.monotonic()
    render_part(data, plan, part, target, threads)
    save(note, cut_note(part, release, time.monotonic() - started))
```

y en el reintento por memoria de `build` (Tarea 5), las líneas `render_part(...)` y
`save(target.with_suffix(".json"), {...})`:

```python
            again = time.monotonic()
            render_part(data, plan, part, target, 1)
            save(target.with_suffix(".json"), cut_note(part, release, time.monotonic() - again))
```

La clave de caché no cambia: `segundos` es metadato de la nota, no ingrediente de `cut_key`, y
`cached_part` sigue validando la entrada solo por `frames` y `samples`, así que las notas ya escritas
por una versión anterior siguen valiendo.

- [ ] **Paso 4: Ejecuta las pruebas rápidas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k CostTest`
Esperado: `Ran 3 tests … OK`.

- [ ] **Paso 5: Escribe la prueba de la orden que falla**

Añade a `test_render.py`, dentro de `CommandTest` (Tarea 10):

```python
    def test_a_dry_run_estimates_the_cost_without_touching_anything(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source, trabajo, _ = self.work(root)
            # No acceptance is asked for: the proposal needs the cost before the user answers.
            first = json.loads(self.invoke("render", source, "--work", trabajo,
                                           "--plan", trabajo / "seleccion-v1.json",
                                           "--dry-run").stdout)
            self.assertEqual((first["reused"], first["new"]), (0, 2))
            self.assertGreater(first["eta_s"], 0)
            self.assertFalse((trabajo / "cortes").exists())
            self.assertFalse((trabajo / "v1").exists())
            self.assertFalse((trabajo / "historial.jsonl").exists())
            self.invoke("render", source, "--work", trabajo, "--plan", trabajo / "seleccion-v1.json",
                        "--accept", "vale, móntalo", "--threads", "1")
            after = json.loads(self.invoke("render", source, "--work", trabajo,
                                           "--plan", trabajo / "seleccion-v1.json",
                                           "--dry-run").stdout)
            # Everything is cached now: a montage of the same plan would only assemble and validate.
            self.assertEqual((after["reused"], after["new"]), (2, 0))
            self.assertLess(after["eta_s"], first["eta_s"])
            # The estimate is now measured, not guessed: the notes carry the seconds they cost.
            notas = [json.loads(path.read_text(encoding="utf-8"))
                     for path in (trabajo / "cortes").glob("*.json")]
            self.assertTrue(all(nota["segundos"] > 0 for nota in notas), notas)
```

- [ ] **Paso 6: Ejecuta la prueba y comprueba que falla**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k test_a_dry_run`
Esperado: FALLA en la comprobación de `invoke`, porque argparse termina con código 2 y
`unrecognized arguments: --dry-run` por la salida de errores.

- [ ] **Paso 7: Engancha `--dry-run` en `montage` y en `register`**

En `montage`, entre `avisos = sources_agree(plan, args.video)` y `record = accepted(...)`, inserta:

```python
    if args.dry_run:
        # Nothing is written, nothing is locked and no acceptance is required: this is what the
        # proposal of §9 quotes as the montage cost before the user has answered.
        print(json.dumps(estimate(plan, work / "cortes", ffmpeg_release()), ensure_ascii=False))
        return 0
```

y en `register`, junto a las demás opciones:

```python
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo estima: cortes reutilizados, nuevos y segundos; no monta nada.")
```

La única salida por la salida estándar de un `--dry-run` es esa línea JSON, para que la propuesta la
lea sin recortar nada. Los avisos siguen yendo por la salida de errores y el código de salida es 0; si
el plan no cuadra con sus tramos, `all_parts` levanta `Refused` y la orden termina con 2 sin montar.
No hay choque con el `plan --dry-run` de §7.1: son opciones de subcomandos distintos y responden a
cosas distintas —aquel, la retención y el presupuesto de fuente; este, lo que cuesta montar—.

- [ ] **Paso 8: Ejecuta las pruebas y comprueba que pasan**

Ejecuta: `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py" -k CommandTest`
Esperado: `Ran 5 tests … OK` (unos 190 s: la quinta añade un montaje completo y dos estimaciones).

- [ ] **Paso 9: Ejecuta toda la batería**

Ejecuta:

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_render.py"
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
python -B -m unittest discover -s tests
```

Esperado: `Ran 51 tests … OK` en la primera (4 + 6 + 8 + 4 + 5 + 1 + 4 + 4 + 5 + 6 + 4 por tareas) y
`OK` en la segunda. En `tests/` sigue valiendo lo dicho en la Tarea 10: solo puede fallar
`test_versions_agree_everywhere`.

- [ ] **Paso 10: Confirma los cambios**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/render.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_render.py
git commit -m "feat(render): --dry-run estima el coste de montaje con lo que ya hay en la caché" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Autorrevisión frente a la especificación

| Requisito | Dónde queda cubierto |
| --- | --- |
| §8 una pasada por corte con la cadena de filtros verificada | Tareas 3 y 4 |
| §8 lectura sin `-t` ni `-to`, que con `-copyts` dan cero fotogramas | Tareas 3 (guarda `trim=end=`) y 4 (`render_part` solo con `-ss`) |
| §8 máximo 40 tramos y subcortes con `N` y `M` repartidos | Tarea 2 (`common.MAX_SPANS`, `subcuts`) |
| §8 `N ≥ 1` y `M ≥ 1` antes de invocar FFmpeg | Tarea 2, comprobado porque FFmpeg acepta `end_frame=0` |
| §8 MKV intermedio con H.264 CRF 18 y PCM de 24 bits no leído desde Python | Tarea 4 (`ENCODER`, `counted_samples` decodifica a 16 bits) |
| §8 ensamblado con concat y AAC una sola vez (D-006) | Tarea 6 |
| §8 validación: decodificación, Σ N, desfase ≤ 0,1 s | Tarea 7 |
| §8 colocación por imagen con 0,08 y 0,15 | Tarea 8 |
| §8 colocación por envolvente desde `pcm_s16le` | Tarea 9 |
| §8 hojas de uniones | Tarea 10 |
| §9 `--accept` o `--directo`, avisos bloqueantes con código 2 | Tarea 1 |
| §9 aceptación registrada en `vN/seleccion.json` y en el evento `accept` de `historial.jsonl` con la frase y el sha256 | Tareas 1 y 10 |
| §9 coste de montaje de la propuesta («reutiliza 36 de 38 · 2 cortes nuevos · ≈2 min») | Tarea 11 (`render --dry-run` → `{reused, new, eta_s}`) |
| §6 caché por clave de huella y reasignación de `source` | Tareas 1 y 2 |
| §6 `vN/` inmutable, JSON en exclusiva, publicación por renombrado | Tarea 10 |
| §6 versión nueva que reutiliza los cortes ya montados | Tarea 10 (`CommandTest`) |
| §11 presupuesto reanudable y reintento único ante memoria | Tarea 5 |
| §11 cerrojo exclusivo y FFmpeg con `-n` | Tarea 10 (`CommandTest`) y `common.ffmpeg` |
| §12 códigos 0, 1, 2, 3, 4 y 130; `pending` entero y detalle en `bloques` | Tareas 5 y 10 (`render`) y `video.main()` |
| §13 corte hasta el último fotograma del medio, fuente desfasada, versión que reutiliza cortes y cerrojo | Tareas 3, 4 y 10 |

**Fuera de alcance, declarado:** `compare` y `vN/cobertura.json` (§8, validación informativa) los
produce `doc.py`, igual que `vN/resumen.md`, `vN/resumen.docx`, `vN/revisiones.json`, `timeline.*` y
las revisiones `resumen-rM.*`. Este plan escribe únicamente `vN/montaje.md`, el informe técnico del
montaje, para no disputarle a `doc.py` el nombre que le asigna §6.

## Desviaciones y umbrales declarados

**Tres** puntos en los que el montaje se aparta de la letra de la especificación aprobada y tres
umbrales que la propia especificación marca como provisionales. El **Plan 4** los registra: las
**tres** desviaciones en `docs/arquitectura.md` y en la decisión **D-009** —la guarda de lectura es la
**tercera**—, y los tres umbrales de §15 en `docs/requisitos.md`.

| Desviación | Qué dice la especificación | Qué hace este plan y por qué |
| --- | --- | --- |
| Punto de búsqueda | `-ss (inicio − 1)` en la redacción anterior de §8 | `S = max(0, inicio − seek_margin(data))`, reutilizando el margen de 0.1.0 (3 s, o 10 s en contenedores que solo buscan hacia delante): con un solo segundo, un contenedor sin índice empieza después del corte |
| Intervalos del grafo | `s − S` en la redacción anterior de §3 | Tiempos **absolutos del contenedor** (`base + s`) con `-copyts`, como ya recoge el §3 vigente. Ambas formas son equivalentes y no se pueden mezclar; medido sobre un medio desfasado 7 s (Tarea 3) |
| **Guarda de lectura (tercera desviación)** | La cadena de filtros aprobada no llevaba ningún `trim` de tiempo; el §8 vigente ya la incorpora («`fps=F` → `trim=end=<base + fin + 1/F>`») tras esta medición | Se añade `trim=end=<base + fin + 1/F>` justo detrás del `fps` inicial. Sin ella FFmpeg decodifica hasta el final del archivo en cada corte (medido: 1 000 de 1 000 fotogramas; 153 con la guarda, misma salida exacta), porque `select` descarta en vez de cerrar la cadena y `trim=end_frame=N` nunca recibe el fotograma que la cerraría. `-t` y `-to` no sirven: junto a `-copyts` dejan la cadena en cero fotogramas. Prueba viva: `PartTest.test_the_reading_stops_at_the_end_of_the_cut` (Tarea 4) |

| Umbral provisional | Valor | Dónde vive |
| --- | --- | --- |
| Desfase máximo de la envolvente | **40 ms** (`ENVELOPE_LAG = 4` bloques de 10 ms), dentro de los 45 ms que cita §8 | Tarea 9 |
| Guarda de modulación para exigir correlación | **6 dB** (`ENVELOPE_SPREAD`) | Tarea 9 |
| Bloqueo por diferencia media de envolvente | **8 dB** (`ENVELOPE_MARK`) | Tareas 9 y 10 |

`COST_GUESS = 0.5` y `ASSEMBLY_SHARE = 0.25` (Tarea 11) **no** son umbrales de validación y no van a
`docs/requisitos.md`: son el arranque de la estimación de `--dry-run` —segundos de montaje por segundo
de salida— mientras la caché de la máquina no trae notas con `segundos`. Nada se bloquea ni se rechaza
con ellos; en cuanto hay un corte montado, la estimación pasa a ser medida.

## Suposiciones que este plan ha tenido que hacer

1. **`common.py` existe antes que `render.py`.** Todo el plan consume las firmas del contrato sin
   redefinirlas. Si `common.py` aún no está, las Tareas 1–11 no arrancan.
2. **Convención de módulos hermanos.** Cada módulo expone `register(sub)`, su subparser fija
   `set_defaults(run=<función>)` y `video.main()` despacha con `return args.run(args) or 0`. Es la
   convención común a los cuatro planes; este plan solo añade `render.register(sub)` a `build_parser`.
3. **Forma de `seleccion-vN.json`.** El esquema del apartado «Contrato» es el único para los cuatro
   planes. `render` lee `version`, `source`, `audio_stream`, `settings.{speed,rate,sample_rate}`,
   `segments[].{id,title,spans,frames,samples,subcuts}` y `warnings`, y rechaza el plan si `frames`,
   `samples` o los `subcuts` publicados no cuadran con los tramos.
4. **Un `.mkv` por corte con dos pasadas más un remux.** El contrato exige llamada de audio aparte y
   el §6 exige `cortes/<clave>.mkv`. Se concilian con una tercera invocación `-c copy`, que no
   recodifica nada y mantiene el invariante de D-006.
5. **Colocación por imagen contra el medio original, no contra `indice.gray`.** El §15 ya ofrece esta
   alternativa («decodificación … del original en los instantes de validación») y el formato del
   índice del barrido no está en el contrato. Comprobado: distancia 0,0000 en el caso correcto y
   0,5720 con contenido ajeno.
6. **Métrica de envolvente.** Medido en esta máquina, la correlación de Pearson es inestable en una
   envolvente plana (una meseta de voz continua correctamente montada baja a 0,668 al recortar los
   bordes). Se conserva el criterio de la especificación —correlación ≥ 0,9— pero la correlación
   **solo se exige cuando la envolvente de referencia tiene al menos 6 dB de desviación típica**, y el
   desfase se estima minimizando la diferencia media en dB, que además bloquea por encima de 8 dB.
   Los tres valores son los umbrales provisionales declarados más arriba.
7. **`cortes/` puede existir.** `new_dir` se reserva para `vN/` y para la carpeta de evidencia
   `fallo-v*`; la caché usa `mkdir(exist_ok=True)`, amparada por la regla de reanudación de §6.
8. **Copia de los cortes a la carpeta de ensamblado.** El *concat demuxer* resuelve los nombres de la
   lista respecto al `cwd`; para no escribir listas con rutas absolutas los cortes se copian a la
   carpeta temporal. En medios largos conviene sustituir la copia por un enlace duro cuando el
   sistema de archivos lo permita; queda anotado, no implementado.
9. **`vN/montaje.md`.** Ya no es una suposición: §6 nombra `vN/montaje.md` junto a `vN/resumen.mp4`,
   `vN/seleccion.json`, `vN/validacion.json` y `vN/cobertura.json`. Este plan lo escribe (Tarea 10) y
   el Plan 3 lo cita como archivo existente sin reescribirlo; `vN/resumen.md` sigue siendo del
   documento, es decir, de `doc.py`.
10. **Coste de montaje estimado, no medido en el momento.** `--dry-run` no monta nada, así que su
    `eta_s` es una extrapolación: la media de segundos por fotograma de las notas ya cacheadas —o
    `COST_GUESS` mientras no haya ninguna— más la parte proporcional del ensamblado. Acierta en el
    orden de magnitud, que es lo que la propuesta necesita («≈2 min»), y no se usa para decidir nada.
11. **Sin medición sobre material real.** Todas las cifras de este plan proceden de medios sintéticos
    de 320×180 y 10–40 s. La aceptación manual del §13 —grabación 4K larga, memoria máxima por corte,
    calibración de umbrales— sigue pendiente y no la cubre ninguna tarea.
