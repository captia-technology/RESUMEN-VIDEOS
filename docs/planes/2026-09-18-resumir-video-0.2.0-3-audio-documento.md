# Modo audio, documento MD/DOCX, search y compare · Plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usa `superpowers:subagent-driven-development`
> (recomendada) o `superpowers:executing-plans` para ejecutar este plan tarea a tarea. Los pasos usan
> casillas (`- [ ]`) para el seguimiento.

**Goal:** Entregar el modo audio completo (detección de `kind`, esquema aceptado y documento como
única entrega), un `prepare` que rechaza lo que el montaje estándar no sabe tratar y deja medidos los
tiempos y los avisos del medio, el documento con marcas expandidas en Markdown y DOCX para vídeo y
audio, la búsqueda en la transcripción y la validación informativa de cobertura.

**Architecture:** `video.py` sigue siendo el único punto de entrada: cada módulo hermano expone
`register(sub)` y `main()` despacha con `args.run(args) or 0`. `prepare` pasa a clasificar el medio
(`kind`), a rechazar las fuentes HDR y a dejar en `metadata.json` la huella, la línea temporal —con
`fps`— y los avisos del sondeo de paquetes que todos los demás módulos leen. `doc.py` construye, a
partir del plan publicado (vídeo) o del esquema aceptado (audio), un mapa de tiempos de salida y expande
con él las marcas que escribe el agente; después convierte a DOCX con Pandoc, con python-docx o degrada
a solo Markdown. `plan --kind audio` publica el esquema de ideas y preguntas que el usuario acepta antes
de redactar. `compare` mide, sin bloquear, cuántas palabras previstas sobreviven a los tramos montados.

**Tech Stack:** Python 3.10–3.13 con biblioteca estándar únicamente (`argparse`, `json`, `re`, `wave`,
`array`, `unicodedata`, `subprocess`, `pathlib`), FFmpeg 8.0.1 invocado con listas de argumentos, y tres
dependencias opcionales que solo se importan si existen: Pandoc (ejecutable externo), `python-docx` y
`Pillow`. Pruebas con `unittest` de la biblioteca estándar.

**Spec:** [`docs/especificaciones/2026-09-18-resumir-video-0.2.0.md`](../especificaciones/2026-09-18-resumir-video-0.2.0.md)
— este plan cubre §5 (modos), §10 (documento) y la parte informativa de §8 (cobertura), más las piezas
de §3 (`prepare` ampliado y `search`), §6, §7.7 (`fuente_vfr` y `huecos_pts`), §9 y §12 (rechazo de
HDR, de vídeo mudo y de varias pistas de vídeo) que esas tres secciones necesitan.

## Global Constraints

- **Ubicación.** La skill vive en `plugins/resumir-video/skills/resumir-video/`. Los scripts están en
  `scripts/{common,video,plan,render,doc}.py` y sus pruebas en `scripts/test_*.py`. Las pruebas del
  repositorio están en `tests/`. Nunca se escribe dentro de la carpeta de la skill en tiempo de
  ejecución (spec §11, «Protección»).
- **Sin dependencias fuera de la biblioteca estándar.** Pandoc, `python-docx` y `Pillow` son
  opcionales: su ausencia degrada la entrega, nunca la rompe (spec §10, §15).
- **Estilo.** Docstring de módulo en inglés; mensajes de error y de ayuda en español, con el prefijo
  `Error: ` que añade `main()`; funciones cortas; comentarios solo donde el porqué no es obvio.
- **Escritura.** JSON creados en exclusiva (`open("x")` mediante `common.save`), carpetas nuevas con
  `common.new_dir`, publicación por renombrado con `common.publish` (nunca sobrescribe). FFmpeg siempre
  con lista de argumentos, nunca por shell.
- **Códigos de salida (spec §12):** 0 correcto, incluido «DOCX no disponible» con aviso; 1 error
  controlado con mensaje `Error: …`; 2 argumentos inválidos o plan con aviso bloqueante; 3 pendiente y
  reanudable; 4 validación fallida; 130 interrupción.
- **Este plan no toca los manifiestos, `SKILL.md` ni la versión declarada en `video.py`:** de todo eso
  se ocupa el plan de integración (plan 4).
- **Python admitido: 3.10–3.13.** No se usa `audioop` (eliminado en 3.13).
- **Se conservan sin cambios de firma** las funciones de la 0.1.0 que pasan a `common.py`: `tool`, `run`,
  `ffmpeg`, `save`, `seconds`, `identity`, `probe`, `duration`, `tag_seconds`, `stream_duration`,
  `stream_end`, `timeline_start`, `seek_margin`, `landing`, `rate_of`, `frame_interval`, `output_rate`,
  `output_interval`, `video_stream`, `streams`, `encoders`, `require_encoders`, `cache_dir`, `new_dir`,
  `frame_count`, `stamp`, `listing`, `positive`.
- **Umbrales provisionales** (spec §15): silencio a −50 dBFS, `cobertura_baja` a 0,90 de media y 0,85
  por corte. Se declaran como provisionales en la referencia y en el documento.
- **Decisiones de integración que este plan aplica literalmente** (fijadas por el arquitecto para los
  cuatro planes):
  - **Esquema único de `seleccion-vN.json`**, con las claves de datos en inglés: `version, parent, kind,
    source {path, size, mtime_ns, sha256}, audio_stream, timeline, settings, segments, reserves,
    estimate, alternativas, sugerencias, warnings, changes, sha256`; cada elemento de `segments` lleva
    `id, numero, title, phrase, reason, audio_evidence, visual_evidence, priority, pinned, visual_only,
    remove_pauses, start, end, spans, frames, samples, subcuts`, y `settings` lleva `target, speed,
    remove_pauses, silence_db, rate, sample_rate, tolerance`. **En el plan publicado los tramos
    conservados de un corte se llaman siempre `spans`**; la grafía `tramos` sigue siendo legítima en
    otros archivos y con otro significado —la clave de caché de `render` (plan 2) la usa para los
    tramos redondeados al milisegundo—, así que este plan solo la descarta dentro de
    `seleccion-vN.json` y `esquema-vN.json`. Los avisos conservan
    `{codigo, mensaje, corte, bloquea}`, y `settings.tolerance` es un número en segundos —la
    semianchura de la banda del objetivo— o `null` cuando no hay objetivo. Estas siete claves
    son el contrato de `settings` para el esquema de audio (tarea 8), construido a mano; la
    función compartida `plan.settings_of` (usada por `plan --kind video`, plan 1, ya cerrada)
    devuelve en realidad ocho claves para el modo vídeo, con `objetivo` además de estas siete.
  - **Registro de subcomandos:** cada módulo expone `register(sub)`, su subparser llama a
    `set_defaults(run=<función>)` y `video.main` despacha con `return args.run(args) or 0`.
  - **`common.kind` se define en este plan** (tarea 1), para que otros módulos lo usen.
    `plan.py` (plan 1, ya cerrado) resuelve hoy el modo con `data.get("kind")` directo y no
    necesita cambiar para consumirlo, salvo que este plan decida conectarlo explícitamente
    en la tarea 8.
  - **`metadata.json["timeline"]`** tiene la forma de este plan: `{start, origin, rate, fps, interval,
    sample_rate}`. `common.timeline(data)` (plan 1) devuelve **siempre** esas seis claves, también en
    medios de solo audio —donde `rate`, `fps` e `interval` son `null` y `origin` es `0.0`—, y `prepare`
    la escribe siempre, en los dos modos. No existe `grid["F"]` ni `common.sample_rate_of`: la
    frecuencia de muestreo viaja dentro de la línea temporal, tomada de la pista que declara
    `data["audio_stream"]`.
  - **Firmas fijadas de `plan.py`:** `settings_of(draft, args, total, grid)` y
    `video_plan(args, work, data, draft, settings, segments, total, levels, words, grid)`. La rama de
    audio encaja con la misma convención —`audio_plan(args, work, data, draft, settings, segments,
    total, levels, words, grid)`— y `plan.run` reparte entre las dos sin guarda previa: la tarea 8
    retira la guarda `kind != "video"` que el plan 1 dejó provisionalmente.
  - **`plan --kind audio` se implementa en este plan** (tarea 8), dentro de `scripts/plan.py` —que crea
    el plan 1— y con sus pruebas en `scripts/test_plan.py`. No se crea `test_audio.py`.
  - **`common.strip_accents` conserva `ñ` y `Ñ`:** «diseñó» se normaliza a «diseño», no a «diseno».
  - **`references/documento.md` lo crea el plan 4** (su tarea de referencias). Este plan solo aporta el
    texto de sus secciones (tarea 10) y no escribe el archivo.
  - **Ningún archivo bajo `plugins/` puede contener literales de ruta absoluta**, porque
    `tests/test_packaging.py::test_payload_is_portable` los prohíbe: los patrones y los casos de prueba
    que los necesitan se construyen por concatenación.
  - **Eventos de `historial.jsonl`:** exactamente `init`, `edit`, `accept`, `render`, `verify`, `doc` y
    `deliver`. Este plan escribe `init`/`edit` en `plan --kind audio`, **`doc` en `doc.document` cada
    vez que publica un documento o una revisión** y `verify` con `"tipo": "cobertura"` en `compare`.
    `deliver` queda reservado a la **entrega final** del trabajo (paso 11 del flujo de `SKILL.md`): no
    lo escribe ningún subcomando de este plan. Ningún plan inventa otros.
  - **Una sola `clock` en `common.py`**, que trunca al segundo y consumen `plan.py` y `doc.py`.
  - **Todos los commits** llevan el pie
    `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- **Recuentos reales del repositorio antes de empezar** (comprobados hoy): 15 pruebas en
  `scripts/test_video.py` y 23 en `tests/test_packaging.py`. La tarea 1 del **plan 1** es la única que
  toca `test_video.py` antes que este plan: retira las cuatro pruebas que se quedan sin sujeto,
  reescribe otras cuatro y añade `test_every_subcommand_is_wired_to_its_function`, así que deja el
  archivo en **12 pruebas**, que es el punto de partida real de las tareas 1 y 2. §13 de la
  especificación habla de las 15 pruebas de la skill y las 23 de `tests/` medidas antes de empezar.
- **Órdenes de comprobación** (desde la raíz del repositorio):
  ```text
  python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
  python -B -m unittest discover -s tests
  ```
  El `-B` es obligatorio: sin él queda `__pycache__` dentro de la skill y `tests/test_packaging.py`
  detecta la copia como sucia.

## Dependencias entre planes

Este plan es el tercero de cuatro. Consume, sin reescribirlas:

| De | Qué | Si aún no existe |
| --- | --- | --- |
| Plan 1 | `scripts/common.py` con las funciones nuevas del contrato y las heredadas de la 0.1.0 (incluida `clock`), y un `video.py` que ya hace `import common` y registra los subcomandos con `register(sub)` | Las tareas 1–10 no pueden empezar; ejecuta antes el plan 1 |
| Plan 1 | `scripts/plan.py` con `load`, `check_draft`, `settings_of`, `publish_version`, `cell`, `dependency_warnings`, `topic_warnings` y el despachador `plan.run`, más su `test_plan.py` con los ayudantes `work_folder`, `draft`, `cut`, `call` y `dry` | La tarea 8 no puede empezar: añade la **rama de audio** a ese `plan.py`, no lo crea |
| Plan 2 | `scripts/render.py`, que publica `vN/seleccion.json`, `vN/validacion.json` y `vN/montaje.md` —el informe técnico del montaje, archivo **existente** que este plan cita pero no lee ni reescribe: `doc` publica `vN/resumen.md`, que es otro archivo— | Las tareas 3–7, 9 y 10 usan ficheros de prueba escritos a mano, así que se pueden ejecutar antes |
| Plan 4 | `check` ampliado con Pandoc, python-docx, Pillow y memoria (spec §3), y `references/documento.md` | No bloquea: `doc.engine()` (tarea 6) es la función que `check` reutiliza para informar del motor disponible, y la tarea 10 deja escrito el texto de las secciones de la referencia para que el plan 4 lo publique |

Todo lo que este plan necesita y **no** está en el contrato común se declara en el bloque
«Interfaces» de la tarea que lo introduce y se recoge en «Contrato ampliado» al final.

---

### Task 1: `kind`, `prepare` con huella y línea temporal, rechazo de HDR y sondeo de paquetes

Clasifica el medio antes de tocar el disco, rechaza lo que el montaje estándar no sabe tratar y deja en
`metadata.json` todo lo que los módulos posteriores necesitan para no volver a sondear el archivo
(spec §3, §5, §6, §7.7, §12).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/common.py` (añadir `pictures` y `kind`)
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/video.py` (reescribir `prepare`)
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_video.py`

**Interfaces:**
- Consumes (de `common.py`, plan 1): `probe(path)`, `run(args)`, `duration(data)`, `identity(path)`,
  `timeline(data)`, `new_dir(path)`, `save(path, data)`, `ffmpeg(*args)`,
  `encoders()`, `fingerprint(path)`, `energy(wav_path, cache_path=None)`,
  `warning(code, message, *, cut=None)` y la constante `HDR_TRANSFERS`. Las pruebas nuevas usan
  `common.…` directamente; confirma que `import common` sigue en la cabecera de `scripts/test_video.py`
  (ya está desde el plan 1; no hace falta añadirlo).
- **`common.timeline(data)` es la del plan 1 con la forma acordada**: devuelve **siempre**
  `{start, origin, rate, fps, interval, sample_rate}` —`fps`, nunca `F`—, también en medios de solo
  audio, donde `rate`, `fps` e `interval` son `null` y `origin` es `0.0`. La frecuencia de muestreo es
  la de la pista que declara `data["audio_stream"]` (la primera de audio si aún no está), así que
  `prepare` fija `audio_stream` **antes** de llamarla y no existe `common.sample_rate_of`.
- Produces:
  - `common.pictures(data) -> list[dict]`: pistas de vídeo que no son carátula. **Lo define este plan**;
    el plan 1 lo consume.
  - `common.kind(data) -> str`: `"video"` o `"audio"`; `ValueError` en cualquier otro caso. **Lo define
    este plan**; el plan 1 lo consume y no lo redefine.
  - `video.reject_hdr(picture) -> None`, `video.packet_times(path, index) -> list[float]` y
    `video.packet_warnings(data) -> list[dict]`. **No hay una `line_of` propia**: la línea temporal de
    los dos modos la da `common.timeline`, y `prepare` solo comprueba que la frecuencia de muestreo que
    devuelve es utilizable.
  - `metadata.json` con las claves nuevas **(ampliación del contrato)**:
    ```json
    {"kind": "video", "audio_stream": 1,
     "source": {"path": "…", "size": 0, "mtime_ns": 0, "sha256": "…"},
     "timeline": {"start": 0.0, "origin": 0.032, "rate": "25/1", "fps": 25.0,
                  "interval": 0.04, "sample_rate": 48000},
     "avisos": [{"codigo": "huecos_pts", "mensaje": "…", "corte": null, "bloquea": false}]}
    ```
    La identidad y la huella viven juntas en `source` —`{path, size, mtime_ns, sha256}`—, que es la
    forma que el plan publicado lleva: no hay una clave `fingerprint` aparte.
    En modo audio, `rate`, `fps` e `interval` son `null`, `origin` es `0.0` y `avisos` está vacío.
    `rate` es la cadena que entiende FFmpeg; `fps` es el mismo valor como número, que es el `F` de
    `N = round(L · F / v)`. `avisos` es el único origen de `fuente_vfr` y `huecos_pts`: `plan.py` los
    propaga desde aquí y no los recalcula.
  - `TRABAJO/energia.f32`: niveles RMS de 10 ms, calculados una sola vez.

