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


if __name__ == "__main__":
    unittest.main()
