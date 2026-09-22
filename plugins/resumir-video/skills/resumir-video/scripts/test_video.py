"""Integration checks using generated media; no downloads or external services."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import common
import video


def invoke(test, *arguments, ok=True):
    # Drop UTF-8 overrides so the check covers the default encoding of piped output.
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    result = subprocess.run([sys.executable, "-B", str(Path(video.__file__)), *map(str, arguments)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    test.assertEqual(result.returncode == 0, ok, result.stderr)
    return result


def synthetic(path, seconds):
    video.ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=25:duration={seconds}",
                 "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path)


def decoded_audio_seconds(path):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0",
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return len(pcm) / 32000


def gray_signature(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=32:18,format=gray",
                           "-f", "rawvideo", "-"], capture_output=True, check=True).stdout


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
class VideoTest(unittest.TestCase):
    def test_extract_edit_and_protect_source(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "vídeo de prueba ' uno.mp4"
            synthetic(source, 6)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            invoke(self, "prepare", source, "--work", root / "evidencia")
            metadata = json.loads((root / "evidencia/metadata.json").read_text(encoding="utf-8"))
            sound = [s for s in metadata["streams"] if s["codec_type"] == "audio"][0]
            self.assertEqual(metadata["audio_stream"], sound["index"])
            self.assertEqual(metadata["source"]["size"], source.stat().st_size)
            self.assertEqual((root / "evidencia/.gitignore").read_text(encoding="utf-8"), "*\n")
            self.assertAlmostEqual(video.duration(video.probe(root / "evidencia/audio.wav")), 6,
                                   delta=.1)
            self.assertAlmostEqual(decoded_audio_seconds(root / "evidencia/audio.wav"), 6, delta=.1)
            invoke(self, "frames", source, "--out", root / "imagenes", "--step", "2")
            index = json.loads((root / "imagenes/index.json").read_text(encoding="utf-8"))
            self.assertEqual([f["time"] for f in index["frames"]], [0, 2, 4])
            self.assertTrue(all((root / "imagenes" / f["file"]).stat().st_size > 0
                                for f in index["frames"]))
            invoke(self, "frames", source, "--out", root / "imagenes", ok=False)
            # Neither prepare nor frames may touch the original: the skill only reads it.
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)

    def test_unicode_output_and_edge_times(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "vídeo ✓ 東京.mp4"
            synthetic(source, 6)
            result = invoke(self, "prepare", source, "--work", root / "trabajo ✓")
            self.assertIn("trabajo ✓", result.stdout)
            self.assertIn("東京", invoke(self, "probe", source).stdout)
            invoke(self, "frames", source, "--out", root / "final-video",
                   "--start", "5.9", "--end", "5.99", "--step", "0.07")
            index = json.loads((root / "final-video/index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["frames"]), 2)
            self.assertAlmostEqual(index["frames"][-1]["time"], 5.96, delta=1e-6)
            error = invoke(self, "prepare", source, "--work", root / "trabajo ✓", ok=False).stderr
            self.assertIn("ya existe", error)

    def test_held_frames_of_variable_rate_recordings(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "pantalla.mp4"
            # 25 fps until 2 s, then one frame held until 8 s (a static slide), then 25 fps again.
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=10",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10",
                         "-vf", r"select='lt(t\,2)+eq(n\,50)+gte(t\,8)'", "-fps_mode", "vfr",
                         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", source)
            invoke(self, "frames", source, "--out", root / "imagenes", "--start", "2", "--end", "9",
                   "--step", "3", "--width", "0")
            index = json.loads((root / "imagenes/index.json").read_text(encoding="utf-8"))
            held, inside, after = (gray_signature(root / "imagenes" / f["file"])
                                   for f in index["frames"])
            self.assertEqual(held, inside)
            self.assertNotEqual(held, after)
            # prepare must still get the whole soundtrack out of a variable-rate recording.
            invoke(self, "prepare", source, "--work", root / "trabajo")
            self.assertAlmostEqual(video.duration(video.probe(root / "trabajo/audio.wav")), 10,
                                   delta=.1)

    def test_forward_only_containers(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "captura.ts"
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=8",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
                         "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-c:a", "aac",
                         "-f", "mpegts", source)
            data = video.probe(source)
            # FORWARD_MARGIN is no longer re-exported by video.py: it is reached through common.
            self.assertEqual(video.seek_margin(data), common.FORWARD_MARGIN)
            invoke(self, "frames", source, "--out", root / "imagenes", "--start", "1", "--end", "7",
                   "--step", "2", "--width", "0")
            images = sorted((root / "imagenes").glob("*.jpg"))
            self.assertEqual(len(images), 3)
            self.assertEqual(len({gray_signature(image) for image in images}), 3)
            invoke(self, "prepare", source, "--work", root / "trabajo")
            self.assertAlmostEqual(video.duration(video.probe(root / "trabajo/audio.wav")), 8,
                                   delta=.2)
            matroska = root / "corta.mkv"
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=5",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
                         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", matroska)
            tagged = video.probe(matroska)
            # The only check of stream_end against a real Matroska: the track length tag, not a guess.
            self.assertAlmostEqual(video.stream_end(tagged, video.streams(tagged)[0]), 5, delta=.1)

    def test_check_reports_environment(self):
        result = subprocess.run([sys.executable, "-B", str(Path(video.__file__)), "check"],
                                capture_output=True, text=True, encoding="utf-8")
        report = json.loads(result.stdout)
        self.assertEqual(list(report), ["version", "python", "python_ok", "platform", "ffmpeg", "ffprobe",
                                        "ffmpeg_version", "libx264", "aac", "faster_whisper",
                                        "transcription_venv", "disk_free_gb", "error", "ok"])
        self.assertEqual(result.returncode == 0, report["ok"])
        self.assertEqual(report["version"], video.__version__)

    def test_prepare_classifies_the_medium_and_records_the_timeline(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            synthetic(root / "con-voz.mp4", 5)
            invoke(self, "prepare", root / "con-voz.mp4", "--work", root / "t-video")
            data = json.loads((root / "t-video/metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "video")
            self.assertEqual(data["timeline"]["fps"], 25.0)
            self.assertEqual(data["timeline"]["rate"], "25/1")
            self.assertAlmostEqual(data["timeline"]["interval"], 0.04)
            self.assertEqual(data["timeline"]["sample_rate"], 48000)
            self.assertEqual(len(data["source"]["sha256"]), 64)
            self.assertEqual(data["avisos"], [])
            self.assertEqual((root / "t-video/energia.f32").stat().st_size % 4, 0)
            self.assertAlmostEqual((root / "t-video/energia.f32").stat().st_size / 4, 500, delta=10)

    def test_prepare_takes_every_audio_container_and_refuses_a_mute_video(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            tone = "sine=frequency=440:sample_rate=48000:duration=5"
            common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "pcm_s16le", root / "solo.wav")
            common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "aac", root / "solo.m4a")
            common.ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-frames:v", "1",
                          root / "caratula.png")
            common.ffmpeg("-i", root / "solo.wav", "-i", root / "caratula.png", "-map", "0:a",
                          "-map", "1:v", "-c:a", "aac", "-c:v", "png",
                          "-disposition:v", "attached_pic", root / "con-caratula.m4a")
            names = ["solo.wav", "solo.m4a", "con-caratula.m4a"]
            if "libmp3lame" in common.encoders():
                common.ffmpeg("-f", "lavfi", "-i", tone, "-c:a", "libmp3lame", root / "solo.mp3")
                names.append("solo.mp3")
            for name in names:
                with self.subTest(name=name):
                    work = root / f"t-{name}"
                    invoke(self, "prepare", root / name, "--work", work)
                    data = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
                    self.assertEqual(data["kind"], "audio")
                    self.assertIsNone(data["timeline"]["fps"])
                    self.assertIsNone(data["timeline"]["rate"])
                    self.assertEqual(data["timeline"]["origin"], 0.0)
                    self.assertEqual(data["timeline"]["sample_rate"], 48000)
                    self.assertEqual(data["avisos"], [])
                    self.assertTrue((work / "audio.wav").is_file())
                    self.assertTrue((work / "energia.f32").is_file())
            common.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=5",
                          "-c:v", "libx264", "-preset", "ultrafast", root / "mudo.mp4")
            error = invoke(self, "prepare", root / "mudo.mp4", "--work", root / "t-mudo",
                           ok=False).stderr
            self.assertIn("no tiene pista de audio", error)
            self.assertFalse((root / "t-mudo").exists())

    def test_hdr_is_refused_and_pts_gaps_are_recorded(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            common.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=2",
                          "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                          "-c:v", "libx264", "-preset", "ultrafast", "-x264-params",
                          "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                          "-c:a", "aac", root / "hdr.mp4")
            error = invoke(self, "prepare", root / "hdr.mp4", "--work", root / "t-hdr",
                           ok=False).stderr
            self.assertIn("HDR", error)
            self.assertFalse((root / "t-hdr").exists())

            synthetic(root / "entera.mp4", 3)
            common.ffmpeg("-i", root / "entera.mp4", "-vf", "select='not(between(n,25,49))'",
                          "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy",
                          root / "hueco.mp4")
            invoke(self, "prepare", root / "hueco.mp4", "--work", root / "t-hueco")
            avisos = json.loads(
                (root / "t-hueco/metadata.json").read_text(encoding="utf-8"))["avisos"]
            self.assertIn("huecos_pts", [aviso["codigo"] for aviso in avisos])
            self.assertFalse(any(aviso["bloquea"] for aviso in avisos))
            self.assertEqual({aviso["corte"] for aviso in avisos}, {None})


class PlanTest(unittest.TestCase):
    def test_missing_encoders_are_reported_before_rendering(self):
        with mock.patch.object(common, "encoders", return_value={"aac"}):
            with self.assertRaisesRegex(ValueError, "libx264"):
                video.require_encoders("libx264", "aac")

    def test_check_prints_json_when_ffmpeg_breaks(self):
        with mock.patch.object(video, "tool", return_value="ffmpeg"),                 mock.patch.object(video, "run", side_effect=OSError("roto")),                 mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(video.check(None), 1)
        report = json.loads(out.getvalue())
        self.assertFalse(report["ok"])
        self.assertIn("roto", report["error"])

    def test_existing_folders_are_refused_clearly(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            with self.assertRaisesRegex(ValueError, "ya existe"):
                video.new_dir(temporary)

    def test_frame_count_excludes_end(self):
        for start, end, step, expected in ((51.36, 51.60, 0.04, 6), (27.16, 27.40, 0.04, 6),
                                           (0.3, 0.9, 0.1, 6), (8.02, 32.02, 0.04, 600),
                                           (0, 600, 15, 40), (5.9, 5.99, 0.07, 2), (0, 1e-6, 1e4, 1)):
            with self.subTest(start=start, end=end, step=step):
                self.assertEqual(video.frame_count(start, end, step), expected)

    def test_stream_end_uses_offsets_and_matroska_tags(self):
        data = {"format": {"duration": "5.52", "start_time": "0"}}
        self.assertAlmostEqual(video.stream_end(data, {"duration": "5.0", "start_time": "0.52"}), 5.52)
        self.assertAlmostEqual(video.stream_end(data, {"duration": "5.0"}), 5.0)
        tagged = {"tags": {"DURATION": "00:01:02.500000000"}}
        self.assertEqual(video.tag_seconds(tagged), 62.5)
        self.assertEqual(video.stream_duration({"format": {"duration": "90"}}, tagged), 62.5)
        self.assertIsNone(video.tag_seconds({"tags": {"DURATION": "roto"}}))
        self.assertEqual(video.output_rate({"r_frame_rate": "1000/1", "avg_frame_rate": "30000/1001"}),
                         "30000/1001")
        self.assertEqual(video.output_rate({}), "30")

    def test_helpers(self):
        self.assertEqual(video.seconds(1e-05), "0.000010")
        self.assertAlmostEqual(video.frame_interval({"avg_frame_rate": "25/1"}), 0.04)
        self.assertAlmostEqual(video.frame_interval({"avg_frame_rate": "0/0", "r_frame_rate": "30000/1001"}),
                               1001 / 30000)
        data = {"format": {"duration": "10.0"}}
        self.assertEqual(video.stream_duration(data, {"duration": "8.5"}), 8.5)
        self.assertEqual(video.stream_duration(data, {}), 10.0)
        with self.assertRaises(ValueError):
            video.duration({"format": {}})

    def test_every_subcommand_is_wired_to_its_function(self):
        parser = video.build_parser()
        self.assertIs(parser.parse_args(["check"]).run, video.check)
        self.assertIs(parser.parse_args(["probe", "v.mp4"]).run, video.show)
        self.assertIs(parser.parse_args(["prepare", "v.mp4", "--work", "t"]).run, video.prepare)
        self.assertIs(parser.parse_args(["frames", "v.mp4", "--out", "o"]).run, video.frames)
        self.assertIs(parser.parse_args(["transcribe", "a.wav", "--out", "o.json"]).run,
                      video.transcribe)

    def test_kind_accepts_video_and_audio_and_refuses_the_rest(self):
        picture = {"index": 0, "codec_type": "video"}
        sound = {"index": 1, "codec_type": "audio"}
        cover = {"index": 2, "codec_type": "video", "disposition": {"attached_pic": 1}}
        self.assertEqual(common.kind({"streams": [picture, sound]}), "video")
        self.assertEqual(common.kind({"streams": [sound]}), "audio")
        self.assertEqual(common.kind({"streams": [sound, cover]}), "audio")
        with self.assertRaisesRegex(ValueError, "pista de audio"):
            common.kind({"streams": [picture]})
        with self.assertRaisesRegex(ValueError, "2 pistas de vídeo"):
            common.kind({"streams": [picture, dict(picture, index=3), sound]})
        self.assertEqual([s["index"] for s in common.pictures({"streams": [picture, cover]})], [0])


if __name__ == "__main__":
    unittest.main()