- [ ] **Paso 1: Escribir la prueba que falla para `kind`**

En `scripts/test_video.py`, dentro de `PlanTest` (pruebas rápidas, sin FFmpeg):

```python
    def test_kind_accepts_video_and_audio_and_refuses_the_rest(self):
        picture = {"index": 0, "codec_type": "video"}
        sound = {"index": 1, "codec_type": "audio"}
        cover = {"index": 2, "codec_type": "video", "disposition": {"attached_pic": 1}}
        self.assertEqual(common.kind({"streams": [picture, sound]}), "video")
        self.assertEqual(common.kind({"streams": [sound]}), "audio")
        self.assertEqual(common.kind({"streams": [sound, cover]}), "audio")
        with self.assertRaisesRegex(ValueError, "pista de audio"):
            common.kind({"streams": [picture]})
        with self.assertRaisesRegex(ValueError, "2 pistas de vídeo"):
            common.kind({"streams": [picture, dict(picture, index=3), sound]})
        self.assertEqual([s["index"] for s in common.pictures({"streams": [picture, cover]})], [0])
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_kind_accepts -v
```

Esperado: FAIL con `AttributeError: module 'common' has no attribute 'kind'`.

- [ ] **Paso 3: Implementar `pictures` y `kind` en `common.py`**

```python
def pictures(data):
    """Picture tracks that are real video: cover art is metadata, not footage."""
    return [s for s in data["streams"] if s["codec_type"] == "video"
            and not s.get("disposition", {}).get("attached_pic")]


def kind(data):
    """`video` (one picture track and audio) or `audio` (no picture track and audio)."""
    videos = pictures(data)
    if not any(s["codec_type"] == "audio" for s in data["streams"]):
        raise ValueError("El medio no tiene pista de audio: una grabación muda no se puede resumir "
                         "con este flujo; extrae fotogramas aparte o aporta el audio.")
    if len(videos) > 1:
        raise ValueError(f"El medio tiene {len(videos)} pistas de vídeo; normaliza la fuente a una sola "
                         "antes de resumirla.")
    return "video" if videos else "audio"
```

- [ ] **Paso 4: Ejecutarla y comprobar que pasa**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_kind_accepts -v
```

Esperado: PASS.

- [ ] **Paso 5: Escribir las dos pruebas que fallan para `prepare`**

En `scripts/test_video.py`, dentro de `VideoTest` (requiere FFmpeg). La segunda recorre los cuatro
contenedores de solo audio que exige §13: `wav`, `m4a`, `m4a` con carátula y `mp3` si la compilación
de FFmpeg trae `libmp3lame`.

```python
    def test_prepare_classifies_the_medium_and_records_the_timeline(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            synthetic(root / "con-voz.mp4", 5)
            invoke(self, "prepare", root / "con-voz.mp4", "--work", root / "t-video")
            data = json.loads((root / "t-video/metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "video")
            self.assertEqual(data["timeline"]["fps"], 25.0)
            self.assertEqual(data["timeline"]["rate"], "25/1")
            self.assertAlmostEqual(data["timeline"]["interval"], 0.04)
            self.assertEqual(data["timeline"]["sample_rate"], 48000)
            self.assertEqual(len(data["source"]["sha256"]), 64)
            self.assertEqual(data["avisos"], [])
            self.assertEqual((root / "t-video/energia.f32").stat().st_size % 4, 0)
            self.assertAlmostEqual((root / "t-video/energia.f32").stat().st_size / 4, 500, delta=10)

    def test_prepare_takes_every_audio_container_and_refuses_a_mute_video(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            tone = "sine=frequency=440:sample_rate=48000:duration=5"
            common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "pcm_s16le", root / "solo.wav")
            common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "aac", root / "solo.m4a")
            common.ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-frames:v", "1",
                          root / "caratula.png")
            common.ffmpeg("-i", root / "solo.wav", "-i", root / "caratula.png", "-map", "0:a",
                          "-map", "1:v", "-c:a", "aac", "-c:v", "png",
                          "-disposition:v", "attached_pic", root / "con-caratula.m4a")
            names = ["solo.wav", "solo.m4a", "con-caratula.m4a"]
            if "libmp3lame" in common.encoders():
                common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "libmp3lame", root / "solo.mp3")
                names.append("solo.mp3")
            for name in names:
                with self.subTest(name=name):
                    work = root / f"t-{name}"
                    invoke(self, "prepare", root / name, "--work", work)
                    data = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
                    self.assertEqual(data["kind"], "audio")
                    self.assertIsNone(data["timeline"]["fps"])
                    self.assertIsNone(data["timeline"]["rate"])
                    self.assertEqual(data["timeline"]["origin"], 0.0)
                    self.assertEqual(data["timeline"]["sample_rate"], 48000)
                    self.assertEqual(data["avisos"], [])
                    self.assertTrue((work / "audio.wav").is_file())
                    self.assertTrue((work / "energia.f32").is_file())
            common.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=5",
                          "-c:v", "libx264", "-preset", "ultrafast", root / "mudo.mp4")
            error = invoke(self, "prepare", root / "mudo.mp4", "--work", root / "t-mudo",
                           ok=False).stderr
            self.assertIn("no tiene pista de audio", error)
            self.assertFalse((root / "t-mudo").exists())
```

- [ ] **Paso 6: Ejecutarlas y comprobar que fallan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_prepare -v
```

Esperado: FAIL con `KeyError: 'kind'`.

- [ ] **Paso 7: Reescribir `prepare` en `video.py`**

Sustituye la función `prepare` de la 0.1.0 por:

```python
def prepare(args):
    data = common.probe(args.video)
    data["kind"] = common.kind(data)
    common.duration(data)
    if data["kind"] == "video":
        reject_hdr(common.pictures(data)[0])
    sounds = [s for s in data["streams"] if s["codec_type"] == "audio"]
    if args.audio_stream is not None:
        sounds = [s for s in sounds if s["index"] == args.audio_stream]
        if not sounds:
            raise ValueError(f"No hay una pista de audio con el índice global {args.audio_stream}; "
                             "consulta probe.")
    audio = sounds[0]
    data["audio_stream"] = audio["index"]
    # Identity and fingerprint live together in `source`, the shape the published plan carries.
    data["source"] = {**data["source"], **common.fingerprint(data["source"]["path"])}
    # common.timeline answers both modes; in audio it leaves rate, fps and interval at null.
    data["timeline"] = common.timeline(data)
    if data["timeline"]["sample_rate"] <= 0:
        raise ValueError(f"La pista de audio {audio['index']} no declara una frecuencia de muestreo "
                         "válida; consulta probe y elige otra con --audio-stream.")
    data["avisos"] = packet_warnings(data)
    out = common.new_dir(args.work)
    # Job folders hold confidential frames and transcripts: keep them out of version control.
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    common.save(out / "metadata.json", data)
    common.ffmpeg("-i", data["source"]["path"], "-map", f"0:{audio['index']}",
                  "-vn", "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1",
                  "-c:a", "pcm_s16le", out / "audio.wav")
    common.energy(out / "audio.wav", out / "energia.f32")
    print(out)
```

`common.kind`, el rechazo del HDR, la selección de pista y el sondeo se evalúan **antes** de `new_dir`,
de modo que un medio rechazado no deja carpeta (spec §5, §12).

- [ ] **Paso 8: Escribir la prueba que falla para el HDR y los huecos de PTS**

También en `VideoTest`:

```python
    def test_hdr_is_refused_and_pts_gaps_are_recorded(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            common.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=2",
                          "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                          "-c:v", "libx264", "-preset", "ultrafast", "-x264-params",
                          "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                          "-c:a", "aac", root / "hdr.mp4")
            error = invoke(self, "prepare", root / "hdr.mp4", "--work", root / "t-hdr",
                           ok=False).stderr
            self.assertIn("HDR", error)
            self.assertFalse((root / "t-hdr").exists())

            synthetic(root / "entera.mp4", 3)
            common.ffmpeg("-i", root / "entera.mp4", "-vf", "select='not(between(n,25,49))'",
                          "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy",
                          root / "hueco.mp4")
            invoke(self, "prepare", root / "hueco.mp4", "--work", root / "t-hueco")
            avisos = json.loads(
                (root / "t-hueco/metadata.json").read_text(encoding="utf-8"))["avisos"]
            self.assertIn("huecos_pts", [aviso["codigo"] for aviso in avisos])
            self.assertFalse(any(aviso["bloquea"] for aviso in avisos))
            self.assertEqual({aviso["corte"] for aviso in avisos}, {None})
```

- [ ] **Paso 9: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_hdr_is_refused -v
```

Esperado: FAIL con `NameError: name 'reject_hdr' is not defined`.

- [ ] **Paso 10: Implementar el rechazo de HDR y el sondeo de paquetes**

En `video.py`, junto a `prepare`:

```python
PACKETS = 600
GAP_FACTOR = 1.5


def reject_hdr(picture):
    """HDR needs its own colour path: the standard montage would wash the picture out (section 12)."""
    transfer = picture.get("color_transfer")
    if transfer in common.HDR_TRANSFERS:
        raise ValueError(f"Fuente HDR ({transfer}): el montaje estándar no conserva su curva de "
                         "color. Convierte el original a SDR antes de resumirlo.")


def packet_times(path, index):
    """Presentation stamps of the first PACKETS packets of one track; the probe stops there."""
    report = json.loads(common.run(
        ["ffprobe", "-v", "error", "-select_streams", str(index), "-show_entries", "packet=pts_time",
         "-read_intervals", f"%+#{PACKETS}", "-of", "json", str(path)]))
    return sorted(float(packet["pts_time"]) for packet in report.get("packets") or []
                  if packet.get("pts_time") not in (None, "N/A"))


def packet_warnings(data):
    """Variable cadence and PTS gaps of the picture track, probed once and carried in metadata."""
    if data["kind"] == "audio":
        return []
    picture = common.pictures(data)[0]
    avisos = []
    if picture.get("avg_frame_rate") != picture.get("r_frame_rate"):
        avisos.append(common.warning(
            "fuente_vfr", f"La cadencia declarada no es constante (r_frame_rate "
            f"{picture.get('r_frame_rate')}, avg_frame_rate {picture.get('avg_frame_rate')}): el "
            "montaje fija F y normaliza con el filtro fps."))
    interval = data["timeline"]["interval"]
    times = packet_times(data["source"]["path"], picture["index"])
    # A gap of one interval is the normal spacing; 1,5 absorbs the rounding of the container.
    gaps = [round(b - a, 6) for a, b in zip(times, times[1:]) if b - a > GAP_FACTOR * interval]
    if gaps:
        avisos.append(common.warning(
            "huecos_pts", f"El sondeo de los primeros {len(times)} paquetes encuentra {len(gaps)} "
            f"saltos mayores de un fotograma (el mayor, {max(gaps):.3f} s): puede faltar imagen en "
            "el original."))
    return avisos
```

Ninguno de los dos avisos bloquea (spec §7.7): `common.warning` los deja con `bloquea: false` y
`corte: null`, y `plan.py` los copia tal cual desde `metadata["avisos"]`.

- [ ] **Paso 11: Ejecutar las tres pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_prepare -v
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_hdr_is_refused -v
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -v
```

Esperado: PASS en las tres. La última ejecuta además las pruebas heredadas: las **12** que deja la
tarea 1 del plan 1 más las **4** de esta tarea (`kind`, los dos `prepare` y el HDR con huecos), es
decir **16** en `test_video.py`; después de este plan solo lo amplía el plan 4 (barrido,
transcripción, subtítulos y `check`).

- [ ] **Paso 12: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/common.py \
        plugins/resumir-video/skills/resumir-video/scripts/video.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_video.py
git commit -m "feat(prepare): clasifica el medio, rechaza HDR y registra huella, tiempos y avisos" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Subcomando `search`

Búsqueda en `transcripcion.json` sin distinguir tildes ni mayúsculas, con el instante de la palabra
cuando la transcripción trae marcas por palabra (spec §3, §9).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/video.py`
- Test: `plugins/resumir-video/skills/resumir-video/scripts/test_video.py`

**Interfaces:**
- Consumes: `common.strip_accents(text)` —que **conserva `ñ` y `Ñ`**: «diseñó» se normaliza a «diseño»,
  nunca a «diseno»— y `common.positive(value)`.
- Produces: `video.normal(text)`, `video.haystack(segment)`, `video.find(data, query, context=1,
  limit=20)`, `video.search(args)` y el JSON que imprime:
  ```json
  {"consulta": "ATEX", "normalizada": "atex", "total": 2,
   "coincidencias": [{"segmento": 1, "inicio": 4.0, "fin": 9.0, "texto": "…", "contexto": "…"}]}
  ```
  `inicio` es el de la palabra cuando hay `words[]`, y el del segmento cuando no.

- [ ] **Paso 1: Escribir la prueba que falla**

En `scripts/test_video.py`, dentro de `PlanTest`:

```python
    TRANSCRIPTION = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Buenos días a todos.", "words": [
            {"start": 0.1, "end": 0.6, "text": " Buenos"}, {"start": 0.6, "end": 1.1, "text": " días"}]},
        {"start": 3.0, "end": 9.0, "text": " La atmósfera ATEX exige un equipo certificado.", "words": [
            {"start": 3.1, "end": 3.3, "text": " La"}, {"start": 3.3, "end": 4.0, "text": " atmósfera"},
            {"start": 4.0, "end": 4.6, "text": " ATEX"}, {"start": 4.6, "end": 5.2, "text": " exige"}]},
        {"start": 9.0, "end": 12.0, "text": " Sin atex no hay permiso.", "words": []},
        {"start": 12.0, "end": 15.0, "text": " El ingeniero diseñó la señal.", "words": []}]}

    def test_search_ignores_accents_and_case(self):
        found = video.find(self.TRANSCRIPTION, "ATEX")
        self.assertEqual(found["normalizada"], "atex")
        self.assertEqual([(h["segmento"], h["inicio"]) for h in found["coincidencias"]],
                         [(1, 4.0), (2, 9.0)])
        self.assertEqual(video.find(self.TRANSCRIPTION, "ATMÓSFERA")["coincidencias"][0]["inicio"], 3.3)
        self.assertEqual(video.find(self.TRANSCRIPTION, "atmosfera")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "zona 0")["total"], 0)
        self.assertIn("Buenos días", video.find(self.TRANSCRIPTION, "atmosfera")["coincidencias"][0]["contexto"])
        self.assertEqual(video.find(self.TRANSCRIPTION, "atex", limit=1)["total"], 1)
        with self.assertRaisesRegex(ValueError, "no vacío"):
            video.find(self.TRANSCRIPTION, "   ")

    def test_the_tilde_of_the_n_is_part_of_the_letter(self):
        # strip_accents keeps ñ and Ñ: «diseñó» normalises to «diseño», never to «diseno».
        self.assertEqual(video.find(self.TRANSCRIPTION, "DISEÑÓ")["normalizada"], "diseño")
        self.assertEqual(video.find(self.TRANSCRIPTION, "diseño")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "diseno")["total"], 0)
        self.assertEqual(video.find(self.TRANSCRIPTION, "señal")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "senal")["total"], 0)
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_search_ignores -v
```

Esperado: FAIL con `AttributeError: module 'video' has no attribute 'find'`.

- [ ] **Paso 3: Implementar `find` y `search` en `video.py`**

```python
SPACES = re.compile(r"\s+")


