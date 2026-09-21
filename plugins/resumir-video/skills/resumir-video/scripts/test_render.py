"""Checks for the montage: fast ones first, then integration over generated media."""

import array
import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import wave

import common
import plan as planner
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


def published(spans, speed=1.25, fps=25.0, sample_rate=48000, ident=1):
    """One cut as plan.py publishes it: the steps of `plan.measure` and the real `plan.cut_row`."""
    grid = {"fps": fps, "sample_rate": sample_rate, "interval": 1 / fps, "origin": 0.0}
    row = {"segment": {"id": ident, "title": "T", "phrase": "p", "reason": "r",
                       "audio_evidence": "a", "priority": 1},
           "a": spans[0][0], "b": spans[-1][1], "spans": spans}
    row["length"] = round(sum(end - start for start, end in spans), 6)
    row["frames"] = common.frames_for(row["length"], fps, speed)
    row["samples"] = common.samples_for(row["frames"], fps, sample_rate)
    row["subcuts"] = planner.split(spans, row["frames"], row["samples"], grid, speed)
    return planner.cut_row(row, ident, 0.0, grid)


class SubcutTest(unittest.TestCase):
    def test_one_pass_keeps_the_whole_cut(self):
        segment = published([(1.0, 2.0), (4.0, 5.0)], ident=3)
        parts = render.subcuts(segment)
        self.assertEqual(len(parts), 1)
        self.assertEqual((parts[0]["frames"], parts[0]["samples"]), (40, 76800))
        self.assertEqual((parts[0]["index"], parts[0]["total"], parts[0]["cut"]), (0, 1, 3))
        self.assertEqual(parts[0]["spans"], [(1.0, 2.0), (4.0, 5.0)])

    def test_the_split_reads_what_plan_published(self):
        # 95 spans give the passes [40, 40, 15]; the last one takes what is left of N and M.
        segment = published([(float(i), i + 0.5) for i in range(95)], speed=2.0)
        parts = render.subcuts(segment)
        self.assertEqual([len(part["spans"]) for part in parts], [40, 40, 15])
        self.assertEqual([part["total"] for part in parts], [3, 3, 3])
        self.assertEqual([(part["frames"], part["samples"]) for part in parts],
                         [(250, 480000), (250, 480000), (94, 180480)])
        self.assertEqual(sum(part["frames"] for part in parts), segment["frames"])
        self.assertEqual(sum(part["samples"] for part in parts), segment["samples"])

    def test_an_exact_tie_passes_because_render_reads_what_plan_published(self):
        # 25,92 - 24,76 is 1,1600000000000001 in floating point: adding it up again gives N = 15
        # and M = 28800, while plan measured the rounded length and published 14 and 26880.
        segment = published([(24.76, 25.92)], speed=2.0)
        self.assertEqual((segment["frames"], segment["samples"]), (14, 26880))
        self.assertEqual(common.frames_for(25.92 - 24.76, 25.0, 2.0), 15)
        parts = render.subcuts(segment)
        self.assertEqual((parts[0]["frames"], parts[0]["samples"]), (14, 26880))

    def test_a_cut_without_passes_or_with_an_empty_one_is_refused(self):
        whole = published([(1.0, 2.0)])
        for missing in ({"subcuts": []}, {"subcuts": None}, {"id": 9}):
            with self.subTest(missing=missing):
                segment = {key: value for key, value in whole.items() if key != "subcuts"}
                with self.assertRaisesRegex(render.Refused, "corte_vacio"):
                    render.subcuts(dict(segment, **missing))
        # FFmpeg answers 0 to trim=end_frame=0 and writes an empty file: the guard lives in Python.
        with self.assertRaisesRegex(render.Refused, "tramos, 0 fotogramas"):
            render.subcuts(dict(whole, subcuts=[dict(whole["subcuts"][0], frames=0)]))
        with self.assertRaisesRegex(render.Refused, "fotogramas y 0 muestras"):
            render.subcuts(dict(whole, subcuts=[dict(whole["subcuts"][0], samples=0)]))

    def test_a_cut_whose_numbers_do_not_add_up_is_refused(self):
        segment = published([(float(i), i + 0.5) for i in range(85)])
        with self.assertRaisesRegex(render.Refused, "declara 999 fotogramas"):
            render.subcuts(dict(segment, frames=999))
        with self.assertRaisesRegex(render.Refused, "declara .* 77 muestras"):
            render.subcuts(dict(segment, samples=77))
        first = segment["subcuts"][0]
        swapped = dict(first, spans=first["spans"][::-1])
        with self.assertRaisesRegex(render.Refused, "tramos no son los del corte"):
            render.subcuts(dict(segment, subcuts=[swapped] + segment["subcuts"][1:]))
        with self.assertRaisesRegex(render.Refused, "máximo es 30"):
            render.subcuts(segment, limit=30)

    def test_the_fractional_rate_is_exact(self):
        rate = 1 / common.output_interval("30000/1001")
        parts = render.subcuts(published([(4.0, 5.0), (7.0, 8.0)], fps=rate))
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
        part = render.subcuts(plan["segments"][0])[0]
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
        other["settings"] = dict(other["settings"], rate="30/1")
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["audio_stream"] = 2
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["source"] = dict(other["source"], sha256="cd")
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["source"] = dict(other["source"], size=999)
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        other = sample_plan()
        other["source"] = dict(other["source"], mtime_ns=999)
        self.assertNotEqual(base, render.cut_key(other, part, "8.0.1"))
        original_encoder = render.ENCODER
        try:
            render.ENCODER = ("-crf", "23")
            self.assertNotEqual(base, render.cut_key(plan, part, "8.0.1"))
        finally:
            render.ENCODER = original_encoder
        other = sample_plan()
        other["source"] = dict(other["source"], path="otra/ruta.mkv")
        self.assertEqual(base, render.cut_key(other, part, "8.0.1"))


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
        # §8 opens the audio chain with aresample; it changes neither N nor M (measured).
        self.assertTrue(text.startswith("[0:a]aresample=async=1:first_pts=0,asplit=2[s0][s1];"))
        self.assertIn("[s0]atrim=start=4.000000:end=5.000000,asetpts=N/SR/TB[t0];", text)
        self.assertIn("[s1]atrim=start=7.000000:end=8.000000,asetpts=N/SR/TB[t1];", text)
        self.assertIn("[t0][t1]concat=n=2:v=0:a=1,atempo=1.250000,", text)
        self.assertTrue(text.endswith("apad=whole_len=76800,atrim=end_sample=76800[a]"))

    def test_speed_one_leaves_no_atempo(self):
        self.assertNotIn("atempo", render.audio_filter([(0.0, 1.0)], 0.0, 1.0, 48000))

    def test_the_chosen_track_replaces_the_default_label(self):
        text = render.audio_filter([(0.0, 1.0)], 0.0, 1.0, 48000, label="0:3")
        self.assertTrue(text.startswith("[0:3]aresample=async=1:first_pts=0,asplit=1[s0];"))


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

    def test_the_reference_cut_keeps_exactly_143_frames_and_274560_samples(self):
        # Reference cut of the measurements: 7.16 s of source at x1.25 are N = 143 and M = 274560.
        spans = [(2.0, 5.08), (5.92, 10.0)]
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "fuente.mkv"
            coded(source)
            picture = root / "corte.mkv"
            common.ffmpeg("-ss", "0.000000", "-noaccurate_seek", "-copyts", "-i", source,
                          "-map", "0:v:0", "-an", "-sn", "-dn",
                          "-vf", render.video_filter(spans, 0.0, "25/1", 1.25, 143),
                          *render.ENCODER, picture)
            self.assertEqual(len(luminances(picture)), 143)

            def samples(chain, name):
                target = root / name
                common.ffmpeg("-ss", "0.000000", "-noaccurate_seek", "-copyts", "-i", source,
                              "-filter_complex", chain, "-map", "[a]", "-vn", "-c:a", "pcm_s16le",
                              target)
                with wave.open(str(target)) as stream:
                    first = int.from_bytes(stream.readframes(1), "little", signed=True)
                    return stream.getnframes(), first

            chain = render.audio_filter(spans, 0.0, 1.25, 274560)
            self.assertTrue(chain.startswith("[0:a]aresample=async=1:first_pts=0,"))
            count, first = samples(chain, "con.wav")
            self.assertEqual(count, 274560)
            # The ramp is t/10 of full scale: the first sample is the source at 2.0 s.
            self.assertLessEqual(abs(first - round(0.2 * 32768)), 4)
            # aresample at the head neither adds nor removes a sample (measured).
            plain = chain.replace("aresample=async=1:first_pts=0,", "")
            self.assertEqual(samples(plain, "sin.wav"), (count, first))


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
            part = render.subcuts(plan["segments"][0])[0]
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
            part = render.subcuts(plan["segments"][0])[0]
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
            part = render.subcuts(plan["segments"][0])[0]
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
            # A note that disagrees with the part is as bad as none: `is_cached` says so and the
            # cut is rebuilt, which is what `build` and the estimate of Tarea 11 also rely on.
            self.assertTrue(render.is_cached(plan, part, cortes, release))
            note["frames"] = 41
            third.with_suffix(".json").write_text(json.dumps(note), encoding="utf-8")
            self.assertFalse(render.is_cached(plan, part, cortes, release))
            fourth = render.cached_part(data, plan, part, cortes, release, 1)
            kept = json.loads(fourth.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual((kept["frames"], kept["samples"]), (40, 76800))
            self.assertFalse(list(cortes.glob("*.parcial")))


MEMORY_FAILURE = "ffmpeg falló (código 1):\nCannot allocate memory"


def cuts_plan(count):
    """A plan of `count` one-pass cuts of 40 frames, enough for the cache without any FFmpeg."""
    return sample_plan(segments=[sample_segment(id=n, numero=n, title=f"C{n}", start=2.0 * n,
                                                end=2.0 * n + 2.0,
                                                spans=[[2.0 * n, 2.0 * n + 2.0]],
                                                frames=40, samples=76800)
                                 for n in range(1, count + 1)])


def stub_render(calls, failures=()):
    """Stands in for `render_part`: records the threads, fails as told, then leaves a cut."""
    def stub(data, plan, part, target, threads):
        calls.append(threads)
        time.sleep(0.03)                # longer than the tick of the monotonic clock on Windows
        if len(calls) <= len(failures):
            raise ValueError(failures[len(calls) - 1])
        target.write_bytes(b"corte")
    return stub


class BudgetTest(unittest.TestCase):
    def test_only_recognised_memory_failures_are_retried(self):
        for text in ("ffmpeg falló (código 1):\nCannot allocate memory",
                     "ffmpeg falló (código 1):\nOut of memory",
                     "ffmpeg falló (código 1):\nav_buffer_alloc() failed",
                     "ffmpeg falló (código 137):\nmatado",
                     "ffmpeg falló (código 3221225495):\n",
                     "ffmpeg falló (código -9):\n"):
            with self.subTest(text=text):
                self.assertTrue(render.retryable(text))
        for text in ("ffmpeg falló (código 1):\nInvalid data found when processing input",
                     "ffmpeg falló (código 2):\nNo such file or directory",
                     # The code is read as a number from the head, never as a substring of stderr.
                     "ffmpeg falló (código 1):\nframe 137 duplicado (código 137)",
                     "ffmpeg falló (código 1370):\n"):
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
        parts = render.all_parts(plan)
        self.assertEqual([part["cut"] for part in parts], [1, 4])
        self.assertEqual(sum(part["frames"] for part in parts), 80)

    def test_a_plan_whose_estimate_disagrees_is_refused(self):
        published = [{"spans": [[1.0, 3.0]], "frames": 40, "samples": 76800}]
        plan = sample_plan(segments=[sample_segment(spans=[[1.0, 3.0]], frames=41, samples=76800,
                                                    subcuts=published)])
        with self.assertRaisesRegex(render.Refused, "41"):
            render.all_parts(plan)
        # The subcuts must add up to the cut's own spans, not just to its totals.
        moved = sample_plan(segments=[sample_segment(
            spans=[[1.0, 3.0]], frames=40, samples=76800,
            subcuts=[{"spans": [[1.0, 2.0]], "frames": 20, "samples": 38400},
                     {"spans": [[2.0, 3.0]], "frames": 20, "samples": 38400}])])
        with self.assertRaisesRegex(render.Refused, "subcortes"):
            render.all_parts(moved)

    def test_one_criterion_says_what_is_already_cached(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary)
            plan = cuts_plan(1)
            part = render.subcuts(plan["segments"][0])[0]
            target = cortes / f"{render.cut_key(plan, part, '8.0.1')}.mkv"
            note = target.with_suffix(".json")
            self.assertFalse(render.is_cached(plan, part, cortes, "8.0.1"))
            target.write_bytes(b"corte")
            self.assertFalse(render.is_cached(plan, part, cortes, "8.0.1"))       # no note
            common.save(note, render.cut_note(part, "8.0.1"))
            self.assertTrue(render.is_cached(plan, part, cortes, "8.0.1"))
            for damaged in (dict(render.cut_note(part, "8.0.1"), frames=41), [], "{"):
                note.unlink()
                if isinstance(damaged, str):
                    note.write_text(damaged, encoding="utf-8")
                else:
                    common.save(note, damaged)
                with self.subTest(note=damaged):
                    self.assertFalse(render.is_cached(plan, part, cortes, "8.0.1"))

    def test_a_memory_failure_is_retried_once_with_one_thread_and_leaves_no_debris(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary)
            plan = cuts_plan(2)
            first = render.subcuts(plan["segments"][0])[0]
            key = render.cut_key(plan, first, "8.0.1")
            (cortes / f"{key}.mkv").write_bytes(b"roto")       # damaged: set aside as `.parcial`
            calls = []
            with mock.patch.object(render, "render_part", stub_render(calls, [MEMORY_FAILURE])), \
                    contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                cuts = render.build(None, plan, cortes, "8.0.1", 4, None)
            # The first pass fails with 4 threads and is repeated once with 1; the second is
            # mounted normally: the retry does not change the threads of what follows.
            self.assertEqual(calls, [4, 1, 4])
            self.assertEqual(len(cuts), 2)
            self.assertFalse(list(cortes.glob("*.parcial")))
            note = json.loads((cortes / f"{key}.json").read_text(encoding="utf-8"))
            note.pop("segundos", None)          # the seconds it cost arrive with Tarea 11
            self.assertEqual(note, render.cut_note(first, "8.0.1"))
            # Progress goes to stderr; stdout stays clean for the JSON state of code 3.
            self.assertEqual(out.getvalue(), "")
            self.assertIn("Corte 2/2", err.getvalue())

    def test_only_memory_failures_get_a_retry_and_only_one(self):
        cases = (("Invalid argument", ["ffmpeg falló (código 1):\nInvalid argument"], [4]),
                 ("second memory failure", [MEMORY_FAILURE, MEMORY_FAILURE], [4, 1]))
        for name, failures, expected in cases:
            with self.subTest(name), tempfile.TemporaryDirectory(prefix="rv-") as temporary:
                cortes, calls = Path(temporary), []
                with mock.patch.object(render, "render_part", stub_render(calls, failures)), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(ValueError):
                        render.build(None, cuts_plan(1), cortes, "8.0.1", 4, None)
                self.assertEqual(calls, expected)
                self.assertFalse(list(cortes.glob("*.parcial")))

    def test_a_resumption_mounts_at_least_one_cut_before_it_stops(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            cortes = Path(temporary)
            plan = cuts_plan(3)
            first = render.subcuts(plan["segments"][0])[0]
            target = cortes / f"{render.cut_key(plan, first, '8.0.1')}.mkv"
            target.write_bytes(b"corte")                        # the first cut is already cached
            common.save(target.with_suffix(".json"), render.cut_note(first, "8.0.1"))
            calls = []
            with mock.patch.object(render, "render_part", stub_render(calls)), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(render.Pending) as caught:
                    render.build(None, plan, cortes, "8.0.1", 1, 0.01)
                # `done` and `total` count what this call mounts: the cached cut is neither, so
                # the resumption advanced by one and one is left.
                self.assertEqual(calls, [1])
                self.assertEqual(caught.exception.state,
                                 {"done": 1, "total": 2, "pending": 1,
                                  "bloques": ["corte 3 subcorte 1/1"]})
                self.assertEqual(len(render.build(None, plan, cortes, "8.0.1", 1, None)), 3)
                self.assertEqual(calls, [1, 1])


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
            report = render.totals_check(staged, render.all_parts(plan))
            self.assertEqual(report["fotogramas"], 70)
            self.assertEqual(report["fotogramas_esperados"], 70)
            self.assertLessEqual(report["desfase_s"], render.SYNC)

    def test_a_montage_short_of_frames_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            _, plan, _, staged = assembled(root)
            parts = render.all_parts(plan)
            parts[0] = dict(parts[0], frames=parts[0]["frames"] + 5)
            with self.assertRaisesRegex(render.Invalid, "75"):
                render.totals_check(staged, parts)

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
            report = render.totals_check(staged, render.all_parts(plan))
            self.assertEqual(report["fotogramas"], 17)
            packets = json.loads(common.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                             "-show_packets", "-show_entries",
                                             "packet=duration_time", "-of", "json", str(staged)]))
            self.assertFalse([item for item in packets["packets"]
                              if float(item["duration_time"]) < 0.001])


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
        # The reference's plateau starts 3 blocks earlier than the produced one's: what was
        # produced happens later than the reference, and `align` reports that as a positive lag
        # (measured against the real function: `align(produced, moved)` is `(0.0, 3, 1.0)`).
        moved = array.array("f", shape[3:] + [-60.0] * 3)
        difference, lag, value = render.align(produced, moved)
        self.assertEqual(lag, 3)
        self.assertLess(difference, 1.0)
        # Mirror case: now it is what was produced whose plateau starts 3 blocks earlier, so it is
        # produced that happens before the reference and the lag flips sign.
        difference, lag, value = render.align(moved, reference)
        self.assertEqual(lag, -3)
        self.assertLess(difference, 1.0)

    def test_a_flat_envelope_says_nothing_about_correlation(self):
        flat = array.array("f", [-9.0] * 40)
        self.assertLess(render.spread(flat), render.ENVELOPE_SPREAD)
        shaped = array.array("f", [-60.0] * 20 + [-9.0] * 20)
        self.assertGreater(render.spread(shaped), render.ENVELOPE_SPREAD)

    def test_a_scrambled_shape_correlates_below_the_gate(self):
        # §8 coverage: a modulated envelope (spread above the gate) whose blocks are reordered
        # correlates poorly even though nothing here is silence or truncated.
        steady = array.array("f", ([-9.0] * 10 + [-40.0] * 10) * 2)
        scrambled = array.array("f", ([-40.0] * 10 + [-9.0] * 10) * 2)
        self.assertGreaterEqual(render.spread(scrambled), render.ENVELOPE_SPREAD)
        self.assertLess(render.correlation(steady, scrambled), render.ENVELOPE_CORRELATION)

    def test_a_lag_beyond_the_gate_is_reported(self):
        # §8 coverage: a shift of 5 blocks (50 ms) exceeds both the 40 ms of ENVELOPE_LAG and the
        # 45 ms of §8; `validate` reads it from `abs(desfase_ms)`, computed the same way here.
        shape = [-60.0] * 10 + [-10.0] * 30 + [-60.0] * 10
        produced = array.array("f", shape)
        reference = array.array("f", shape[5:] + [-60.0] * 5)
        difference, lag, value = render.align(produced, reference)
        self.assertEqual(lag, 5)
        desfase_ms = abs(lag) * round(render.LEVEL_BLOCK * 1000)
        self.assertGreater(desfase_ms, 45)
        self.assertGreater(desfase_ms, render.ENVELOPE_LAG * round(render.LEVEL_BLOCK * 1000))


