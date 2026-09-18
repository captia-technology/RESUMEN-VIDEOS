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

    def test_band_never_falls_below_ten_seconds(self):
        self.assertAlmostEqual(common.tolerance(720), 36.0)
        self.assertAlmostEqual(common.tolerance(200), 10.0)
        self.assertAlmostEqual(common.tolerance(100), 10.0)
        self.assertAlmostEqual(common.tolerance(240), 12.0)

    def test_rounding_to_the_returned_precision_cannot_reach_the_original(self):
        for text in ("179.9999s", "179.9996s", "2:59.9999"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                common.parse_target(text, 180.0)
        self.assertAlmostEqual(common.parse_target("179.99s", 180.0), 179.99)


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
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            medium = Path(temporary) / "medio.bin"
            data = b"A" * (6 * 1024 * 1024)
            medium.write_bytes(data)
            # Hash must be exactly the complete file, not just the ends.
            expected = hashlib.sha256(data).hexdigest()
            self.assertEqual(common.fingerprint(medium)["sha256"], expected)
            # Byte 5 MiB: past the first 4 MiB, so only reading a 6 MiB file whole notices it.
            with medium.open("r+b") as stream:
                stream.seek(5 * 1024 * 1024)
                stream.write(b"QQQQ")
            self.assertNotEqual(common.fingerprint(medium)["sha256"], expected)

    def test_large_files_use_only_ends(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            large = Path(temporary) / "grande.bin"
            data = b"A" * (12 * 1024 * 1024)
            large.write_bytes(data)
            # Hash must be exactly the first 4 MiB + last 4 MiB.
            expected = hashlib.sha256(data[:common.CHUNK] + data[-common.CHUNK:]).hexdigest()
            self.assertEqual(common.fingerprint(large)["sha256"], expected)


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
            long_path = Path(temporary) / "largo.wav"
            tone_wav(long_path, seconds=120.0, pauses=())
            started = time.perf_counter()
            common.energy(long_path)
            spent = time.perf_counter() - started
            # Budget alarm, not a comparison of implementations: 30 s per 2 h, scaled to 120 s.
            self.assertLess(spent, 0.5)

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


if __name__ == "__main__":
    unittest.main()