def normal(text):
    return SPACES.sub(" ", common.strip_accents(text).casefold()).strip()


def haystack(segment):
    """Normalised text of a segment and, per character, the word it belongs to."""
    words = segment.get("words") or []
    if not words:
        text = normal(segment.get("text", ""))
        return text, [None] * len(text)
    pieces, owners = [], []
    for index, word in enumerate(words):
        piece = normal(word.get("text", ""))
        if not piece:
            continue
        if pieces:
            pieces.append(" ")
            owners.append(index)
        pieces.append(piece)
        owners.extend([index] * len(piece))
    return "".join(pieces), owners


def find(data, query, context=1, limit=20):
    needle = normal(query)
    if not needle:
        raise ValueError("Indica un texto de búsqueda no vacío.")
    segments, hits = data.get("segments") or [], []
    for number, segment in enumerate(segments):
        text, owners = haystack(segment)
        words = segment.get("words") or []
        position = text.find(needle)
        while position >= 0 and len(hits) < limit:
            owner = owners[position] if position < len(owners) else None
            start = words[owner]["start"] if owner is not None and owner < len(words) else segment["start"]
            around = segments[max(0, number - context):number + context + 1]
            hits.append({"segmento": number, "inicio": round(float(start), 3),
                         "fin": round(float(segment["end"]), 3),
                         "texto": str(segment.get("text", "")).strip(),
                         "contexto": " ".join(str(s.get("text", "")).strip() for s in around)})
            position = text.find(needle, position + len(needle))
    return {"consulta": query, "normalizada": needle, "total": len(hits), "coincidencias": hits}


def search(args):
    path = Path(args.transcription)
    if not path.is_file():
        raise ValueError(f"No existe la transcripción: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    print(json.dumps(find(data, args.query, args.context, args.max), ensure_ascii=False, indent=2))
```

Añade `import re` a las importaciones del módulo si aún no está.

- [ ] **Paso 4: Registrar el subcomando en `build_parser`**

```python
    p = sub.add_parser("search", help="Busca en la transcripción sin distinguir tildes ni mayúsculas.")
    p.add_argument("transcription", help="transcripcion.json de la carpeta de trabajo.")
    p.add_argument("query", help="Texto buscado; se comparan minúsculas y sin tildes.")
    p.add_argument("--context", type=int, default=1,
                   help="Segmentos de contexto a cada lado (por defecto 1).")
    p.add_argument("--max", type=common.positive, default=20,
                   help="Coincidencias como máximo (por defecto 20).")
    p.set_defaults(run=search)
```

No se añade nada al diccionario de despacho de la 0.1.0: el plan 1 ya convirtió todos los subcomandos
heredados a este patrón; el nuevo subparser de `search` solo necesita seguirlo
(`set_defaults(run=search)`), sin nada más que tocar en `main()`.

- [ ] **Paso 5: Ejecutar las dos pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_search_ignores -v
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -k test_the_tilde_of_the_n -v
```

Esperado: PASS en ambas; con ellas `test_video.py` queda en **18** pruebas (12 heredadas del plan 1,
4 de la tarea 1 y 2 de esta), que es el total con el que se cierra este plan.

- [ ] **Paso 6: Comprobar la salida real del subcomando**

```text
python -B plugins/resumir-video/skills/resumir-video/scripts/video.py search --help
```

Esperado: la ayuda en español con `--context` y `--max` y sus valores por defecto.

- [ ] **Paso 7: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/video.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_video.py
git commit -m "feat(search): busca en la transcripción sin tildes ni mayúsculas" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `doc.py` — mapa de tiempos y marcas `[[t]]` y `[[r]]`

Primer archivo de `doc.py`: el mapa que convierte un instante del original en su instante de salida,
respetando tramos, pausas eliminadas y velocidad, y la expansión de las marcas de tiempo con errores
que citan la línea (spec §10).

**Files:**
- Create: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Create: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `common.clock(value)` —la **única** del proyecto, que trunca al segundo: `752.3 → "12:32"`,
  `3725 → "1:02:05"`— y, más adelante, `common.tool`, `common.run`, `common.publish`, `common.history`,
  `common.save`, `common.new_dir`, `common.duration`, `common.positive`, `common.warning` y
  `common.plan_sha256`. `doc.py` no define su propio `clock`.
- Produces:
  - `doc.stretches_of(cut) -> list[tuple[float, float]]`: los tramos conservados, que en el plan
    publicado se llaman siempre `spans`; `doc` no lee ninguna otra clave para ellos.
  - `doc.bounds_of(cut, pieces) -> tuple[float, float]`: los límites del corte. El plan publicado trae
    `start` y `end`; la función los deduce de los tramos para admitir también planes escritos a mano.
  - `doc.placements(segments, speed, rate) -> list[dict]` con
    `{"id", "title", "start", "end", "offset", "length", "stretches": [(a, b, salida)]}`. Usa el
    `frames` publicado por `render` cuando existe, de modo que los tiempos del documento coinciden
    exactamente con el montaje; si no, calcula `N = round(L · F / v)`.
  - `doc.output_at(t, spans, speed) -> float | None`.
  - `doc.moment(t, spans, speed) -> str` y `doc.interval(a, b, spans, speed) -> str`
    (`spans=None` significa modo audio: solo el tiempo del original).
  - `doc.expand(text, context) -> str` y `doc.replace_line(line, number, context) -> str`.
  - **Ampliación del contrato:** `placements` y `output_at` viven en `doc.py`; si `plan.py` necesita
    el mismo mapa, lo importa desde aquí (`import doc`), no lo duplica.
- **Sin rutas absolutas en el código.** `tests/test_packaging.py::test_payload_is_portable` rechaza
  cualquier archivo bajo `plugins/` que contenga una letra de unidad seguida de `:` y barra, `/Users/`
  o `/home/`. El detector de rutas del documento y su caso de prueba necesitan justo esos textos, así
  que se construyen por concatenación y nunca aparecen como literales.

- [ ] **Paso 1: Escribir la prueba que falla para el mapa de salida**

Crea `scripts/test_doc.py`:

```python
"""Fast checks for doc.py: no FFmpeg, no optional dependencies."""

import json
from pathlib import Path
import tempfile
import unittest

import common
import doc

# The published plan of the montage: spans, frames, samples and the bounds of every cut.
SEGMENTS = [{"id": 1, "numero": 1, "title": "Requisito y excepción", "start": 10.0, "end": 20.0,
             "spans": [[10.0, 13.0], [15.0, 20.0]], "frames": 160, "samples": 307200},
            {"id": 2, "numero": 2, "title": "Zona ATEX", "start": 30.0, "end": 36.0,
             "spans": [[30.0, 34.0]], "frames": 80, "samples": 153600}]


def context(spans=..., total=96.0):
    spans = doc.placements(SEGMENTS, 1.25, 25.0) if spans is ... else spans
    return {"metadata": {"source": {"path": "grabación.mp4"}}, "total": total, "spans": spans,
            "speed": 1.25, "settings": {"speed": 1.25, "remove_pauses": True, "rate": "25/1",
                                        "sample_rate": 48000}, "version": 1,
            "out": Path("."), "transcriber": "small (es)", "avisos": [], "schema": None}


class MapTest(unittest.TestCase):
    def test_output_time_follows_stretches_pauses_and_speed(self):
        spans = doc.placements(SEGMENTS, 1.25, 25.0)
        self.assertEqual([(s["offset"], s["length"]) for s in spans], [(0.0, 6.4), (6.4, 3.2)])
        for source, expected in ((10.0, 0.0), (11.0, 0.8), (13.0, 2.4), (14.0, 2.4), (15.0, 2.4),
                                 (16.0, 3.2), (20.0, 6.4), (30.0, 6.4), (34.0, 9.6), (35.0, 9.6),
                                 (36.0, 9.6)):
            with self.subTest(source=source):
                self.assertAlmostEqual(doc.output_at(source, spans, 1.25), expected, places=6)
        for outside in (9.9, 25.0, 40.0):
            self.assertIsNone(doc.output_at(outside, spans, 1.25))

    def test_the_published_frame_count_rules_over_the_computed_one(self):
        # A cut whose published N does not match L · F / v: the document follows the montage.
        held = [dict(SEGMENTS[0], frames=161), SEGMENTS[1]]
        spans = doc.placements(held, 1.25, 25.0)
        self.assertEqual([(s["offset"], s["length"]) for s in spans], [(0.0, 6.44), (6.44, 3.2)])

    def test_a_plan_without_bounds_derives_them_from_its_spans(self):
        # Hand-written plans may drop start and end; the published one always carries them.
        bare = [{k: v for k, v in cut.items() if k not in ("start", "end")} for cut in SEGMENTS]
        spans = doc.placements(bare, 1.25, 25.0)
        self.assertEqual([(s["start"], s["end"]) for s in spans], [(10.0, 20.0), (30.0, 34.0)])
        self.assertAlmostEqual(doc.output_at(11.0, spans, 1.25), 0.8, places=6)
        self.assertAlmostEqual(doc.output_at(14.0, spans, 1.25), 2.4, places=6)
        # Without a published end there is no last pause: 35 s is simply outside the cut.
        self.assertIsNone(doc.output_at(35.0, spans, 1.25))
        with self.assertRaisesRegex(ValueError, "no tiene tramos"):
            doc.placements([{"id": 7}], 1.25, 25.0)
```

La prueba de `clock` no está aquí: `clock` es de `common.py` y la comprueba `test_common.py` (plan 1).

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'doc'`.

- [ ] **Paso 3: Crear `doc.py` con el mapa de tiempos**

Esta cabecera es la definitiva del módulo: `argparse`, `datetime`, `os`, `sys` y `common` los usan las
tareas 4 a 10, así que se escriben ya y no vuelven a tocarse.

```python
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
```

- [ ] **Paso 4: Ejecutar la prueba y comprobar que pasa**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS (3 pruebas).

- [ ] **Paso 5: Escribir la prueba que falla para la expansión de marcas**

Añade a `test_doc.py`:

```python
class MarkTest(unittest.TestCase):
    def test_time_marks_report_the_output_or_its_absence(self):
        self.assertEqual(doc.expand("Ver [[t=11.0]] y [[t=25.0]].\n", context()),
                         "Ver 0:11 (resumen 0:00) y 0:25 (no incluido en el resumen).\n")
        self.assertEqual(doc.expand("[[t=35.0]]\n", context()), "0:35 (resumen 0:09)\n")
        self.assertEqual(doc.expand("[[r=30-34]]\n", context()), "0:30–0:34 (resumen 0:06–0:09)\n")
        self.assertEqual(doc.expand("[[r=22-26]]\n", context()), "0:22–0:26 (no incluido en el resumen)\n")
        self.assertEqual(doc.expand("[[r=11-26]]\n", context()),
                         "0:11–0:26 (incluido en parte en el resumen)\n")

    def test_audio_mode_only_stamps_the_original(self):
        self.assertEqual(doc.expand("[[t=11.0]] y [[r=30-34]]\n", context(spans=None)),
                         "0:11 y 0:30–0:34\n")

    def test_every_refusal_names_its_line(self):
        # The absolute paths are joined, never written out: a literal one would trip the
        # packaging check that forbids them anywhere under plugins/.
        drive = "C" + ":" + "/trabajo/salida"
        home = "/" + "Users" + "/ana/salida"
        cases = [("ok\nmarca [[x=3]]\n", "Línea 2: marca desconocida"),
                 ("[[t=500]]\n", "Línea 1: 500 s queda fuera del medio"),
                 ("[[t=abc]]\n", "no es un número de segundos"),
                 ("[[r=30]]\n", "debe ser inicio-fin en segundos"),
                 ("[[r=34-30]]\n", "tiene el fin antes del inicio"),
                 ("texto [[ficha]] dentro\n", "debe ocupar una línea entera"),
                 (f"Guarda en {drive}\n", "Línea 1: ruta absoluta"),
                 (f"Guarda en {home}\n", "Línea 1: ruta absoluta"),
                 ("Queda un dato TODO\n", "Línea 1: texto pendiente")]
        for text, message in cases:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                doc.expand(text, context())

    def test_a_link_is_not_an_absolute_path(self):
        self.assertEqual(doc.expand("Consulta https://ejemplo.org/guia.\n", context()),
                         "Consulta https://ejemplo.org/guia.\n")

    def test_a_doubtful_answer_is_not_a_pending_text(self):
        self.assertEqual(doc.expand("La cifra (pendiente de verificar) es 12.\n", context()),
                         "La cifra (pendiente de verificar) es 12.\n")
```

- [ ] **Paso 6: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k MarkTest -v
```

Esperado: FAIL con `AttributeError: module 'doc' has no attribute 'expand'`.

- [ ] **Paso 7: Implementar la expansión en `doc.py`**

```python
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
```

Añade además, provisionalmente, el despachador de bloques que la tarea 4 completará:

```python
def block(name, number, context):
    if context["spans"] is None and name in VIDEO_ONLY:
        raise ValueError(f"Línea {number}: la marca [[{name}]] no existe en modo audio.")
    raise ValueError(f"Línea {number}: la marca [[{name}]] aún no está disponible.")
```

- [ ] **Paso 8: Ejecutar todas las pruebas de `doc.py` y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS (8 pruebas).

- [ ] **Paso 9: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): mapa de tiempos de salida y marcas [[t]] y [[r]]" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Bloques `[[ficha]]`, `[[indice]]` y `[[validacion]]`

