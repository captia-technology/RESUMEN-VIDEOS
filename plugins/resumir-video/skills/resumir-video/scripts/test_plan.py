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
        rows, included, settings, report = self.prepared("40%")
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

    def test_a_suggestion_never_touches_essentials_pinned_or_dependencies(self):
        segments = [cut(1, 2.0, 10.0, 1), cut(2, 11.0, 18.0, 3, pinned=True),
                    cut(3, 19.0, 26.0, 3), cut(4, 40.0, 47.0, 3, depends_on=[5]),
                    cut(5, 49.0, 55.0, 3)]
        rows, included, settings, report = self.prepared("12s", segments)
        hints = plan.suggestions(rows, included, settings, report)
        # 1 is essential, 2 is pinned and 5 is needed by 4: only 4 can be suggested.
        self.assertEqual(hints[0]["cortes"], [4])


if __name__ == "__main__":
    unittest.main()
