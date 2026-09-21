"""Checks for the montage: fast ones first, then integration over generated media."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