Los tres bloques que el script genera a partir del plan publicado y del informe de validación
(spec §10). `[[validacion]]` degrada con un aviso si `validacion.json` todavía no existe, de modo que
esta tarea no depende del plan 2.

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `context` con `metadata`, `total`, `spans`, `speed`, `settings`, `version`, `out`,
  `transcriber`, `avisos` y `schema` (lo construye la tarea 7).
- Consumes de `vN/validacion.json` **(lo publica el plan 2, con esta forma exacta)**:
  ```json
  {"fotogramas_esperados": 18150, "fotogramas": 18150, "video_s": 726.0, "audio_s": 725.98,
   "desfase_s": 0.021,
   "colocacion": [{"corte": 1, "titulo": "…", "salida_s": [0.0, 6.4],
                   "imagen": [{"punto": "inicio", "salida_s": 0.0, "origen_s": 10.0,
                               "distancia": 0.031}],
                   "envolvente": [{"punto": "inicio", "bloques": 86, "desfase_ms": 20,
                                   "correlacion": 0.97, "modulacion_db": 20.0}]}],
   "marcas": ["corte 2 (inicio): imagen a 0,1100"], "uniones": [160],
   "uniones_hojas": ["union-01.jpg"]}
  ```
  `uniones` es la lista de fotogramas de unión, no un recuento, y `marcas` la lista de ventanas
  señaladas; `uniones_hojas` añade el nombre de la hoja de contacto de cada unión, presente en el
  JSON real aunque `doc.py` no la lee. Si el archivo falta, `doc` no falla: escribe una frase
  explícita y añade un aviso al informe.
- Produces: `doc.table(rows)`, `doc.percent(part, whole)`, `doc.count(number, singular, plural)`,
  `doc.transcriber(work)`, `doc.ficha(context)`, `doc.indice(context)`, `doc.validacion(context)` y el
  despachador `doc.block` definitivo.

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py`:

```python
class BlockTest(unittest.TestCase):
    def test_ficha_describes_the_medium_and_the_techniques(self):
        text = doc.expand("[[ficha]]\n", context())
        self.assertIn("| Archivo | grabación.mp4 |", text)
        self.assertIn("| Duración original | 1:36 |", text)
        self.assertIn("| Duración del resumen | 0:09 (10,0 % del original) |", text)
        self.assertIn("| Técnicas | 2 cortes · pausas eliminadas · velocidad ×1,25 |", text)
        self.assertIn("| Versión | v1 ·", text)

    def test_ficha_in_audio_mode_counts_ideas_and_questions(self):
        data = context(spans=None)
        data["schema"] = {"ideas": [{"id": 1}, {"id": 2}], "questions": [{"id": 1}]}
        text = doc.expand("[[ficha]]\n", data)
        self.assertIn("| Ideas clave | 2 ideas |", text)
        self.assertIn("| Preguntas | 1 pregunta |", text)
        self.assertNotIn("Técnicas", text)

    def test_indice_lists_source_and_output_times(self):
        text = doc.expand("[[indice]]\n", context())
        self.assertIn("| # | Origen | Salida | Tema |", text)
        self.assertIn("| 1 | 0:10–0:20 | 0:00–0:06 | Requisito y excepción |", text)
        self.assertIn("| 2 | 0:30–0:36 | 0:06–0:09 | Zona ATEX |", text)

    def test_validacion_reads_the_report_or_declares_its_absence(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            out = Path(temporary)
            data = context()
            data["out"] = out
            text = doc.expand("[[validacion]]\n", data)
            self.assertIn("no disponible", text)
            self.assertEqual(len(data["avisos"]), 1)
            (out / "validacion.json").write_text(json.dumps(
                {"fotogramas_esperados": 240, "fotogramas": 240, "video_s": 9.6, "audio_s": 9.58,
                 "desfase_s": 0.021,
                 "colocacion": [{"corte": 1, "titulo": "A", "salida_s": [0.0, 6.4],
                                 "imagen": [{"punto": "inicio", "distancia": 0.031}],
                                 # `bloques: 0` is a degenerate window (never measured): its
                                 # desfase_ms of 0 must not count as a perfect measurement.
                                 "envolvente": [{"punto": "inicio", "bloques": 86, "desfase_ms": 20,
                                                 "correlacion": 0.97},
                                                {"punto": "fin", "bloques": 0, "desfase_ms": 0,
                                                 "correlacion": None}]},
                                {"corte": 2, "titulo": "B", "salida_s": [6.4, 9.6],
                                 "imagen": [{"punto": "inicio", "distancia": 0.11}],
                                 "envolvente": [{"punto": "inicio", "bloques": 100, "desfase_ms": -40,
                                                 "correlacion": None}]}],
                 "marcas": ["corte 2 (inicio): imagen a 0,1100"], "uniones": [160]}),
                encoding="utf-8")
            data = context()
            data["out"] = out
            text = doc.expand("[[validacion]]\n", data)
            self.assertIn("| Fotogramas | 240 de 240 esperados |", text)
            self.assertIn("| Desfase vídeo/audio | 0,021 s |", text)
            self.assertIn("| Colocación de los cortes | 2 cortes comprobados · imagen máx. 0,110 · "
                          "envolvente máx. 40 ms |", text)
            self.assertIn("| Ventanas marcadas | 1 ventana |", text)
            self.assertIn("| Hojas de uniones | 1 unión |", text)
            self.assertEqual(data["avisos"], [])

    def test_video_only_blocks_are_refused_in_audio_mode(self):
        for name in ("indice", "timeline", "validacion"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "no existe en modo audio"):
                doc.expand(f"[[{name}]]\n", context(spans=None))
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k BlockTest -v
```

Esperado: FAIL con `ValueError: Línea 1: la marca [[ficha]] aún no está disponible.`

- [ ] **Paso 3: Implementar las utilidades de formato en `doc.py`**

```python
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
```

- [ ] **Paso 4: Implementar los tres bloques y el despachador**

Sustituye el `block` provisional de la tarea 3 por:

```python
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
    return {"ficha": ficha, "indice": indice, "validacion": validacion}[name](context)
```

`timeline` se añade al diccionario en la tarea 5; hasta entonces `[[timeline]]` en modo vídeo
provoca `KeyError`, que `main()` convierte en error controlado.

- [ ] **Paso 5: Ejecutar las pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS (13 pruebas).

- [ ] **Paso 6: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): bloques de ficha, índice de cortes e informe de validación" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Bloque `[[timeline]]` en texto y PNG opcional

El timeline se entrega siempre en texto; el PNG solo si Pillow está instalado, y su ausencia se avisa
sin cambiar el código de salida (spec §10, §15).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `doc.placements`, `common.clock`, `context["out"]` y `context["avisos"]`.
- Produces: `doc.timeline_row(spans, total, width=WIDTH) -> str`,
  `doc.timeline_text(spans, total, width=WIDTH) -> str`,
  `doc.timeline_png(spans, total, path) -> Path | None` y la entrada `timeline` del despachador.
  El PNG se escribe en `context["out"] / "timeline.png"` y el Markdown lo referencia como
  `timeline.png`, siempre relativo, nunca absoluto.

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py`:

```python
class TimelineTest(unittest.TestCase):
    def test_text_row_marks_the_kept_stretches(self):
        spans = doc.placements(SEGMENTS, 1.25, 25.0)
        row = doc.timeline_row(spans, 96.0, 48)
        self.assertEqual(len(row), 48)
        self.assertEqual([i for i, c in enumerate(row) if c == "█"], [5, 6, 7, 8, 9, 15, 16, 17])

    def test_text_timeline_states_both_durations(self):
        spans = doc.placements(SEGMENTS, 1.25, 25.0)
        text = doc.timeline_text(spans, 96.0)
        self.assertIn("original 1:36", text)
        self.assertIn("resumen 0:09", text)
        self.assertIn("0:00 ▕", text)
        self.assertIn("▏ 1:36", text)

    def test_png_is_written_when_pillow_exists_and_never_twice(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            data = context()
            data["out"] = Path(temporary)
            text = doc.expand("[[timeline]]\n", data)
            picture = Path(temporary) / "timeline.png"
            try:
                import PIL  # noqa: F401
            except ImportError:
                self.assertNotIn("![", text)
                self.assertTrue(any("Pillow" in aviso for aviso in data["avisos"]))
                return
            self.assertIn("![Línea temporal del resumen](timeline.png)", text)
            self.assertTrue(picture.is_file())
            before = picture.read_bytes()
            doc.expand("[[timeline]]\n", data)
            self.assertEqual(picture.read_bytes(), before)
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k TimelineTest -v
```

Esperado: FAIL con `AttributeError: module 'doc' has no attribute 'timeline_row'`.

- [ ] **Paso 3: Implementar el timeline de texto**

```python
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
```

- [ ] **Paso 4: Implementar el PNG opcional y registrar el bloque**

```python
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
```

y añade `timeline` al diccionario de `block`:

```python
    return {"ficha": ficha, "indice": indice, "timeline": timeline,
            "validacion": validacion}[name](context)
```

- [ ] **Paso 5: Ejecutar las pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS (16 pruebas). Con Pillow 12.2.0 instalado, el PNG mide 900×60 px y muestra una barra
gris con los cortes en azul.

- [ ] **Paso 6: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): timeline de texto y PNG opcional con Pillow" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: DOCX con Pandoc, con python-docx y degradación a solo Markdown

Tres caminos con la misma entrada y el mismo código de salida 0 (spec §10, §12).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `common.tool(name)` **(ampliación del contrato: se reutiliza para `pandoc`, no solo para
  FFmpeg; en Windows busca `pandoc.exe`, comprobado)** y `common.run(args)`.
- Produces: `doc.engine() -> str | None` (`"pandoc"`, `"python-docx"` o `None`),
  `doc.render_docx(markdown, target, base) -> None` (subconjunto de Markdown) y
  `doc.to_docx(markdown_path, target, base) -> str | None`, que devuelve el motor usado o `None`.
  `to_docx` escribe siempre en `Path(f"{target}.parcial")` y publica con `Path.replace`, porque
  en Windows un archivo aún abierto no se puede renombrar (comprobado).

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py` (junto a los imports, `import zipfile` y `from unittest import mock`):

````python
SAMPLE = """# Resumen

Párrafo con **negrita**, *cursiva* y `código`.

- Primera idea
- Segunda idea

| # | Origen | Tema |
| --- | --- | --- |
| 1 | 0:10–0:20 | Requisito |

```text
0:00 ▕·····█████▏ 1:36
```
"""


class DocxTest(unittest.TestCase):
    def test_markdown_only_when_no_converter_exists(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            base = Path(temporary)
            (base / "resumen.md").write_text(SAMPLE, encoding="utf-8")
            with mock.patch.object(doc.common, "tool", return_value=None), \
                 mock.patch.object(doc, "has_python_docx", return_value=False):
                self.assertIsNone(doc.to_docx(base / "resumen.md", base / "resumen.docx", base))
            self.assertFalse((base / "resumen.docx").exists())
            self.assertFalse(list(base.glob("*.parcial")))

    def test_the_available_engine_produces_a_readable_docx(self):
        if doc.engine() is None:
            self.skipTest("Ni Pandoc ni python-docx disponibles")
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            base = Path(temporary)
            (base / "resumen.md").write_text(SAMPLE, encoding="utf-8")
            used = doc.to_docx(base / "resumen.md", base / "resumen.docx", base)
            self.assertIn(used, ("pandoc", "python-docx"))
            with zipfile.ZipFile(base / "resumen.docx") as bundle:
                xml = bundle.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:tbl>", xml)
            self.assertIn("Requisito", xml)
            self.assertFalse(list(base.glob("*.parcial")))

    def test_the_markdown_subset_covers_the_document(self):
        if not doc.has_python_docx():
            self.skipTest("python-docx no instalado")
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            base = Path(temporary)
            doc.render_docx(SAMPLE, base / "fallback.docx", base)
            with zipfile.ZipFile(base / "fallback.docx") as bundle:
                xml = bundle.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:tbl>", xml)
            self.assertIn("<w:b/>", xml)
            self.assertIn("<w:i/>", xml)
            self.assertIn("Segunda idea", xml)
````

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k DocxTest -v
```

Esperado: FAIL con `AttributeError: module 'doc' has no attribute 'to_docx'`.

- [ ] **Paso 3: Implementar la detección de motor y la conversión con Pandoc**

```python
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
```

- [ ] **Paso 4: Implementar el subconjunto de Markdown con python-docx**

```python
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
```

- [ ] **Paso 5: Ejecutar las pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS. Con Pandoc 3.9 en PATH, `test_the_available_engine_produces_a_readable_docx` usa
`pandoc`; `test_the_markdown_subset_covers_the_document` se salta si `python-docx` no está instalado.

- [ ] **Paso 6: Comprobar a mano el camino de python-docx**

Si `python-docx` no está en el intérprete habitual, verifícalo una vez en un entorno aparte, fuera del
repositorio:

```text
python -m venv %TEMP%\docx-venv
%TEMP%\docx-venv\Scripts\python.exe -m pip install python-docx
%TEMP%\docx-venv\Scripts\python.exe -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k test_the_markdown_subset -v
```

Esperado: PASS con `python-docx` 1.2.0 (comprobado en esta máquina: tabla, negrita, cursiva e imagen
presentes en `word/document.xml`).

- [ ] **Paso 7: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): DOCX con Pandoc o python-docx y degradación a solo Markdown" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Subcomando `doc` en modo vídeo y revisiones `resumen-rM`

Publica `vN/resumen.md`, `vN/resumen.docx` y las revisiones posteriores, sin volver a montar (spec §6,
§10, A-4).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/video.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `common.publish(staged, final)`, `common.history(work, event, payload)`,
  `common.duration(data)`, `common.output_interval(rate)`, `common.positive(value)`.
- Consumes de `vN/seleccion.json`, que publica `render` (plan 2) copiando el `seleccion-vN.json` de
  `plan` (plan 1) con la frase de aceptación. Es el **esquema único acordado**, con las claves de datos
  en inglés: `version, parent, kind, source {path, size, mtime_ns, sha256}, audio_stream, timeline,
  settings, segments, reserves, estimate, alternativas, sugerencias, warnings, changes, sha256`.
  `doc` lee de él, y solo de él:
  - `segments[i]` con `id`, `numero`, `title`, `start`, `end`, `spans` (los tramos conservados, que en
    el plan publicado se llaman siempre así), `frames` (la `N` del corte) y `samples`;
  - `settings` con `speed`, `rate` (la fracción de `F`, p. ej. `"25/1"`) y `remove_pauses`; `target`,
    `silence_db`, `sample_rate` y `tolerance` están, pero `doc` no los usa.

  `start`, `end` y `remove_pauses` están garantizados en el plan publicado; si faltan —plan escrito a
  mano— `bounds_of` deduce los límites de los tramos y la ficha infiere que se quitaron pausas porque
  algún corte tiene más de un tramo.
