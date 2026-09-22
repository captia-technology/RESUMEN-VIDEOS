"""Fast checks for doc.py: no FFmpeg, no optional dependencies."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

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

    def test_a_docx_failure_after_the_markdown_is_published_still_records_the_revision(self):
        # A published .md is immutable and irreplaceable at that name: a later DOCX crash must
        # never cost the revision its row in revisiones.json or its event in historial.jsonl.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            doc.report_of(doc.arguments(work=work, version=1))
            (work / "documento-v1-r2.md").write_text(
                "# Resumen\n\nCorrige la cifra: son 12 equipos.\n", encoding="utf-8")
            with mock.patch.object(doc, "to_docx", side_effect=RuntimeError("pandoc se cayó")):
                report = doc.report_of(doc.arguments(
                    work=work, version=1, source=work / "documento-v1-r2.md",
                    revision="corrige la cifra de equipos", accept="la cifra correcta es 12"))
            self.assertEqual(report["revision"], 2)
            self.assertIsNone(report["motor"])
            self.assertIsNone(report["docx"])
            self.assertTrue(any("DOCX" in aviso for aviso in report["avisos"]))
            self.assertTrue((work / "v1/resumen-r2.md").is_file())
            rows = json.loads((work / "v1/revisiones.json").read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["revision"], 2)
            self.assertEqual(rows[0]["frase"], "la cifra correcta es 12")
            events = [json.loads(line)["evento"] for line
                      in (work / "historial.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events, ["doc", "doc"])


class RevisionTest(unittest.TestCase):
    def test_next_revision_never_hands_out_the_same_number_twice(self):
        # A plain glob() + max() cannot see its own sibling call's choice until something is
        # published under that name; the exclusive reservation must, so two calls from the very
        # same state never collide.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            out = work / "v1"
            first = doc.next_revision(out)
            second = doc.next_revision(out)
            self.assertNotEqual(first, second)

    def test_record_revision_stages_the_index_before_replacing_it(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = workspace(temporary)
            out = work / "v1"
            source = work / "documento-v1-r2.md"
            source.write_text("# Resumen\n", encoding="utf-8")
            with mock.patch.object(doc.os, "replace", wraps=doc.os.replace) as replace:
                doc.record_revision(out, 2, "motivo", "la frase", source)
            self.assertEqual(replace.call_count, 1)
            staged, final = replace.call_args[0]
            self.assertEqual(Path(staged).name, "revisiones.json.parcial")
            self.assertEqual(Path(final).name, "revisiones.json")
            self.assertFalse(list(out.glob("revisiones.json.parcial")))


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


if __name__ == "__main__":
    unittest.main()
