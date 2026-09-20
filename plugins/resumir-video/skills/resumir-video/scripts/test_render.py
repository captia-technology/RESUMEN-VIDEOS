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


if __name__ == "__main__":
    unittest.main()