- Produces:
  - `doc.register(sub)`, con la **convención de registro acordada**: cada módulo hermano expone
    `register(sub)`, cada subparser llama a `set_defaults(run=<función>)` y `video.main` despacha con
    `return args.run(args) or 0`. `video.py` fija `sys.dont_write_bytecode = True` antes de importar
    los hermanos.
  - `doc.context_of(work, number, out, metadata, schema=None) -> dict`, `doc.next_revision(out) -> int`,
    `doc.record_revision(out, number, reason, phrase, source) -> list`, `doc.publish_document(...)`,
    `doc.report_of(args) -> dict` y `doc.document(args) -> int`.
  - **`document` imprime su informe y devuelve 0**, igual que `compare`; el diccionario lo devuelve
    `report_of`, que es lo que llaman las pruebas.
  - Informe por stdout:
    ```json
    {"markdown": "…/resumen.md", "docx": "…/resumen.docx", "motor": "pandoc",
     "revision": null, "avisos": []}
    ```
  - Evento `doc` en `historial.jsonl` —uno por publicación, sea el documento o una revisión—, con
    `{version, revision, motor, archivo, kind}`. Es el único evento que escribe `doc.document`:
    `deliver` está reservado a la entrega final del trabajo y no lo escribe este subcomando.
  - **Ampliación del contrato:** `vN/revisiones.json` es el único índice de `vN/` que se reescribe
    (preparado aparte y publicado con `os.replace`, porque solo crece); todo lo demás publicado en
    `vN/` es inmutable. `vN/montaje.md`, el informe técnico que publica `render` (plan 2), ya está en
    la carpeta cuando llega `doc`: este plan lo cita como archivo existente y no lo lee ni lo
    reescribe. El documento de §6 es `vN/resumen.md` y lo escribe solo `doc`.

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py`:

```python
def workspace(root, kind="video"):
    """Minimal work folder: what prepare, plan and render leave behind."""
    work = Path(root)
    (work / "v1").mkdir(parents=True)
    source = {"path": "grabación.mp4", "size": 1, "mtime_ns": 2, "sha256": "ab"}
    (work / "metadata.json").write_text(json.dumps(
        {"format": {"duration": "96.0", "start_time": "0.000000"}, "streams": [],
         "source": source, "kind": kind, "audio_stream": 1, "avisos": [],
         "timeline": {"start": 0.0, "origin": 0.0, "rate": "25/1", "fps": 25.0,
                      "interval": 0.04, "sample_rate": 48000}}), encoding="utf-8")
    (work / "transcripcion.json").write_text(json.dumps(
        {"language": "es", "settings": {"model": "small"}, "segments": []}), encoding="utf-8")
    # The published plan, with the agreed key names; doc only reads segments and settings.
    (work / "v1/seleccion.json").write_text(json.dumps(
        {"version": 1, "parent": None, "kind": "video", "source": source, "audio_stream": 1,
         "timeline": {"start": 0.0, "origin": 0.0, "rate": "25/1", "fps": 25.0,
                      "interval": 0.04, "sample_rate": 48000},
         "settings": {"target": "10%", "speed": 1.25, "remove_pauses": True, "silence_db": -50.0,
                      "rate": "25/1", "sample_rate": 48000, "tolerance": 10.0},
         "segments": [{"id": 1, "numero": 1, "title": "Requisito y excepción",
                       "start": 10.0, "end": 20.0, "spans": [[10.0, 13.0], [15.0, 20.0]],
                       "frames": 160, "samples": 307200},
                      {"id": 2, "numero": 2, "title": "Zona ATEX", "start": 30.0, "end": 36.0,
                       "spans": [[30.0, 34.0]], "frames": 80, "samples": 153600}],
         "reserves": [], "estimate": {}, "alternativas": [], "sugerencias": [], "warnings": [],
         "changes": [], "sha256": "no-comprobado-por-doc"}), encoding="utf-8")
    (work / "documento-v1.md").write_text(
        "# Resumen\n\n[[ficha]]\n\n## Índice\n\n[[indice]]\n\n"
        "El requisito aparece en [[t=11.0]].\n", encoding="utf-8")
    return work


