# Núcleo compartido y subcomando `plan` — Plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usa `superpowers:subagent-driven-development`
> (recomendada) o `superpowers:executing-plans` para ejecutar este plan tarea a tarea. Los pasos usan
> casillas (`- [ ]`) para el seguimiento.

**Goal:** dotar a `resumir-video` de `scripts/common.py` (núcleo compartido) y de `scripts/plan.py` con el
subcomando `plan`, de modo que el agente pueda proponer y estimar un resumen —tramos, avisos,
alternativas, sugerencias, propuesta y versión inmutable— sin montar nada todavía.

**Architecture:** `common.py` recoge lo que hoy vive en `video.py` (FFmpeg, identidad, línea temporal,
carpetas, formatos) y añade el cálculo determinista nuevo: objetivo y banda, huella, energía RMS cacheada,
silencios, rejilla de fotogramas, islas sin pausas, ajuste de bordes, `N` y `M` exactos, publicación
atómica, cerrojo, historial, reserva de versión, sha256 canónico, reloj de lectura, tope de tramos y
avisos. `plan.py` consume ese núcleo: valida el borrador del agente, ajusta bordes en orden cronológico,
fusiona contiguos, construye tramos, calcula la estimación exacta y los seis estados, emite los avisos,
propone alternativas y sugerencias, escribe `seleccion-vN.json` y `propuesta-vN.md`, y registra el
historial. `video.py` pierde `render`, `verify` y `validate_plan`, pasa a despachar por `args.run` y solo
registra el subcomando nuevo. El montaje (`render.py`), el esquema de audio y el documento (`doc.py`) son
otros planes y aquí no se tocan.

**Tech Stack:** Python 3.10–3.13, únicamente biblioteca estándar (`argparse`, `array`, `contextlib`,
`datetime`, `hashlib`, `json`, `math`, `os`, `pathlib`, `re`, `shutil`, `subprocess`, `sys`, `unicodedata`,
`wave`). FFmpeg 8.0.1 solo a través de listas de argumentos, nunca por shell. Pruebas con `unittest`.

**Spec:** `docs/especificaciones/2026-09-18-resumir-video-0.2.0.md` (fuente de verdad). Este plan cubre
§3 (símbolos y convención temporal), §4 (invocación y parámetros), §6 (borrador, plan de vídeo, versiones
e importación) y §7 (compresión) completos. La única parte de §6 que queda fuera es el esquema de las
entradas de solo audio (`plan --kind audio` y `esquema-vN.json`), que se implementa entero en el plan de
audio y documento.

## Global Constraints

- Rutas: la skill vive en `plugins/resumir-video/skills/resumir-video/`; el código en `scripts/common.py`,
  `scripts/video.py`, `scripts/plan.py`; las pruebas de la skill en `scripts/test_*.py` y las del
  repositorio en `tests/`. Los planes del proyecto en `docs/planes/`.
- Registro de subcomandos, común a los cuatro módulos: cada módulo hermano expone `register(sub)`, que
  crea su subparser y termina en `parser.set_defaults(run=<función>)`; `video.build_parser` hace lo mismo
  con los suyos y `video.main` despacha con `return args.run(args) or 0`. Ningún plan vuelve a escribir
  un `if args.command == …`.
- Estilo obligatorio, imitado de `scripts/video.py` 0.1.0: docstring de módulo en inglés, docstrings de
  función en inglés, mensajes de error y ayuda en español con el prefijo `Error: …`, funciones cortas, sin
  dependencias fuera de la biblioteca estándar, FFmpeg invocado con listas de argumentos (nunca shell),
  JSON creado en exclusiva (`open(..., "x")`), carpetas nuevas con `new_dir`, comentarios solo donde el
  porqué no es obvio.
- Nada publicado se sobrescribe: `vN/`, `documento-vN/` y los JSON publicados son inmutables.
- No se escribe nunca dentro de la carpeta de la skill: `video.py` fija `sys.dont_write_bytecode = True`
  antes de importar los módulos hermanos y las órdenes se ejecutan con `python -B`.
- Python admitido 3.10–3.13; no se usa `audioop` (eliminado en 3.13) ni `math.sumprod` (3.12+).
- Constantes del contrato, con estos valores exactos:
  `MEMORY_PATTERNS = ("Cannot allocate memory", "Out of memory", "av_buffer_alloc() failed")`,
  `SILENCE_DB = -50.0`, `MIN_SILENCE = 0.30`, `PAUSE_MARGIN = 0.08`, `MIN_ISLAND = 0.12`,
  `MIN_EDGE_ISLAND = 0.20`, `TOLERANCE_RATIO = 0.05`, `TOLERANCE_FLOOR = 10.0`, `MAX_SPANS = 40`,
  `BLOCKING = ("esenciales_superan_objetivo", "dependencia_excluida", "tema_sin_cubrir", "corte_vacio")`.
- Firmas del contrato, intocables: `parse_target(text, total)`, `tolerance(target)`, `fingerprint(path)`,
  `energy(wav_path, cache_path=None)`, `silences(levels, a, b, threshold=SILENCE_DB, min_silence=MIN_SILENCE)`,
  `snap(t, interval, origin)`,
  `islands(levels, a, b, *, interval, origin, remove_pauses=True, threshold=SILENCE_DB, min_silence=MIN_SILENCE, margin=PAUSE_MARGIN)`,
  `adjust_edges(a, b, levels, words, *, threshold=SILENCE_DB)`, `frames_for(length, rate, speed)`,
  `samples_for(n_frames, rate, sample_rate)`, `publish(staged, final)`, `lock(path)`,
  `history(work, event, payload)`, `reserve_version(work, prefix)`, `plan_sha256(plan)`,
  `warning(code, message, *, cut=None)`, `strip_accents(text)`.
- Se conservan sin cambio de firma, trasladadas a `common.py`: `tool`, `run`, `ffmpeg`, `save`, `seconds`,
  `identity`, `probe`, `duration`, `tag_seconds`, `stream_duration`, `stream_end`, `timeline_start`,
  `seek_margin`, `landing`, `rate_of`, `frame_interval`, `output_rate`, `output_interval`, `video_stream`,
  `streams`, `encoders`, `require_encoders`, `cache_dir`, `new_dir`, `frame_count`, `stamp`, `listing`,
  `positive`.
- Códigos de salida (§12): 0 correcto; 1 error controlado (`Error: …`); 2 argumentos inválidos **o plan con
  aviso bloqueante**; 3 pendiente reanudable; 4 validación fallida; 130 interrupción.
- Versión de la skill: este plan **no** toca `__version__` ni los manifiestos (lo hace el plan de
  empaquetado, cuando los cinco módulos existan); `tests/test_packaging.py` seguirá pasando con la
  versión ya publicada mientras tanto.
- Comprobaciones del repositorio (`AGENTS.md`), que deben seguir pasando al final de cada tarea:
  `python -B -m unittest discover -s tests` y
  `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"`.

## Contrato ampliado (lo que el contrato no fijaba y este plan declara)

Todo lo de abajo es **añadido**, nunca sustituye una firma del contrato. Cada tarea que lo introduce lo
repite en su bloque «Interfaces».

| Añadido en `common.py` | Por qué hacía falta |
| --- | --- |
| `ENERGY_STEP = 0.01`, `ENERGY_FLOOR = -120.0`, `ENERGY_BLOCK = 600`, `FULL_SCALE`, `SQUARES`, `squares()`, `levels_of(sound, window)` | `energy` necesita el paso de 10 ms, un suelo en dBFS y un bucle RMS que no cargue el archivo entero |
| `bounds(levels, a, b)` | la conversión de segundos a índices de la rejilla de 10 ms la hacían tres funciones (`silences`, `voiced` y `plan.percentile`) copiando las mismas dos líneas, y el redondeo abría una ventana de más en 140 de los 2000 primeros múltiplos de 0,04 s |
| `voiced(levels, a, b, threshold=SILENCE_DB)` | `adjust_edges` necesita preguntar «¿hay voz en estos 80 ms?» |
| `EDGE_LOOK = 0.08`, `EDGE_WINDOW = 0.60`, `EDGE_SILENCE = 0.10`, `WORD_MARGIN = 0.02` | los cuatro umbrales de §7.3, que el contrato no nombraba |
| `HISTORY_LIMIT = 4096`, `HISTORY_TEXT = 300`, `VERSION_ATTEMPTS = 3`, `CHUNK = 4 MiB` | límites de §6 y §11 |
| `write_reserved(path, text)` | `publish` no sobrescribe por contrato, y `reserve_version` deja el archivo ya creado: llenarlo exige `os.replace` sobre la reserva |
| `shorten(value)` | el historial recorta a cualquier profundidad, no solo en el primer nivel, y nunca aborta un trabajo ya hecho |
| `timeline(data)` | §3 y §5: `plan` necesita `fps`, el origen de la rejilla y `SR`; `prepare` (otro plan) escribirá ese mismo diccionario en `metadata.json`, **siempre**, también en solo audio, donde `rate`, `fps` e `interval` son `null` |
| `clock(value)` | el sello de lectura (`0:24`, `1:02:07`) lo usan la propuesta de `plan.py` y el documento de `doc.py`: hay **una sola** definición y vive aquí |
| `MAX_SPANS = 40` | el tope de tramos por invocación de FFmpeg lo aplican `plan.py` (subcortes) y `render.py` (montaje): una sola constante para los dos |

| Añadido en el borrador (§6) | Por qué hacía falta |
| --- | --- |
| `topics: [{"nombre", "cortes": [id], "imprescindible": bool}]` | sin él, el aviso `tema_sin_cubrir` de §7.7 no es computable: el inventario vive en `analisis.md`, que ningún script lee |
| `visual_evidence` **no** es obligatorio cuando `kind == "audio"` | §5: en audio no hay imagen que aportar. `check_draft` ya lo admite; el esquema que lo aprovecha lo publica el plan de audio y documento |

**Esquema único de `seleccion-vN.json`,** el mismo que dan por bueno el plan de montaje y el de
documento. Las claves de datos van en inglés; solo `alternativas`, `sugerencias`, `excluidos`,
`recorrido`, las claves internas de `estimate`, las de los avisos (`codigo`, `mensaje`, `corte`,
`bloquea`) y, en `settings`, `objetivo`, más `numero` y `salida` en cada tramo, conservan el español ya
contratado: esas tres últimas son justo las que el usuario lee en la propuesta (§9) —el objetivo de la
cabecera y las columnas `#` y `Salida estimada` de la tabla—, y los planes de montaje y de documento ya
las consumen con ese nombre:

```json
{
  "version": 1, "parent": null, "kind": "video", "request": "…",
  "source": {"path": "…", "size": 123, "mtime_ns": 456, "sha256": "…"},
  "audio_stream": 1,
  "timeline": {"start": 0.0, "origin": 0.032, "rate": "25/1", "fps": 25.0,
               "interval": 0.04, "sample_rate": 48000},
  "settings": {"target": "40%", "objetivo": 24.0, "tolerance": 10.0, "speed": 1.25,
               "remove_pauses": true, "silence_db": -50.0, "rate": "25/1", "sample_rate": 48000},
  "segments": [{"id": 1, "numero": 1, "title": "…", "phrase": "…", "reason": "…",
                "audio_evidence": "…", "visual_evidence": "…", "priority": 1, "pinned": false,
                "visual_only": false, "remove_pauses": true, "depends_on": [],
                "start": 2.0, "end": 10.0, "spans": [[2.0, 5.08], [5.92, 10.0]],
                "frames": 143, "samples": 274560, "salida": [0.0, 5.72],
                "subcuts": [{"spans": [[2.0, 5.08], [5.92, 10.0]], "frames": 143,
                             "samples": 274560}]}],
  "reserves": [], "excluidos": [], "estimate": {}, "alternativas": [], "sugerencias": [],
  "warnings": [], "changes": [], "recorrido": "…", "sha256": "…"
}
```

`source` **funde** la identidad de `identity` con la huella de `fingerprint`: no hay clave `fingerprint`
aparte. `settings.rate` y `settings.sample_rate` son los que `render` necesita para reconstruir la
cadencia sin abrir `metadata.json`; `settings.objetivo` son los segundos ya resueltos de
`settings.target` y `settings.tolerance` la semianchura de la banda. `salida` y `depends_on` son
añadidos de este plan sobre el mínimo que `render` exige: el primero lo usa el diff de `changes`, el
segundo el regreso a una versión.

**Avisos que este plan no emite:** `huecos_pts` y `fuente_vfr` (los detecta el sondeo de paquetes de
`prepare`), `origen_reasignado` (lo emite `render`) y `cobertura_baja` (lo emite `compare`). `plan`
propaga los dos primeros si `metadata.json` los trae en la clave `avisos`. `identidad_parcial` solo
aparece en `plan --import`.

**Interfaz que este plan consume y no produce:** `metadata.json` ampliado por `prepare` con `kind`,
`source` con huella, `timeline` y `audio_stream`, y las funciones `common.pictures` y `common.kind`, que
define el plan de audio y documento. Mientras `prepare` no escriba esas claves, `plan` deriva la línea
temporal con `common.timeline`, completa la huella con `common.fingerprint` y trata como `video`
cualquier trabajo cuyo `metadata.json` no declare `kind`, así que no queda bloqueado.

## Medidas de esta máquina (FFmpeg 8.0.1, Python 3.11.9, Windows 11)

- El bucle RMS por tabla de cuadrados tarda **11,9 s por cada 2 h** de audio mono a 16 kHz; construir la
  tabla de 65 536 cuadrados cuesta 26 ms una sola vez. Las alternativas medidas fueron 21,6 s
  (`operator.mul` sobre `memoryview`) y 32,9 s (bucle Python llano).
- Para el corte de prueba `[[2.0, 5.08], [5.92, 10.0]]` a ×1,25 y 25 fps, `frames_for` da `N = 143` y
  `samples_for` da `M = 274560`; las recetas de FFmpeg de la especificación producen exactamente
  `nb_read_frames=143` y `duration_ts=274560`. Los números de `plan.py` son los que `render` obtendrá.
- Las 28 funciones que se trasladan ocupan **235** de las 599 líneas de `video.py` 0.1.0, y `render`,
  `verify` y `validate_plan` otras **135**: `common.py` queda en unas 254 líneas y `video.py` en unas
  240. Las pruebas de la skill **no** sobreviven con un solo cambio:
  `test_missing_encoders_are_reported_before_rendering` pasa a parchear `common.encoders` en vez de
  `video.encoders`, y las ocho que montan o validan un plan se reparten en dos grupos. **Cuatro se
  retiran** porque se quedan sin sujeto y su cobertura es toda del montaje
  (`test_many_joins_keep_audio_in_sync`, `test_short_cuts_are_not_truncated_by_the_concatenation`,
  `test_matroska_track_length_limits_cuts` y `test_plan_rejects_invalid_or_unsubstantiated_cuts`).
  De la tercera hay que rescatar algo antes de borrarla: `test_stream_end_uses_offsets_and_matroska_tags`
  trabaja sobre diccionarios escritos a mano y no abre ningún MKV, así que con ella se iría la única
  comprobación de `stream_end` contra un medio real. La tarea 1 la conserva dentro de una de las cuatro
  que reescribe, que graba un Matroska y compara el final calculado con la etiqueta de longitud de pista.
  **Cuatro se reescriben** aquí mismo, quedándose con la parte que no monta nada, porque arrastraban
  cobertura de `prepare`, `frames` y `probe` que ninguna otra prueba tiene
  (`test_extract_edit_and_protect_source`, `test_unicode_output_and_edge_times`,
  `test_held_frames_of_variable_rate_recordings` y `test_forward_only_containers`). El plan de montaje
  **no vuelve a abrir `test_video.py`**: por el montaje este archivo se toca una sola vez, aquí, en la
  tarea 1. Los planes de audio y documento y de evidencia lo amplían después por otro motivo, cuando
  reescriben `prepare` y `frames`.
  De las **15** pruebas que la skill tiene hoy quedan 11, más la nueva del registro de subcomandos:
  **12**. El recuento cumple §13, que manda conservar las 15 de la skill «ampliadas con las de abajo» y
  reescribir «las que solo ejercitaban el `render` de la 0.1.0 […] para conservar su cobertura de
  `prepare`, `frames` y `probe`»: eso es exactamente lo que hace la tarea 1 con las cuatro que
  reescribe. Las cuatro que retira tampoco pierden nada, porque en la 0.2.0 el montaje deja de vivir en
  `video.py` y se rehace entero en `render.py`: sin `render` ni `validate_plan` en este módulo, esas
  cuatro se quedan sin sujeto en `test_video.py` y su cobertura **se traslada**, no se pierde.
  `test_many_joins_keep_audio_in_sync` (sincronía de vídeo y audio con muchas uniones) y
  `test_short_cuts_are_not_truncated_by_the_concatenation` (cortes breves que la concatenación no debe
  truncar, con la comprobación de que ningún paquete de vídeo dura menos de 1 ms) pasan a
  `test_render.py`, en el plan de montaje. `test_matroska_track_length_limits_cuts` (rechazo del corte
  que se sale del medio) y `test_plan_rejects_invalid_or_unsubstantiated_cuts` (borrador inválido o sin
  justificar) pasan a `plan.check_draft`, en la tarea 10 de este mismo plan y con más casos que
  `validate_plan`; de la primera de esas dos, el `stream_end` contra un MKV real se queda aquí, dentro
  de `test_forward_only_containers` (paso 6), por lo dicho arriba. Por eso la suma de pruebas de la
  skill **crece**: de las 15 de hoy se pasa a **100** al terminar el plan (37 en `test_common.py`, 12 en
  `test_video.py` y 51 en `test_plan.py`). Las **23** de `tests/` no cambian.

---

### Task 1: `common.py` con el núcleo trasladado de 0.1.0 y `video.py` reducido a extracción

**Files:**
- Crear: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/video.py` (cabecera, borrado de
  `render`, `verify` y `validate_plan`, y despacho por `args.run`)
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_video.py` (se retiran cuatro
  pruebas y el ayudante `plan_for`, se reescriben otras cuatro sin `render`, se reapunta el parche de
  `encoders` y se añade la del registro de subcomandos). **Es el único plan que toca este archivo por
  el montaje:** el plan de montaje solo crea `test_render.py` y no abre `test_video.py`.

**Interfaces:**
- Consumes: nada.
- Produces: módulo `common` con `tool`, `run`, `ffmpeg`, `save`, `seconds`, `identity`, `probe`,
  `duration`, `tag_seconds`, `stream_duration`, `stream_end`, `timeline_start`, `seek_margin`, `landing`,
  `rate_of`, `frame_interval`, `output_rate`, `output_interval`, `video_stream`, `streams`, `encoders`,
  `require_encoders`, `cache_dir`, `new_dir`, `frame_count`, `stamp`, `listing`, `positive` y las
  constantes `MIN_PYTHON`, `MAX_FRAMES`, `HDR_TRANSFERS`, `SEEK_MARGIN`, `FORWARD_SEEK`,
  `FORWARD_MARGIN`, `DEFAULT_THREADS`. `video.py` reexporta con el mismo nombre las veintiséis que
  sigue citando —él o sus pruebas—, así que `video.duration(...)` sigue existiendo; el resto se alcanza
  como `common.<nombre>`.
- Produces también: `video.show(args)` (el `probe` de la línea de órdenes) y el despacho
  `args.run(args)`; cada subparser de `video.py` fija su `run` con `set_defaults`. **`show` es el
  nombre definitivo** de esa función: ningún plan posterior la renombra ni la duplica como
  `show_probe`; el plan de evidencia y empaquetado la reencuentra como `video.show` cuando reescribe
  `frames`.
- Deja de producir: `video.render`, `video.verify` y `video.validate_plan`. El montaje se rehace entero
  en `render.py` (otro plan) sobre el plan versionado, y `validate_plan` desaparece con su prueba porque
  `plan.check_draft` lo sustituye con más casos.

- [ ] **Paso 1: crear `common.py` con la cabecera y las constantes**

Crea el archivo con exactamente esta cabecera:

```python
"""Shared core: FFmpeg execution, atomic publishing, identity, timeline, energy and warnings."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 10)
MAX_FRAMES = 600
HDR_TRANSFERS = ("smpte2084", "arib-std-b67")
SEEK_MARGIN = 3.0
# Demuxers without an index seek forward to the next keyframe, so they need a wider margin.
FORWARD_SEEK = ("mpegts", "mpegtsraw", "mpeg", "m2ts", "mts")
FORWARD_MARGIN = 10.0
DEFAULT_THREADS = min(4, os.cpu_count() or 1)
```

- [ ] **Paso 2: mover las 28 funciones, sin tocar una línea de su cuerpo**

