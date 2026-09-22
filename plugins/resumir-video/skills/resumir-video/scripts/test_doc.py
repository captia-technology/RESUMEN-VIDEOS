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


if __name__ == "__main__":
    unittest.main()