class DocumentTest(unittest.TestCase):
    def test_video_document_is_published_once_and_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            self.assertEqual(doc.document(doc.arguments(work=work, version=1)), 0)
            text = (work / "v1/resumen.md").read_text(encoding="utf-8")
            self.assertIn("| Archivo | grabación.mp4 |", text)
            self.assertIn("| Técnicas | 2 cortes · pausas eliminadas · velocidad ×1,25 |", text)
            self.assertIn("0:11 (resumen 0:00)", text)
            self.assertNotIn("[[", text)
            record = json.loads((work / "historial.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(record["evento"], "doc")
            self.assertEqual((record["version"], record["revision"]), (1, None))
            before = text
            with self.assertRaises(ValueError):
                doc.report_of(doc.arguments(work=work, version=1))
            self.assertEqual((work / "v1/resumen.md").read_text(encoding="utf-8"), before)
            self.assertFalse(list((work / "v1").glob("*.parcial")))

    def test_a_revision_publishes_rM_beside_the_first_delivery(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            doc.report_of(doc.arguments(work=work, version=1))
            (work / "documento-v1-r2.md").write_text(
                "# Resumen\n\nCorrige la cifra: son 12 equipos.\n", encoding="utf-8")
            report = doc.report_of(doc.arguments(
                work=work, version=1, source=work / "documento-v1-r2.md",
                revision="corrige la cifra de equipos", accept="la cifra correcta es 12"))
            self.assertEqual(report["revision"], 2)
            self.assertEqual(Path(report["markdown"]), work / "v1/resumen-r2.md")
            self.assertTrue((work / "v1/resumen.md").is_file())
            rows = json.loads((work / "v1/revisiones.json").read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["revision"], 2)
            self.assertEqual(rows[0]["frase"], "la cifra correcta es 12")
            self.assertEqual(rows[0]["motivo"], "corrige la cifra de equipos")
            events = [json.loads(line)["evento"] for line
                      in (work / "historial.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events, ["doc", "doc"])

    def test_a_revision_needs_the_literal_phrase(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            doc.report_of(doc.arguments(work=work, version=1))
            (work / "documento-v1-r2.md").write_text("# Resumen\n\nOtra cosa.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--accept"):
                doc.report_of(doc.arguments(work=work, version=1,
                                            source=work / "documento-v1-r2.md",
                                            revision="cambia algo"))
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k DocumentTest -v
```

Esperado: FAIL con `AttributeError: module 'doc' has no attribute 'arguments'`.

- [ ] **Paso 3: Implementar el contexto y el ayudante de pruebas**

`context_of` recibe ya leídos `metadata` y, en audio, `schema`, porque `document` los necesita antes
para decidir la carpeta de salida y comprobar la aceptación. Esta es su firma definitiva.

```python
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
```

- [ ] **Paso 4: Implementar las revisiones y la publicación**

```python
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
```

- [ ] **Paso 5: Implementar `document` y el registro del subcomando**

```python
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
```

En `video.py`, antes de las demás importaciones de módulos hermanos:

```python
import sys

sys.dont_write_bytecode = True  # The skill folder may be a read-only plugin cache.

import common  # noqa: E402
import doc  # noqa: E402
```

y en `build_parser`, tras registrar los subcomandos propios:

```python
    doc.register(sub)
```

`main()` termina con `return args.run(args) or 0`: la convención acordada vale para todos los
subcomandos, propios y de los módulos hermanos.

- [ ] **Paso 6: Ejecutar las pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_video.py" -v
```

Esperado: PASS en ambas; `test_doc.py` suma 22 pruebas (3 + 5 + 5 + 3 + 3 + 3).

- [ ] **Paso 7: Comprobar la ayuda y el código de salida del subcomando**

```text
python -B plugins/resumir-video/skills/resumir-video/scripts/video.py doc --help
python -B plugins/resumir-video/skills/resumir-video/scripts/video.py doc --work . --version 0
```

Esperado: las seis opciones en español; `--version 0` devuelve código 2 (argumento inválido) y una
publicación correcta devuelve 0.

- [ ] **Paso 8: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/video.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): publica el documento de la versión y sus revisiones resumen-rM" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `plan --kind audio` — esquema de ideas y preguntas, propuesta y sha256

El esquema que se muestra y se acepta antes de redactar (spec §4, §5, §6, §9, A-3). Es la **única**
implementación del modo audio de `plan`: el plan 1 crea `plan.py` con la rama de vídeo y su despachador
`run`, y esta tarea le añade la rama de audio.

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/plan.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_plan.py`

**Interfaces:**
- Consumes de `plan.py` (plan 1, tareas 10, 13, 15 y 16): `load(path)`, `dumps(data)`,
  `check_draft(draft, total, kind)`, `settings_of(draft, args, total, grid)` —**la firma fijada**, que
  toma la rejilla para copiar `rate` y `sample_rate` a los ajustes—,
  `publish_version(work, prefix, body, extra=None)` —que reserva `N`, fija `body["version"]` y
  `body["sha256"]`, escribe el JSON con `common.write_reserved` y publica `propuesta-vN.md`—,
  `cell(text)`, `dependency_warnings(rows, included)`, `topic_warnings(draft, rows, included)` y el
  despachador `run(args)`, que ya resuelve `work`, `data`, `total`, `draft`, `kind`, `settings`,
  `segments`, `levels`, `words` y `grid` antes de repartir. En audio, `grid` es la línea temporal que
  `prepare` escribió: la misma forma de seis claves, con `rate`, `fps` e `interval` a `null`.
- Modifica —código **ya existente** del plan 1, no solo la rama nueva de `audio_plan`— la firma de
  `check_parent(draft, work)` (`plan.py:124-131`) a `check_parent(draft, work, kind)`: el cuerpo pasa
  a comprobar `esquema-v{parent}.json` cuando `kind == "audio"` y `seleccion-v{parent}.json` en
  vídeo, en vez de asumir siempre el prefijo `seleccion` (hoy `check_parent` rechazaría cualquier
  `parent` de un esquema publicado). Actualiza también su única llamada, en `run` (`plan.py:915`), de
  `check_parent(draft, work)` a `check_parent(draft, work, kind)` — `run` ya calcula `kind` antes de
  esa línea (`kind = args.kind or data.get("kind") or "video"`), así que no hace falta adelantar
  nada, solo pasarlo.
- Consumes de `common.py`: `clock(value)`, `warning(code, message, *, cut=None)`, `plan_sha256(plan)`,
  `history(work, event, payload)`.
- Consumes de `test_plan.py` (plan 1): los ayudantes `work_folder(root, …, videos=0)`, `cut(...)`,
  `draft(work, segments, **head)`, `options(work, **extra)`, `call(work, **extra)` y `dry(work, **extra)`.
  `work_folder(root, seconds=…, videos=0)` ya deja `metadata.json` con `kind: "audio"`,
  `audio_stream: 0` y la línea temporal completa, porque `common.timeline` la devuelve también en solo
  audio: esta tarea **no** añade un ayudante propio para el modo audio.
- Consumes del borrador (§6): `segments[]` —con `included`, y sin `visual_evidence` obligatorio en
  audio, como ya declara el plan 1— y `questions[]`, la lista de preguntas de la sesión con
  `{id, start, end, question, answer, audio_evidence}`. **Esta tarea fija esa grafía inglesa**, igual
  que `segments`, `excluded` y `topics`, y sustituye a la grafía `preguntas` que el plan 1 había
  anotado en su tabla del borrador antes de que el modo audio pasara a este plan.
- Produces:
  - `plan.questions_of(draft, total) -> list[dict]`,
  - `plan.audio_plan(args, work, data, draft, settings, segments, total, levels, words, grid) -> int`,
    con la **misma convención de firma** que `video_plan`,
  - `plan.audio_proposal(body, total, name, version) -> str`,
  - la rama `kind == "audio"` de `plan.run`, que sustituye a la guarda `kind != "video"` del plan 1,
  - `esquema-vN.json` y `propuesta-vN.md`.
- Forma de `esquema-vN.json`, con las mismas claves inglesas que el esquema acordado de
  `seleccion-vN.json` (sin `timeline`, `segments`, `reserves` ni `estimate`, que en audio no existen):
  ```json
  {"version": 1, "parent": null, "kind": "audio", "request": "resume la reunión",
   "source": {"path": "…", "size": 1, "mtime_ns": 2, "sha256": "…"}, "audio_stream": 0,
   "settings": {"target": null, "speed": 1.0, "remove_pauses": false, "silence_db": -50.0,
                "rate": null, "sample_rate": 48000, "tolerance": null},
   "ideas": [{"numero": 1, "id": 1, "priority": 1, "title": "Alcance ATEX",
              "phrase": "el alcance cubre zona 1", "reason": "Define el ámbito",
              "audio_evidence": "12–45 s: definición del alcance", "start": 12.0, "end": 45.0}],
   "questions": [{"id": 1, "start": 100.0, "end": 130.0, "question": "¿Aplica a subcontratas?",
                  "answer": "Sí, con el mismo permiso.", "audio_evidence": "100–130 s: respuesta"}],
   "excluded": [], "changes": ["propuesta inicial"], "warnings": [], "sha256": "…"}
  ```
  En audio no hay montaje, así que `settings` se publica neutralizado (objetivo, velocidad y pausas
  sin efecto) y el agente lo indica al usuario (§4).
- Historial: `init` en la primera versión y `edit` cuando el borrador trae `parent`. No hay un evento
  `plan`: el vocabulario acordado es `init, edit, accept, render, verify, doc, deliver`.

- [ ] **Paso 1: Escribir la prueba que falla para la validación de las preguntas**

En `scripts/test_plan.py`, junto a los demás ayudantes. No hay ayudante de carpeta: el
`work_folder(root, seconds=…, videos=0)` del plan 1 ya escribe `kind: "audio"`, `audio_stream: 0` y la
línea temporal de solo audio.

```python
def question(id_, start, end, **extra):
    base = {"id": id_, "start": start, "end": end, "question": f"¿Pregunta {id_}?",
            "answer": "Respuesta de la fuente.", "audio_evidence": f"{start:.0f}–{end:.0f} s"}
    base.update(extra)
    return base


IDEAS = [cut(1, 12.0, 45.0, 1), cut(2, 60.0, 90.0, 1), cut(3, 200.0, 240.0, 2, included=False)]
QUESTIONS = [question(1, 100.0, 130.0), question(2, 150.0, 180.0)]
```

y la clase de pruebas:

```python
class AudioQuestionsTest(unittest.TestCase):
    def test_every_refusal_names_what_is_wrong(self):
        cases = [({"questions": "x"}, "una lista «questions»"),
                 ({"questions": [{**QUESTIONS[0], "id": 0}]}, "id entero positivo"),
                 ({"questions": [QUESTIONS[0], {**QUESTIONS[1], "id": 1}]}, "El id 1 se repite"),
                 ({"questions": [QUESTIONS[1], QUESTIONS[0]]}, "rompe el orden cronológico"),
                 ({"questions": [{**QUESTIONS[0], "end": 400.0}]}, "fuera del medio"),
                 ({"questions": [{**QUESTIONS[0], "end": 100.0}]}, "fuera del medio"),
                 ({"questions": [{**QUESTIONS[0], "answer": "  "}]}, "Falta answer en la pregunta 1")]
        for change, message in cases:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                plan.questions_of(change, 300.0)

    def test_a_correct_list_is_normalised(self):
        rows = plan.questions_of({"questions": QUESTIONS}, 300.0)
        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["question"], "¿Pregunta 1?")
        self.assertEqual(plan.questions_of({}, 300.0), [])
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k AudioQuestions -v
```

Esperado: FAIL con `AttributeError: module 'plan' has no attribute 'questions_of'`.

- [ ] **Paso 3: Implementar `questions_of` en `plan.py`**

```python
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
```

- [ ] **Paso 4: Ejecutarla y comprobar que pasa**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k AudioQuestions -v
```

Esperado: PASS (2 pruebas).

- [ ] **Paso 5: Escribir la prueba que falla para el esquema, la propuesta y el sha256**

Añade a `test_plan.py`:

```python
class AudioSchemaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-")
        self.work = Path(self.temporary.name)
        work_folder(self.work, seconds=300.0, videos=0)

    def tearDown(self):
        self.temporary.cleanup()

    def test_the_outline_is_published_with_a_proposal_and_a_canonical_hash(self):
        draft(self.work, IDEAS, request="resume la reunión",
              settings={"target": "10%", "speed": 1.5}, questions=QUESTIONS)
        code, output = call(self.work)
        self.assertEqual(code, 0)
        self.assertIn("esquema-v1.json", output)
        body = json.loads((self.work / "esquema-v1.json").read_text(encoding="utf-8"))
        self.assertEqual((body["kind"], body["version"]), ("audio", 1))
        self.assertEqual([(item["numero"], item["id"], item["start"], item["end"])
                          for item in body["ideas"]], [(1, 1, 12.0, 45.0), (2, 2, 60.0, 90.0)])
        self.assertEqual([item["id"] for item in body["questions"]], [1, 2])
        self.assertNotIn("segments", body)
        self.assertEqual(body["settings"], {"target": None, "speed": 1.0, "remove_pauses": False,
                                            "silence_db": -50.0, "rate": None,
                                            "sample_rate": 48000, "tolerance": None})
        self.assertEqual(body["sha256"], common.plan_sha256(
            {k: v for k, v in body.items() if k != "sha256"}))
        text = (self.work / "propuesta-v1.md").read_text(encoding="utf-8")
        self.assertIn("# Esquema v1", text)
        self.assertIn("2 ideas · 2 preguntas", text)
        self.assertIn("se ignoran objetivo, velocidad y pausas", text)
        self.assertIn("| 1 | 0:12–0:45 | 1 | Frase 1 |", text)
        self.assertIn("| 1 | 1:40–2:10 | ¿Pregunta 1? |", text)
        record = json.loads((self.work / "historial.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual((record["evento"], record["ideas"], record["preguntas"]), ("init", 2, 2))

    def test_a_second_version_records_an_edit(self):
        draft(self.work, IDEAS, questions=QUESTIONS)
        call(self.work)
        draft(self.work, IDEAS, parent=1, questions=QUESTIONS)
        code, _ = call(self.work)
        self.assertEqual(code, 0)
        self.assertTrue((self.work / "esquema-v2.json").is_file())
        self.assertTrue((self.work / "propuesta-v2.md").is_file())
        events = [json.loads(line)["evento"] for line
                  in (self.work / "historial.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events, ["init", "edit"])

    def test_dry_run_writes_nothing(self):
        draft(self.work, IDEAS, questions=QUESTIONS)
        before = sorted(p.name for p in self.work.iterdir())
        code, body = dry(self.work)
        self.assertEqual(code, 0)
        self.assertEqual(len(body["ideas"]), 2)
        self.assertEqual(body["sha256"], common.plan_sha256(
            {k: v for k, v in body.items() if k != "sha256"}))
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), before)

    def test_blocking_warnings_also_stop_an_outline(self):
        segments = [dict(IDEAS[0], depends_on=[3]), IDEAS[1], IDEAS[2]]
        draft(self.work, segments, questions=QUESTIONS)
        code, _ = call(self.work)
        self.assertEqual(code, 2)
        body = json.loads((self.work / "esquema-v1.json").read_text(encoding="utf-8"))
        self.assertEqual([item["codigo"] for item in body["warnings"] if item["bloquea"]],
                         ["dependencia_excluida"])

    def test_an_audio_job_never_asks_for_a_picture(self):
        segments = [{k: v for k, v in item.items() if k != "visual_evidence"} for item in IDEAS]
        draft(self.work, segments, questions=QUESTIONS)
        self.assertEqual(call(self.work)[0], 0)
```

- [ ] **Paso 6: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -k AudioSchema -v
```

Esperado: FAIL; la guarda `kind != "video"` que el plan 1 dejó en `run` rechaza el trabajo con
`El modo audio publica un esquema de ideas, no una selección de tramos`, así que no se escribe ningún
`esquema-v1.json`.

- [ ] **Paso 7: Implementar la rama de audio en `plan.py`**

```python
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
```

y en `run`, **retira la guarda** que el plan 1 dejó provisionalmente —las dos líneas

```python
    if kind != "video":
        raise ValueError("El modo audio publica un esquema de ideas, no una selección de tramos; "
                         "este subcomando todavía no lo genera.")
```

— y sustituye la última línea por el reparto, con la firma fijada de las dos ramas:

```python
    if kind == "audio":
        return audio_plan(args, work, data, draft, settings, segments, total, levels, words, grid)
    return video_plan(args, work, data, draft, settings, segments, total, levels, words, grid)
```

`run` ya calcula `grid` antes (`data.get("timeline") or common.timeline(data)`) y se lo pasa a
`settings_of(draft, args, total, grid)`, así que las dos ramas reciben la misma rejilla sin volver a
sondear el medio.

`check_parent` (`plan.py:124-131`) es **código ya existente del plan 1**, no de esta rama nueva, y hoy
solo sabe comprobar `seleccion-v{parent}.json`; en audio el padre publicado es `esquema-vN.json`, así
que esta tarea le cambia la firma y el cuerpo:

```python
def check_parent(draft, work, kind):
    """`parent` is null or the number of a version this folder has already published."""
    parent = draft.get("parent")
    if parent is None:
        return
    prefix = "esquema" if kind == "audio" else "seleccion"
    if type(parent) is not int or parent < 1 or not (work / f"{prefix}-v{parent}.json").is_file():
        raise ValueError("parent debe ser nulo o el número de una versión ya publicada "
                         f"({prefix}-vN.json en la carpeta de trabajo); recibido {parent!r}.")
```

y actualiza su única llamada, en el mismo `run` (`plan.py:915`), de `check_parent(draft, work)` a
`check_parent(draft, work, kind)`; `kind` ya está calculado ahí arriba (justo antes de la guarda que
esta tarea retira), así que la llamada solo cambia de aridad, no de lugar. Sin esta corrección,
`test_a_second_version_records_an_edit` (paso 5) fallaría: su segunda llamada plantea un borrador con
`parent: 1` sobre un trabajo de audio donde solo existe `esquema-v1.json`, y el `check_parent` de dos
argumentos de hoy buscaría `seleccion-v1.json` y lo rechazaría con código 2 en vez de publicar
`esquema-v2.json`.

`publish_version` fija `body["version"]` y `body["sha256"]` **antes** de escribir, calculando el hash
sobre el cuerpo sin la clave `sha256`: es exactamente lo que recomprueba `doc` en la tarea 9
(comprobado: el hash es estable tras escribir y releer el JSON y no depende del orden de las claves).

- [ ] **Paso 8: Ejecutar las pruebas del planificador y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: PASS; las siete pruebas nuevas de esta tarea (2 de `AudioQuestionsTest` y 5 de
`AudioSchemaTest`) se suman a las del plan 1.

- [ ] **Paso 9: Comprobar la ayuda real del subcomando**

```text
python -B plugins/resumir-video/skills/resumir-video/scripts/video.py plan --help
```

Esperado: `--kind {video,audio}` con `video` por defecto. El subparser y su `set_defaults(run=plan.run)`
son del plan 1: esta tarea **no** toca `video.py`.

- [ ] **Paso 10: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/plan.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_plan.py
git commit -m "feat(plan): esquema de ideas y preguntas del modo audio con propuesta y sha256" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `doc` en modo audio con aceptación contra el esquema

La entrega del modo audio: `documento-vN/resumen.md` (+ `.docx`), con la aceptación registrada y las
marcas de vídeo rechazadas (spec §5, §9, §10).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

**Interfaces:**
- Consumes: `common.plan_sha256(plan)` —que **ignora la clave `sha256`** por contrato del plan 1—,
  `common.new_dir(path)`, `common.save(path, data)`, `common.history(work, event, payload)` y el
  `esquema-vN.json` que publica la tarea 8, del que `doc` lee `ideas`, `questions` y `sha256`.
- Produces: `doc.accepted(schema, phrase) -> str` (devuelve el sha256 comprobado) y la rama de audio
  de `doc.report_of`, que crea `documento-vN/` con `new_dir`, publica `resumen.md` (+ `.docx`) y deja
  una copia inmutable del esquema en `documento-vN/esquema.json`.
- Historial: el mismo evento `doc` de la tarea 7, con el sha256 aceptado y la frase literal del
  usuario en la carga. `deliver` sigue reservado a la entrega final y no lo escribe `doc.document`.

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py`:

```python
def audio_workspace(root):
    work = Path(root)
    source = {"path": "reunión.m4a", "size": 1, "mtime_ns": 2, "sha256": "ab"}
    (work / "metadata.json").write_text(json.dumps(
        {"format": {"duration": "300.0"}, "streams": [], "kind": "audio", "audio_stream": 0,
         "source": source, "avisos": [],
         "timeline": {"start": 0.0, "origin": 0.0, "rate": None, "fps": None,
                      "interval": None, "sample_rate": 48000}}), encoding="utf-8")
    (work / "transcripcion.json").write_text(json.dumps(
        {"language": "es", "settings": {"model": "small"}, "segments": []}), encoding="utf-8")
    # Exactly what plan --kind audio publishes.
    schema = {"version": 1, "parent": None, "kind": "audio", "request": "resume la reunión",
              "source": source, "audio_stream": 0,
              "settings": {"target": None, "speed": 1.0, "remove_pauses": False,
                           "silence_db": -50.0, "rate": None, "sample_rate": 48000,
                           "tolerance": None},
              "ideas": [{"numero": 1, "id": 1, "priority": 1, "title": "Alcance ATEX",
                         "phrase": "cubre zona 1", "reason": "Define el ámbito",
                         "audio_evidence": "12–45 s", "start": 12.0, "end": 45.0}],
              "questions": [], "excluded": [], "changes": ["propuesta inicial"], "warnings": []}
    schema["sha256"] = common.plan_sha256(schema)
    (work / "esquema-v1.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    (work / "documento-v1.md").write_text(
        "# Resumen de la reunión\n\n[[ficha]]\n\nEl alcance se explica en [[t=12.0]].\n",
        encoding="utf-8")
    return work


class AudioDocumentTest(unittest.TestCase):
    def test_audio_delivery_needs_the_literal_acceptance(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = audio_workspace(temporary)
            with self.assertRaisesRegex(ValueError, "--accept"):
                doc.report_of(doc.arguments(work=work, version=1))
            self.assertFalse((work / "documento-v1").exists())

    def test_audio_delivery_publishes_the_document_and_the_schema(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = audio_workspace(temporary)
            report = doc.report_of(doc.arguments(work=work, version=1,
                                                 accept="adelante, redáctalo"))
            self.assertEqual(Path(report["markdown"]), work / "documento-v1/resumen.md")
            text = (work / "documento-v1/resumen.md").read_text(encoding="utf-8")
            self.assertIn("| Archivo | reunión.m4a |", text)
            self.assertIn("| Ideas clave | 1 idea |", text)
            self.assertIn("| Preguntas | 0 preguntas |", text)
            self.assertIn("El alcance se explica en 0:12.", text)
            self.assertNotIn("resumen 0:", text)
            self.assertTrue((work / "documento-v1/esquema.json").is_file())
            record = json.loads((work / "historial.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual((record["evento"], record["kind"]), ("doc", "audio"))
            self.assertEqual(record["frase"], "adelante, redáctalo")

    def test_a_hand_edited_schema_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = audio_workspace(temporary)
            schema = json.loads((work / "esquema-v1.json").read_text(encoding="utf-8"))
            schema["ideas"][0]["title"] = "Otro título"
            (work / "esquema-v1.json").write_text(json.dumps(schema, ensure_ascii=False),
                                                  encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sha256"):
                doc.report_of(doc.arguments(work=work, version=1, accept="adelante"))
            self.assertFalse((work / "documento-v1").exists())

    def test_video_marks_are_refused_in_an_audio_document(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = audio_workspace(temporary)
            (work / "documento-v1.md").write_text("# Resumen\n\n[[indice]]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Línea 3: la marca \\[\\[indice\\]\\] no existe"):
                doc.report_of(doc.arguments(work=work, version=1, accept="adelante"))
            self.assertFalse((work / "documento-v1").exists())
```

`common` ya está importado en `test_doc.py` desde la Tarea 3; no hace falta tocar los imports.

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k AudioDocumentTest -v
```

Esperado: FAIL con `ValueError: No existe la carpeta de la versión: …/documento-v1`.

- [ ] **Paso 3: Implementar la comprobación de aceptación**

```python
def accepted(schema, phrase):
    """The schema must be the one the user accepted, untouched, and the phrase must be literal."""
    if not (phrase or "").strip():
        raise ValueError("Falta --accept con la frase literal del usuario: en modo audio el esquema "
                         "se acepta antes de redactar.")
    recorded = schema.get("sha256")
    # plan_sha256 ignores the sha256 key by contract, so the stored one never feeds itself.
    computed = common.plan_sha256(schema)
    if recorded != computed:
        raise ValueError("El esquema no corresponde a su sha256: se ha modificado a mano. Vuelve a "
                         "generarlo con plan --kind audio y acéptalo de nuevo.")
    return computed
```

- [ ] **Paso 4: Derivar la rama de audio en `report_of`**

Sustituye `report_of` por esta versión, que trata las dos carpetas de salida. `context_of` no cambia:
ya recibía `metadata` y admitía `schema`, y `document` sigue siendo el envoltorio que imprime el
informe y devuelve 0. El orden importa: el documento se expande **antes** de crear `documento-vN/`, de
modo que una marca inválida no deja ninguna carpeta a medias.

```python
def report_of(args):
    work = Path(args.work).resolve()
    number = args.version
    metadata = read_json(work / "metadata.json")
    audio = metadata.get("kind") == "audio"
    out = work / (f"documento-v{number}" if audio else f"v{number}")
    source = Path(args.source) if args.source else work / f"documento-v{number}.md"
    if not source.is_file():
        raise ValueError(f"No existe el documento de partida: {source}")
    if args.revision and not (args.accept or "").strip():
        raise ValueError("Una revisión exige --accept con la frase literal del usuario.")
    schema, digest = None, None
    if audio:
        schema = read_json(work / f"esquema-v{number}.json")
        digest = accepted(schema, args.accept)
    elif not out.is_dir():
        raise ValueError(f"No existe la carpeta de la versión: {out}")
    context = context_of(work, number, out, metadata, schema)
    text = expand(source.read_text(encoding="utf-8-sig"), context)
    if audio and not out.is_dir():
        common.new_dir(out)
        common.save(out / "esquema.json", schema)
    revision = next_revision(out) if args.revision else None
    name = "resumen" if revision is None else f"resumen-r{revision}"
    markdown, used = publish_document(text, out, name, out, args.no_docx)
    if revision is not None:
        record_revision(out, revision, args.revision, args.accept, source)
    if used is None and not args.no_docx:
        context["avisos"].append("Sin Pandoc ni python-docx: la entrega es solo Markdown. Instala "
                                 "Pandoc (pandoc.org) o ejecuta `python -m pip install python-docx`.")
    common.history(work, "doc", {"version": number, "revision": revision, "motor": used,
                                 "archivo": markdown.name, "kind": metadata.get("kind"),
                                 "sha256": digest, "frase": args.accept})
    return {"markdown": str(markdown),
            "docx": None if used is None else str(markdown.with_suffix(".docx")),
            "motor": used, "revision": revision, "avisos": context["avisos"]}
```

- [ ] **Paso 5: Ejecutar las pruebas de audio y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k AudioDocumentTest -v
```

Esperado: PASS (4 pruebas).

- [ ] **Paso 6: Ejecutar toda la suite rápida y comprobar que no hay regresiones**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_plan.py" -v
```

Esperado: PASS en ambas; `test_doc.py` suma 26 pruebas.

- [ ] **Paso 7: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(doc): entrega del modo audio con aceptación contra el sha256 del esquema" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `compare` — cobertura de palabras y `cobertura_baja`

Validación informativa: mide cuántas de las palabras que el plan pretendía conservar sobreviven enteras
a los tramos montados, no bloquea y devuelve código 0 (spec §7.7, §8).

**Files:**
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/doc.py`
- Modify: `plugins/resumir-video/skills/resumir-video/scripts/test_doc.py`

`references/documento.md` **no se escribe aquí**: lo crea el plan 4 en su tarea de referencias. El
paso 6 deja redactado el texto de sus secciones para que ese plan lo publique sin reinventarlo.

**Interfaces:**
- Consumes: `common.warning(code, message, *, cut=None)`, `common.save(path, data)`,
  `common.history(work, event, payload)`, `common.positive(value)`, `doc.read_json(path)`.
- Produces: `doc.words_of(data) -> list[tuple[float, float, str]]`,
  `doc.coverage(segments, words) -> dict`, `doc.compare(args) -> int` y `vN/cobertura.json`:
  ```json
  {"version": 1, "disponible": true, "media": 0.94, "minimo": 0.87, "palabras": 812,
   "cubiertas": 763,
   "cortes": [{"corte": 1, "palabras": 52, "cubiertas": 49, "cobertura": 0.942,
               "perdidas": ["ATEX", "zona"]}],
   "avisos": [{"codigo": "cobertura_baja", "mensaje": "…", "corte": null, "bloquea": false}]}
  ```
- **`compare` es repetible.** `vN/` es inmutable: si `vN/cobertura.json` ya existe, `compare` no lo
  reescribe, avisa por `stderr` y devuelve 0. Volver a llamarlo tras montar otra vez nunca es un error.
- Historial: evento `verify` con `{"tipo": "cobertura", …}`, el mismo nombre que usa `render` para su
  validación; `compare` se distingue por `tipo`.
- **Suposición declarada:** la especificación no define la fórmula. Se adopta, por corte, la fracción
  de palabras de la transcripción que caen dentro de los límites del corte y sobreviven **enteras**
  dentro de alguno de sus tramos, con 20 ms de holgura. Es determinista, no exige volver a transcribir
  la salida y da valores compatibles con los umbrales 0,90 y 0,85 del §7.7. Los tramos y los límites
  se leen con `stretches_of` y `bounds_of` de la tarea 3, así que la fórmula vale igual para el plan
  publicado y para uno escrito a mano sin `start`/`end`.

- [ ] **Paso 1: Escribir la prueba que falla**

Añade a `test_doc.py`:

```python
WORDS = {"segments": [
    {"start": 3.0, "end": 9.0, "text": "", "words": [
        {"start": 3.1, "end": 3.3, "text": "La"}, {"start": 3.3, "end": 4.0, "text": "atmósfera"},
        {"start": 4.0, "end": 4.6, "text": "ATEX"}, {"start": 5.1, "end": 5.6, "text": "exige"},
        {"start": 5.6, "end": 6.1, "text": "un"}, {"start": 6.1, "end": 7.0, "text": "equipo"}]},
    {"start": 9.0, "end": 12.0, "text": "Sin permiso no se entra", "words": [
        {"start": 9.1, "end": 9.5, "text": "Sin"}, {"start": 9.5, "end": 9.9, "text": "permiso"},
        {"start": 10.2, "end": 11.0, "text": "no"}, {"start": 11.0, "end": 11.8, "text": "se"}]}]}
CUTS = [{"id": 1, "start": 3.0, "end": 9.0, "spans": [[3.0, 5.0], [5.5, 9.0]]},
        {"id": 2, "start": 9.0, "end": 12.0, "spans": [[9.0, 10.0]]}]


class CoverageTest(unittest.TestCase):
    def test_words_lost_to_a_removed_pause_are_counted(self):
        result = doc.coverage(CUTS, doc.words_of(WORDS))
        self.assertEqual(result["palabras"], 10)
        self.assertEqual(result["cubiertas"], 7)
        self.assertEqual(result["media"], 0.7)
        self.assertEqual(result["minimo"], 0.5)
        self.assertEqual(result["cortes"][0]["perdidas"], ["exige"])
        self.assertEqual(result["cortes"][1]["perdidas"], ["no", "se"])
        self.assertEqual([w["codigo"] for w in result["avisos"]], ["cobertura_baja"])
        self.assertFalse(result["avisos"][0]["bloquea"])

    def test_a_clean_cut_covers_everything_and_warns_about_nothing(self):
        whole = [{"id": 1, "start": 3.0, "end": 9.0, "spans": [[3.0, 9.0]]}]
        result = doc.coverage(whole, doc.words_of(WORDS))
        self.assertEqual((result["media"], result["minimo"]), (1.0, 1.0))
        self.assertEqual(result["avisos"], [])

    def test_compare_writes_the_report_and_returns_zero(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            (work / "transcripcion.json").write_text(json.dumps(
                {"language": "es", "settings": {"model": "small"},
                 "segments": [{"start": 10.0, "end": 20.0, "text": "uno", "words": [
                     {"start": 10.0, "end": 10.4, "text": "uno"},
                     {"start": 13.5, "end": 14.2, "text": "dos"}]}]}), encoding="utf-8")
            self.assertEqual(doc.compare(doc.arguments(work=work, version=1)), 0)
            report = json.loads((work / "v1/cobertura.json").read_text(encoding="utf-8"))
            self.assertEqual(report["version"], 1)
            self.assertTrue(report["disponible"])
            self.assertEqual(report["cortes"][0]["perdidas"], ["dos"])
            self.assertEqual([w["codigo"] for w in report["avisos"]], ["cobertura_baja"])
            record = json.loads((work / "historial.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual((record["evento"], record["tipo"]), ("verify", "cobertura"))

    def test_compare_can_be_run_again_without_touching_the_published_report(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            self.assertEqual(doc.compare(doc.arguments(work=work, version=1)), 0)
            before = (work / "v1/cobertura.json").read_bytes()
            self.assertEqual(doc.compare(doc.arguments(work=work, version=1)), 0)
            self.assertEqual((work / "v1/cobertura.json").read_bytes(), before)
            lines = (work / "historial.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

    def test_compare_without_a_transcription_says_so(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            (work / "transcripcion.json").unlink()
            self.assertEqual(doc.compare(doc.arguments(work=work, version=1)), 0)
            report = json.loads((work / "v1/cobertura.json").read_text(encoding="utf-8"))
            self.assertFalse(report["disponible"])

    def test_compare_refuses_an_audio_job(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = audio_workspace(temporary)
            with self.assertRaisesRegex(ValueError, "solo se aplica al modo vídeo"):
                doc.compare(doc.arguments(work=work, version=1))
```

- [ ] **Paso 2: Ejecutarla y comprobar que falla**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -k CoverageTest -v
```

Esperado: FAIL con `AttributeError: module 'doc' has no attribute 'coverage'`.

- [ ] **Paso 3: Implementar la cobertura**

```python
EPSILON = 0.02
LOW_MEAN = 0.9
LOW_CUT = 0.85


def words_of(data):
    """Every word with its own marks; a segment without them counts as a single unit."""
    rows = []
    for segment in data.get("segments") or []:
        marks = segment.get("words") or []
        if marks:
            rows += [(float(w["start"]), float(w["end"]), str(w.get("text", "")).strip())
                     for w in marks if str(w.get("text", "")).strip()]
        elif str(segment.get("text", "")).strip():
            rows.append((float(segment["start"]), float(segment["end"]),
                         str(segment["text"]).strip()))
    return sorted(rows)


def coverage(segments, words):
    """Share of the words of each cut that survive whole inside its kept stretches."""
    rows = []
    for cut in segments:
        pieces = stretches_of(cut)
        first, last = bounds_of(cut, pieces)
        total, lost = 0, []
        for start, end, text in words:
            if end <= first or start >= last:
                continue
            total += 1
            if not any(a - EPSILON <= start and end <= b + EPSILON for a, b in pieces):
                lost.append(text)
        rows.append({"corte": cut["id"], "palabras": total, "cubiertas": total - len(lost),
                     "cobertura": round((total - len(lost)) / total, 3) if total else 1.0,
                     "perdidas": lost[:10]})
    palabras = sum(row["palabras"] for row in rows)
    cubiertas = sum(row["cubiertas"] for row in rows)
    media = round(cubiertas / palabras, 3) if palabras else 1.0
    minimo = min((row["cobertura"] for row in rows), default=1.0)
    avisos = []
    if media < LOW_MEAN or minimo < LOW_CUT:
        avisos.append(common.warning(
            "cobertura_baja",
            f"Cobertura media {media:.2f} y mínima {minimo:.2f}: revisa los bordes de los cortes "
            "marcados o declara la pérdida en las limitaciones del documento."))
    return {"media": media, "minimo": minimo, "palabras": palabras, "cubiertas": cubiertas,
            "cortes": rows, "avisos": avisos}
```

- [ ] **Paso 4: Implementar el subcomando `compare`**

```python
def compare(args):
    work = Path(args.work).resolve()
    metadata = read_json(work / "metadata.json")
    if metadata.get("kind") != "video":
        raise ValueError("compare solo se aplica al modo vídeo: en audio no hay montaje que "
                         "contrastar con la transcripción.")
    out = work / f"v{args.version}"
    published = out / "cobertura.json"
    if published.is_file():
        # A published version is immutable, and running compare twice is not a mistake:
        # report what is already there and change nothing.
        print(f"Aviso: {out.name}/cobertura.json ya está publicado; no se reescribe.",
              file=sys.stderr)
        print(published.read_text(encoding="utf-8-sig"), end="")
        return 0
    plan = read_json(out / "seleccion.json")
    transcription = work / "transcripcion.json"
    if not transcription.is_file():
        report = {"version": args.version, "disponible": False,
                  "motivo": "No hay transcripcion.json: la cobertura de palabras no se puede medir."}
    else:
        report = {"version": args.version, "disponible": True,
                  **coverage(plan["segments"], words_of(read_json(transcription)))}
    common.save(published, report)
    common.history(work, "verify", {"tipo": "cobertura", "version": args.version,
                                    "media": report.get("media"), "minimo": report.get("minimo")})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
```

y añade su subparser a `register(sub)`:

```python
    p = sub.add_parser("compare", help="Cobertura de palabras del resumen frente al original "
                                       "(informativo, nunca bloquea).")
    p.add_argument("--work", required=True, help="Carpeta de trabajo creada por prepare.")
    p.add_argument("--version", type=common.positive, required=True, help="Versión montada (vN).")
    p.set_defaults(run=compare)
```

- [ ] **Paso 5: Ejecutar las pruebas y comprobar que pasan**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_doc.py" -v
```

Esperado: PASS (32 pruebas).

- [ ] **Paso 6: Dejar redactado el texto de `references/documento.md` para el plan 4**

**No crees el archivo.** `references/documento.md` lo publica el plan 4 en su tarea de referencias,
junto a `operacion.md`, `compresion.md` y `revision.md`. Lo que esta tarea aporta es el texto de las
secciones que describen lo implementado aquí, ya redactado y sin ninguna ruta absoluta
(`tests/test_packaging.py::test_payload_is_portable` las prohíbe en cualquier archivo bajo
`plugins/`). Guárdalo en el mensaje de entrega de esta tarea o en la propia pull request, y cita este
paso desde el plan 4.

El plan 4 ya tiene redactadas sus secciones «Estructura», «Marcas», «DOCX y timeline» y «Cobertura»:
estas cuatro las **completan**, no las sustituyen, y aportan además la de búsqueda.

````markdown
## Buscar en la transcripción

```text
python3 'SKILL_DIR/scripts/video.py' search 'TRABAJO/transcripcion.json' 'ATEX' --context 2
```

Compara en minúsculas y sin tildes, pero la eñe se conserva: «diseñó» se busca como «diseño» y
«diseno» no la encuentra. Devuelve, por coincidencia, el segmento, el instante de la **palabra**
cuando la transcripción trae marcas por palabra, el del segmento cuando no, el texto y el contexto.
`--max` limita el número de coincidencias (20 por defecto).

## Marcas del documento

El agente escribe `TRABAJO/documento-vN.md` con marcas y el script las expande:

| Marca | Se convierte en |
| --- | --- |
| `[[t=752.3]]` | `12:32 (resumen 1:05)` o `12:32 (no incluido en el resumen)` |
| `[[r=745-800]]` | `12:25–13:20 (resumen 1:02–1:15)`, `(no incluido…)` o `(incluido en parte…)` |
| `[[ficha]]` | Tabla con archivo, duraciones, porcentaje, técnicas, transcriptor y versión |
| `[[indice]]` | Tabla `# / Origen / Salida / Tema` (solo vídeo) |
| `[[timeline]]` | Línea temporal de texto y, con Pillow, `timeline.png` (solo vídeo) |
| `[[validacion]]` | Resumen de `vN/validacion.json` (solo vídeo) |

Reglas: las marcas de bloque ocupan una línea entera; los tiempos van en segundos; en modo audio,
`[[t]]` y `[[r]]` solo dan el tiempo del original y `[[indice]]`, `[[timeline]]` y `[[validacion]]` no
existen. `doc` se detiene citando la línea si encuentra una marca desconocida, un tiempo fuera del
medio, una ruta absoluta o un texto pendiente de completar (`TBD`, `TODO`, `FIXME`, `XXX`,
`(pendiente de completar)`); «(pendiente de verificar)» sí es válido y un enlace `https://…` no se
confunde con una ruta.

Si el instante cae en una pausa eliminada se usa el inicio del tramo siguiente del mismo corte, y si
esa pausa es la última del corte, el instante de salida de su fin.

## Publicar el documento

```text
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1 --accept 'adelante, redáctalo'
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1 --source 'TRABAJO/documento-v1-r2.md' --revision 'corrige la cifra' --accept 'la cifra correcta es 12'
```

En vídeo publica `vN/resumen.md` y `vN/resumen.docx`; en audio crea `documento-vN/` con `resumen.md`,
`resumen.docx` y una copia inmutable del esquema aceptado. En audio, `--accept` con la frase literal
del usuario es obligatorio y se comprueba contra el sha256 del esquema. Una revisión publica
`resumen-rM` (M ≥ 2) junto a la anterior y la registra en `revisiones.json`; la entrega apunta siempre
a la M mayor. Nada publicado se sobrescribe —`vN/montaje.md`, el informe técnico que escribe `render`,
tampoco se toca—. Cada publicación deja un evento `doc` en `historial.jsonl`; `deliver` es el de la
entrega final del trabajo.

DOCX: Pandoc si está en PATH; si no, `python-docx` con un subconjunto de Markdown (títulos, párrafos,
listas, tablas, negrita, cursiva, código e imagen). Sin ninguno de los dos la entrega es solo Markdown,
con código 0, aviso en el informe e instrucciones de instalación. `--no-docx` fuerza esa entrega.
El timeline es siempre de texto; el PNG requiere Pillow.

## Cobertura (informativa)

```text
python3 'SKILL_DIR/scripts/video.py' compare --work 'TRABAJO' --version 1
```

Escribe `vN/cobertura.json` y devuelve 0 siempre. Mide, por corte, qué proporción de las palabras de la
transcripción comprendidas en el corte sobrevive entera dentro de sus tramos (holgura de 20 ms). Por
debajo de 0,90 de media o de 0,85 en algún corte emite `cobertura_baja`, que no bloquea: el agente lo
resuelve moviendo bordes o lo declara en las limitaciones antes de entregar. Los dos umbrales son
provisionales hasta la calibración con material real. Repetir la orden sobre una versión que ya tiene
su `cobertura.json` no la reescribe: avisa y devuelve 0.
````

- [ ] **Paso 7: Ejecutar todas las comprobaciones del repositorio**

```text
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
python -B -m unittest discover -s tests
```

Esperado: PASS. `tests/test_packaging.py` seguirá fallando en `test_versions_agree_everywhere` hasta
que el plan 4 actualice los manifiestos, y en `test_referenced_files_exist` si `SKILL.md` ya enlaza
`references/documento.md` antes de que ese plan lo cree: son los dos únicos fallos admisibles al
cerrar este plan, y deben declararse al entregar.

- [ ] **Paso 8: Commit**

```bash
git add plugins/resumir-video/skills/resumir-video/scripts/doc.py \
        plugins/resumir-video/skills/resumir-video/scripts/test_doc.py
git commit -m "feat(compare): cobertura de palabras por corte con aviso cobertura_baja" \
           -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Contrato ampliado

Todo lo que este plan necesita y no venía en el contrato común, reunido para que los planes 1, 2 y 4
lo adopten sin conflicto:

| # | Ampliación | Quién la usa |
| --- | --- | --- |
| 1 | `common.pictures(data)` y `common.kind(data)`, que **define este plan** (tarea 1) | `prepare`, `plan`, `render`, `doc` |
| 2 | `metadata.json` con `kind`, `audio_stream`, `source` `{path, size, mtime_ns, sha256}`, `timeline` `{start, origin, rate, fps, interval, sample_rate}` —la que `common.timeline` devuelve siempre, también en solo audio, y que `prepare` escribe en los dos modos— y `avisos` (`fuente_vfr`, `huecos_pts`) | todos |
| 3 | Convención de subcomandos: cada módulo expone `register(sub)` y cada subparser llama a `set_defaults(run=…)`; `video.main` despacha con `return args.run(args) or 0` | `video.py`, `plan.py`, `render.py`, `doc.py` |
| 4 | `vN/seleccion.json` con el esquema único acordado; `doc` solo lee `segments[]` (`id`, `numero`, `title`, `start`, `end`, `spans`, `frames`, `samples`) y `settings` (`speed`, `rate`, `remove_pauses`) | lo publica `render` (plan 2) copiando el `seleccion-vN.json` de `plan` (plan 1); lo consume `doc` |
| 5 | `vN/validacion.json` con `fotogramas_esperados`, `fotogramas`, `video_s`, `audio_s`, `desfase_s`, `colocacion[]` (`imagen[].distancia`, `imagen[].salida_s`, `imagen[].origen_s`, `envolvente[].desfase_ms`, `envolvente[].bloques`, `envolvente[].modulacion_db`), `marcas[]`, `uniones[]` y la clave de nivel superior `uniones_hojas` (presente pero no leída por `doc`) (forma real del plan 2) | lo produce el plan 2, lo consume `doc` |
| 6 | `placements`, `output_at`, `stretches_of` y `bounds_of` viven en `doc.py`; `clock` vive en `common.py` y la usan `plan.py` y `doc.py` | `plan.py`, `doc.py` |
| 7 | `publish_version` (plan 1) rellena la reserva con `common.write_reserved`, nunca con `common.save` (modo exclusivo `x`) | `plan.py` |
| 8 | `common.tool` se reutiliza para `pandoc`, no solo para FFmpeg | `doc.py` |
| 9 | `vN/revisiones.json` es el único índice de una versión que se reescribe (staged + `os.replace`) | `doc.py` |
| 10 | Los `avisos` del informe de `doc` son textos operativos; solo `cobertura_baja`, `fuente_vfr` y `huecos_pts` usan `common.warning` | `doc.py`, `video.py` |
| 11 | `doc.document` y `doc.compare` imprimen su informe y devuelven 0; el diccionario del documento lo devuelve `doc.report_of` | pruebas de `doc` |
| 12 | El borrador de audio trae `questions[]` con `{id, start, end, question, answer, audio_evidence}`, y las pruebas del modo audio viven en `scripts/test_plan.py` | `plan.py` |
| 13 | `compare` es repetible: si `vN/cobertura.json` existe, avisa, no lo reescribe y devuelve 0 | `doc.py` |
| 14 | `doc.document` escribe el evento `doc` en cada publicación (documento o revisión); `deliver` se reserva a la entrega final y no lo escribe ningún subcomando de este plan | `doc.py` |
| 15 | `vN/montaje.md` es el informe técnico del montaje y lo publica `render` (plan 2); `doc` no lo lee ni lo reescribe, y `vN/resumen.md` sigue siendo el documento de §6 | `render.py`, `doc.py` |
| 16 | Firmas de `plan.py`: `settings_of(draft, args, total, grid)`, `video_plan(…, grid)` y `audio_plan(…, grid)`; `run` reparte entre las dos ramas sin guarda previa | `plan.py` |

## Comprobaciones empíricas hechas al escribir este plan

Todas en esta máquina (Windows 11, Python 3.11.9, FFmpeg 8.0.1-full_build, Pandoc 3.9, Pillow 12.2.0,
`python-docx` 1.2.0 en un entorno aparte):

- `kind` sobre medios sintéticos: `solo.wav`, `solo.m4a`, `solo.mp3` y un `.m4a` con carátula dan
  `audio`; un MP4 con vídeo y audio da `video`; un MP4 mudo y un MKV con dos pistas de vídeo se
  rechazan **antes** de crear la carpeta. Del `.m4a` con carátula, `ffprobe` devuelve la pista de
  audio en el índice 0 y la imagen en el 1, con `disposition.attached_pic = 1` (medido hoy); esta
  compilación de FFmpeg trae `libmp3lame`, así que el caso del `mp3` no se salta.
- `prepare` sobre esos cuatro medios: `metadata.json`, `audio.wav` de 16 kHz mono y `energia.f32` de
  502 bloques (5 s → 500 bloques de 10 ms, más el relleno del contenedor). La caché de energía se
  relee tal cual.
- **Rechazo de HDR.** Marcar la curva con `-color_trc smpte2084` **no** deja rastro en el contenedor:
  `ffprobe` no devuelve `color_transfer` (medido, con y sin 10 bits). La receta que sí lo graba es
  `-x264-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc"`, con la que `ffprobe`
  devuelve `color_transfer: smpte2084` y `color_primaries: bt2020`. Es la que usa la prueba.
- **Sondeo de paquetes.** `ffprobe -v error -select_streams <índice global> -show_entries
  packet=pts_time -read_intervals %+#600 -of json` acepta el índice global de la pista (no solo
  `v:0`): sobre un clip de 3 s a 25 fps devuelve 75 paquetes de vídeo en 0,08 s, todos separados
  0,040 s. Sobre el mismo clip con los fotogramas 25–49 eliminados por `select` —sin `setpts`, para
  conservar los PTS— el salto mayor es de **1,04 s**, muy por encima del umbral de 1,5 intervalos.
  Sobre una fuente de cadencia variable los saltos van de 0,033 a 0,034 s, así que ese umbral no
  produce falsos `huecos_pts`.
- Mapa de salida con `F = 25` y `v = 1,25`: corte 10–20 s con tramos 10–13 y 15–20 da 6,4 s
  (`N = 160`); 11 s → 0,8 s; 14 s (pausa) → 2,4 s; 35 s (última pausa del corte 30–36) → 9,6 s; fuera
  de todo corte → `None`. Con un plan escrito a mano que trae `spans` y `frames` pero no `start` ni
  `end` —el plan publicado sí los trae— los mismos instantes dan los mismos valores y 35 s queda fuera
  del corte, como debe. Con un `frames` publicado que no cuadra con `L · F / v` (161 en vez de 160)
  manda el publicado: 6,44 s de salida y el corte siguiente arranca ahí (medido hoy).
- Bloque `[[validacion]]` sobre la forma real del `validacion.json` del plan 2: las cinco filas salen
  tal cual las comprueba la prueba, con la coma decimal y los plurales correctos.
- Cadencia desde `settings["rate"]` con `1 / common.output_interval(rate)`: `"25/1"` → 25,0 y
  `"30000/1001"` → 29,97003.
- Marcas: los rechazos citan su línea; `(pendiente de verificar)` se acepta; `https://…` no se
  confunde con una ruta absoluta, porque el lookbehind exige que la letra anterior a los dos puntos no
  sea otra letra.
- Timeline de texto: con 96 s de original y 48 columnas, los cortes ocupan las columnas 5–9 y 15–17.
  PNG de 900×60 px: barra gris con bloques azules en 101–192 y 285–339 px (inspeccionado).
- Pandoc: `pandoc --from=markdown --to=docx --resource-path=… --output … …` incrusta la tabla, el
  bloque de código y el PNG. El renombrado del `.parcial` falla en Windows si el ZIP sigue abierto:
  por eso se publica con el archivo cerrado.
- `python-docx`: el subconjunto de Markdown produce `<w:tbl>`, `<w:b/>`, `<w:i/>`, lista con viñetas e
  `word/media/image1.png`.
- `search`: «ATEX», «atmosfera» y «ATMÓSFERA» encuentran lo esperado, con el instante de la palabra
  (3,3 s) cuando hay `words[]` y el del segmento (9,0 s) cuando no. Como `strip_accents` conserva la
  eñe, «diseño» encuentra «diseñó» y «diseno» no encuentra nada.
- `compare`: con dos cortes y 10 palabras, media 0,7 y mínima 0,5, con `cobertura_baja` no bloqueante;
  un corte sin pausas da 1,0 y ningún aviso.
- `common.plan_sha256`: estable tras escribir y releer el JSON e independiente del orden de las claves.
  `reserve_version` devuelve v1, v2 y v3 en llamadas sucesivas.
- Registro de subcomandos con `set_defaults(run=…)`: `video.py --version` (acción) y
  `video.py doc --version 1` (número) conviven sin conflicto; un `--version 0` devuelve código 2.
- Las órdenes de prueba funcionan tal cual, incluidas
  `python -B -m unittest discover -s <scripts> -p "test_doc.py" -k <prueba> -v`, y con `-B` no queda
  ningún `__pycache__`.
- **Ensayo completo del plan.** Antes de aplicar las decisiones de integración se montaron `doc.py`,
  `plan.py`, el `search` de `video.py` y sus pruebas copiando literalmente los bloques de código de
  este documento, sobre un `common.py` mínimo con las funciones del contrato: 37 pruebas, todas en
  verde, salvo `test_the_markdown_subset_covers_the_document`, que se salta sin `python-docx` y pasa
  con `python-docx` 1.2.0 en un intérprete aparte. **Ese ensayo no cubre la versión actual**: las
  decisiones de integración cambiaron `clock` de módulo, fijaron `spans` como única grafía de los
  tramos **dentro del plan publicado**, movieron el modo audio a `plan.py` con las pruebas en
  `test_plan.py`, partieron `document` en `report_of` más `document`, añadieron el rechazo de HDR y el
  sondeo de paquetes, unificaron la línea temporal en `common.timeline` y renombraron a `doc` el
  evento que escribe `doc.document`. Repetir el ensayo con los bloques de código de esta versión es
  **(pendiente de evidencia)**: hazlo al ejecutar la tarea 1 y anota el recuento real.
- Recuento previsto de pruebas, para contrastarlo con lo que salga: `test_video.py` pasa de las 12 que
  deja la tarea 1 del plan 1 a **18** (+6: 3 rápidas —`kind`, `search` y la eñe— y 3 con FFmpeg —los
  dos `prepare` y el HDR con huecos—), `test_doc.py` llega a **32** y `test_plan.py` suma **+7** a las
  del plan 1. Punto de partida medido hoy en el repositorio, antes de cualquier plan: 15 pruebas en
  `scripts/test_video.py` y 23 en `tests/`.