def spoken(path, length=12):
    """Source with 1 s of tone and 0.5 s of silence in turns: an envelope with real modulation."""
    common.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=320x180:r=25:d={length}",
                  "-f", "lavfi", "-i", "aevalsrc=exprs='0.5*sin(2*PI*440*t)*"
                                       r"lt(mod(t\,1.5)\,1.0)':sample_rate=48000:"
                                       f"duration={length}",
                  "-vf", "geq=lum='N':cb=128:cr=128,format=yuv420p",
                  "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast", "-bf", "0",
                  "-c:a", "pcm_s16le", path)


def spoken_second_track(path, length=6):
    """Same tone/silence envelope, but as the SECOND audio stream; the first is silent."""
    common.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=320x180:r=25:d={length}",
                  "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={length}",
                  "-f", "lavfi", "-i", "aevalsrc=exprs='0.5*sin(2*PI*440*t)*"
                                       r"lt(mod(t\,1.5)\,1.0)':sample_rate=48000:"
                                       f"duration={length}",
                  "-map", "0:v", "-map", "1:a", "-map", "2:a",
                  "-vf", "geq=lum='N':cb=128:cr=128,format=yuv420p",
                  "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast", "-bf", "0",
                  "-c:a", "pcm_s16le", path)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class SoundPlacementTest(unittest.TestCase):
    # 74 frames / 142 080 samples (spans up to 4.4 s instead of 4.08 s): the previous fixture left
    # only 0.001 of margin over ENVELOPE_CORRELATION at the end (0.901 measured); this one measures
    # 0.973 and 1.0, so a codec change would not block a correct montage by accident.
    def built(self, root, source_path=None):
        source = source_path or root / "voz.mkv"
        if source_path is None:
            spoken(source)
        spans = [[0.0, 1.08], [1.42, 2.58], [2.92, 4.4]]
        plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                           segments=[sample_segment(id=1, numero=1, title="A", start=0.0, end=4.4,
                                                    spans=spans, frames=74, samples=142080)])
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
            rows = render.sound_placement(data, staged, spans, 0.0, 74 / 25, 1.25, root)
            self.assertEqual([row["punto"] for row in rows], ["inicio", "fin"])
            # Measured here: 0.81 dB / 0.973 at the start and 0.17 dB / 1.0 at the end, both with
            # real margin over ENVELOPE_MARK and ENVELOPE_CORRELATION.
            for row in rows:
                with self.subTest(row=row):
                    self.assertLessEqual(row["diferencia_db"], render.ENVELOPE_MARK, row)
                    self.assertLessEqual(abs(row["desfase_ms"]), render.ENVELOPE_LAG * 10, row)
                    self.assertGreater(row["bloques"], 80, row)
                    self.assertIsNotNone(row["correlacion"], row)
                    self.assertGreaterEqual(row["correlacion"], render.ENVELOPE_CORRELATION, row)

    def test_a_cut_claimed_from_the_wrong_place_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            data, staged, _ = self.built(root)
            moved = [(0.75, 1.83), (2.17, 3.33), (3.67, 5.15)]
            rows = render.sound_placement(data, staged, moved, 0.0, 74 / 25, 1.25, root)
            # §8 coverage: measured 54.22 / 74.16 dB and correlación −0.131 / −0.498, so both the
            # difference and the correlation gates would reject this montage.
            self.assertTrue(any(row["diferencia_db"] > render.ENVELOPE_MARK for row in rows), rows)
            self.assertTrue(any(row["correlacion"] is not None
                                and row["correlacion"] < render.ENVELOPE_CORRELATION
                                for row in rows), rows)

    def test_a_shifted_source_is_still_matched_correctly(self):
        # §13 coverage of hallazgo 4: base contada dos veces. `shifted()` (Tarea 3) remuxes with
        # -output_ts_offset so format.start_time = 7 s; the numbers must be identical to the
        # unshifted source above, because window_levels never adds `base`.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            plain = root / "voz-plana.mkv"
            spoken(plain)
            moved = root / "voz-desfasada.mkv"
            shifted(moved, plain, ahead=7)
            data, staged, spans = self.built(root, source_path=moved)
            self.assertAlmostEqual(common.timeline_start(data), 7.0, places=3)
            rows = render.sound_placement(data, staged, spans, 0.0, 74 / 25, 1.25, root)
            for row in rows:
                with self.subTest(row=row):
                    self.assertLessEqual(row["diferencia_db"], render.ENVELOPE_MARK, row)
                    self.assertIsNotNone(row["correlacion"], row)
                    self.assertGreaterEqual(row["correlacion"], render.ENVELOPE_CORRELATION, row)

    def test_the_chosen_track_is_compared_against_the_source(self):
        # §8 coverage of hallazgo 5: `plan["audio_stream"]` is not the first audio track. Without
        # `track`, sound_placement would compare the montage against the silent first track and
        # reject a correct montage.
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "dos-pistas.mkv"
            spoken_second_track(source)
            spans = [[0.5, 1.58], [1.92, 3.08]]
            plan = sample_plan(source={"path": str(source.resolve()), **common.fingerprint(source)},
                               segments=[sample_segment(id=1, numero=1, title="A", start=0.5,
                                                        end=3.08, spans=spans, frames=56,
                                                        samples=107520)])
            plan["settings"]["speed"] = 1.0
            plan["audio_stream"] = 2                    # the second audio stream, absolute index 2
            data = common.probe(source)
            cortes = root / "cortes"
            cortes.mkdir()
            cuts = render.build(data, plan, cortes, render.ffmpeg_release(), 1, None)
            staged = cortes / "resumen.mp4"
            render.assemble(cortes, cuts, staged, 1)
            spans_t = [(a, b) for a, b in spans]
            rows = render.sound_placement(data, staged, spans_t, 0.0, 56 / 25, 1.0, root,
                                          track=f"0:{plan['audio_stream']}")
            for row in rows:
                with self.subTest(row=row):
                    self.assertLessEqual(row["diferencia_db"], render.ENVELOPE_MARK, row)


if __name__ == "__main__":
    unittest.main()
