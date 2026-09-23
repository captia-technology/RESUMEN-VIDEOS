import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import common
import overlay

try:
    from PIL import Image
except ImportError:
    Image = None

SPANS = [{"id": 4, "title": "Primer tema", "start": 10.0, "end": 20.0, "offset": 0.0, "length": 2.0},
         {"id": 9, "title": "", "start": 40.0, "end": 45.0, "offset": 2.0, "length": 2.0}]


class CutsTest(unittest.TestCase):
    def test_labels_override_titles_and_every_cut_gets_one(self):
        cuts = overlay.cuts_of(SPANS, {"4": "Rótulo propio"})
        self.assertEqual([c["label"] for c in cuts], ["Rótulo propio", "Corte 9"])
        self.assertEqual([(c["n"], c["s"], c["e"]) for c in cuts], [(1, 0.0, 2.0), (2, 2.0, 4.0)])

    def test_labels_must_be_a_map_of_texts(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            path = Path(temporary) / "rotulos.json"
            path.write_text('["no"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--labels"):
                overlay.load_labels(path)
        self.assertEqual(overlay.load_labels(None), {})


@unittest.skipIf(Image is None, "Pillow requerido")
class PictureTest(unittest.TestCase):
    def test_the_labelled_timeline_grows_with_the_legend(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            few = overlay.labelled_timeline(overlay.cuts_of(SPANS), 60.0, 1.5,
                                            Path(temporary) / "pocos.png")
            many = [dict(SPANS[0], id=n, offset=2.0 * n) for n in range(10)]
            more = overlay.labelled_timeline(overlay.cuts_of(many), 60.0, 1.5,
                                             Path(temporary) / "muchos.png")
            with Image.open(few) as a, Image.open(more) as b:
                self.assertEqual(a.width, 1800)
                self.assertGreater(b.height, a.height)
            self.assertFalse(list(Path(temporary).glob("*.parcial")))

    def test_a_panel_covers_the_frame_and_leaves_the_top_transparent(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cuts = overlay.cuts_of(SPANS)
            path = Path(temporary) / "panel.png"
            place = overlay.panel(cuts, cuts[1], 60.0, 1.25, (640, 360), path)
            with Image.open(path) as layer:
                self.assertEqual(layer.size, (640, 360))
                self.assertEqual(layer.getpixel((5, 5))[3], 0)
                self.assertGreater(layer.getpixel((5, 355))[3], 200)
            self.assertLess(place["x0"] + place["inner"], 640)


@unittest.skipUnless(Image is not None and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg y Pillow requeridos")
class AnnotateTest(unittest.TestCase):
    def test_a_derived_copy_is_published_beside_the_untouched_version(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            work = Path(temporary)
            version = work / "v1"
            version.mkdir()
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "testsrc=size=320x180:rate=10:duration=4", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=4", "-c:v", "libx264", "-pix_fmt",
                            "yuv420p", "-c:a", "aac", "-shortest", str(version / "resumen.mp4")],
                           check=True)
            before = (version / "resumen.mp4").read_bytes()
            (work / "metadata.json").write_text(json.dumps(
                {"kind": "video", "format": {"duration": "60"}}), encoding="utf-8")
            (version / "seleccion.json").write_text(json.dumps({
                "settings": {"speed": 1.0, "rate": "10/1"},
                "segments": [{"id": 4, "title": "Uno", "start": 10.0, "end": 12.0,
                              "spans": [[10.0, 12.0]], "frames": 20},
                             {"id": 9, "title": "Dos", "start": 40.0, "end": 42.0,
                              "spans": [[40.0, 42.0]], "frames": 20}]}), encoding="utf-8")
            args = types.SimpleNamespace(work=str(work), version=1, labels=None, threads=1)
            with mock.patch("sys.stdout"):
                self.assertEqual(overlay.annotate(args), 0)
            target = work / "v1-rotulado"
            self.assertEqual(sorted(p.name for p in target.iterdir()),
                             ["linea-tiempo.png", "resumen-rotulado.mp4", "rotulos.json"])
            self.assertEqual((version / "resumen.mp4").read_bytes(), before)
            labels = json.loads((target / "rotulos.json").read_text(encoding="utf-8"))
            self.assertEqual([c["rotulo"] for c in labels["cortes"]], ["Uno", "Dos"])
            self.assertAlmostEqual(common.duration(common.probe(target / "resumen-rotulado.mp4")),
                                   4.0, delta=0.1)
            self.assertIn('"evento": "annotate"', (work / "historial.jsonl").read_text("utf-8"))
            with self.assertRaisesRegex(ValueError, "no se sobrescribe"):
                overlay.annotate(args)


if __name__ == "__main__":
    unittest.main()