Corta de `video.py` y pega en `common.py`, **en este orden y con su docstring y sus comentarios
intactos**: `tool`, `run`, `ffmpeg`, `save`, `seconds`, `identity`, `probe`, `duration`, `tag_seconds`,
`stream_duration`, `stream_end`, `timeline_start`, `seek_margin`, `landing`, `rate_of`, `frame_interval`,
`output_rate`, `output_interval`, `video_stream`, `streams`, `encoders`, `require_encoders`, `cache_dir`,
`new_dir`, `frame_count`, `stamp`, `listing`, `positive`. No cambies ninguna firma ni ningún mensaje. Son
235 de las 599 líneas del archivo. `landing` y `HDR_TRANSFERS` se trasladan aunque `video.py` deje de
usarlos: el plan de montaje conserva la guarda de búsqueda y el rechazo de HDR es del plan de `prepare`.

- [ ] **Paso 3: borrar de `video.py` lo que el montaje rehace**

Borra las funciones `validate_plan`, `verify` y `render` (135 líneas) y el bloque de `render` de
`build_parser`. En `video.py` quedan `check`, `prepare`, `frames`, `transcribe`, `show` (paso 4),
`build_parser` y `main`, y sus constantes propias desaparecen porque ahora se importan. La 0.2.0 monta
desde un plan versionado, con caché de cortes y validación bloqueante, y eso vive entero en `render.py`:
dejar aquí el montaje de 0.1.0 obligaría a mantener dos rutas de salida incompatibles.

- [ ] **Paso 4: reescribir la cabecera y el despacho de `video.py`**

Sustituye todo lo anterior a `def check(args):` por:

```python
"""Local evidence extraction and deterministic editing; editorial choices belong to the calling agent."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys

# Set before the sibling modules load: the skill folder may live in a read-only plugin cache.
sys.dont_write_bytecode = True

import common
from common import (DEFAULT_THREADS, MAX_FRAMES, MIN_PYTHON, cache_dir, duration, encoders, ffmpeg,
                    frame_count, frame_interval, identity, new_dir, output_rate, positive, probe,
                    require_encoders, run, save, seconds, seek_margin, stream_duration, stream_end,
                    streams, tag_seconds, timeline_start, tool, video_stream)

__version__ = "0.1.0"
```

`import common` es la vía general: todo lo que `video.py` ya no usa —`landing`, `rate_of`,
`output_interval`, `stamp`, `listing`, `HDR_TRANSFERS`, `SEEK_MARGIN`, `FORWARD_SEEK` y
`FORWARD_MARGIN`— se alcanza como `common.<nombre>` y sale de la lista reexportada, que queda con los
veintiséis nombres que este archivo o `test_video.py` citan de verdad. `video.duration(...)` y
`video.stream_end(...)` siguen existiendo, que es lo que las pruebas esperan. `subprocess` y `tempfile`
tampoco siguen en la cabecera: el primero solo lo usaban `run` y `landing`, que se van a `common.py`, y
el segundo solo `render`, que se borra en el paso 3.

Añade, justo antes de `build_parser`, la orden que faltaba como función:

```python
def show(args):
    """`probe`: every track and the file identity, as JSON on standard output."""
    print(json.dumps(probe(args.video), ensure_ascii=False, indent=2))
```

En `build_parser`, da a cada subparser su función. `check` pasa de `sub.add_parser("check", …)` suelto a:

```python
    p = sub.add_parser("check", help="Comprueba Python, FFmpeg (libx264, AAC), faster-whisper y espacio libre; imprime JSON.")
    p.set_defaults(run=check)
```

y los demás reciben, como última línea de su bloque, `p.set_defaults(run=show)`,
`p.set_defaults(run=prepare)`, `p.set_defaults(run=frames)` y `p.set_defaults(run=transcribe)`.

Sustituye el cuerpo de `main` posterior a `args = build_parser().parse_args()` por:

```python
    try:
        # check runs before the version guard, so its report can show python_ok: false.
        if args.command != "check" and sys.version_info < MIN_PYTHON:
            raise ValueError("Se requiere Python 3.10 o superior.")
        if args.command in ("probe", "prepare", "frames"):
            for executable in ("ffmpeg", "ffprobe"):
                if not tool(executable):
                    raise ValueError(f"Falta {executable} en PATH (se necesita el ejecutable, "
                                     "no un .cmd/.bat).")
        return args.run(args) or 0
    except MemoryError:
```

El resto de `except` queda igual. `prepare`, `frames`, `transcribe` y `show` devuelven `None`, que el
`or 0` convierte en 0; `check` ya devuelve 0 o 1, y `plan` devolverá 0 o 2.

- [ ] **Paso 5: retirar de `test_video.py` las cuatro pruebas sin sujeto**

Borra enteras `test_many_joins_keep_audio_in_sync`,
`test_short_cuts_are_not_truncated_by_the_concatenation` y `test_matroska_track_length_limits_cuts` de
`VideoTest`, y `test_plan_rejects_invalid_or_unsubstantiated_cuts` de `PlanTest`: las cuatro solo
ejercitan `render` y `validate_plan`, que este paso elimina. Con ellas se va el ayudante `plan_for`,
que ya no llama nadie.

| Prueba retirada | Dónde queda su cobertura |
| --- | --- |
| `test_many_joins_keep_audio_in_sync` | `test_render.py` (plan de montaje): sincronía de vídeo y audio con muchas uniones |
| `test_short_cuts_are_not_truncated_by_the_concatenation` | `test_render.py`, incluida la comprobación de que ningún paquete de vídeo dura menos de 1 ms |
| `test_matroska_track_length_limits_cuts` | `plan.check_draft` (tarea 10) rechaza el corte fuera del medio antes de montar, y su comprobación de `stream_end` contra un MKV real pasa al paso 6, dentro de `test_forward_only_containers` |
| `test_plan_rejects_invalid_or_unsubstantiated_cuts` | `plan.check_draft` (tarea 10), con más casos que `validate_plan` |

Los ayudantes `invoke`, `synthetic`, `gray_signature` y `decoded_audio_seconds` **se quedan**: los usan
las cuatro pruebas del paso 6 y los planes posteriores, que añaden a este mismo archivo pruebas de
`prepare` y de `frames`. Ninguna importación se va: `hashlib`, `io`, `json`, `os`, `shutil`,
`subprocess`, `sys`, `tempfile` y `mock` siguen en uso. Y **se queda también** el decorador
`@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")` de
`VideoTest`, que conserva las cuatro pruebas con medios reales del paso 6 y
`test_check_reports_environment`.

- [ ] **Paso 6: reescribir las otras cuatro para que no monten nada**

Estas cuatro comprobaban `prepare`, `frames`, `probe` y `seek_margin` de camino al montaje, y esa parte
no la recupera ninguna prueba nueva: se quedan, sin el bloque que montaba. Conservan su nombre, que es
el que citan los planes posteriores. La última recoge además el `stream_end` contra un Matroska real que
se iba con `test_matroska_track_length_limits_cuts`, porque
`test_stream_end_uses_offsets_and_matroska_tags` trabaja sobre diccionarios escritos a mano y no abre
ningún medio. Sustituye las cuatro por estas:

```python
    def test_extract_edit_and_protect_source(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "vídeo de prueba ' uno.mp4"
            synthetic(source, 6)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            invoke(self, "prepare", source, "--work", root / "evidencia")
            metadata = json.loads((root / "evidencia/metadata.json").read_text(encoding="utf-8"))
            sound = [s for s in metadata["streams"] if s["codec_type"] == "audio"][0]
            self.assertEqual(metadata["audio_stream"], sound["index"])
            self.assertEqual(metadata["source"]["size"], source.stat().st_size)
            self.assertEqual((root / "evidencia/.gitignore").read_text(encoding="utf-8"), "*\n")
            self.assertAlmostEqual(video.duration(video.probe(root / "evidencia/audio.wav")), 6,
                                   delta=.1)
            self.assertAlmostEqual(decoded_audio_seconds(root / "evidencia/audio.wav"), 6, delta=.1)
            invoke(self, "frames", source, "--out", root / "imagenes", "--step", "2")
            index = json.loads((root / "imagenes/index.json").read_text(encoding="utf-8"))
            self.assertEqual([f["time"] for f in index["frames"]], [0, 2, 4])
            self.assertTrue(all((root / "imagenes" / f["file"]).stat().st_size > 0
                                for f in index["frames"]))
            invoke(self, "frames", source, "--out", root / "imagenes", ok=False)
            # Neither prepare nor frames may touch the original: the skill only reads it.
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)

    def test_unicode_output_and_edge_times(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "vídeo ✓ 東京.mp4"
            synthetic(source, 6)
            result = invoke(self, "prepare", source, "--work", root / "trabajo ✓")
            self.assertIn("trabajo ✓", result.stdout)
            self.assertIn("東京", invoke(self, "probe", source).stdout)
            invoke(self, "frames", source, "--out", root / "final-video",
                   "--start", "5.9", "--end", "5.99", "--step", "0.07")
            index = json.loads((root / "final-video/index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["frames"]), 2)
            self.assertAlmostEqual(index["frames"][-1]["time"], 5.96, delta=1e-6)
            error = invoke(self, "prepare", source, "--work", root / "trabajo ✓", ok=False).stderr
            self.assertIn("ya existe", error)

    def test_held_frames_of_variable_rate_recordings(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "pantalla.mp4"
            # 25 fps until 2 s, then one frame held until 8 s (a static slide), then 25 fps again.
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=10",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10",
                         "-vf", r"select='lt(t\,2)+eq(n\,50)+gte(t\,8)'", "-fps_mode", "vfr",
                         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", source)
            invoke(self, "frames", source, "--out", root / "imagenes", "--start", "2", "--end", "9",
                   "--step", "3", "--width", "0")
            index = json.loads((root / "imagenes/index.json").read_text(encoding="utf-8"))
            held, inside, after = (gray_signature(root / "imagenes" / f["file"])
                                   for f in index["frames"])
            self.assertEqual(held, inside)
            self.assertNotEqual(held, after)
            # prepare must still get the whole soundtrack out of a variable-rate recording.
            invoke(self, "prepare", source, "--work", root / "trabajo")
            self.assertAlmostEqual(video.duration(video.probe(root / "trabajo/audio.wav")), 10,
                                   delta=.1)

    def test_forward_only_containers(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "captura.ts"
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=8",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
                         "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-c:a", "aac",
                         "-f", "mpegts", source)
            data = video.probe(source)
            # FORWARD_MARGIN is no longer re-exported by video.py: it is reached through common.
            self.assertEqual(video.seek_margin(data), common.FORWARD_MARGIN)
            invoke(self, "frames", source, "--out", root / "imagenes", "--start", "1", "--end", "7",
                   "--step", "2", "--width", "0")
            images = sorted((root / "imagenes").glob("*.jpg"))
            self.assertEqual(len(images), 3)
            self.assertEqual(len({gray_signature(image) for image in images}), 3)
            invoke(self, "prepare", source, "--work", root / "trabajo")
            self.assertAlmostEqual(video.duration(video.probe(root / "trabajo/audio.wav")), 8,
                                   delta=.2)
            matroska = root / "corta.mkv"
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=5",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
                         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", matroska)
            tagged = video.probe(matroska)
            # The only check of stream_end against a real Matroska: the track length tag, not a guess.
            self.assertAlmostEqual(video.stream_end(tagged, video.streams(tagged)[0]), 5, delta=.1)
```

Lo que pierden es solo el montaje: el `render` de dos cortes y sus comprobaciones de duración, el
`resumen.md`, la negativa a sobrescribir la carpeta de salida y el rechazo del corte fuera de la
pista. Todo eso lo rehace el plan de montaje sobre el plan versionado.

- [ ] **Paso 7: reapuntar el parche de `encoders` y cubrir el despacho**

Añade la importación junto a la existente:

```python
import common
import video
```

cambia el parche de la prueba de los codificadores:

```python
    def test_missing_encoders_are_reported_before_rendering(self):
        with mock.patch.object(common, "encoders", return_value={"aac"}):
            with self.assertRaisesRegex(ValueError, "libx264"):
                video.require_encoders("libx264", "aac")
```

y añade a `PlanTest` la prueba del registro de subcomandos, que es lo único que cubre el despacho nuevo
mientras `test_render.py` no exista:

```python
    def test_every_subcommand_is_wired_to_its_function(self):
        parser = video.build_parser()
        self.assertIs(parser.parse_args(["check"]).run, video.check)
        self.assertIs(parser.parse_args(["probe", "v.mp4"]).run, video.show)
        self.assertIs(parser.parse_args(["prepare", "v.mp4", "--work", "t"]).run, video.prepare)
        self.assertIs(parser.parse_args(["frames", "v.mp4", "--out", "o"]).run, video.frames)
        self.assertIs(parser.parse_args(["transcribe", "a.wav", "--out", "o.json"]).run,
                      video.transcribe)
```

- [ ] **Paso 8: ejecutar las dos baterías completas**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
python -B -m unittest discover -s tests
```

Esperado: `OK` en ambas (12 y 23 pruebas). Comprueba además que no ha aparecido ningún `__pycache__`
dentro de `plugins/`:

```bash
git status --short plugins/
```

- [ ] **Paso 9: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/video.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_video.py
git commit -m "refactor: extraer el nucleo compartido y dejar video.py en extraccion de evidencia" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: objetivo de compresión y banda de tolerancia

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Crear: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `common` de la tarea 1.
- Produces: `parse_target(text, total) -> float | None` (segundos de salida, redondeados a 3 decimales;
  `None` si no hay objetivo; `ValueError` si es ambiguo o fuera de rango) y
  `tolerance(target) -> float`. Constantes `TOLERANCE_RATIO = 0.05`, `TOLERANCE_FLOOR = 10.0`, la expresión
  `TARGET` y la tabla `UNITS`, que tiene una clave por cada una de las once formas que acepta el grupo
  `unit`: la búsqueda es directa, sin alternativa que recortar.

- [ ] **Paso 1: escribir la prueba que falla**

Crea `scripts/test_common.py` con:

```python
"""Fast checks of the shared core; only the ones that need media touch FFmpeg."""

import array
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
import wave

import common


