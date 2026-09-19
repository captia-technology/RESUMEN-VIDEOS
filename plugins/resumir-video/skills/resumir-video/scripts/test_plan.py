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