class ObjetivoTest(unittest.TestCase):
    def test_reads_percentages_durations_and_clocks(self):
        for text, expected in (("10%", 360.0), ("10 %", 360.0), ("10 por ciento", 360.0),
                               ("720s", 720.0), ("720 s", 720.0), ("12min", 720.0),
                               ("12 min", 720.0), ("0:12:00", 720.0), ("12:00", 720.0),
                               ("1,5 min", 90.0), ("0.5h", 1800.0)):
            with self.subTest(text=text):
                self.assertAlmostEqual(common.parse_target(text, 3600), expected)
        for text in (None, "", "   ", "ninguno"):
            self.assertIsNone(common.parse_target(text, 3600))

    def test_rejects_ambiguous_and_out_of_range_targets(self):
        for text in ("12", "mucho", "1:2:3", "0%", "100%", "120%", "2h", "3600s", "0:00:00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                common.parse_target(text, 3600)

    def test_rounding_never_returns_the_whole_recording(self):
        # Section 4 talks about the target the caller receives, not about an unrounded intermediate.
        for text in ("179.9999s", "179.9996s", "2:59.9999"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                common.parse_target(text, 180.0)
        self.assertAlmostEqual(common.parse_target("179.99s", 180.0), 179.99)

    def test_band_never_falls_below_ten_seconds(self):
        self.assertAlmostEqual(common.tolerance(720), 36.0)
        self.assertAlmostEqual(common.tolerance(200), 10.0)
        self.assertAlmostEqual(common.tolerance(100), 10.0)
        self.assertAlmostEqual(common.tolerance(240), 12.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: 4 errores `AttributeError: module 'common' has no attribute 'parse_target'`.

- [ ] **Paso 3: implementación mínima**

Añade a `common.py`, después de `DEFAULT_THREADS`, las constantes:

```python
TOLERANCE_RATIO = 0.05
TOLERANCE_FLOOR = 10.0

TARGET = re.compile(r"^(?:(?P<pct>\d+(?:[.,]\d+)?)\s*(?:%|por\s?ciento)"
                    r"|(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>s|seg|segundos?|m|min|minutos?|h|horas?)"
                    r"|(?P<clock>\d{1,2}(?::\d{2}){1,2}(?:[.,]\d+)?))$")
UNITS = {"s": 1, "seg": 1, "segundo": 1, "segundos": 1, "m": 60, "min": 60, "minuto": 60,
         "minutos": 60, "h": 3600, "hora": 3600, "horas": 3600}
```

añade `import re` al bloque de importaciones (orden alfabético, entre `pathlib` y `shutil`), y las dos
funciones al final del archivo:

```python
def parse_target(text, total):
    """Target output length in seconds from '10%', '720s', '12min' or '0:12:00'; None when absent."""
    if text is None:
        return None
    clean = " ".join(str(text).split()).lower()
    if not clean or clean in ("ninguno", "sin objetivo"):
        return None
    match = TARGET.match(clean)
    if not match:
        raise ValueError(f"Objetivo ambiguo: «{text}». Indica un porcentaje (10%), una duración "
                         "(720s, 12min) o un tiempo (0:12:00).")
    if match["pct"] is not None:
        percent = float(match["pct"].replace(",", "."))
        if not 0 < percent < 100:
            raise ValueError("El porcentaje del objetivo debe estar entre 0 y 100 "
                             f"(recibido {percent:g}).")
        value = total * percent / 100
    elif match["num"] is not None:
        value = float(match["num"].replace(",", ".")) * UNITS[match["unit"]]
    else:
        value = 0.0
        for part in match["clock"].replace(",", ".").split(":"):
            value = value * 60 + float(part)
    # Section 4 guarantees the returned target, so round before checking its range.
    value = round(value, 3)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Objetivo no válido: «{text}».")
    if value >= total:
        raise ValueError(f"El objetivo ({value:.1f} s) no es menor que el original ({total:.1f} s).")
    return value


def tolerance(target):
    """Half-width of the acceptance band around a target, never narrower than ten seconds."""
    return max(TOLERANCE_RATIO * target, TOLERANCE_FLOOR)
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 4 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): interpretar el objetivo de compresion y su banda de tolerancia" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: huella del medio

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `common` de la tarea 2.
- Produces: `fingerprint(path) -> {"size", "mtime_ns", "sha256"}`, con el sha256 de los primeros y los
  últimos 4 MiB (el archivo entero si mide 8 MiB o menos). Constante `CHUNK = 4 * 1024 * 1024`. Sus tres
  claves se funden con las de `identity` para formar el `source` de `metadata.json` y del plan publicado:
  la usarán `prepare` al sondear el medio, `render` para reasignar un plan movido y `plan --import` para
  completar la identidad de un plan 0.1.

- [ ] **Paso 1: escribir la prueba que falla**

Añade a `test_common.py`:

```python
class HuellaTest(unittest.TestCase):
    def test_survives_a_move_and_notices_both_ends(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            big = root / "grande.bin"
            big.write_bytes(b"A" * (9 * 1024 * 1024) + b"Z" * 16)
            original = common.fingerprint(big)
            moved = root / "otro nombre.bin"
            big.replace(moved)
            self.assertEqual(common.fingerprint(moved)["sha256"], original["sha256"])
            self.assertEqual(set(original), {"size", "mtime_ns", "sha256"})
            with moved.open("r+b") as stream:
                stream.seek(-4, os.SEEK_END)
                stream.write(b"QQQQ")
            self.assertNotEqual(common.fingerprint(moved)["sha256"], original["sha256"])

    def test_small_files_are_hashed_whole_and_only_once(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            small = Path(temporary) / "corto.bin"
            small.write_bytes(b"hola")
            self.assertEqual(common.fingerprint(small)["size"], 4)
            self.assertEqual(common.fingerprint(small)["sha256"],
                             hashlib.sha256(b"hola").hexdigest())

    def test_files_below_eight_mib_are_hashed_through_the_middle(self):
        # Pinning the value, not just its sensitivity: with a lower threshold the head and the tail
        # of a 6 MiB file overlap, the middle is hashed twice and the digest stops matching.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            medium = Path(temporary) / "medio.bin"
            body = bytes(range(256)) * (6 * 1024 * 4)
            medium.write_bytes(body)
            self.assertEqual(common.fingerprint(medium)["sha256"],
                             hashlib.sha256(body).hexdigest())

    def test_large_files_use_only_ends(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            long = Path(temporary) / "largo.bin"
            body = bytes(range(256)) * (12 * 1024 * 4)
            long.write_bytes(body)
            ends = body[:common.CHUNK] + body[-common.CHUNK:]
            self.assertEqual(common.fingerprint(long)["sha256"], hashlib.sha256(ends).hexdigest())
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Huella -v
```

Esperado: 4 errores `AttributeError: module 'common' has no attribute 'fingerprint'`.

- [ ] **Paso 3: implementación mínima**

Añade `import hashlib` a las importaciones, `CHUNK = 4 * 1024 * 1024` junto a las demás constantes y:

```python
def fingerprint(path):
    """Identity that survives a move: size, mtime and a hash of the first and last 4 MiB."""
    path = Path(path).resolve(strict=True)
    info = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if info.st_size <= 2 * CHUNK:
            # Read whole below 8 MiB: hashing only the ends would skip the middle of these files.
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                digest.update(block)
        else:
            digest.update(stream.read(CHUNK))
            stream.seek(-CHUNK, os.SEEK_END)
            digest.update(stream.read(CHUNK))
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": digest.hexdigest()}
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 8 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): huella del medio con sha256 de sus dos extremos" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: energía RMS cacheada y detección de silencios

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `common` de la tarea 3. `publish` todavía no existe (llega en la tarea 8), así que la caché
  se escribe en un `.parcial` y se renombra con `os.rename`; la tarea 8 sustituye esa línea por `publish`.
- Produces: `energy(wav_path, cache_path=None) -> array('f')` con el nivel RMS en dBFS cada 10 ms;
  `bounds(levels, a, b) -> (first, last)` (añadido declarado: convierte `[a, b)` en segundos a índices de
  la rejilla de 10 ms, `first = max(0, int(a / ENERGY_STEP + 1e-9))` y
  `last = min(len(levels), math.ceil(b / ENERGY_STEP - 1e-9))`, y la usan `silences`, `voiced` y, en la
  tarea 13, `plan.percentile`: nadie repite esas dos líneas);
  `silences(levels, a, b, threshold=SILENCE_DB, min_silence=MIN_SILENCE) -> list[tuple[float, float]]`;
  `voiced(levels, a, b, threshold=SILENCE_DB) -> bool` (añadido declarado); constantes
  `SILENCE_DB = -50.0`, `MIN_SILENCE = 0.30`, `ENERGY_STEP = 0.01`, `ENERGY_FLOOR = -120.0`,
  `ENERGY_BLOCK = 600`, `FULL_SCALE`, `SQUARES`, y los ayudantes `squares()` y `levels_of(sound, window)`.
  El índice `i` de `levels` cubre `[i·0,01, (i+1)·0,01)` segundos.

- [ ] **Paso 1: escribir la prueba que falla, con un WAV sintético sin FFmpeg**

Añade a `test_common.py`. `tone_wav` memoriza las muestras por forma porque cada segundo de tono
cuesta unos 17 ms de Python puro y la batería lo pide una decena de veces; el tono de 120 s con el que
se vigila el presupuesto se construye una sola vez por el mismo motivo:

```python
SAMPLES = {}


def tone_wav(path, seconds=6.0, rate=16000, pauses=((1.0, 1.5), (3.0, 3.6))):
    """16 kHz mono PCM with a 440 Hz tone and exact silences; no FFmpeg needed."""
    key = (seconds, rate, pauses)
    if key not in SAMPLES:
        samples = array.array("h")
        for index in range(int(seconds * rate)):
            moment = index / rate
            quiet = any(a <= moment < b for a, b in pauses)
            samples.append(0 if quiet else int(8000 * math.sin(2 * math.pi * 440 * moment)))
        SAMPLES[key] = samples.tobytes()
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(SAMPLES[key])


class EnergiaTest(unittest.TestCase):
    def test_levels_silences_and_budget(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "tono.wav"
            tone_wav(path)
            levels = common.energy(path)
            self.assertEqual(len(levels), 600)
            self.assertAlmostEqual(levels[50], -15.19, delta=0.1)
            self.assertEqual(levels[120], common.ENERGY_FLOOR)
            # 1.16 s is 115.999… steps of 10 ms: the window opens at 116, never at 115.
            self.assertEqual(common.bounds(levels, 1.16, 2.32), (116, 232))
            self.assertEqual(common.silences(levels, 0, 6), [(1.0, 1.5), (3.0, 3.6)])
            self.assertEqual(common.silences(levels, 0, 6, min_silence=0.55), [(3.0, 3.6)])
            self.assertEqual(common.silences(levels, 1.2, 2.0), [(1.2, 1.5)])
            self.assertEqual(common.silences(levels, 1.25, 2.0), [])
            self.assertTrue(common.voiced(levels, 0.5, 0.58))
            self.assertFalse(common.voiced(levels, 1.1, 1.18))
            self.assertEqual(common.silences(levels, 0, 6, threshold=-10.0), [(0.0, 6.0)])
            long_path = Path(temporary) / "largo.wav"
            tone_wav(long_path, seconds=120.0, pauses=())
            started = time.perf_counter()
            common.energy(long_path)
            spent = time.perf_counter() - started
            # A catastrophe alarm, six times the documented budget of 30 s per 2 h: it is sensitive
            # to how busy the machine is and it does not tell one implementation from another.
            self.assertLess(spent, 3.0)

    def test_the_table_of_squares_is_built_once(self):
        table = common.squares()
        self.assertEqual(len(table), 65536)
        self.assertEqual(table[300], 300 * 300)
        self.assertIs(common.squares(), table)

    def test_cache_is_written_once_and_reread(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            tone_wav(root / "tono.wav")
            cache = root / "energia.f32"
            common.energy(root / "tono.wav", cache)
            self.assertEqual(cache.stat().st_size, 600 * 4)
            # Levels no recording gives: reading the cache and recomputing it are told apart.
            marked = array.array("f", [-7.5] * 600)
            cache.write_bytes(marked.tobytes())
            self.assertEqual(list(common.energy(root / "tono.wav", cache)), list(marked))
            self.assertFalse(list(root.glob("*.parcial")))
            cache.write_bytes(b"\x00" * 8)
            recomputed = common.energy(root / "tono.wav", cache)
            self.assertEqual(len(recomputed), 600)
            self.assertEqual(recomputed[120], common.ENERGY_FLOOR)

    def test_only_the_analysis_format_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "estereo.wav"
            with wave.open(str(path), "wb") as sound:
                sound.setnchannels(2)
                sound.setsampwidth(2)
                sound.setframerate(16000)
                sound.writeframes(b"\x00" * 640)
            with self.assertRaisesRegex(ValueError, "mono PCM de 16 bits"):
                common.energy(path)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Energia -v
```

Esperado: 4 errores `AttributeError: module 'common' has no attribute 'energy'`.

- [ ] **Paso 3: implementación mínima**

Añade `import array` y `import wave` a las importaciones, estas constantes:

```python
SILENCE_DB = -50.0
MIN_SILENCE = 0.30
ENERGY_STEP = 0.01
ENERGY_FLOOR = -120.0
ENERGY_BLOCK = 600
FULL_SCALE = 32768.0 * 32768.0
SQUARES = []
```

y estas cuatro funciones:

```python
def squares():
    """Square of every 16-bit sample read as unsigned, so the RMS loop stays inside C calls."""
    if not SQUARES:
        SQUARES.extend(value * value for value in range(32768))
        SQUARES.extend((value - 65536) * (value - 65536) for value in range(32768, 65536))
    return SQUARES


def levels_of(sound, window):
    """dBFS of every `window` frames of an open mono 16-bit wave, read block by block."""
    table, levels, pending = squares().__getitem__, array.array("f"), b""
    while True:
        raw = sound.readframes(window * ENERGY_BLOCK)
        if not raw:
            return levels
        pending += raw
        # Whole windows only: the remainder is carried over so the grid never drifts.
        usable = len(pending) - len(pending) % (2 * window)
        block = array.array("H")
        block.frombytes(pending[:usable])
        if sys.byteorder == "big":
            block.byteswap()
        pending = pending[usable:]
        for start in range(0, len(block), window):
            mean = sum(map(table, block[start:start + window])) / window
            levels.append(ENERGY_FLOOR if mean <= 0
                          else max(ENERGY_FLOOR, 10 * math.log10(mean / FULL_SCALE)))


def energy(wav_path, cache_path=None):
    """RMS level in dBFS every 10 ms; cached, and never loading the whole recording."""
    with wave.open(str(wav_path), "rb") as sound:
        if sound.getsampwidth() != 2 or sound.getnchannels() != 1:
            raise ValueError("La energía se calcula sobre el audio de análisis mono PCM de 16 bits "
                             "que crea prepare.")
        window = max(1, round(sound.getframerate() * ENERGY_STEP))
        expected = sound.getnframes() // window
        cache = Path(cache_path) if cache_path is not None else None
        if cache is not None and cache.is_file():
            cached, data = array.array("f"), cache.read_bytes()
            if len(data) == expected * cached.itemsize:
                cached.frombytes(data)
                return cached
        levels = levels_of(sound, window)
    if cache is not None:
        # A cache that did not match is stale, not sacred: os.replace overwrites it in one step.
        staged = cache.with_name(cache.name + ".parcial")
        staged.write_bytes(levels.tobytes())
        os.replace(staged, cache)
    return levels


def bounds(levels, a, b):
    """[a, b) seconds as indices of the 10 ms grid, clipped to what `levels` actually covers."""
    # The epsilons keep 1.16 s (115.999… steps) from opening a window one index too early or wide.
    first = max(0, int(a / ENERGY_STEP + 1e-9))
    last = min(len(levels), math.ceil(b / ENERGY_STEP - 1e-9))
    return first, last


def silences(levels, a, b, threshold=SILENCE_DB, min_silence=MIN_SILENCE):
    """Stretches of [a, b) whose level never reaches `threshold` and last at least `min_silence`."""
    first, last = bounds(levels, a, b)
    runs, start = [], None
    for index in range(first, last):
        if levels[index] < threshold:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, last))
    found = []
    for x, y in runs:
        low, high = max(a, x * ENERGY_STEP), min(b, y * ENERGY_STEP)
        if high - low >= min_silence - 1e-9:
            found.append((round(low, 6), round(high, 6)))
    return found


def voiced(levels, a, b, threshold=SILENCE_DB):
    """True when any 10 ms window of [a, b) reaches `threshold`."""
    first, last = bounds(levels, a, b)
    return any(levels[index] >= threshold for index in range(first, last))
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 12 tests … OK`.

- [ ] **Paso 5: medir el presupuesto real de esta máquina**

Desde `plugins/resumir-video/skills/resumir-video/scripts/`:

```bash
python -B -c "import tempfile, time; from pathlib import Path; import common, test_common; d = Path(tempfile.mkdtemp()); test_common.tone_wav(d / 'largo.wav', seconds=120.0, pauses=()); common.squares(); t = time.perf_counter(); common.energy(d / 'largo.wav'); print('segundos por 2 h:', round((time.perf_counter() - t) * 60, 1))"
```

Esperado: un valor del orden de 12 s por cada 2 h (medido en esta máquina: 11,9 s). Anótalo en el commit;
si supera 30 s, el bucle no está usando la tabla de cuadrados y hay que revisar el paso 3.

- [ ] **Paso 6: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): energia RMS cacheada por bloques y deteccion de silencios" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: rejilla de fotogramas e islas sin pausas

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `silences`, `SILENCE_DB`, `MIN_SILENCE` de la tarea 4.
- Produces: `snap(t, interval, origin) -> float` (instante de la rejilla más próximo, empates hacia
  arriba, redondeado a 6 decimales) e
  `islands(levels, a, b, *, interval, origin, remove_pauses=True, threshold=SILENCE_DB, min_silence=MIN_SILENCE, margin=PAUSE_MARGIN) -> list[list[float]]`.
  Constantes `PAUSE_MARGIN = 0.08`, `MIN_ISLAND = 0.12`, `MIN_EDGE_ISLAND = 0.20`. La lista vacía significa
  «el corte se queda sin material»: quien la recibe emite `corte_vacio`. Los filtros de longitud
  (`MIN_ISLAND` y `MIN_EDGE_ISLAND`) son de §7.4 y solo se aplican al quitar pausas: con
  `remove_pauses=False` el corte conserva su único tramo `[a, b]`, porque los `visual_only` conservan sus
  pausas y su vacío lo decide `L < v / F`, no el tamaño de las islas.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class IslasTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        path = Path(self.temporary.name) / "tono.wav"
        tone_wav(path)
        self.levels = common.energy(path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_grid_rounds_to_the_nearest_frame(self):
        self.assertAlmostEqual(common.snap(1.234, 0.04, 0.0), 1.24)
        self.assertAlmostEqual(common.snap(1.219, 0.04, 0.0), 1.2)
        self.assertAlmostEqual(common.snap(1.2, 0.04, 0.032), 1.192)
        self.assertAlmostEqual(common.snap(1.0, 1001 / 30000, 0.0), 1.001)
        self.assertAlmostEqual(common.snap(2.0, 1001 / 30000, 0.0), 2.002)

    def test_pauses_leave_islands_on_the_grid(self):
        self.assertEqual(common.islands(self.levels, 0.5, 4.0, interval=0.04, origin=0.0),
                         [[0.52, 1.08], [1.44, 3.08], [3.52, 4.0]])
        self.assertEqual(common.islands(self.levels, 0.5, 4.0, interval=0.04, origin=0.0,
                                        remove_pauses=False), [[0.52, 4.0]])
        self.assertEqual(common.islands(self.levels, 0.5, 2.0, interval=0.04, origin=0.032),
                         [[0.512, 1.072], [1.432, 1.992]])

    def test_a_cut_inside_a_pause_keeps_nothing(self):
        self.assertEqual(common.islands(self.levels, 1.1, 1.4, interval=0.04, origin=0.0), [])

    def test_short_and_edge_spans_are_dropped(self):
        self.assertEqual(common.islands(self.levels, 0.95, 3.7, interval=0.04, origin=0.0),
                         [[1.44, 3.08]])

    def test_a_visual_cut_keeps_its_short_span(self):
        # §7.4: keeping the pauses means keeping the span too, even below MIN_EDGE_ISLAND.
        self.assertEqual(common.islands(self.levels, 1.1, 1.2, interval=0.04, origin=0.0,
                                        remove_pauses=False), [[1.12, 1.2]])

    def test_interior_spans_shorter_than_min_island_are_dropped(self):
        # Three pauses: the middle one creates a short interior span between longer voiced sections.
        # Pauses at (1.0, 1.4), (1.5, 1.9), and (4.0, 4.5) leave spans: [0,1.0], [1.4,1.5] (0.1s),
        # [1.9,4.0], and [4.5,6.0]. The interior span [1.4,1.5] is < MIN_ISLAND and should disappear.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "interior_short.wav"
            tone_wav(path, seconds=6.0, pauses=((1.0, 1.4), (1.5, 1.9), (4.0, 4.5)))
            levels = common.energy(path)
            islands = common.islands(levels, 0, 6.0, interval=0.01, origin=0.0, margin=0.0)
            # The [1.4,1.5] span (0.1s < MIN_ISLAND) disappears; three spans survive.
            self.assertEqual(islands, [[0.0, 1.0], [1.9, 4.0], [4.5, 6.0]])

        # Same setup but with a 0.12s interior gap (exactly MIN_ISLAND): [1.4, 1.52].
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "interior_exact.wav"
            tone_wav(path, seconds=6.0, pauses=((1.0, 1.4), (1.52, 1.9), (4.0, 4.5)))
            levels = common.energy(path)
            islands = common.islands(levels, 0, 6.0, interval=0.01, origin=0.0, margin=0.0)
            # The [1.4, 1.52] span (0.12s == MIN_ISLAND) survives as an interior span.
            self.assertEqual(islands, [[0.0, 1.0], [1.4, 1.52], [1.9, 4.0], [4.5, 6.0]])

    def test_neighbours_closer_than_a_frame_are_fused(self):
        # With a large frame interval, snapped boundaries can be closer than one frame apart,
        # triggering fusion of adjacent island groups. Standard pauses leave three voiced spans;
        # with interval=1.5, they all fuse into one; with interval=0.04, they stay separate.
        # With interval=1.5, snap([0,1.0]) = [0, 1.5], snap([1.5,3.0]) = [1.5, 3.0],
        # snap([3.6,6.0]) = [3.0, 6.0], and gaps become 0.0 and 0.0, triggering fusion.
        islands_fused = common.islands(self.levels, 0, 6, interval=1.5, origin=0.0, margin=0.0)
        # All three spans fuse into one large span covering [0, 6].
        self.assertEqual(islands_fused, [[0.0, 6.0]])

        # With the normal interval, spans stay separate.
        islands_separate = common.islands(self.levels, 0, 6, interval=0.04, origin=0.0, margin=0.0)
        # Three spans survive without fusion.
        self.assertEqual(islands_separate, [[0.0, 1.0], [1.52, 3.0], [3.6, 6.0]])
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Islas -v
```

Esperado: 7 errores `AttributeError: module 'common' has no attribute 'snap'`.

- [ ] **Paso 3: implementación mínima**

Constantes nuevas:

```python
PAUSE_MARGIN = 0.08
MIN_ISLAND = 0.12
MIN_EDGE_ISLAND = 0.20
```

y las dos funciones:

```python
def snap(t, interval, origin):
    """Nearest instant of the frame grid; ties go up so the same value always lands the same way."""
    steps = math.floor((t - origin) / interval + 0.5)
    return round(origin + steps * interval, 6)


def islands(levels, a, b, *, interval, origin, remove_pauses=True, threshold=SILENCE_DB,
            min_silence=MIN_SILENCE, margin=PAUSE_MARGIN):
    """Spans of [a, b) that survive removing pauses, snapped to the frame grid."""
    if remove_pauses:
        spans, cursor = [], a
        for start, end in silences(levels, a, b, threshold, min_silence):
            gap = (start + margin, end - margin)
            if gap[1] - gap[0] <= 0:
                continue
            if gap[0] > cursor:
                spans.append([cursor, gap[0]])
            cursor = max(cursor, gap[1])
        if b > cursor:
            spans.append([cursor, b])
        spans = [span for span in spans if span[1] - span[0] >= MIN_ISLAND - 1e-9]
        while spans and spans[0][1] - spans[0][0] < MIN_EDGE_ISLAND - 1e-9:
            spans.pop(0)
        while spans and spans[-1][1] - spans[-1][0] < MIN_EDGE_ISLAND - 1e-9:
            spans.pop()
    else:
        # §7.4: a visual_only cut keeps its pauses, so nothing is dropped for being short here.
        spans = [[a, b]]
    grid = []
    for start, end in spans:
        low, high = snap(start, interval, origin), snap(end, interval, origin)
        if high - low < interval - 1e-9:
            continue
        if grid and low - grid[-1][1] < interval - 1e-9:
            grid[-1][1] = high
        else:
            grid.append([low, high])
    return grid
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 19 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): rejilla de fotogramas e islas tras quitar pausas" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: ajuste de bordes fuera de la voz

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `silences`, `voiced`, `SILENCE_DB` de la tarea 4.
- Produces: `nearest_silence(levels, edge, direction, limit, threshold) -> float | None`, el ayudante
  que hace la búsqueda de un solo lado: con `direction = -1` busca hacia atrás desde `edge` (ajustando
  el inicio de un corte) y con `direction = +1` hacia delante desde `edge` (ajustando su fin);
  `adjust_edges` lo llama una vez por lado. También `adjust_edges(a, b, levels, words, *,
  threshold=SILENCE_DB) -> (float, float, str | None)`. `words` es la lista plana de palabras de la
  transcripción, cada una `{"start", "end"}`; admite `None` como equivalente a la lista vacía, y con la
  lista vacía (subtítulos sin palabras) el ajuste sigue funcionando y solo pierde la protección de
  palabra. El tercer valor es `"borde_en_voz"` o `None`. Constantes añadidas `EDGE_LOOK = 0.08`,
  `EDGE_WINDOW = 0.60`, `EDGE_SILENCE = 0.10`, `WORD_MARGIN = 0.02`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class BordesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        path = Path(self.temporary.name) / "tono.wav"
        tone_wav(path)
        self.levels = common.energy(path)
        self.words = [{"start": 0.0, "end": 1.0}, {"start": 1.5, "end": 3.0},
                      {"start": 3.65, "end": 5.9}]

    def tearDown(self):
        self.temporary.cleanup()

    def test_both_edges_move_to_the_nearest_silence(self):
        self.assertEqual(common.adjust_edges(2.0, 2.5, self.levels, self.words), (1.5, 3.0, None))

    def test_clean_edges_are_left_alone(self):
        self.assertEqual(common.adjust_edges(1.2, 1.3, self.levels, self.words), (1.2, 1.3, None))

    def test_without_a_nearby_silence_it_warns(self):
        start, end, note = common.adjust_edges(4.0, 4.5, self.levels, self.words)
        self.assertEqual((start, end), (3.6, 4.5))
        self.assertEqual(note, "borde_en_voz")

    def test_it_never_invades_the_neighbouring_word(self):
        words = [{"start": 0.0, "end": 1.0}, {"start": 1.48, "end": 2.9}, {"start": 2.95, "end": 5.9}]
        start, end, _ = common.adjust_edges(2.0, 2.5, self.levels, words)
        self.assertAlmostEqual(start, 1.5)
        self.assertAlmostEqual(end, 2.93)
        # Mirror on the start side: the previous word's end (1.49) sits inside the preceding
        # silence (1.0, 1.5), 0.01 s short of its far edge, so the raw candidate (1.5) would leave
        # less than WORD_MARGIN after the word; the start is pushed to 1.49 + 0.02 = 1.51 instead.
        mirrored = [{"start": 0.0, "end": 1.49}, {"start": 1.5, "end": 3.0}, {"start": 3.65, "end": 5.9}]
        start, end, _ = common.adjust_edges(2.0, 2.5, self.levels, mirrored)
        self.assertAlmostEqual(start, 1.51)
        self.assertAlmostEqual(end, 3.0)

    def test_it_works_without_word_marks(self):
        self.assertEqual(common.adjust_edges(2.0, 2.5, self.levels, []), (1.5, 3.0, None))
        self.assertEqual(common.adjust_edges(2.0, 2.5, self.levels, None), (1.5, 3.0, None))

    def test_silence_beyond_the_window_is_ignored(self):
        # Cut end at b=1.0; the leading pause (0.0, 0.2) keeps the start side untouched (voiced
        # lookback [0.02, 0.1) is silent), isolating the check to EDGE_WINDOW on the end side.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "justo_fuera.wav"
            # Pause starts at b + 0.61 s: only 0.7 - 0.61 = 0.09 s show inside the widened search
            # window, below EDGE_SILENCE (0.10 s), so no candidate qualifies.
            tone_wav(path, seconds=3.0, pauses=((0.0, 0.2), (1.61, 3.0)))
            levels = common.energy(path)
            start, end, note = common.adjust_edges(0.1, 1.0, levels, [])
            self.assertEqual((start, end), (0.1, 1.0))
            self.assertEqual(note, "borde_en_voz")
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "justo_dentro.wav"
            # Pause starts at b + 0.60 s exactly: 0.7 - 0.60 = 0.10 s show, meeting EDGE_SILENCE.
            tone_wav(path, seconds=3.0, pauses=((0.0, 0.2), (1.60, 3.0)))
            levels = common.energy(path)
            start, end, note = common.adjust_edges(0.1, 1.0, levels, [])
            self.assertEqual((start, end), (0.1, 1.6))
            self.assertIsNone(note)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Bordes -v
```

Esperado: 6 errores `AttributeError: module 'common' has no attribute 'adjust_edges'`.

- [ ] **Paso 3: implementación mínima**

Constantes nuevas:

```python
EDGE_LOOK = 0.08
EDGE_WINDOW = 0.60
EDGE_SILENCE = 0.10
WORD_MARGIN = 0.02
```

y las funciones:

```python
def nearest_silence(levels, edge, direction, limit, threshold):
    """Closest edge of a silence within EDGE_WINDOW of `edge`, or None when nothing qualifies.

    `direction` is -1 to search backward from `edge` (adjusting a cut's start) or +1 to search
    forward (adjusting its end). `limit`, when not None, is the neighbouring word's edge on that
    side: the result never lands closer to `edge` than `limit` plus WORD_MARGIN would allow.
    """
    # The search window grows by EDGE_SILENCE so a pause that starts before it still shows 0.1 s.
    if direction < 0:
        gaps = reversed(silences(levels, max(0.0, edge - EDGE_WINDOW - EDGE_SILENCE), edge,
                                 threshold, EDGE_SILENCE))
    else:
        gaps = silences(levels, edge, edge + EDGE_WINDOW + EDGE_SILENCE, threshold, EDGE_SILENCE)
    for gap in gaps:
        near = gap[1] if direction < 0 else gap[0]
        if direction < 0 and near < edge - EDGE_WINDOW:
            continue
        if direction > 0 and near > edge + EDGE_WINDOW:
            continue
        if limit is None:
            candidate = near
        elif direction < 0:
            candidate = max(near, limit + WORD_MARGIN)
        else:
            candidate = min(near, limit - WORD_MARGIN)
        if direction < 0 and candidate < edge:
            return round(candidate, 6)
        if direction > 0 and candidate > edge:
            return round(candidate, 6)
    return None


def adjust_edges(a, b, levels, words, *, threshold=SILENCE_DB):
    """Move both edges out of speech; returns the pair and `borde_en_voz` when no silence is near."""
    words = words or []
    note, start, end = None, a, b
    if voiced(levels, max(0.0, a - EDGE_LOOK), a, threshold):
        limit = max((word["end"] for word in words if word["end"] <= a), default=None)
        candidate = nearest_silence(levels, a, -1, limit, threshold)
        if candidate is None:
            note = "borde_en_voz"
        else:
            start = candidate
    if voiced(levels, b, b + EDGE_LOOK, threshold):
        limit = min((word["start"] for word in words if word["start"] >= b), default=None)
        candidate = nearest_silence(levels, b, 1, limit, threshold)
        if candidate is None:
            note = "borde_en_voz"
        else:
            end = candidate
    return start, end, note
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 25 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): llevar los bordes de cada corte al silencio mas cercano" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `N` y `M` exactos, sha256 canónico, avisos, reloj de lectura y texto sin tildes

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `common` de la tarea 6.
- Produces: `frames_for(length, rate, speed) -> int` (`N = round(L·F/v)`, empates hacia arriba, nunca
  negativo), `samples_for(n_frames, rate, sample_rate) -> int` (`M = round(N/F·SR)`),
  `plan_sha256(plan) -> str` (JSON canónico con `sort_keys`, separadores `(",", ":")`, ignorando la clave
  `sha256`), `warning(code, message, *, cut=None) -> dict` con
  `{"codigo", "mensaje", "corte", "bloquea"}` donde `bloquea = code in BLOCKING`,
  `clock(value) -> str` (sello de lectura `0:24` / `1:02:07`, **truncado** al segundo) y
  `strip_accents(text) -> str` (conserva `ñ` y `Ñ`). Constantes `BLOCKING`, `MEMORY_PATTERNS` y
  `MAX_SPANS = 40`.
- `clock` y `MAX_SPANS` viven aquí porque los comparten más de un módulo: el reloj lo usan la propuesta
  de `plan.py` y el documento de `doc.py`, y el tope de tramos lo usan los subcortes de `plan.py` y el
  montaje de `render.py`. Ninguno de los dos se redefine en otro archivo.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class ExactitudTest(unittest.TestCase):
    def test_frames_and_samples_match_the_rendered_cut(self):
        self.assertEqual(common.frames_for(7.16, 25, 1.25), 143)
        self.assertEqual(common.samples_for(143, 25, 48000), 274560)
        self.assertEqual(common.frames_for(10, 25, 1.0), 250)
        self.assertEqual(common.frames_for(0.5, 25, 1.0), 13)
        self.assertEqual(common.frames_for(0.0, 25, 1.25), 0)
        self.assertEqual(common.samples_for(200, 30000 / 1001, 48000), 320320)

    def test_the_digest_ignores_key_order_and_its_own_field(self):
        one = {"b": 2, "a": [1, {"y": 1, "x": 2}], "sha256": "lo que sea"}
        other = {"a": [1, {"x": 2, "y": 1}], "b": 2}
        self.assertEqual(common.plan_sha256(one), common.plan_sha256(other))
        self.assertNotEqual(common.plan_sha256(one), common.plan_sha256({"a": [1], "b": 2}))

    def test_warnings_carry_their_own_blocking_flag(self):
        self.assertEqual(common.warning("corte_vacio", "sin tramos", cut=7),
                         {"codigo": "corte_vacio", "mensaje": "sin tramos", "corte": 7,
                          "bloquea": True})
        self.assertEqual(common.warning("corte_breve", "muy corto")["bloquea"], False)
        self.assertEqual(common.BLOCKING, ("esenciales_superan_objetivo", "dependencia_excluida",
                                           "tema_sin_cubrir", "corte_vacio"))
        self.assertIn("av_buffer_alloc() failed", common.MEMORY_PATTERNS)
        self.assertEqual(common.MAX_SPANS, 40)

    def test_searching_ignores_accents_but_not_the_spanish_n(self):
        self.assertEqual(common.strip_accents("Año ATEX: ¿Qué diseñó Muñoz?"),
                         "Año ATEX: ¿Que diseño Muñoz?")
        self.assertEqual(common.strip_accents("ÑANDÚ ÜÖ"), "ÑANDU UO")

    def test_the_reading_clock_truncates_to_the_second(self):
        self.assertEqual(common.clock(0), "0:00")
        self.assertEqual(common.clock(5.72), "0:05")
        self.assertEqual(common.clock(24.36), "0:24")
        self.assertEqual(common.clock(1005), "16:45")
        self.assertEqual(common.clock(3727), "1:02:07")
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Exactitud -v
```

Esperado: 5 errores `AttributeError: module 'common' has no attribute 'frames_for'`.

- [ ] **Paso 3: implementación mínima**

Añade `import unicodedata` a las importaciones, estas constantes:

```python
MEMORY_PATTERNS = ("Cannot allocate memory", "Out of memory", "av_buffer_alloc() failed")
BLOCKING = ("esenciales_superan_objetivo", "dependencia_excluida", "tema_sin_cubrir", "corte_vacio")
MAX_SPANS = 40
```

y estas seis funciones:

```python
def frames_for(length, rate, speed):
    """N = round(L * F / v); ties go up, so the same length always yields the same count."""
    return max(0, math.floor(length * rate / speed + 0.5))


def samples_for(n_frames, rate, sample_rate):
    """M = round(N / F * SR): the audio that exactly covers N frames."""
    return max(0, math.floor(n_frames / rate * sample_rate + 0.5))


def plan_sha256(plan):
    """Canonical digest of a plan: the same content always yields the same value."""
    body = {key: value for key, value in plan.items() if key != "sha256"}
    text = json.dumps(body, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def warning(code, message, *, cut=None):
    """One entry of the warnings list; `bloquea` comes from BLOCKING, never from the caller."""
    return {"codigo": code, "mensaje": message, "corte": cut, "bloquea": code in BLOCKING}


def strip_accents(text):
    """Accent-free copy for searching; ñ is a letter of its own in Spanish and survives."""
    guarded = unicodedata.normalize("NFC", text).replace("ñ", "\x00").replace("Ñ", "\x01")
    plain = "".join(ch for ch in unicodedata.normalize("NFD", guarded)
                    if not unicodedata.combining(ch))
    return plain.replace("\x00", "ñ").replace("\x01", "Ñ")


def clock(value):
    """Reading stamp, truncated to the second: 752.3 -> 12:32, 3725 -> 1:02:05."""
    hours, rest = divmod(int(value), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
```

Se trunca, no se redondea: un sello de lectura nunca debe adelantar a un instante que aún no ha llegado,
y así el mismo valor da el mismo texto en la propuesta, en el diff de cambios y en el documento.

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -v
```

Esperado: `Ran 30 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): N y M exactos, sha256 canonico, avisos, reloj y texto sin tildes" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: publicación atómica, cerrojo, historial y reserva de versión

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `common` de la tarea 7.
- Produces: `publish(staged, final) -> None` (renombra; **nunca** sobrescribe), `lock(path)`
  (gestor de contexto con `O_EXCL`; el segundo intento levanta `ValueError`),
  `history(work, event, payload) -> None` (una línea JSON por llamada en `historial.jsonl`, en modo
  añadir, menor de 4 KiB), el añadido declarado `shorten(value)`, que recorta los textos del registro
  **a cualquier profundidad**, `reserve_version(work, prefix) -> (int, Path)` (crea en exclusiva
  `<prefix>-vN.json`, tres intentos) y el añadido declarado `write_reserved(path, text) -> None`, que
  llena una versión ya reservada con `os.replace`. Constantes `HISTORY_LIMIT = 4096`,
  `HISTORY_TEXT = 300`, `VERSION_ATTEMPTS = 3`. **No toca `energy`:** la caché de energía no es un
  artefacto publicado sino un derivado reconstruible que se repara sobrescribiéndose con `os.replace`,
  así que `publish` —que nunca sobrescribe— no le sirve. Lo único que esta tarea cambia en `energy` es
  el nombre del archivo intermedio, que pasa a llevar el pid (`energia.f32.<pid>.parcial`) para que
  dos procesos que escriban la misma caché a la vez no compartan el mismo `.parcial` (en Windows, con
  cuatro hilos sobre la misma ruta, el nombre fijo daba `PermissionError` en 3 de 5 rondas).
- `history` **nunca levanta**: si el registro sigue pasando de 4 KiB escribe una línea mínima con una
  nota, y si el archivo no se deja abrir —o el `payload` ni siquiera es un mapeo— se calla. Por eso el
  armado del registro (`shorten`) va **dentro** del bloque protegido, no antes. El historial es un
  diario; un montaje o una versión ya publicados no se deshacen porque falle una anotación. Los eventos admitidos son exactamente `init`,
  `edit`, `accept`, `render`, `verify`, `doc` y `deliver`; este plan solo escribe `init` y `edit`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class PublicacionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_publishing_never_replaces(self):
        (self.work / "a.txt").write_text("uno", encoding="utf-8")
        common.publish(self.work / "a.txt", self.work / "b.txt")
        self.assertEqual((self.work / "b.txt").read_text(encoding="utf-8"), "uno")
        self.assertFalse((self.work / "a.txt").exists())
        (self.work / "a.txt").write_text("dos", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no se sobrescribe"):
            common.publish(self.work / "a.txt", self.work / "b.txt")
        self.assertEqual((self.work / "b.txt").read_text(encoding="utf-8"), "uno")

    def test_the_lock_is_exclusive_and_is_released(self):
        marker = self.work / "montaje.lock"
        with common.lock(marker):
            self.assertTrue(marker.is_file())
            with self.assertRaisesRegex(ValueError, "Otro proceso"):
                with common.lock(marker):
                    pass
        self.assertFalse(marker.exists())

    def test_history_trims_at_every_depth_and_never_raises(self):
        common.history(self.work, "init", {"version": 1, "segments": 12})
        common.history(self.work, "edit", {"version": 2, "peticion": "x" * 500,
                                           "detalle": {"cambios": ["y" * 500]}})
        # A record that no trimming can shrink must not abort the work it was only logging.
        common.history(self.work, "render", {str(n): "z" * 200 for n in range(30)})
        common.history(Path(self.work) / "no-existe", "verify", {"version": 1})
        # A payload that is not a mapping writes nothing and, above all, raises nothing.
        common.history(self.work, "edit", ["ni", "siquiera", "un", "mapeo"])
        lines = (self.work / "historial.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["evento"] for line in lines],
                         ["init", "edit", "render"])
        self.assertEqual(len(json.loads(lines[1])["peticion"]), common.HISTORY_TEXT)
        self.assertEqual(len(json.loads(lines[1])["detalle"]["cambios"][0]), common.HISTORY_TEXT)
        self.assertEqual(json.loads(lines[2])["nota"], "registro recortado por exceder 4 KiB")
        self.assertTrue(all(len(line.encode("utf-8")) < common.HISTORY_LIMIT for line in lines))

    def test_versions_are_reserved_exclusively(self):
        first, first_path = common.reserve_version(self.work, "seleccion")
        second, second_path = common.reserve_version(self.work, "seleccion")
        self.assertEqual((first, second), (1, 2))
        self.assertEqual(first_path.name, "seleccion-v1.json")
        self.assertEqual(first_path.stat().st_size, 0)
        common.write_reserved(second_path, '{"version": 2}\n')
        self.assertEqual(second_path.read_text(encoding="utf-8"), '{"version": 2}\n')
        self.assertFalse(list(self.work.glob("*.parcial")))
        for number in (3, 4, 5):
            (self.work / f"seleccion-v{number}.json").write_text("{}", encoding="utf-8")
        self.assertEqual(common.reserve_version(self.work, "seleccion")[0], 6)
        self.assertEqual(common.reserve_version(self.work, "borrador")[0], 1)

    def test_two_concurrent_reservations_never_share_a_version(self):
        # Threads, not processes, but the guarantee is the same: O_EXCL is the file system's.
        ready, taken = threading.Barrier(2), []

        def reserve():
            ready.wait()
            taken.append(common.reserve_version(self.work, "seleccion"))

        workers = [threading.Thread(target=reserve) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sorted(number for number, _ in taken), [1, 2])
        self.assertEqual(sorted(path.name for _, path in taken),
                         ["seleccion-v1.json", "seleccion-v2.json"])
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Publicacion -v
```

Esperado: 5 errores `AttributeError: module 'common' has no attribute 'publish'`. Añade también
`import threading` a la cabecera de `test_common.py`.

- [ ] **Paso 3: implementación mínima**

Añade `import contextlib` y `import datetime` a las importaciones de `common.py`, estas constantes:

```python
HISTORY_LIMIT = 4096
HISTORY_TEXT = 300
VERSION_ATTEMPTS = 3
```

y estas seis funciones:

```python
def publish(staged, final):
    """Atomic rename that never replaces: the destination must not exist."""
    staged, final = Path(staged), Path(final)
    if final.exists():
        raise ValueError(f"Ya está publicado y no se sobrescribe: {final}")
    # Windows refuses an existing destination by itself; the check above covers POSIX.
    os.rename(staged, final)


@contextlib.contextmanager
def lock(path):
    """Exclusive marker for one job folder: a second process fails instead of waiting."""
    path = Path(path)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError(f"Otro proceso está trabajando en esta carpeta ({path}); espera a que "
                         "termine, o borra ese archivo si quedó de una interrupción.") from None
    try:
        os.write(handle, f"{os.getpid()}\n".encode("utf-8"))
    finally:
        # Closed before yielding: Windows cannot remove a file that is still open.
        os.close(handle)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def shorten(value):
    """Copy of a record with every text trimmed, however deep it sits inside the payload."""
    if isinstance(value, str):
        return value[:HISTORY_TEXT - 1] + "…" if len(value) > HISTORY_TEXT else value
    if isinstance(value, dict):
        return {key: shorten(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shorten(item) for item in value]
    return value


def history(work, event, payload):
    """One append-only line per call; a diary never undoes the work it was only writing down."""
    moment = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        record = shorten({"cuando": moment, "evento": event, **payload})
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if len(line.encode("utf-8")) >= HISTORY_LIMIT:
            line = json.dumps({"cuando": moment, "evento": event,
                               "nota": "registro recortado por exceder 4 KiB"},
                              ensure_ascii=False, sort_keys=True)
        with (Path(work) / "historial.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except (OSError, TypeError, ValueError):
        # Losing a line of the log never justifies losing a montage or a version already published.
        pass


def reserve_version(work, prefix):
    """Reserve the next N by creating `<prefix>-vN.json` exclusively; three attempts."""
    work = Path(work)
    pattern = re.compile(rf"{re.escape(prefix)}-v(\d+)\.json")
    used = [int(match.group(1)) for match in
            (pattern.fullmatch(path.name) for path in work.glob(f"{prefix}-v*.json")) if match]
    first = max(used, default=0) + 1
    for number in range(first, first + VERSION_ATTEMPTS):
        path = work / f"{prefix}-v{number}.json"
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return number, path
    raise ValueError(f"No se pudo reservar una versión de {prefix} tras {VERSION_ATTEMPTS} "
                     "intentos; otra sesión está escribiendo en la misma carpeta.")


def write_reserved(path, text):
    """Fill a version reserved by reserve_version: staged beside it and replaced atomically."""
    path = Path(path)
    staged = path.with_name(path.name + ".parcial")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)
```

- [ ] **Paso 4: un archivo intermedio por proceso en la caché de energía**

En `energy`, la caché sigue publicándose con `os.replace` (debe poder sobrescribir una caché corrupta;
`publish` no sobrescribe por contrato). Cambia solo el nombre del archivo intermedio para que cada
proceso escriba el suyo:

```python
        staged = cache.with_name(f"{cache.name}.{os.getpid()}.parcial")
```

Añade a `EnergiaTest.test_cache_is_written_once_and_reread` la comprobación de que el nombre
intermedio lleva el pid: parchea `os.replace` con `unittest.mock.patch.object` para capturar sus
argumentos y afirma que `staged.name == f"energia.f32.{os.getpid()}.parcial"`.

- [ ] **Paso 5: ejecutar la batería completa**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
```

Esperado: `Ran 47 tests … OK` (35 de `test_common.py` y 12 de `test_video.py`).

- [ ] **Paso 6: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): publicacion atomica, cerrojo, historial y reserva de version" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: la línea temporal compartida

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/common.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_common.py`

**Interfaces:**
- Consumes: `video_stream`, `output_rate`, `output_interval`, `timeline_start` de la tarea 1.
- Produces (añadido declarado): `timeline(data) -> {"start", "origin", "rate", "fps", "interval",
  "sample_rate"}`, con `origin = (video.start_time − format.start_time) mod 1/F` (§3) y la frecuencia de
  muestreo de la pista elegida en `data["audio_stream"]` (la primera de audio si no está). Es
  **exactamente** el diccionario que `prepare` escribirá en `metadata.json["timeline"]`; `plan.py` lo
  toma de ahí y, si falta, lo calcula con esta función.
- **Las seis claves están siempre**, también en un medio de solo audio (§5): allí no hay rejilla que
  describir, así que `rate`, `fps` e `interval` son `None`, `origin` es `0.0` y `start` y `sample_rate`
  se calculan igual. Así `prepare` escribe `timeline` en los dos modos sin ramas propias y ni `plan`,
  ni `render`, ni `doc` tienen que preguntar por el modo antes de leerla. Sin pista de audio sí
  levanta `ValueError`: un medio mudo no se resume con este flujo. El filtro de pistas de imagen es el
  mismo que el plan de audio y documento factoriza después en `common.pictures`; sustituir la
  condición por esa llamada no cambia el resultado.
- `kind(data)` y `pictures(data)` **no** se definen aquí: los aporta el plan de audio y documento, que
  es quien distingue los dos modos. `sample_rate_of` tampoco existe: la frecuencia de muestreo viaja
  dentro de la línea temporal, que es donde la buscan `plan`, `render` y `doc`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
def probe_like(rate="25/1", start="0.032000", sample_rate="48000"):
    return {"format": {"duration": "60.000000", "start_time": "0.000000"},
            "streams": [{"index": 0, "codec_type": "video", "r_frame_rate": rate,
                         "avg_frame_rate": rate, "start_time": start},
                        {"index": 1, "codec_type": "audio", "sample_rate": sample_rate}]}


class LineaTest(unittest.TestCase):
    def test_the_grid_starts_at_the_video_offset(self):
        grid = common.timeline(probe_like())
        self.assertEqual(set(grid), {"start", "origin", "rate", "fps", "interval", "sample_rate"})
        self.assertEqual(grid["rate"], "25/1")
        self.assertAlmostEqual(grid["interval"], 0.04)
        self.assertAlmostEqual(grid["fps"], 25.0)
        self.assertAlmostEqual(grid["origin"], 0.032)
        self.assertEqual(grid["sample_rate"], 48000)
        self.assertAlmostEqual(common.timeline(probe_like(rate="30000/1001"))["fps"], 30000 / 1001)
        self.assertAlmostEqual(common.timeline(probe_like(start="0.000000"))["origin"], 0.0)
        # offset >= interval: modulo distinguishes from simple subtraction (0.1 mod 0.04 = 0.02)
        self.assertAlmostEqual(common.timeline(probe_like(start="0.1"))["origin"], 0.02, places=9)
        # Origin measured from container start, not zero (format.start_time = 1.0, video.start_time = 1.032)
        offset_from_container = common.timeline(
            {"format": {"duration": "60.0", "start_time": "1.0"},
             "streams": [{"index": 0, "codec_type": "video", "r_frame_rate": "25/1",
                          "avg_frame_rate": "25/1", "start_time": "1.032"},
                         {"index": 1, "codec_type": "audio", "sample_rate": "48000"}]})
        self.assertAlmostEqual(offset_from_container["origin"], 0.032, places=9)
        with self.assertRaisesRegex(ValueError, "pista de audio"):
            common.timeline({"format": {"duration": "60.0", "start_time": "0.0"},
                             "streams": [probe_like()["streams"][0]]})

    def test_audio_only_media_keep_the_same_six_keys(self):
        picture, sound = probe_like()["streams"]
        only_sound = {"format": {"duration": "60.0", "start_time": "0.0"}, "streams": [sound]}
        line = common.timeline(only_sound)
        self.assertEqual(set(line), {"start", "origin", "rate", "fps", "interval", "sample_rate"})
        self.assertEqual((line["rate"], line["fps"], line["interval"]), (None, None, None))
        self.assertEqual((line["start"], line["origin"], line["sample_rate"]), (0.0, 0.0, 48000))
        # Cover art is metadata, not footage: a tagged m4a is still an audio-only medium.
        cover = dict(picture, index=2, disposition={"attached_pic": 1})
        self.assertEqual(common.timeline({**only_sound, "streams": [sound, cover]}), line)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_common.py" -k Linea -v
```

Esperado: 2 errores `AttributeError: module 'common' has no attribute 'timeline'`.

- [ ] **Paso 3: implementación mínima**

```python
def timeline(data):
    """Container start, grid, cadence and sample rate that the whole job shares (sections 3, 5)."""
    sounds = [stream for stream in data["streams"] if stream["codec_type"] == "audio"]
    if not sounds:
        raise ValueError("El medio no tiene pista de audio: no se puede analizar al ponente.")
    chosen = next((s for s in sounds if s["index"] == data.get("audio_stream")), sounds[0])
    line = {"start": timeline_start(data), "origin": 0.0, "rate": None, "fps": None,
            "interval": None, "sample_rate": int(chosen.get("sample_rate") or 0)}
    # Audio-only media keep the same six keys with no grid to fill; cover art is not footage.
    if not any(stream["codec_type"] == "video"
               and not stream.get("disposition", {}).get("attached_pic")
               for stream in data["streams"]):
        return line
    video = video_stream(data)
    rate = output_rate(video)
    interval = output_interval(rate)
    try:
        offset = float(video.get("start_time") or 0) - timeline_start(data)
    except (TypeError, ValueError):
        offset = 0.0
    if not math.isfinite(offset) or offset < 0:
        offset = 0.0
    return {**line, "origin": round(math.fmod(offset, interval), 9), "rate": rate,
            "fps": round(1 / interval, 9), "interval": interval}
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
```

Esperado: `Ran 49 tests … OK` (37 de `test_common.py` y 12 de `test_video.py`).

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_common.py
git commit -m "feat(common): la linea temporal compartida por plan, montaje y documento" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `plan.py` — lectura y validación del borrador

**Files:**
- Crear: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Crear: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: de `common`, `parse_target`, `tolerance`, `SILENCE_DB`, `timeline`, `MAX_SPANS`.
- Produces: `load(path) -> dict` (UTF-8 con o sin BOM), `number(value, name) -> float`,
  `flag(segment, key, default=False) -> bool`, `check_draft(draft, total, kind) -> list`
  (§9: rechaza **sin escribir** identificadores inexistentes o repetidos, límites fuera del medio,
  evidencias vacías y solapes estrictos; los contiguos son legales),
  `settings_of(draft, args, total, grid) -> dict` con las claves
  `{"target", "objetivo", "tolerance", "speed", "remove_pauses", "silence_db", "rate",
  "sample_rate"}`, y `words_of(transcription) -> list` (lista plana de palabras ordenada por `start`).
  Constantes `SHORT_CUT = 3.0`, `SHORT_VISUAL = 4.0`, `PAUSE_SHARE = 0.45`,
  `QUIET_MARGIN = 3.0`, `FAST_SPEED = 1.5`, `LOW_TARGET = 0.05`, `CODEC_MARGIN = 0.1`,
  `TEXT = ("title", "phrase", "reason", "audio_evidence")`, `BAR = 60`. `MAX_SPANS` **no** se redefine
  aquí: viene de `common` (tarea 7) porque el montaje aplica el mismo tope.
  `visual_evidence` solo es obligatorio cuando `kind == "video"` (añadido declarado).
- `settings` es lo que se publica tal cual en `seleccion-vN.json`: `target` es el texto que escribió el
  agente, `objetivo` sus segundos ya resueltos, `tolerance` la semianchura de la banda **en segundos**
  (un número, no un par de límites) y `rate` y `sample_rate` los de la línea temporal, para que `render`
  no tenga que abrir `metadata.json`.
- **La firma `settings_of(draft, args, total, grid)` es la definitiva**, con `grid` como cuarto
  parámetro: de ahí salen `rate` y `sample_rate`. Ningún plan posterior la reduce a
  `settings_of(draft, args, total)`; la rama de audio la llama igual, con la línea temporal de un medio
  sin imagen (`rate`, `fps` e `interval` a `None`).
- `check_draft` exige tipos estrictos (`int` para identificadores, prioridad y cortes de tema; `bool`
  para las marcas; listas y objetos donde toca) y rechaza duplicados en `depends_on` y
  `topics.cortes`; `settings_of` valida con el mismo rigor los ajustes que vengan del borrador.

- [ ] **Paso 1: escribir la prueba que falla**

Crea `scripts/test_plan.py`:

```python
"""Checks of the planner; the fast ones build their own media with the wave module."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import common
import plan
import video
from test_common import tone_wav

PAUSES = ((5, 6), (12, 12.8), (20, 21.5), (30, 30.5), (42, 43), (50, 51))
GRID = {"start": 0.0, "origin": 0.0, "rate": "25/1", "fps": 25.0, "interval": 0.04,
        "sample_rate": 48000}


def work_folder(root, seconds=60.0, pauses=PAUSES, rate="25/1", start="0.000000", videos=1):
    """A job folder like the one prepare leaves behind, without touching FFmpeg."""
    work = Path(root)
    tone_wav(work / "audio.wav", seconds=seconds, pauses=pauses)
    streams = [{"index": 0, "codec_type": "video", "r_frame_rate": rate, "avg_frame_rate": rate,
                "start_time": start, "width": 320, "height": 180}][:videos]
    streams.append({"index": videos, "codec_type": "audio", "sample_rate": "48000",
                    "start_time": "0.000000"})
    data = {"format": {"duration": f"{seconds:.6f}", "start_time": "0.000000",
                       "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": streams, "audio_stream": videos,
            "kind": "video" if videos else "audio"}
    # A stand-in for the medium: nothing opens it, but `plan --import` fingerprints it.
    (work / "medio.mp4").write_bytes(b"medio de prueba")
    # Identity and fingerprint live together in `source`, as prepare will write them.
    data["source"] = {"path": str(work / "medio.mp4"),
                      **common.fingerprint(work / "medio.mp4")}
    # prepare always writes the timeline, also in audio mode, where the grid keys are null.
    data["timeline"] = common.timeline(data)
    data["avisos"] = []
    (work / "metadata.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def cut(id_, start, end, priority=2, included=True, **extra):
    base = {"id": id_, "start": start, "end": end, "title": f"Tema {id_}",
            "phrase": f"Frase {id_}", "reason": "Motivo", "audio_evidence": "Tono",
            "visual_evidence": "Patrón", "priority": priority, "included": included,
            "pinned": False, "depends_on": [], "remove_pauses": True, "visual_only": False}
    base.update(extra)
    return base


def draft(work, segments, **head):
    body = {"parent": None, "request": "prueba", "settings": {"target": "40%", "speed": 1.25},
            "segments": segments, "excluded": [], "topics": []}
    body.update(head)
    (Path(work) / "borrador.json").write_text(json.dumps(body, ensure_ascii=False),
                                              encoding="utf-8")
    return body


def options(work, **extra):
    base = dict(work=str(work), draft=str(Path(work) / "borrador.json"), target=None, speed=None,
                pauses=None, silence_db=None, kind=None, dry_run=True, import_from=None,
                revert=None)
    base.update(extra)
    return argparse.Namespace(**base)


BASE = [cut(1, 2.0, 10.0, 1), cut(2, 11.0, 18.0, 1), cut(3, 19.0, 26.0, 2),
        cut(4, 28.0, 33.0, 2, included=False), cut(5, 40.0, 47.0, 3), cut(6, 49.0, 55.0, 3)]


class BorradorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        work_folder(self.work)

    def tearDown(self):
        self.temporary.cleanup()

    def test_a_correct_draft_is_accepted_whole(self):
        body = draft(self.work, BASE)
        segments = plan.check_draft(body, 60.0, "video")
        self.assertEqual([segment["id"] for segment in segments], [1, 2, 3, 4, 5, 6])

    def test_touching_cuts_are_legal_but_overlaps_are_not(self):
        plan.check_draft({"segments": [cut(1, 2.0, 5.0), cut(2, 5.0, 8.0)]}, 60.0, "video")
        with self.assertRaisesRegex(ValueError, "desordenado, solapado o fuera"):
            plan.check_draft({"segments": [cut(1, 2.0, 9.0), cut(2, 8.0, 12.0)]}, 60.0, "video")

    def test_every_rejection_of_section_nine(self):
        cases = {"identificador repetido": [cut(1, 2, 5), cut(1, 6, 8)],
                 "fuera del medio": [cut(1, 2, 5), cut(2, 59, 61)],
                 "evidencia vacía": [cut(1, 2, 5, visual_evidence="   ")],
                 "frase vacía": [cut(1, 2, 5, phrase="")],
                 "dependencia inexistente": [cut(1, 2, 5, depends_on=[9])],
                 "dependencia de sí mismo": [cut(1, 2, 5, depends_on=[1])],
                 "prioridad inválida": [cut(1, 2, 5, priority=4)],
                 "prioridad no entera": [cut(1, 2, 5, priority=2.0)],
                 "prioridad booleana": [cut(1, 2, 5, priority=True)],
                 "identificador no entero": [cut("a", 2, 5)],
                 "tiempo no finito": [cut(1, 2, float("inf"))],
                 "marca booleana": [cut(1, 2, 5, pinned="sí")],
                 "dependencia duplicada": [cut(1, 2, 5), cut(2, 6, 8),
                                          cut(3, 9, 11, depends_on=[1, 1])]}
        for label, segments in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                plan.check_draft({"segments": segments}, 60.0, "video")
        with self.assertRaisesRegex(ValueError, "al menos un corte"):
            plan.check_draft({"segments": []}, 60.0, "video")

    def test_audio_drafts_do_not_need_a_picture(self):
        segments = [dict(cut(1, 2, 5))]
        segments[0].pop("visual_evidence")
        plan.check_draft({"segments": segments}, 60.0, "audio")
        with self.assertRaisesRegex(ValueError, "visual_evidence"):
            plan.check_draft({"segments": segments}, 60.0, "video")

    def test_topics_must_point_at_real_cuts(self):
        body = {"segments": [cut(1, 2, 5)],
                "topics": [{"nombre": "Normativa", "cortes": [9], "imprescindible": True}]}
        with self.assertRaisesRegex(ValueError, "cita cortes que no existen"):
            plan.check_draft(body, 60.0, "video")
        bad = {"topics no es lista": None,
               "topics es un diccionario": {"nombre": "x", "cortes": [1]},
               "tema no es objeto": ["no soy un tema"],
               "cortes no es lista": [{"nombre": "x", "cortes": 1}],
               "cortes con booleano": [{"nombre": "x", "cortes": [True]}],
               "cortes duplicados": [{"nombre": "x", "cortes": [1, 1]}],
               "imprescindible no booleano": [{"nombre": "x", "cortes": [1],
                                              "imprescindible": "sí"}]}
        for label, topics in bad.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                plan.check_draft({"segments": [cut(1, 2, 5)], "topics": topics}, 60.0, "video")


class AjustesTest(unittest.TestCase):
    def test_the_call_overrides_the_draft(self):
        body = {"settings": {"target": "40%", "speed": 1.25}}
        base = plan.settings_of(body, options("."), 60.0, GRID)
        self.assertEqual(base, {"target": "40%", "objetivo": 24.0, "tolerance": 10.0, "speed": 1.25,
                                "remove_pauses": True, "silence_db": -50.0, "rate": "25/1",
                                "sample_rate": 48000})
        other = plan.settings_of(body, options(".", target="12s", speed=1.0, pauses="no",
                                               silence_db=-45.0), 60.0, GRID)
        self.assertEqual(other, {"target": "12s", "objetivo": 12.0, "tolerance": 10.0, "speed": 1.0,
                                 "remove_pauses": False, "silence_db": -45.0, "rate": "25/1",
                                 "sample_rate": 48000})
        bad = {"remove_pauses no booleano": ({"remove_pauses": "no"}, "booleano"),
               "speed nulo": ({"speed": None}, "número finito"),
               "speed no numérico": ({"speed": "x"}, "número finito"),
               "silence_db no numérico": ({"silence_db": "x"}, "número finito")}
        for label, (settings, pattern) in bad.items():
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, pattern):
                plan.settings_of({"settings": settings}, options("."), 60.0, GRID)

    def test_the_defaults_are_the_ones_of_the_spec(self):
        self.assertEqual(plan.settings_of({}, options("."), 60.0, GRID),
                         {"target": None, "objetivo": None, "tolerance": None, "speed": 1.25,
                          "remove_pauses": True, "silence_db": -50.0, "rate": "25/1",
                          "sample_rate": 48000})

    def test_speed_stays_between_one_and_two(self):
        for speed in (0.5, 2.5):
            with self.subTest(speed=speed), self.assertRaisesRegex(ValueError, "entre 1,0 y 2,0"):
                plan.settings_of({}, options(".", speed=speed), 60.0, GRID)


class PalabrasTest(unittest.TestCase):
    def test_words_are_flattened_and_sorted(self):
        transcription = {"segments": [{"words": [{"start": 2.0, "end": 2.4, "text": "dos"},
                                                 {"start": 1.0, "end": 1.4, "text": "uno"}]},
                                      {"words": []},
                                      {"words": [{"start": 3.0, "end": 3.4, "text": "tres"}]}]}
        self.assertEqual([word["start"] for word in plan.words_of(transcription)], [1.0, 2.0, 3.0])
        self.assertEqual(plan.words_of({"segments": [{"text": "sin palabras"}]}), [])
        self.assertEqual(plan.words_of(None), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `ModuleNotFoundError: No module named 'plan'`.

- [ ] **Paso 3: implementación mínima**

Crea `scripts/plan.py`:

```python
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
```

Nota sobre `type(key) is not int`: `True` es instancia de `int`, pero `type(True) is bool`, así que la
comprobación por tipo exacto rechaza `True` como identificador sin líneas adicionales.

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 9 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): leer y validar el borrador del agente" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: tramos por corte — bordes en cadena, fusión, islas, subcortes y corte vacío

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: `common.adjust_edges`, `common.islands`, `common.frames_for`, `common.samples_for`.
- Produces: `adjusted(segments, levels, words, threshold) -> list[row]`,
  `fuse(rows, interval) -> (list[row], list[str])`, `join(one, other) -> dict`,
  `spans_of(row, levels, grid, settings) -> list`, `untouched(row) -> bool`,
  `split(spans, frames, samples, grid, speed) -> list` (partes de
  `{"spans", "frames", "samples"}`, de `common.MAX_SPANS` tramos como mucho),
  `measure(rows, levels, grid, settings) -> list[row]`.
  Un `row` es `{"segment", "a", "b", "note"}` y, tras `measure`, también
  `{"spans", "length", "frames", "output", "samples", "empty", "subcuts", "source"}`.
  `empty` es verdadero cuando no quedan tramos, cuando `L < v/F` o cuando `N < 1`: ese corte vuelve a
  reservas y genera `corte_vacio`. La cadencia sale de `grid["fps"]` y la frecuencia de muestreo de
  `grid["sample_rate"]`, las dos claves que `prepare` escribe: ni `measure` ni `split` reciben `SR`
  suelto (tarea 9).
- `split` reparte **los dos** totales del corte, `N` y `M`: cada subcorte menos el último toma
  `frames_for` y `samples_for` de sus propios tramos y el último se queda con lo que reste de `N` y de
  `M` (§7.5), igual que hace `render.subcuts` en el plan de montaje. Recalcular `M` subcorte a subcorte
  pierde muestras siempre que `N/F·SR` no sea entero.
- `fuse` solo funde vecinos que comparten `included`: una reserva pegada a un corte incluido no puede
  arrastrarlo fuera del montaje.
- `fuse` remapea las `depends_on` de todas las filas que apunten a un id absorbido hacia el id
  conservado (siguiendo cadenas, sin duplicados ni autodependencias), porque de otro modo
  `dependency_warnings` (tarea 13) emitiría un `dependencia_excluida` falso.
- `fuse` deja en cada fila resultante `row["absorbed"]`: la lista ordenada de los ids que esa fila
  absorbió (vacía si ninguno), para que `topic_warnings` (tarea 13) siga dando por cubierto un tema
  cuyo corte citado sobrevive con otro id tras la fusión.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class TramosTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)
        self.grid = self.data["timeline"]
        self.levels = common.energy(self.work / "audio.wav")
        self.settings = {"speed": 1.25, "remove_pauses": True, "silence_db": -50.0,
                         "target": None, "objetivo": None}

    def tearDown(self):
        self.temporary.cleanup()

    def measure(self, segments, **extra):
        rows, notes = plan.fuse(plan.adjusted(segments, self.levels, [], -50.0),
                                self.grid["interval"])
        settings = dict(self.settings, **extra)
        return plan.measure(rows, self.levels, self.grid, settings), notes

    def test_spans_frames_and_samples_of_one_cut(self):
        rows, _ = self.measure([cut(1, 2.0, 10.0, 1)])
        self.assertEqual(rows[0]["spans"], [[2.0, 5.08], [5.92, 10.0]])
        self.assertAlmostEqual(rows[0]["length"], 7.16)
        self.assertEqual(rows[0]["frames"], 143)
        self.assertEqual(rows[0]["samples"], 274560)
        self.assertFalse(rows[0]["empty"])

    def test_keeping_pauses_keeps_one_span(self):
        rows, _ = self.measure([cut(1, 2.0, 10.0, 1)], remove_pauses=False)
        self.assertEqual(rows[0]["spans"], [[2.0, 10.0]])
        self.assertEqual(rows[0]["frames"], 160)
        rows, _ = self.measure([cut(1, 2.0, 10.0, 1, visual_only=True)])
        self.assertEqual(rows[0]["spans"], [[2.0, 10.0]])

    def test_a_cut_swallowed_by_a_pause_is_empty(self):
        rows, _ = self.measure([cut(1, 20.1, 21.4, 2)])
        self.assertEqual(rows[0]["spans"], [])
        self.assertTrue(rows[0]["empty"])

    def test_touching_cuts_are_merged_with_the_lowest_id(self):
        rows, notes = self.measure([cut(1, 2.0, 5.0, 2), cut(2, 5.0, 8.0, 1),
                                    cut(4, 34.0, 35.0, 2), cut(5, 35.04, 36.0, 2),
                                    cut(3, 40.0, 47.0, 3)])
        # 4 and 5 sit exactly one frame (the 0.04 s interval) apart: that is not "touching", so
        # they must stay separate even though every other gap here is either 0 or many seconds.
        self.assertEqual([row["segment"]["id"] for row in rows], [1, 4, 5, 3])
        self.assertEqual(rows[0]["segment"]["priority"], 1)
        self.assertEqual(rows[0]["segment"]["title"], "Tema 1 · Tema 2")
        self.assertEqual(rows[0]["spans"], [[2.0, 5.08], [5.92, 8.0]])
        self.assertEqual(notes, ["fusion: 1 + 2 -> 1"])

    def test_an_included_cut_never_merges_with_a_reserve(self):
        rows, notes = self.measure([cut(1, 2.0, 5.0, 2), cut(2, 5.0, 8.0, 1, included=False),
                                    cut(3, 40.0, 47.0, 3)])
        self.assertEqual([row["segment"]["id"] for row in rows], [1, 2, 3])
        self.assertEqual([row["segment"]["included"] for row in rows], [True, False, True])
        self.assertEqual(notes, [])

    def test_dependencies_follow_the_fused_cut(self):
        rows, notes = self.measure([cut(1, 2.0, 5.0, 2), cut(2, 5.0, 8.0, 1),
                                    cut(3, 40.0, 47.0, 3, depends_on=[2])])
        self.assertEqual([row["segment"]["id"] for row in rows], [1, 3])
        self.assertEqual(rows[1]["segment"]["depends_on"], [1])
        self.assertEqual(notes, ["fusion: 1 + 2 -> 1"])

    def test_the_adjustment_never_crosses_the_neighbour(self):
        # Measured before fuse: the clamp is what keeps them from overlapping, and the merge of
        # the pair that ends up touching is checked by the test above.
        rows = plan.adjusted([cut(1, 2.0, 11.5, 1), cut(2, 11.6, 18.0, 1)], self.levels, [], -50.0)
        self.assertEqual([(row["a"], row["b"]) for row in rows], [(2.0, 11.6), (11.6, 18.0)])
        # Without `floor_`, cut 2's start would drift back into the pause behind cut 1's end
        # (a2 = 6.0): the clamp is what keeps it at the neighbour's edge instead.
        rows = plan.adjusted([cut(1, 2.0, 6.3, 1), cut(2, 6.4, 10.0, 1)], self.levels, [], -50.0)
        self.assertEqual([(row["a"], row["b"]) for row in rows], [(2.0, 6.3), (6.3, 10.0)])

    def test_more_than_forty_spans_become_subcuts(self):
        # range(48) still leaves 49 spans (split as [40, 9]), but unlike range(49) its rounding
        # does not happen to cancel out: recomputing M per subcut would silently disagree with the
        # whole cut's total, so this case actually discriminates between the two approaches.
        pauses = tuple((1.0 + 1.2 * index, 1.4 + 1.2 * index) for index in range(48))
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = Path(temporary)
            data = work_folder(work, pauses=pauses)
            levels = common.energy(work / "audio.wav")
            rows, _ = plan.fuse(plan.adjusted([cut(1, 0.5, 59.0, 1)], levels, [], -50.0),
                                data["timeline"]["interval"])
            rows = plan.measure(rows, levels, data["timeline"], self.settings)
            self.assertEqual(len(rows[0]["spans"]), 49)
            self.assertEqual([len(part["spans"]) for part in rows[0]["subcuts"]], [40, 9])
            self.assertEqual(sum(part["frames"] for part in rows[0]["subcuts"]), rows[0]["frames"])
            self.assertEqual(sum(part["samples"] for part in rows[0]["subcuts"]),
                             rows[0]["samples"])
            # 25 fps and 48000 Hz divide exactly, so the sums above hold however M is worked out.
            # At 30000/1001 fps and 44100 Hz they do not: only sharing out M like N keeps the sum.
            odd = dict(data["timeline"], rate="30000/1001", fps=30000 / 1001,
                       interval=1001 / 30000, sample_rate=44100)
            rows, _ = plan.fuse(plan.adjusted([cut(1, 0.5, 59.0, 1)], levels, [], -50.0),
                                odd["interval"])
            rows = plan.measure(rows, levels, odd, self.settings)
            self.assertGreater(len(rows[0]["subcuts"]), 1)
            # Pinned to the exact value: recomputing M per subcut would total 1 659 819 instead.
            self.assertEqual(rows[0]["samples"], 1659818)
            self.assertEqual(sum(part["frames"] for part in rows[0]["subcuts"]), rows[0]["frames"])
            self.assertEqual(sum(part["samples"] for part in rows[0]["subcuts"]),
                             rows[0]["samples"])
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Tramos -v
```

Esperado: 8 errores `AttributeError: module 'plan' has no attribute 'fuse'`.

- [ ] **Paso 3: implementación mínima**

Añade a `plan.py`:

```python
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
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 17 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): tramos por corte con bordes, fusion, subcortes y corte vacio" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: estimación exacta, retención, presupuesto y los seis estados

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: las filas medidas de la tarea 11 y `common.tolerance`.
- Produces: `retention(rows, settings) -> float` (ρ sobre **todos** los candidatos, incluidos y reservas,
  con ρ = 1 en `visual_only` y en los que conservan pausas; devuelve 1,0 exacto cuando
  `settings["remove_pauses"]` es falso, sin ni siquiera recorrer las filas, y en cualquier otro caso
  acota el cociente a `[1e-6, 1.0]` porque el ajuste a la rejilla puede alargar un tramo hasta casi un
  fotograma y ρ nunca puede superar 1 por definición), `band(target) -> ([float, float], float)`,
  `state_of(estimate, essentials, target, top) -> str` (uno de `sin_objetivo`, `inalcanzable`,
  `inviable`, `por_encima`, `por_debajo`, `ok`, evaluados **en ese orden**: el primero que se cumple
  gana, y `ok` es el caso que sobrevive a los cinco anteriores; el techo llega ya resuelto en `top`,
  así que no hace falta pasar `total`) y
  `estimate_of(rows, included, settings, total, grid) -> dict` con las claves
  `cortes`, `origen`, `tras_pausas`, `salida`, `margen`, `porcentaje`, `objetivo`, `banda`, `retencion`,
  `esenciales`, `presupuesto` (`B = T_obj·v/ρ`), `minimo`, `maximo` (`T_max = T_orig·ρ/v`) y `estado`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
def prepared(segments, levels, grid, target=None, speed=1.25, pauses=True, silence_db=-50.0):
    """Measured rows, included ids, settings and estimate: the start of every check below."""
    settings = {"target": target, "objetivo": common.parse_target(target, 60.0), "speed": speed,
               "remove_pauses": pauses, "silence_db": silence_db}
    rows, _ = plan.fuse(plan.adjusted(segments, levels, [], silence_db), grid["interval"])
    rows = plan.measure(rows, levels, grid, settings)
    included = {row["segment"]["id"] for row in rows
               if row["segment"]["included"] and not row["empty"]}
    return rows, included, settings, plan.estimate_of(rows, included, settings, 60.0, grid)


class EstimacionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)
        self.grid = self.data["timeline"]
        self.levels = common.energy(self.work / "audio.wav")

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, target, segments=None, speed=1.25, pauses=True):
        segments = BASE if segments is None else segments
        return prepared(segments, self.levels, self.grid, target=target, speed=speed,
                        pauses=pauses)[3]

    def test_the_whole_estimate_of_the_reference_draft(self):
        self.assertEqual(self.report("40%"),
                         {"cortes": 5, "origen": 35.0, "tras_pausas": 30.48, "salida": 24.36,
                          "margen": 0.1, "porcentaje": 40.6, "objetivo": 24.0,
                          "banda": [14.0, 34.0], "retencion": 0.878, "esenciales": 10.8,
                          "presupuesto": 34.169, "minimo": 18.0, "maximo": 42.144,
                          "estado": "ok"})

    def test_the_six_states(self):
        self.assertEqual(self.report(None)["estado"], "sin_objetivo")
        base = self.report("40%")
        self.assertEqual(base["estado"], "ok")
        self.assertEqual(self.report("12s")["estado"], "por_encima")
        self.assertEqual(self.report("40s")["estado"], "por_debajo")
        self.assertEqual(self.report("1%")["estado"], "inviable")
        self.assertEqual(self.report("55s")["estado"], "inalcanzable")
        # Strict edges of section 7.6: at target == top + margin the comparison must stay a
        # `>`, so equality still falls through to `por_debajo` instead of `inalcanzable`.
        self.assertEqual(self.report(f"{base['maximo'] + 10}s")["estado"], "por_debajo")
        # At essentials == target + margin the essentials check must also stay a `>`, so
        # equality falls through past `inviable` to whatever the full estimate resolves to.
        self.assertEqual(self.report(f"{base['esenciales'] - 10}s")["estado"], "por_encima")

    def test_the_band_of_a_short_target_is_the_ten_second_floor(self):
        self.assertEqual(self.report("12s")["banda"], [2.0, 22.0])
        self.assertEqual(self.report("40s")["banda"], [30.0, 50.0])
        # The floor also clamps the lower edge at zero instead of going negative.
        self.assertEqual(self.report("1%")["banda"], [0.0, 10.6])

    def test_retention_counts_every_candidate(self):
        # A reserve (id 4, included=False) and an off-grid visual_only cut (id 2) are both
        # needed to discriminate `retention`: with every edge on the sampling grid, `length`
        # equals `source` and the `untouched` branch is a no-op.
        segments = [cut(1, 2.0, 10.0, 1), cut(2, 19.013, 21.027, 2, visual_only=True),
                    cut(3, 40.0, 47.0, 2, remove_pauses=False),
                    cut(4, 50.0, 55.0, 3, included=False)]
        self.assertAlmostEqual(self.report("40%", segments)["retencion"], 0.920051, places=6)
        # A global remove_pauses=False keeps every candidate whole: ratio is exactly one.
        self.assertEqual(self.report("40%", segments, pauses=False)["retencion"], 1.0)

    def test_keeping_pauses_and_speed_change_the_output(self):
        self.assertEqual(self.report("40%", pauses=False)["salida"], 28.0)
        self.assertEqual(self.report("40%", speed=1.0)["salida"], 30.48)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Estimacion -v
```

Esperado: 5 errores `AttributeError: module 'plan' has no attribute 'estimate_of'`.

- [ ] **Paso 3: implementación mínima**

```python
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
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 22 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): estimacion exacta, retencion, presupuesto y los seis estados" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: la tabla de avisos de §7.7

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: `common.warning`, `common.bounds`, `common.ENERGY_FLOOR`, las filas medidas y
  `row["absorbed"]` de `fuse` (tarea 11).
- Produces: `percentile(levels, a, b, share=0.10) -> float`,
  `cut_warnings(row, levels, settings) -> list` (`corte_vacio`, `borde_en_voz`, `corte_breve`,
  `visual_breve`, `pausas_excesivas`, `sin_pausas_detectadas`),
  `global_warnings(estimate, settings, total, has_words) -> list` (`velocidad_alta`,
  `objetivo_muy_bajo`, `objetivo_muy_alto`, `esenciales_superan_objetivo` y
  `sin_marcas_por_palabra`), `dependency_warnings(rows, included) -> list` (`dependencia_excluida`) y
  `topic_warnings(draft, rows, included) -> list` (`tema_sin_cubrir`): trece códigos en total.
  `topic_warnings` considera cubierto un tema si alguno de sus cortes está en `included` o en el
  `absorbed` de una fila incluida, porque tras una fusión el corte citado sigue en el montaje con otro
  id.
  `huecos_pts`, `fuente_vfr` y `cobertura_baja` no se emiten aquí: los producen `prepare` y `compare`;
  `plan` copia los que `metadata.json` traiga en la clave `avisos`.
- `cut_warnings` usa `settings` de verdad: el umbral de `sin_pausas_detectadas` es
  `settings["silence_db"] − QUIET_MARGIN` (−53 dBFS con el −50 por defecto, que es lo que fija §7.7) y
  el mensaje nombra ese umbral, no el literal. Los dos avisos de pausas (`pausas_excesivas` y
  `sin_pausas_detectadas`) se saltan cuando el corte no quita pausas, sea por `remove_pauses` global o
  por el del corte: sin descartes no hay nada que medir.
- `percentile` no repite la conversión de segundos a índices: la pide a `common.bounds` (tarea 4).

- [ ] **Paso 1: escribir la prueba que falla**

```python
class AvisosTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)
        self.grid = self.data["timeline"]
        self.levels = common.energy(self.work / "audio.wav")

    def tearDown(self):
        self.temporary.cleanup()

    def codes(self, segments, target="40%", speed=1.25, has_words=True, data=None,
              silence_db=-50.0, **head):
        rows, included, settings, report = prepared(segments, self.levels, self.grid, target=target,
                                                    speed=speed, silence_db=silence_db)
        found = plan.global_warnings(report, settings, 60.0, has_words)
        found += (plan.dependency_warnings(rows, included)
                 + plan.topic_warnings(head, rows, included))
        for row in rows:
            if row["segment"].get("included", False) and (row["segment"]["id"] in included
                                                          or row["empty"]):
                found += plan.cut_warnings(row, self.levels, settings)
        # Same tail as `video_plan`: what prepare left in `metadata.json` travels unchanged.
        found += [common.warning(item["codigo"], item["mensaje"], cut=item.get("corte"))
                  for item in (data or self.data).get("avisos", [])]
        return [(item["codigo"], item["corte"], item["bloquea"]) for item in found]

    def test_an_empty_cut_blocks_and_hides_the_other_warnings(self):
        found = self.codes([cut(1, 2.0, 10.0, 1), cut(2, 20.1, 21.4, 2)])
        # Not just "corte_vacio" is present: nothing else about cut 2 survives alongside it.
        self.assertEqual([item for item in found if item[1] == 2], [("corte_vacio", 2, True)])

    def test_dependencies_and_topics_block(self):
        found = self.codes([cut(1, 2.0, 10.0, 1, depends_on=[2]),
                            cut(2, 19.0, 26.0, 3, included=False)])
        self.assertIn(("dependencia_excluida", 1, True), found)
        found = self.codes([cut(1, 2.0, 10.0, 1), cut(2, 19.0, 26.0, 3, included=False)],
                           topics=[{"nombre": "Normativa", "cortes": [2], "imprescindible": True}])
        self.assertIn(("tema_sin_cubrir", None, True), found)

    def test_topics_follow_the_fused_cut(self):
        # 1 (2.0-7.0) and 2 (7.0-10.0) touch and fuse into 1: a topic that only cites 2 still
        # counts it covered, since 2 rides inside 1's cut in the render.
        found = self.codes([cut(1, 2.0, 7.0, 1), cut(2, 7.0, 10.0, 1)],
                           topics=[{"nombre": "Normativa", "cortes": [2], "imprescindible": True}])
        self.assertNotIn(("tema_sin_cubrir", None, True), found)
        # The opposite: two reserves (19.0-24.0 and 24.0-26.0) fuse together, but neither
        # survives into `included`, so a topic that cites only the absorbed reserve still has
        # nothing to show for it.
        found = self.codes([cut(1, 2.0, 10.0, 1), cut(2, 19.0, 24.0, 2, included=False),
                            cut(3, 24.0, 26.0, 2, included=False)],
                           topics=[{"nombre": "Normativa", "cortes": [3], "imprescindible": True}])
        self.assertIn(("tema_sin_cubrir", None, True), found)

    def test_short_visual_and_fast_warnings(self):
        found = self.codes([cut(1, 2.0, 10.0, 1), cut(2, 19.0, 21.0, 2, visual_only=True),
                            cut(3, 40.0, 47.0, 2, remove_pauses=False)], speed=1.75)
        self.assertIn(("velocidad_alta", None, False), found)
        self.assertIn(("visual_breve", 2, False), found)
        self.assertIn(("corte_breve", 1, False), self.codes([cut(1, 11.5, 13.5, 2),
                                                             cut(2, 40.0, 47.0, 1)]))
        # Both pause warnings are skipped by the cut's own mark, even over a loud, pause-free
        # background that would otherwise read as an undetected silence: a visual_only cut
        # (13.5-18.0) and one with remove_pauses=False (31.0-38.0), neither touching a real pause.
        guarded = self.codes([cut(1, 2.0, 10.0, 1), cut(2, 13.5, 18.0, 2, visual_only=True),
                              cut(3, 31.0, 38.0, 2, remove_pauses=False)])
        for key in (2, 3):
            marked = {item[0] for item in guarded if item[1] == key}
            self.assertNotIn("pausas_excesivas", marked)
            self.assertNotIn("sin_pausas_detectadas", marked)

    def test_pauses_and_background_warnings(self):
        found = self.codes([cut(1, 11.8, 13.0, 2), cut(2, 40.0, 47.0, 1)])
        self.assertIn(("pausas_excesivas", 1, False), found)
        self.assertIn(("sin_pausas_detectadas", 1, False),
                      self.codes([cut(1, 2.0, 5.0, 1), cut(2, 40.0, 47.0, 1)]))

    def test_the_quiet_floor_follows_the_silence_setting(self):
        rows, _, settings, _ = prepared([cut(1, 2.0, 5.0, 1), cut(2, 40.0, 47.0, 1)], self.levels,
                                        self.grid, target="40%", silence_db=-45.0)
        found = plan.cut_warnings(rows[0], self.levels, settings)
        message = next(item["mensaje"] for item in found
                       if item["codigo"] == "sin_pausas_detectadas")
        # With --silence-db -45 the quiet floor is −48 dBFS, not the −53 of the default −50.
        self.assertIn("−48 dBFS", message)
        # A job that keeps its pauses removes none: neither pause warning has anything to measure.
        kept = dict(settings, remove_pauses=False)
        codes = [item["codigo"] for item in plan.cut_warnings(rows[0], self.levels, kept)]
        self.assertNotIn("sin_pausas_detectadas", codes)
        self.assertNotIn("pausas_excesivas", codes)

    def test_target_speed_and_propagated_warnings(self):
        self.assertIn(("objetivo_muy_bajo", None, False),
                      self.codes([cut(1, 2.0, 10.0, 1), cut(2, 40.0, 47.0, 2)], target="2s"))
        self.assertIn(("esenciales_superan_objetivo", None, True), self.codes(BASE, target="1%"))
        self.assertIn(("objetivo_muy_alto", None, False), self.codes(BASE, target="55s"))
        self.assertIn(("sin_marcas_por_palabra", None, False),
                      self.codes(BASE, has_words=False))
        # `fuente_vfr` is prepare's: plan neither measures the cadence nor re-reads the streams,
        # it only copies what `metadata.json` already carries in `avisos`.
        carried = json.loads(json.dumps(self.data))
        carried["avisos"] = [common.warning("fuente_vfr", "La fuente declara cadencia variable "
                                            "(25/1 frente a 24000/1001).")]
        self.assertIn(("fuente_vfr", None, False), self.codes(BASE, data=carried))

    def test_edges_inside_speech_are_reported(self):
        self.assertIn(("borde_en_voz", 1, False), self.codes([cut(1, 4.0, 4.5, 1),
                                                              cut(2, 40.0, 47.0, 1)]))

    def test_the_tenth_percentile_of_a_quiet_cut(self):
        self.assertEqual(plan.percentile(self.levels, 20.0, 21.5), common.ENERGY_FLOOR)
        self.assertGreater(plan.percentile(self.levels, 2.0, 5.0), -50.0 - plan.QUIET_MARGIN)
        # An empty window (a == b) has nothing to sort: the floor is the fallback, not a crash.
        self.assertEqual(plan.percentile(self.levels, 5.0, 5.0), common.ENERGY_FLOOR)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Avisos -v
```

Esperado: 9 errores `AttributeError: module 'plan' has no attribute 'global_warnings'`.

- [ ] **Paso 3: implementación mínima**

```python
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
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 31 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): los trece avisos que calcula el planificador" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: alternativas y sugerencias

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: `measure`, `estimate_of`, `band` de las tareas 11 y 12.
- Produces: `copies(rows) -> list[row]` (filas nuevas que comparten `segment`, `a`, `b` y `note`),
  `alternatives(rows, levels, grid, settings, included, total) -> list` con **las cuatro**
  combinaciones `{1,0; la velocidad actual o 1,25} × {pausas sí; pausas no}`, cada una con
  `{"velocidad", "pausas", "salida", "porcentaje", "estado"}`;
  `movable(row, rows, included, *, essentials=False) -> bool` (nunca `pinned`, nunca aquello de lo
  que dependa un corte incluido; la prioridad 1 solo se protege si `essentials` es `False`) y
  `suggestions(rows, included, settings, report) -> list` con
  `{"tipo", "texto"}` más `cortes` o `valor`. Las sugerencias no se aplican solas: solo se muestran.
- `suggestions` no recibe `total` ni `grid`: la banda, el estado, los esenciales, el mínimo y el
  máximo llegan ya resueltos en `report`, y lo demás sale de `settings` y de las propias filas.
  `alternatives` tampoco recibe `sample_rate` suelto: `measure` lo lee de `grid` desde la tarea 11.
- Con `essentials=True`, `movable` deja pasar la prioridad 1 (lo usa `sacrificar` para elegir qué
  esenciales renunciar) pero sigue excluyendo siempre `pinned` y los cortes de los que dependa un
  incluido. `anadir` salta las reservas cuya dependencia siga excluida (no propone una reserva sola
  si lo que necesita no entra también). Ambas reglas vienen de §7.6.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class AlternativasTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)
        self.grid = self.data["timeline"]
        self.levels = common.energy(self.work / "audio.wav")

    def tearDown(self):
        self.temporary.cleanup()

    def prepared(self, target, segments=None, speed=1.25):
        """The module helper of task 12, with the fixtures of this class."""
        return prepared(BASE if segments is None else segments, self.levels, self.grid,
                        target=target, speed=speed)

    def test_the_four_combinations_of_speed_and_pauses(self):
        rows, included, settings, _ = self.prepared("40%")
        self.assertEqual(plan.alternatives(rows, self.levels, self.grid, settings, included, 60.0),
                         [{"velocidad": 1.0, "pausas": True, "salida": 30.48,
                           "porcentaje": 50.8, "estado": "ok"},
                          {"velocidad": 1.0, "pausas": False, "salida": 35.0,
                           "porcentaje": 58.33, "estado": "por_encima"},
                          {"velocidad": 1.25, "pausas": True, "salida": 24.36,
                           "porcentaje": 40.6, "estado": "ok"},
                          {"velocidad": 1.25, "pausas": False, "salida": 28.0,
                           "porcentaje": 46.67, "estado": "ok"}])

    def test_a_speed_of_one_still_offers_four(self):
        rows, included, settings, _ = self.prepared("40%", speed=1.0)
        rows_out = plan.alternatives(rows, self.levels, self.grid, settings, included, 60.0)
        self.assertEqual([(item["velocidad"], item["pausas"]) for item in rows_out],
                         [(1.0, True), (1.0, False), (1.25, True), (1.25, False)])

    def test_alternatives_do_not_disturb_the_measured_rows(self):
        rows, included, settings, _ = self.prepared("40%")
        plan.alternatives(rows, self.levels, self.grid, settings, included, 60.0)
        self.assertEqual(sum(row["frames"] for row in rows if row["segment"]["id"] in included),
                         609)

    def test_suggestions_for_each_state(self):
        for target, tipo in (("12s", "quitar"), ("40s", "anadir"), ("55s", "objetivo")):
            with self.subTest(target=target):
                rows, included, settings, report = self.prepared(target)
                hints = plan.suggestions(rows, included, settings, report)
                self.assertEqual([hint["tipo"] for hint in hints], [tipo])
        rows, included, settings, report = self.prepared("1%")
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual([hint["tipo"] for hint in hints],
                         ["velocidad", "sacrificar", "porcentaje"])
        self.assertEqual(hints[0]["valor"], 1.3)
        self.assertEqual(hints[1]["cortes"], [1])
        self.assertEqual(hints[2]["valor"], 18.0)
        rows, included, settings, report = self.prepared("40%")
        self.assertEqual(plan.suggestions(rows, included, settings, report), [])
        rows, included, settings, report = self.prepared(None)
        self.assertEqual(plan.suggestions(rows, included, settings, report), [])
        # Beyond x1,5 the speed hint disappears; sacrificar and porcentaje still show up.
        essentials = [cut(1, 2.0, 10.0, 1), cut(2, 11.0, 18.0, 1), cut(3, 19.0, 26.0, 1)]
        rows, included, settings, report = self.prepared("1s", essentials)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual([hint["tipo"] for hint in hints], ["sacrificar", "porcentaje"])
        # Just under the cap the speed hint appears, rounded up to the nearest 0,05.
        rows, included, settings, report = self.prepared("3.5s", essentials)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual(hints[0]["tipo"], "velocidad")
        self.assertEqual(hints[0]["valor"], 1.45)
        # A second reserve that no longer fits once the first is taken is left out too, not
        # just the ones blocked by an unmet dependency.
        segments = [cut(1, 0.2, 5.0, 2), cut(2, 31.0, 33.5, 2, included=False),
                   cut(3, 34.0, 59.0, 2, included=False)]
        rows, included, settings, report = self.prepared("14s", segments)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual(hints[0]["cortes"], [2])

    def test_a_suggestion_never_touches_essentials_pinned_or_dependencies(self):
        # 1 is essential, 2 is pinned and 4 depends on 3: only 4, plain and unprotected, is
        # free to remove. Each guard here is load-bearing (see the mutation proof of the
        # fixes round in the task report): dropping any one of the three lets its own cut
        # through instead of leaving `cortes` at [4].
        segments = [cut(1, 0.2, 5.0, 1), cut(2, 6.2, 12.0, 3, pinned=True),
                    cut(3, 13.0, 20.0, 3), cut(4, 21.7, 30.0, 3, depends_on=[3])]
        rows, included, settings, report = self.prepared("1s", segments)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual(hints[0]["cortes"], [4])
        # A reserve whose dependency stays excluded is never proposed on its own: 2 depends
        # on 3, and only 3 (which fits by itself) is recovered.
        segments = [cut(1, 0.2, 5.0, 2),
                   cut(2, 31.0, 33.0, 2, included=False, depends_on=[3]),
                   cut(3, 34.0, 55.0, 2, included=False)]
        rows, included, settings, report = self.prepared("14s", segments)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual(hints[0]["cortes"], [3])
        # A pinned essential is never sacrificed either: with nothing else to offer, the
        # whole suggestion is dropped instead of touching it.
        segments = [cut(1, 2.0, 20.0, 1, pinned=True), cut(2, 40.0, 47.0, 3),
                   cut(3, 49.0, 55.0, 3)]
        rows, included, settings, report = self.prepared("0.1s", segments)
        hints = plan.suggestions(rows, included, settings, report)
        self.assertEqual([hint["tipo"] for hint in hints], ["porcentaje"])
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Alternativas -v
```

Esperado: 5 errores `AttributeError: module 'plan' has no attribute 'alternatives'`.

- [ ] **Paso 3: implementación mínima**

```python
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
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 36 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): las cuatro alternativas y las sugerencias por estado" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: `propuesta-vN.md`, el recorrido de texto y la fila publicada de cada corte

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: las filas medidas, la estimación, las alternativas y las sugerencias de las tareas 11–14, y
  `common.clock` de la tarea 7.
- Produces: `cell(text) -> str` (escapa `|` y saltos de línea), `length(cut) -> float` (segundos de
  salida de una fila publicada), `cut_row(row, index, place, grid) -> dict` (la fila tal como se
  publica: `id`, `numero`, `title`, `phrase`, `reason`, `audio_evidence`, `visual_evidence`,
  `priority`, `pinned`, `visual_only`, `remove_pauses`, `depends_on`, `start`, `end`, `spans`,
  `frames`, `samples`, `salida` y `subcuts`), `bar(rows, included, total, width=BAR) -> str` y
  `proposal(plan, reserves, total, name) -> str`. La propuesta contiene, en este orden: cabecera,
  cadena de técnicas, cambios, avisos, tabla de cortes, reservas, exclusiones deliberadas,
  alternativas, sugerencias, recorrido y ejemplos de respuesta (§9).
  El `numero` de la tabla es el que el usuario cita («el 7»); el `id` es el identificador estable.
- `clock` **no** se define aquí: es la de `common` (tarea 7), la misma que usará el documento. Trunca al
  segundo, así que `5,72 s` se lee `0:05`.
- **El «coste de montaje» no sale de aquí.** §9 pide que, tras cada edición, el agente muestre el diff,
  la estimación nueva y el coste de montaje («reutiliza 36 de 38 · 2 cortes nuevos · ≈2 min»). Lo
  primero y lo segundo los da `proposal`; lo tercero procede de **`render --dry-run`** (plan de
  montaje), que sin montar nada cuenta los cortes que están en la caché y los nuevos, estima el tiempo
  e imprime `{reused, new, eta_s}`. `plan.py` no sabe qué hay en `cortes/`, así que ni lo calcula ni lo
  escribe en `propuesta-vN.md`: el agente añade esa línea al mostrar la propuesta, con la salida de esa
  orden.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class PropuestaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)
        self.grid = self.data["timeline"]
        self.levels = common.energy(self.work / "audio.wav")

    def tearDown(self):
        self.temporary.cleanup()

    def test_a_cell_never_breaks_the_table(self):
        self.assertEqual(plan.cell("a | b\nc"), "a \\| b c")

    def test_the_published_row_of_a_cut(self):
        settings = {"target": "40%", "objetivo": 24.0, "speed": 1.25, "remove_pauses": True,
                    "silence_db": -50.0}
        rows, _ = plan.fuse(plan.adjusted([cut(1, 2.0, 10.0, 1)], self.levels, [], -50.0),
                            self.grid["interval"])
        rows = plan.measure(rows, self.levels, self.grid, settings)
        row = plan.cut_row(rows[0], 1, 0.0, self.grid)
        self.assertEqual((row["numero"], row["id"], row["priority"]), (1, 1, 1))
        self.assertEqual((row["start"], row["end"]), (2.0, 10.0))
        self.assertEqual(row["spans"], [[2.0, 5.08], [5.92, 10.0]])
        self.assertEqual((row["frames"], row["samples"]), (143, 274560))
        self.assertEqual(row["salida"], [0.0, 5.72])
        self.assertEqual(row["subcuts"], [{"spans": [[2.0, 5.08], [5.92, 10.0]],
                                           "frames": 143, "samples": 274560}])
        self.assertAlmostEqual(plan.length(row), 5.72)

    def test_the_text_timeline_marks_what_is_kept(self):
        settings = {"target": None, "objetivo": None, "speed": 1.25, "remove_pauses": True,
                    "silence_db": -50.0}
        rows, _ = plan.fuse(plan.adjusted(BASE, self.levels, [], -50.0), self.grid["interval"])
        rows = plan.measure(rows, self.levels, self.grid, settings)
        included = {row["segment"]["id"] for row in rows if row["segment"]["included"]}
        self.assertEqual(plan.bar(rows, included, 60.0),
                         "··########·#######·#######··············#######··######·····")
        self.assertEqual(len(plan.bar(rows, included, 60.0)), plan.BAR)

    def test_the_proposal_has_every_section_of_section_nine(self):
        body = {"version": 1, "changes": ["propuesta inicial"], "warnings": [],
                "settings": {"speed": 1.25}, "excluidos": [{"title": "Saludos",
                                                            "reason": "Sin contenido"}],
                "estimate": {"cortes": 1, "origen": 8.0, "tras_pausas": 7.16, "salida": 5.72,
                             "porcentaje": 9.53, "objetivo": 6.0, "banda": [0.0, 16.0],
                             "estado": "ok"},
                "segments": [{"numero": 1, "id": 1, "priority": 1, "phrase": "Frase 1",
                              "start": 2.0, "end": 10.0, "salida": [0.0, 5.72]}],
                "alternativas": [{"velocidad": 1.0, "pausas": True, "salida": 7.16,
                                  "porcentaje": 11.93, "estado": "ok"}],
                "sugerencias": [], "recorrido": "#" * plan.BAR}
        reserves = [{"id": 4, "start": 28.0, "end": 33.0, "reason": "Ejemplo alternativo"}]
        text = plan.proposal(body, reserves, 60.0, "medio.mp4")
        for heading in ("# Propuesta v1", "## Cambios", "## Avisos", "## Cortes", "## Reservas",
                        "## Exclusiones deliberadas", "## Alternativas", "## Sugerencias",
                        "## Recorrido", "## Cómo responder"):
            self.assertIn(heading, text)
        # clock truncates, so 5,72 s of output is read as 0:05 everywhere.
        self.assertIn("Original 1:00 · objetivo 0:06 (banda 0:00–0:16) · estimación 0:05 "
                      "(9,5 %) · estado **ok**", text)
        self.assertIn("1 cortes · 0:08 → sin pausas 0:07 → ×1,25 → 0:05", text)
        self.assertIn("| 1 | 0:02–0:10 | 0:00–0:05 (6 s) | 1 | Frase 1 |", text)
        self.assertIn("| 4 | 0:28–0:33 | Ejemplo alternativo |", text)
        self.assertIn("| Saludos | Sin contenido |", text)
        self.assertIn("| ×1,00 | sí | 0:07 | 11,9 % | ok |", text)
        self.assertIn("- ninguna: el plan está dentro de la banda", text)
        self.assertIn("- ninguno", text)
        self.assertIn("«quita el 7 y el 9»", text)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Propuesta -v
```

Esperado: 4 errores `AttributeError: module 'plan' has no attribute 'cell'`.

- [ ] **Paso 3: implementación mínima**

```python
def cell(text):
    """One Markdown cell: a pipe or a newline would break the table."""
    return str(text).replace("|", "\\|").replace("\n", " ")


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
    head += ["", "## Reservas", "", "| id | Origen | Qué aportaría |", "| --- | --- | --- |"]
    for item in reserves:
        head.append(f"| {item['id']} | {clock(item['start'])}–{clock(item['end'])} | "
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
                                          or ["- ninguna: el plan está dentro de la banda"])
    head += ["", "## Recorrido", "", f"`{plan['recorrido']}`", "",
             f"0:00 ← cada carácter son {total / BAR:.0f} s → {clock(total)}", "",
             "## Cómo responder", "",
             "- «acepta» o «móntalo» para montar esta versión.",
             "- «quita el 7 y el 9», «añade el 6», «alarga el 3 diez segundos».",
             "- «añade la parte donde habla de ATEX», «parte el 4», «une 4 y 5».",
             "- «súbelo al 15 %», «sin acelerar», «no quites pausas en el 12».",
             "- «vuelve a la v1» o «¿qué has dejado fuera?».", ""]
    return "\n".join(head)
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: `Ran 40 tests … OK`.

- [ ] **Paso 5: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): propuesta en Markdown, recorrido de texto y fila publicada del corte" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: publicación de la versión, historial, diff de cambios y subcomando `plan`

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/video.py` (`build_parser` y `main`)
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: todo lo anterior, más `common.reserve_version`, `common.write_reserved`,
  `common.publish`, `common.history`, `common.plan_sha256`, `common.energy`, `common.fingerprint`,
  `common.timeline`, `common.duration`.
- Produces: `dumps(data) -> str`, `source_of(data) -> dict` (identidad y huella fundidas en
  `{path, size, mtime_ns, sha256}`), `publish_version(work, prefix, body, extra=None) -> (int, Path)`,
  `changes(work, parent, cuts, notes) -> list[str]`,
  `video_plan(args, work, data, draft, settings, segments, total, levels, words, grid) -> int`,
  `run(args) -> int` y `register(sub) -> parser`, que crea el subcomando `plan` con las opciones
  `--work`, `--draft`, `--target`, `--speed`, `--pauses`, `--silence-db`, `--kind`, `--dry-run`,
  `--import` y `--revert` y lo cierra con `set_defaults(run=run)`. `video.py` solo lo llama.
  `run` devuelve **2** en tres casos: si el plan publicado lleva algún aviso bloqueante, si falta
  `--draft` y si rechaza el borrador (§12: un borrador que falta o que el agente tiene que corregir es
  un argumento inválido, no un fallo controlado; en los dos casos se imprime `Error: …` por la salida
  de errores y no se escribe nada). `--dry-run` no reserva versión, no escribe propuesta ni historial;
  sí puede crear `energia.f32`, que es material de `prepare`.
- El `extra` de `publish_version` es un invocable **sin argumentos** que devuelve el Markdown
  acompañante: cuando se le llama, la versión ya está fijada en `body["version"]`, que es de donde la
  lee `proposal`, así que pasársela aparte solo duplicaría el dato.
- **La firma `video_plan(args, work, data, draft, settings, segments, total, levels, words, grid)` es
  la definitiva**, con `grid` como décimo parámetro: `run` la llama exactamente así, y ningún plan
  posterior la recorta. El plan de audio y documento encaja `audio_plan` con esa misma convención y el
  mismo orden de parámetros.
- `--kind audio` se acepta en la línea de órdenes y llega a `check_draft`, pero el esquema de audio lo
  publica el plan de audio y documento: aquí `run` lo rechaza con un mensaje claro y esa tarea sustituye
  las dos líneas de la guarda (`if kind != "video": raise …`) por el reparto entre `audio_plan` y
  `video_plan`. Es el único cambio previsto de otro plan sobre `run`.

- [ ] **Paso 1: escribir la prueba que falla**

Añade a `test_plan.py` un ayudante y la clase:

```python
def call(work, **extra):
    """Run plan.run capturing its stdout, as the CLI would."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = plan.run(options(work, dry_run=False, **extra))
    return code, buffer.getvalue()


def dry(work, **extra):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = plan.run(options(work, **extra))
    text = buffer.getvalue()
    return code, json.loads(text[text.index("{"):text.rindex("}") + 1])


class VersionesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)

    def tearDown(self):
        self.temporary.cleanup()

    def test_the_first_version_publishes_plan_proposal_and_history(self):
        draft(self.work, BASE)
        code, output = call(self.work)
        self.assertEqual(code, 0)
        self.assertIn("seleccion-v1.json", output)
        body = json.loads((self.work / "seleccion-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["sha256"], common.plan_sha256(body))
        self.assertEqual([item["id"] for item in body["segments"]], [1, 2, 3, 5, 6])
        self.assertEqual([item["id"] for item in body["reserves"]], [4])
        self.assertNotIn("fingerprint", body)
        self.assertEqual(set(body["source"]), {"path", "size", "mtime_ns", "sha256"})
        self.assertEqual(body["source"]["sha256"], self.data["source"]["sha256"])
        self.assertEqual((body["settings"]["rate"], body["settings"]["sample_rate"]),
                         ("25/1", 48000))
        self.assertEqual(body["timeline"], self.data["timeline"])
        self.assertEqual(body["estimate"]["salida"], 24.36)
        self.assertEqual(body["changes"], ["propuesta inicial"])
        self.assertIn("# Propuesta v1", (self.work / "propuesta-v1.md").read_text(encoding="utf-8"))
        record = json.loads((self.work / "historial.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual((record["evento"], record["version"], record["segments"]), ("init", 1, 5))

    def test_the_second_version_diffs_and_leaves_the_first_untouched(self):
        draft(self.work, BASE)
        call(self.work)
        before = (self.work / "seleccion-v1.json").read_bytes()
        segments = [dict(segment) for segment in BASE]
        segments[3]["included"] = True
        segments[4]["included"] = False
        segments[2]["end"] = 23.0
        segments[2]["phrase"] = "Frase 3 recortada"
        draft(self.work, segments, parent=1)
        code, output = call(self.work)
        self.assertEqual(code, 0)
        body = json.loads((self.work / "seleccion-v2.json").read_text(encoding="utf-8"))
        # Section 9 asks for seconds in the three lines: 4 lasts 93 frames at 25 fps, so 3,7 s.
        self.assertEqual(body["changes"],
                         ["alta: 4 · Tema 4 · 3,7 s", "baja: 5 · Tema 5",
                          "cambio: 3 · Tema 3 · 4,5 s → 2,1 s · Frase 3 recortada"])
        self.assertEqual(body["estimate"]["salida"], 20.76)
        self.assertEqual((self.work / "seleccion-v1.json").read_bytes(), before)
        self.assertEqual(len((self.work / "historial.jsonl").read_text(
            encoding="utf-8").splitlines()), 2)

    def test_a_blocking_warning_publishes_and_returns_two(self):
        draft(self.work, [cut(1, 2.0, 10.0, 1, depends_on=[2]),
                          cut(2, 19.0, 26.0, 3, included=False)])
        code, _ = call(self.work)
        self.assertEqual(code, 2)
        body = json.loads((self.work / "seleccion-v1.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item["bloquea"] for item in body["warnings"]))

    def test_a_silent_reserve_does_not_block_and_an_emptied_cut_is_a_change(self):
        # 20,0–21,5 is silence in the fixture: the discards leave that cut without spans.
        quiet = cut(2, 20.1, 21.4, 3, included=False)
        draft(self.work, [cut(1, 2.0, 10.0, 1), quiet])
        code, _ = call(self.work)
        # A reserve the agent left out never reaches the render: emptiness does not block it.
        self.assertEqual(code, 0)
        body = json.loads((self.work / "seleccion-v1.json").read_text(encoding="utf-8"))
        self.assertNotIn("corte_vacio", [item["codigo"] for item in body["warnings"]])
        draft(self.work, [cut(1, 2.0, 10.0, 1), dict(quiet, included=True)])
        code, _ = call(self.work)
        self.assertEqual(code, 2)
        body = json.loads((self.work / "seleccion-v2.json").read_text(encoding="utf-8"))
        self.assertIn("corte_vacio", [item["codigo"] for item in body["warnings"]])
        # Section 7.4: the emptied cut goes back to reserves, and that is noted in `changes`.
        self.assertEqual(body["changes"],
                         ["corte vacío: 2 · Tema 2 · sin tramos tras quitar pausas: "
                          "vuelve a reservas (corte_vacio)"])

    def test_dry_run_writes_no_version(self):
        draft(self.work, BASE)
        code, body = dry(self.work)
        self.assertEqual(code, 0)
        self.assertEqual(body["estimate"]["salida"], 24.36)
        self.assertEqual(sorted(path.name for path in self.work.iterdir()),
                         ["audio.wav", "borrador.json", "energia.f32", "medio.mp4",
                          "metadata.json"])

    def test_the_call_overrides_the_target_of_the_draft(self):
        draft(self.work, BASE)
        code, body = dry(self.work, target="12s")
        self.assertEqual(body["estimate"]["estado"], "por_encima")
        self.assertEqual(body["settings"]["target"], "12s")

    def test_a_bad_draft_is_refused_with_code_two_and_without_writing(self):
        draft(self.work, [cut(1, 2.0, 9.0), cut(2, 8.0, 12.0)])
        code, _ = call(self.work)
        self.assertEqual(code, 2)
        self.assertFalse(list(self.work.glob("seleccion-v*.json")))
        self.assertFalse(list(self.work.glob("propuesta-v*.md")))
        # A draft that is missing is the same class of invalid argument as one that is wrong.
        self.assertEqual(call(self.work, draft=None)[0], 2)
        draft(self.work, BASE)
        with self.assertRaisesRegex(ValueError, "modo audio"):
            call(self.work, kind="audio")


class CliTest(unittest.TestCase):
    def test_the_subcommand_is_wired_and_documented(self):
        parser = video.build_parser()
        parsed = parser.parse_args(["plan", "--work", "T", "--draft", "b.json", "--target", "10%",
                                    "--speed", "1.5", "--pauses", "no", "--silence-db", "-45",
                                    "--kind", "audio", "--dry-run"])
        self.assertEqual((parsed.command, parsed.work, parsed.draft, parsed.target), 
                         ("plan", "T", "b.json", "10%"))
        self.assertEqual((parsed.speed, parsed.pauses, parsed.silence_db), (1.5, "no", -45.0))
        self.assertEqual((parsed.kind, parsed.dry_run, parsed.import_from, parsed.revert),
                         ("audio", True, None, None))
        # The shared convention: the subparser carries its own entry point.
        self.assertIs(parsed.run, plan.run)
        self.assertIs(parser.parse_args(["check"]).run, video.check)
        self.assertEqual(parser.parse_args(["plan", "--work", "T", "--import", "p.json"]).import_from,
                         "p.json")
        self.assertEqual(parser.parse_args(["plan", "--work", "T", "--revert", "2"]).revert, 2)
```

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Versiones -v
```

Esperado: 7 errores `AttributeError: module 'plan' has no attribute 'run'`.

- [ ] **Paso 3: implementar la publicación en `plan.py`**

Añade `import sys` a la cabecera de `plan.py` (orden alfabético, después de `pathlib`) y estas funciones:

```python
def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def source_of(data):
    """Identity and fingerprint of the medium in one place: path, size, mtime and sha256."""
    source = dict(data["source"])
    source.update(data.get("fingerprint") or {})
    if "sha256" not in source:
        source.update(common.fingerprint(source["path"]))
    return source


def publish_version(work, prefix, body, extra=None):
    """Reserve N, fill it atomically and publish the companion Markdown beside it.

    `extra` takes no arguments: by the time it runs, N is already in `body["version"]`.
    """
    version, path = common.reserve_version(work, prefix)
    body["version"] = version
    body["sha256"] = common.plan_sha256(body)
    common.write_reserved(path, dumps(body) + "\n")
    if extra is not None:
        staged = work / f"propuesta-v{version}.md.parcial"
        staged.write_text(extra(), encoding="utf-8")
        common.publish(staged, work / f"propuesta-v{version}.md")
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
    reserves = [cut_row(row, 0, 0.0, grid) for row in rows
                if row["segment"]["id"] not in included]
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
                   {"version": version, "segments": len(cuts), "estado": report["estado"],
                    "salida": report["salida"], "sha256": body["sha256"],
                    "peticion": draft.get("request", "")})
    print(path)
    return 2 if blocking else 0


def run(args):
    """Entry point registered by `register`; video.py reaches it through args.run."""
    work = Path(args.work).resolve()
    if not work.is_dir():
        raise ValueError(f"No existe la carpeta de trabajo: {work}")
    data = load(work / "metadata.json")
    total = common.duration(data)
    if not args.draft:
        # Section 12: a draft that is missing is as invalid an argument as one that is wrong, so it
        # leaves by the same door as `check_draft` below, with code 2 and without writing anything.
        print("Error: indica --draft con el borrador del agente.", file=sys.stderr)
        return 2
    # prepare writes `kind`; a job that does not declare it is a video job, as in 0.1.0.
    kind = args.kind or data.get("kind") or "video"
    if kind != "video":
        raise ValueError("El modo audio publica un esquema de ideas, no una selección de tramos; "
                         "este subcomando todavía no lo genera.")
    draft = load(args.draft)
    grid = data.get("timeline") or common.timeline(data)
    try:
        settings = settings_of(draft, args, total, grid)
        segments = check_draft(draft, total, kind)
    except ValueError as exc:
        # The same door: a draft the agent has to fix is an invalid argument, not a controlled
        # failure.
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    transcript = work / "transcripcion.json"
    words = words_of(load(transcript)) if transcript.is_file() else []
    levels = common.energy(work / "audio.wav", work / "energia.f32")
    return video_plan(args, work, data, draft, settings, segments, total, levels, words, grid)


def register(sub):
    """Add the `plan` subcommand and leave its entry point in the parsed arguments."""
    parser = sub.add_parser("plan",
                            help="Calcula tramos, estimación, avisos y propuesta desde un borrador.")
    parser.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    parser.add_argument("--draft", help="Borrador del agente (JSON) con segments y settings.")
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
    parser.add_argument("--import", dest="import_from",
                        help="Convierte un plan 0.1 en un borrador nuevo.")
    parser.add_argument("--revert", type=common.positive,
                        help="Copia seleccion-vN.json a un borrador nuevo.")
    parser.set_defaults(run=run)
    return parser
```

El `%%` de la ayuda de `--target` es obligatorio: argparse interpreta `%` en las cadenas de ayuda.

- [ ] **Paso 4: registrar el subcomando en `video.py`**

Dos líneas, las únicas que este plan añade a `video.py` después de la tarea 1. Junto a `import common`,
en la cabecera:

```python
import plan
```

y al final de `build_parser`, justo antes del `return parser`:

```python
    plan.register(sub)
```

`plan.py` solo importa `common` y la biblioteca estándar, así que registrarlo no encarece `check`; el
despacho ya lo hace `main` con `args.run(args)` desde la tarea 1, y no hay ningún `if args.command`
nuevo que escribir.

- [ ] **Paso 5: ejecutar las pruebas y la CLI real**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
python -B plugins/resumir-video/skills/resumir-video/scripts/video.py plan --help
```

Esperado: `Ran 97 tests … OK` (37 + 12 + 48) y la ayuda con las diez opciones. Comprueba también el
código de salida real de un plan con aviso bloqueante creando la carpeta de prueba a mano si quieres;
el valor debe ser 2.

- [ ] **Paso 6: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/video.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): publicar seleccion-vN.json, la propuesta y el historial desde el subcomando plan" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: importar planes 0.1 y volver a una versión publicada

**Files:**
- Modificar: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Prueba: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes: `common.reserve_version`, `common.write_reserved`, `common.fingerprint`,
  `common.history` y `common.warning`.
- Produces: `import_plan(args, work, data, total) -> int` (§6: cortes ordenados con `id` desde 1,
  `priority = 1`, `included = true`, `remove_pauses` y `visual_only` a falso, `depends_on` vacío, un
  tramo `[start, end)`, velocidad 1,0; la identidad se contrasta **solo** con `size` y `mtime_ns` y la
  huella se completa desde el archivo actual con el aviso `identidad_parcial`) y
  `revert(args, work) -> int` («vuelve a la vN»: copia `seleccion-vN.json` a un borrador nuevo).
  Ambos escriben `borrador-vN.json`, nunca un plan: el resultado sigue exigiendo revisión y aceptación,
  y ambos llevan el `source` completo (`path`, `size`, `mtime_ns`, `sha256`), sin clave `fingerprint`
  aparte. `run` los atiende antes de exigir `--draft`.
- Ese final común es de las dos funciones, así que se escribe una sola vez:
  `publish_draft(work, body, event, payload, dry_run) -> int` imprime el borrador y devuelve 0 con
  `--dry-run`; si no, reserva `borrador-vN.json`, fija `body["version"]`, lo escribe con
  `write_reserved`, anota el historial con `event` y `payload` —más la versión reservada—, imprime la
  ruta y devuelve 0. `import_plan` y `revert` solo se diferencian en el cuerpo que preparan y en lo que
  anotan.

- [ ] **Paso 1: escribir la prueba que falla**

```python
class ImportarTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        self.data = work_folder(self.work)

    def tearDown(self):
        self.temporary.cleanup()

    def old_plan(self, **changes):
        body = {"source": dict(self.data["source"]), "audio_stream": 1,
                "segments": [{"start": 3.0, "end": 9.0, "title": "Requisito", "reason": "Motivo",
                              "audio_evidence": "Voz", "visual_evidence": "Tabla"},
                             {"start": 20.0, "end": 25.0, "title": "Excepción", "reason": "Motivo",
                              "audio_evidence": "Voz", "visual_evidence": "Tabla"}]}
        body.update(changes)
        path = self.work / "plan01.json"
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return path

    def test_a_zero_one_plan_becomes_a_draft_that_still_needs_review(self):
        code, output = call(self.work, import_from=str(self.old_plan()))
        self.assertEqual(code, 0)
        self.assertIn("borrador-v1.json", output)
        body = json.loads((self.work / "borrador-v1.json").read_text(encoding="utf-8"))
        self.assertEqual([(item["id"], item["start"], item["end"], item["priority"],
                           item["included"], item["remove_pauses"], item["visual_only"],
                           item["depends_on"]) for item in body["segments"]],
                         [(1, 3.0, 9.0, 1, True, False, False, []),
                          (2, 20.0, 25.0, 1, True, False, False, [])])
        self.assertEqual(body["settings"]["speed"], 1.0)
        self.assertEqual(body["settings"]["remove_pauses"], False)
        self.assertEqual([item["codigo"] for item in body["warnings"]], ["identidad_parcial"])
        self.assertNotIn("fingerprint", body)
        self.assertEqual(set(body["source"]), {"path", "size", "mtime_ns", "sha256"})
        self.assertEqual(body["source"]["sha256"],
                         common.fingerprint(self.data["source"]["path"])["sha256"])
        self.assertFalse(list(self.work.glob("seleccion-v*.json")))

    def test_only_size_and_mtime_are_contrasted(self):
        moved = dict(self.data["source"], path="otra/ruta/medio.mp4")
        code, _ = call(self.work, import_from=str(self.old_plan(source=moved)))
        self.assertEqual(code, 0)
        with self.assertRaisesRegex(ValueError, "difiere: size"):
            call(self.work, import_from=str(self.old_plan(
                source=dict(self.data["source"], size=99))))

    def test_reverting_copies_a_published_plan_into_a_new_draft(self):
        draft(self.work, BASE)
        call(self.work)
        code, output = call(self.work, revert=1)
        self.assertEqual(code, 0)
        self.assertIn("borrador-v1.json", output)
        body = json.loads((self.work / "borrador-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(body["parent"], 1)
        self.assertEqual([(item["id"], item["included"]) for item in body["segments"]],
                         [(1, True), (2, True), (3, True), (4, False), (5, True), (6, True)])
        self.assertEqual([(item["start"], item["end"]) for item in body["segments"]][:2],
                         [(2.0, 10.0), (11.0, 18.0)])
        self.assertEqual(body["settings"]["target"], "40%")
        self.assertEqual(body["source"]["sha256"], self.data["source"]["sha256"])
        with self.assertRaisesRegex(ValueError, "No existe seleccion-v9.json"):
            call(self.work, revert=9)
```

`work_folder` ya deja un `medio.mp4` de mentira en la carpeta desde la tarea 10, así que
`common.fingerprint` tiene un archivo real que leer y estas pruebas no necesitan preparar nada más.

- [ ] **Paso 2: ejecutarla y verla fallar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k Importar -v
```

Esperado: 3 fallos; `run` exige `--draft` y no mira `import_from` ni `revert`.

- [ ] **Paso 3: implementación mínima**

```python
def publish_draft(work, body, event, payload, dry_run):
    """The shared ending of --import and --revert: a new draft, never a plan."""
    if dry_run:
        print(dumps(body))
        return 0
    version, path = common.reserve_version(work, "borrador")
    body["version"] = version
    common.write_reserved(path, dumps(body) + "\n")
    common.history(work, event, {"version": version, **payload})
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
    segments, previous = [], 0.0
    for index, segment in enumerate(old.get("segments") or [], start=1):
        start = number(segment.get("start"), f"start del corte {index}")
        end = number(segment.get("end"), f"end del corte {index}")
        if not previous <= start < end <= total:
            raise ValueError(f"El corte {index} del plan importado está fuera del medio.")
        title = segment.get("title", f"Corte {index}")
        segments.append({"id": index, "start": start, "end": end, "title": title, "phrase": title,
                         "reason": segment.get("reason", "Importado de un plan 0.1"),
                         "audio_evidence": segment.get("audio_evidence", "Importado de un plan 0.1"),
                         "visual_evidence": segment.get("visual_evidence",
                                                        "Importado de un plan 0.1"),
                         "priority": 1, "included": True, "pinned": False, "depends_on": [],
                         "remove_pauses": False, "visual_only": False})
        previous = end
    if not segments:
        raise ValueError("El plan importado no tiene cortes.")
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
    kept = {item["id"] for item in old.get("segments", [])}
    segments = []
    for item in old.get("segments", []) + old.get("reserves", []):
        segments.append({"id": item["id"], "start": item["start"], "end": item["end"],
                         "title": item["title"], "phrase": item["phrase"], "reason": item["reason"],
                         "audio_evidence": item["audio_evidence"],
                         "visual_evidence": item.get("visual_evidence", ""),
                         "priority": item["priority"], "included": item["id"] in kept,
                         "pinned": item.get("pinned", False),
                         "depends_on": item.get("depends_on", []),
                         "remove_pauses": item.get("remove_pauses", True),
                         "visual_only": item.get("visual_only", False)})
    segments.sort(key=lambda item: item["start"])
    body = {"parent": old["version"], "request": f"Vuelve a la v{old['version']}",
            "source": old["source"],
            "settings": {key: old["settings"][key] for key in
                         ("target", "speed", "remove_pauses", "silence_db")},
            "segments": segments, "excluded": old.get("excluidos", []), "topics": []}
    return publish_draft(work, body, "edit", {"desde": old["version"]}, args.dry_run)
```

y en `run`, justo después de calcular `total` y antes de exigir `--draft`:

```python
    if args.import_from:
        return import_plan(args, work, data, total)
    if args.revert is not None:
        return revert(args, work)
```

- [ ] **Paso 4: ejecutarla y verla pasar**

```bash
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
```

Esperado: `Ran 100 tests … OK` (37 + 12 + 51), en menos de dos minutos.

- [ ] **Paso 5: comprobación final de todo el repositorio**

```bash
python -B -m unittest discover -s tests
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
claude plugin validate plugins/resumir-video --strict
claude plugin validate . --strict
git status --short
```

Esperado: ambas baterías en `OK`, los dos validadores sin errores y ningún `__pycache__` ni archivo
sin seguimiento dentro de `plugins/`.

- [ ] **Paso 6: commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): importar planes 0.1 y volver a una version publicada" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Qué queda fuera de este plan

| Pendiente | Dónde se hace |
| --- | --- |
| `prepare` ampliado (`kind`, huella en `source`, línea temporal, rechazo de HDR y sondeo de paquetes en `metadata.json`), `frames`, `transcribe`, `search`, `check` ampliado, `common.kind` y `common.pictures` | Plan de audio y documento |
| `render.py`: caché de cortes, presupuesto, montaje con las recetas verificadas, ensamblado y validación bloqueante; `--accept`, `--directo` y `--dry-run`. La cobertura de las cuatro pruebas que la tarea 1 retira de `test_video.py` se rehace en `test_render.py`, que es el único archivo de pruebas que ese plan escribe | Plan de montaje |
| El «coste de montaje» de §9 («reutiliza 36 de 38 · 2 cortes nuevos · ≈2 min»), que el agente muestra junto a la propuesta | `render --dry-run`, que lo imprime como `{reused, new, eta_s}` (plan de montaje) |
| `plan --kind audio` y `esquema-vN.json` (ideas y preguntas con tiempos), con su código en `plan.py` y sus pruebas en `test_plan.py`; sustituye la guarda de `run` por el reparto entre `audio_plan` y `video_plan` | Plan de audio y documento |
| `doc.py` y `compare`: documento, marcas, DOCX, timeline, cobertura y `cobertura_baja` | Plan de documento |
| Subida de versión de `__version__`, manifiestos, `CHANGELOG.md`, `README.md` y documentación; `SKILL.md` y las referencias nuevas | Plan de empaquetado |
| `huecos_pts` y `fuente_vfr` (sondeo de paquetes) | `prepare`; `plan` los propaga desde `metadata.json.avisos` |

## Autorrevisión

- **Cobertura de la especificación.** §3 símbolos y convención temporal → tareas 9 y 11 (`timeline`,
  `snap`, `islands`, `frames_for`, `samples_for`). §4 invocación y parámetros → tareas 2, 10 y 16
  (`parse_target`, `settings_of`, el subcomando con sus diez opciones). §6 borrador → tarea 10; plan
  publicado → tareas 15 y 16; versiones e historial → tareas 8 y 16; importación y regreso a una
  versión → tarea 17; formatos de archivo (`borrador-vN.json`, `seleccion-vN.json`, `propuesta-vN.md`,
  `historial.jsonl`) → tareas 16 y 17; `esquema-vN.json` queda para el plan de audio y documento.
  §7.1 presupuesto y retención → tarea 12;
  §7.2 selección (la decide el agente, el script solo la respeta) → tarea 10; §7.3 bordes y fusión →
  tareas 6 y 11; §7.4 pausas, rejilla y corte vacío → tareas 5, 11 y 13; §7.5 velocidad, estimación
  exacta y subcortes → tareas 7, 11 y 12; §7.6 estados, alternativas y sugerencias → tareas 12 y 14;
  §7.7 avisos → tarea 13, con las cuatro excepciones declaradas arriba: de los 18 códigos, la tarea 13
  emite 13, `identidad_parcial` es de la tarea 17, `huecos_pts` y `fuente_vfr` son de `prepare`,
  `origen_reasignado` de `render` y `cobertura_baja` de `compare`.
- **Sin marcadores.** Ningún paso dice «TBD», «similar a la tarea N» ni «añade validación»: cada uno
  lleva el código o la orden exacta.
- **Nombres coherentes.** `rows` es siempre la lista de filas `{"segment", "a", "b", "note"}` que
  `measure` completa; `included` es siempre un conjunto de identificadores; `grid` es siempre el
  diccionario de `common.timeline` (`start`, `origin`, `rate`, `fps`, `interval`, `sample_rate`);
  `report` es siempre el resultado de `estimate_of`; `body` es siempre el documento que se publica.
  `comma` se define en la tarea 14 y se usa en la 15 y la 16; `clock` y `MAX_SPANS` se definen una sola
  vez, en `common.py` (tarea 7).
- **Recuento de pruebas.** El repositorio parte de 15 pruebas en la skill y 23 en `tests/`. La tarea 1
  deja la skill en 12 (retira cuatro, reescribe otras cuatro sin montar nada y añade la del registro de
  subcomandos); al terminar el plan hay 37 en `test_common.py`, 12 en `test_video.py` y 51 en
  `test_plan.py`: **100** con `-p "test_*.py"`, más las 23 de `tests/`, que este plan no toca.
  `test_video.py` no vuelve a cambiar por el montaje: el plan de montaje solo crea `test_render.py`.
- **Códigos de salida.** `run` devuelve 0 cuando publica sin avisos bloqueantes y 2 en los tres casos
  de §12 que le corresponden: borrador ausente, borrador rechazado y plan publicado con aviso
  bloqueante —los dos primeros son la misma clase de argumento inválido—. Los fallos de
  entorno (carpeta inexistente, `metadata.json` ilegible) siguen saliendo por `main` como `Error: …` con
  código 1.
- **Eventos del historial.** Este plan escribe `init` (primera versión o importación) y `edit` (versión
  derivada o regreso a una anterior). `accept`, `render`, `verify`, `doc` y `deliver` son de los otros
  planes; ninguno inventa eventos nuevos.
