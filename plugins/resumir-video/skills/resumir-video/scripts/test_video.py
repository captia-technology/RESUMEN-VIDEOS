"""Integration checks using generated media; no downloads or external services."""

from array import array
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import wave

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


def marked(path, seconds):
    """Source whose luminance encodes its own instant: lum = 5 * floor(t), encoded losslessly."""
    video.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=320x180:r=25:d={seconds}",
                 "-vf", "geq=lum='clip(5*floor(T),0,255)':cb=128:cr=128",
                 "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", path)


def gray_at(path, time):
    """64x64 gray bytes of the frame on screen at `time`, extracted on its own (0.1.0 method)."""
    return subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, time - 3):.6f}",
                           "-noaccurate_seek", "-copyts", "-i", str(path), "-frames:v", "1",
                           "-vf", f"fps=1000:start_time={time:.6f},scale=64:64,format=gray",
                           "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                          capture_output=True, check=True).stdout


@contextlib.contextmanager
def fake_whisper(model):
    """Stand-in for faster_whisper: the tests never load real weights."""
    module = types.ModuleType("faster_whisper")
    module.WhisperModel = model
    previous = sys.modules.get("faster_whisper")
    sys.modules["faster_whisper"] = module
    try:
        yield
    finally:
        sys.modules.pop("faster_whisper", None)
        if previous is not None:
            sys.modules["faster_whisper"] = previous


class Recorder:
    """Minimal WhisperModel: one segment per whole second of the block it is given."""

    loads = []

    def __init__(self, name, device="cpu", **rest):
        Recorder.loads.append(device)
        if device == "cuda":
            raise RuntimeError("Library cublas64_12.dll is not found")
        self.device = device

    def transcribe(self, path, language=None, vad_filter=True, **rest):
        with wave.open(str(path)) as stream:
            seconds = stream.getnframes() / stream.getframerate()
        parts = []
        for number in range(int(seconds)):
            word = types.SimpleNamespace(start=number + 0.1, end=number + 0.9,
                                         word=f" palabra{number}")
            parts.append(types.SimpleNamespace(start=number + 0.1, end=number + 0.9,
                                               text=f" palabra{number}", words=[word],
                                               no_speech_prob=0.0, avg_logprob=-0.2))
        return iter(parts), types.SimpleNamespace(language=language or "es")


class Reluctant(Recorder):
    """Model that drops the second half of each block unless the VAD is off, like a real miss."""

    def transcribe(self, path, language=None, vad_filter=True, **rest):
        parts, info = super().transcribe(path, language=language, **rest)
        parts = list(parts)
        return iter(parts[:len(parts) // 2] if vad_filter else parts), info


def tone(path, seconds, rate=16000):
    """16 kHz mono PCM: a second of silence at the end of every ten, like a real pause."""
    samples = array("h")
    for index in range(seconds * rate):
        quiet = (index // rate) % 10 == 9
        samples.append(0 if quiet else int(8000 * math.sin(2 * math.pi * 440 * index / rate)))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(samples.tobytes())


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
            index = json.loads((root / "imagenes/b00000/index.json").read_text(encoding="utf-8"))
            self.assertEqual([f["time"] for f in index["frames"]], [0, 2, 4])
            self.assertTrue(all((root / "imagenes/b00000" / f["file"]).stat().st_size > 0
                                for f in index["frames"]))
            # Repetir la llamada ya no falla: salta el bloque terminado.
            invoke(self, "frames", source, "--out", root / "imagenes", "--step", "2")
            self.assertEqual(len(list((root / "imagenes").glob("b?????"))), 1)
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
            # El último fotograma real (5.96) nunca es recuperable: el filtro fps de una sola
            # pasada necesita un fotograma siguiente para saber cuánto mantener el actual, y el
            # último no lo tiene (limitación de diseño de sweep_block, tareas 1-2, no un bug).
            # --step 0.04 coincide con la rejilla de la fuente (25 fps); 5.94 es el penúltimo
            # fotograma, el límite realmente recuperable de una fuente de 6 s.
            invoke(self, "frames", source, "--out", root / "final-video",
                   "--start", "5.9", "--end", "5.95", "--step", "0.04")
            index = json.loads((root / "final-video/b00005/index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["frames"]), 2)
            self.assertAlmostEqual(index["frames"][-1]["time"], 5.94, delta=1e-6)
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
            index = json.loads((root / "imagenes/b00002/index.json").read_text(encoding="utf-8"))
            held, inside, after = (gray_signature(root / "imagenes/b00002" / f["file"])
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
            images = sorted((root / "imagenes" / "b00001").glob("frame-*.jpg"))
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

    def test_the_sweep_index_holds_the_frame_on_screen(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "marcada.mp4"
            marked(source, 50)
            data = video.probe(source)
            stream = video.video_stream(data)
            folder = root / "fotogramas" / "b00000"
            folder.mkdir(parents=True)
            index = video.sweep_block(data, stream, folder, 0.0, 50.0, 15.0, 1280)
            self.assertEqual([f["time"] for f in index["frames"]], [0.0, 15.0, 30.0, 45.0])
            raw = (folder / "indice.gray").read_bytes()
            self.assertEqual(len(raw), 4 * video.INDEX_SIDE ** 2)
            for number, instant in enumerate((0.0, 15.0, 30.0, 45.0)):
                with self.subTest(instant=instant):
                    self.assertEqual(raw[number * 4096:(number + 1) * 4096], gray_at(source, instant))
            self.assertEqual(len(list(folder.glob("hoja-*.jpg"))), 1)
            detail = root / "fotogramas" / "detalle"
            detail.mkdir()
            video.sweep_block(data, stream, detail, 30.0, 30.2, 0.04, 0)
            self.assertEqual(len(list(detail.glob("frame-*.jpg"))), 5)
            self.assertEqual(video.probe(detail / "frame-0000.jpg")["streams"][0]["width"], 320)
            # S = max(0, 30 - 3) = 27 > 0: con -copyts los intervalos siguen en tiempo absoluto del
            # contenedor, no relativos a S (conversion de intervalos de §13; desviacion en D-009).
            first = (detail / "indice.gray").read_bytes()[:4096]
            self.assertEqual(first, gray_at(source, 30.0))
            self.assertNotEqual(first, gray_at(source, 27.0))

    def test_a_rounded_rate_or_the_default_rounding_take_another_frame(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "marcada.mp4"
            marked(source, 50)
            reference = gray_at(source, 15.0)
            for chain in (f"fps={1 / 15:.6f}:start_time=0.000000:round=up",
                          "fps=1/15.000000:start_time=0.000000"):
                with self.subTest(chain=chain):
                    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0", "-noaccurate_seek",
                                          "-copyts", "-i", str(source), "-filter_complex",
                                          f"[0:v]{chain},scale=64:64,format=gray[g]",
                                          "-map", "[g]", "-frames:v", "2", "-f", "rawvideo",
                                          "-pix_fmt", "gray", "-"],
                                         capture_output=True, check=True).stdout
                    self.assertNotEqual(raw[4096:8192], reference)

    def test_the_sweep_keeps_held_frames_of_variable_rate_recordings(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "pantalla.mp4"
            # 25 fps until 2 s, then one frame held until 8 s (a static slide), then 25 fps again.
            video.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=10",
                         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10",
                         "-vf", r"select='lt(t\,2)+eq(n\,50)+gte(t\,8)'", "-fps_mode", "vfr",
                         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", source)
            data = video.probe(source)
            folder = root / "b00002"
            folder.mkdir()
            video.sweep_block(data, video.video_stream(data), folder, 2.0, 11.0, 3.0, 1280)
            raw = (folder / "indice.gray").read_bytes()
            held, inside, after = (raw[i * 4096:(i + 1) * 4096] for i in range(3))
            self.assertEqual(held, inside)
            self.assertNotEqual(inside, after)

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

    def test_the_sweep_resumes_and_reports_what_is_pending(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "marcada.mp4"
            marked(source, 50)
            out = root / "trabajo" / "fotogramas"
            arguments = video.build_parser().parse_args(
                ["frames", str(source), "--out", str(out), "--step", "5", "--block", "10"])
            with mock.patch.object(video, "MAX_FRAMES", 4), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
                self.assertEqual(video.frames(arguments), 3)
            report = json.loads(printed.getvalue().splitlines()[-1])
            self.assertEqual((report["done"], report["total"]), (4, 10))
            # `pending` es siempre un entero; el detalle va en `bloques` (§12).
            self.assertEqual(report["pending"], 3)
            self.assertEqual(report["bloques"], ["b00020", "b00030", "b00040"])
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["b00000", "b00010"])
            (out / "b00010" / "index.json").unlink()
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.frames(arguments), 0)
            self.assertTrue((out / "b00010.parcial").is_dir())
            self.assertEqual(len(sorted(out.glob("b?????/index.json"))), 5)
            last = json.loads((out / "b00040" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual([f["time"] for f in last["frames"]], [40.0, 45.0])

    def test_frames_refuses_audio_only_media_with_exit_code_two(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "solo-audio.m4a"
            video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                         "-c:a", "aac", source)
            result = invoke(self, "frames", source, "--out", root / "fotogramas", ok=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("solo audio", result.stderr)

    def test_transcription_runs_in_resumable_blocks(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(out), "--block", "10", "--slack", "2",
                 "--language", "es", "--budget", "0", "--device", "cpu"])
            Recorder.loads.clear()
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
                self.assertEqual(video.transcribe(arguments), 3)
            report = json.loads(printed.getvalue().splitlines()[-1])
            self.assertEqual((report["done"], report["total"]), (1, 3))
            self.assertEqual(report["pending"], 2)
            self.assertEqual(report["bloques"], ["bloque-001", "bloque-002"])
            self.assertFalse(out.exists())
            self.assertTrue((root / "transcripcion.parcial" / "bloque-000.json").is_file())
            arguments.budget = None
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(Recorder.loads, ["cpu", "cpu"])
            self.assertEqual([round(b["end"] - b["start"], 3) for b in data["blocks"]],
                             [9.15, 10.0, 10.85])
            self.assertEqual(len(data["segments"]), 29)
            self.assertEqual(data["language"], "es")
            self.assertTrue(all(a["end"] <= b["start"]
                                for a, b in zip(data["segments"], data["segments"][1:])))
            self.assertAlmostEqual(data["segments"][-1]["start"], 28.25, delta=0.01)
            self.assertFalse((root / "transcripcion.parcial").exists())

    def test_resuming_with_other_settings_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(out), "--block", "10", "--slack", "2",
                 "--language", "es", "--budget", "0"])
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 3)
            arguments.beam_size = 5
            with fake_whisper(Recorder), self.assertRaisesRegex(video.Refused, "no coinciden"):
                video.transcribe(arguments)

    def test_corrupt_block_is_redone_instead_of_blocking_forever(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(out), "--block", "10", "--slack", "2",
                 "--language", "es", "--budget", "0"])
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 3)
            piece = root / "transcripcion.parcial" / "bloque-000.json"
            piece.write_text('{"index": 0, "segments": [', encoding="utf-8")  # truncated on purpose
            # Redoing the corrupt block must not raise FileExistsError on the retry's save(): the
            # call has to behave exactly as a first attempt on that block, still bounded by budget.
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
                self.assertEqual(video.transcribe(arguments), 3)
            report = json.loads(printed.getvalue().splitlines()[-1])
            self.assertEqual(report["pending"], 2)
            self.assertEqual(json.loads(piece.read_text(encoding="utf-8"))["index"], 0)
            arguments.budget = None
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 0)
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["segments"]), 29)
            self.assertFalse((root / "transcripcion.parcial").exists())

    def test_a_failed_publish_can_be_retried_without_touching_the_final_output(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(out), "--block", "10", "--slack", "2",
                 "--language", "es"])
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO), \
                 mock.patch.object(common, "publish", side_effect=OSError("fallo simulado")):
                with self.assertRaises(OSError):
                    video.transcribe(arguments)
            self.assertFalse(out.exists())
            staged = root / "transcripcion.parcial" / "transcripcion.json"
            self.assertTrue(staged.is_file())
            # Real retry, publish() no longer mocked: save()'s "x" mode must not choke on the
            # transcripcion.json a previous, failed attempt already left inside the work area.
            with fake_whisper(Recorder), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 0)
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["segments"]), 29)
            self.assertFalse((root / "transcripcion.parcial").exists())

    def test_auto_device_falls_back_to_cpu_and_dll_folders_are_checked(self):
        arguments = video.build_parser().parse_args(
            ["transcribe", "audio.wav", "--out", "transcripcion.json", "--device", "auto"])
        Recorder.loads.clear()
        with fake_whisper(Recorder), mock.patch("sys.stderr", new_callable=io.StringIO) as noted:
            model, device = video.load_model(arguments)
        self.assertEqual((Recorder.loads, device), (["cuda", "cpu"], "cpu"))
        self.assertIn("CUDA", noted.getvalue())
        self.assertEqual(model.device, "cpu")
        arguments.dll_dir = ["carpeta-que-no-existe"]
        with fake_whisper(Recorder), self.assertRaisesRegex(video.Refused, "no existe"):
            video.load_model(arguments)

    def test_gaps_with_sound_are_transcribed_again_without_vad(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(out), "--block", "10", "--slack", "2",
                 "--language", "es"])
            with fake_whisper(Reluctant), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            recovered = [s for s in data["segments"] if s.get("recuperado")]
            self.assertTrue(recovered)
            self.assertGreater(max(s["end"] for s in data["segments"]), 25)
            self.assertTrue(all(a["start"] <= b["start"]
                                for a, b in zip(data["segments"], data["segments"][1:])))

    def test_corrupt_gap_is_redone_instead_of_blocking_forever(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            tone(audio, 30)
            work = root / "transcripcion.parcial"
            work.mkdir()
            arguments = video.build_parser().parse_args(
                ["transcribe", str(audio), "--out", str(root / "transcripcion.json"),
                 "--language", "es", "--device", "cpu"])
            levels = common.energy(str(audio), root / "energia.f32")
            total = round(len(levels) * video.LEVEL_STEP, 3)
            with fake_whisper(Reluctant):
                segments, device = video.recover(work, [], levels, total, "es", None, arguments)
            self.assertTrue(any(s.get("recuperado") for s in segments))
            piece = work / "hueco-000.json"
            self.assertTrue(piece.is_file())
            original = piece.read_bytes()
            piece.write_bytes(original[:len(original) // 2])  # real bytes, truncated for real
            # Redoing the corrupt gap must not raise FileExistsError on the retry's save(): the
            # call has to behave exactly as a first attempt on that gap.
            with fake_whisper(Reluctant):
                redone, device = video.recover(work, [], levels, total, "es", device, arguments)
            self.assertTrue(any(s.get("recuperado") for s in redone))
            self.assertEqual(json.loads(piece.read_text(encoding="utf-8"))["segments"],
                             [{k: v for k, v in s.items() if k != "recuperado"} for s in redone])


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

    TRANSCRIPTION = {"segments": [
        {"start": 0.0, "end": 3.0, "text": " Buenos días a todos.", "words": [
            {"start": 0.1, "end": 0.6, "text": " Buenos"}, {"start": 0.6, "end": 1.1, "text": " días"}]},
        {"start": 3.0, "end": 9.0, "text": " La atmósfera ATEX exige un equipo certificado.", "words": [
            {"start": 3.1, "end": 3.3, "text": " La"}, {"start": 3.3, "end": 4.0, "text": " atmósfera"},
            {"start": 4.0, "end": 4.6, "text": " ATEX"}, {"start": 4.6, "end": 5.2, "text": " exige"}]},
        {"start": 9.0, "end": 12.0, "text": " Sin atex no hay permiso.", "words": []},
        {"start": 12.0, "end": 15.0, "text": " El ingeniero diseñó la señal.", "words": []}]}

    def test_search_ignores_accents_and_case(self):
        found = video.find(self.TRANSCRIPTION, "ATEX")
        self.assertEqual(found["normalizada"], "atex")
        self.assertEqual([(h["segmento"], h["inicio"]) for h in found["coincidencias"]],
                         [(1, 4.0), (2, 9.0)])
        self.assertEqual(video.find(self.TRANSCRIPTION, "ATMÓSFERA")["coincidencias"][0]["inicio"], 3.3)
        self.assertEqual(video.find(self.TRANSCRIPTION, "atmosfera")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "zona 0")["total"], 0)
        self.assertIn("Buenos días", video.find(self.TRANSCRIPTION, "atmosfera")["coincidencias"][0]["contexto"])
        self.assertEqual(video.find(self.TRANSCRIPTION, "atex", limit=1)["total"], 1)
        with self.assertRaisesRegex(ValueError, "no vacío"):
            video.find(self.TRANSCRIPTION, "   ")

    def test_the_tilde_of_the_n_is_part_of_the_letter(self):
        # strip_accents keeps ñ and Ñ: «diseñó» normalises to «diseño», never to «diseno».
        self.assertEqual(video.find(self.TRANSCRIPTION, "DISEÑÓ")["normalizada"], "diseño")
        self.assertEqual(video.find(self.TRANSCRIPTION, "diseño")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "diseno")["total"], 0)
        self.assertEqual(video.find(self.TRANSCRIPTION, "señal")["total"], 1)
        self.assertEqual(video.find(self.TRANSCRIPTION, "senal")["total"], 0)


class SweepTest(unittest.TestCase):
    def test_blocks_cover_the_interval_on_the_sampling_grid(self):
        self.assertEqual(video.sweep_blocks(0, 1800, 15.0),
                         [(0.0, 600.0, 40), (600.0, 1200.0, 40), (1200.0, 1800.0, 40)])
        self.assertEqual(video.sweep_blocks(0, 50, 15.0, length=30.0),
                         [(0.0, 30.0, 2), (30.0, 50.0, 2)])
        self.assertEqual(video.sweep_blocks(120, 135, 1.0), [(120.0, 135.0, 15)])
        self.assertEqual(video.sweep_blocks(0, 1.5, 15.0), [(0.0, 1.5, 1)])
        # Un paso mayor que el bloque no puede producir bloques vacios.
        self.assertEqual(video.sweep_blocks(0, 90, 40.0, length=30.0),
                         [(0.0, 40.0, 1), (40.0, 80.0, 1), (80.0, 90.0, 1)])

    def test_names_sheets_and_space(self):
        self.assertEqual(video.block_name(0), "b00000")
        self.assertEqual(video.block_name(600.0), "b00600")
        self.assertEqual(video.block_name(3661.4), "b03661")
        self.assertEqual([video.sheet_count(n) for n in (0, 1, 25, 26, 40, 50)], [1, 1, 1, 2, 2, 2])
        self.assertEqual(video.space_needed(40), 40_000_000)

    def test_unfinished_blocks_are_renamed_and_finished_ones_kept(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            done, half = root / "b00000", root / "b00600"
            done.mkdir()
            (done / "index.json").write_text("{}", encoding="utf-8")
            half.mkdir()
            (half / "frame-0000.jpg").write_bytes(b"x")
            self.assertEqual(video.clear_partial(done), done)
            self.assertIsNone(video.clear_partial(half))
            self.assertFalse(half.exists())
            self.assertTrue((root / "b00600.parcial" / "frame-0000.jpg").is_file())
            half.mkdir()
            (half / "frame-0000.jpg").write_bytes(b"y")
            self.assertIsNone(video.clear_partial(half))
            self.assertTrue((root / "b00600.parcial-2").is_dir())
            self.assertIsNone(video.clear_partial(root / "b01200"))
            broken = root / "b01800"
            broken.mkdir()
            (broken / "index.json").write_text('{"start": 1800.0,', encoding="utf-8")  # truncado
            self.assertIsNone(video.clear_partial(broken))
            self.assertTrue((root / "b01800.parcial").is_dir())


class AudioBlockTest(unittest.TestCase):
    def levels(self, seconds, loud=-20.0, islands=()):
        """Ten-millisecond levels: loud everywhere except in the given quiet second-long islands."""
        data = array("f", [loud] * int(seconds / video.LEVEL_STEP))
        for start in islands:
            for index in range(int(start / video.LEVEL_STEP), int((start + 1) / video.LEVEL_STEP)):
                data[index] = -70.0
        return data

    def test_blocks_are_cut_at_the_quietest_window(self):
        levels = self.levels(2000, islands=(590.0, 1180.0, 1780.0))
        blocks = video.speech_blocks(levels, 2000.0)
        self.assertEqual(blocks, [(0.0, 590.15), (590.15, 1180.15), (1180.15, 1780.15),
                                  (1780.15, 2000.0)])
        self.assertEqual(round(sum(b - a for a, b in blocks), 3), 2000.0)
        self.assertTrue(all(blocks[i][1] == blocks[i + 1][0] for i in range(len(blocks) - 1)))
        self.assertEqual(video.speech_blocks(self.levels(300), 300.0), [(0.0, 300.0)])
        self.assertEqual(video.quiet_cut(levels, 540.0, 660.0), 590.15)

    def test_only_gaps_with_sound_are_reported(self):
        levels = self.levels(300, loud=-70.0)
        for index in range(20000, 26000):
            levels[index] = -30.0
        spoken = [{"start": 0.0, "end": 100.0}, {"start": 150.0, "end": 200.0},
                  {"start": 260.0, "end": 300.0}]
        self.assertEqual(video.gaps(spoken, levels, 0.0, 300.0), [(200.0, 260.0)])
        self.assertEqual(video.gaps([{"start": 0.0, "end": 300.0}], levels, 0.0, 300.0), [])
        self.assertEqual(video.gaps([], levels, 0.0, 300.0), [(0.0, 300.0)])


class SubtitleTest(unittest.TestCase):
    SRT = ("﻿1\n00:00:01,000 --> 00:00:04,500\nPrimera <i>línea</i>\nsegunda línea\n\n"
           "2\n00:01:02,25 --> 00:01:05,000\nOtra frase\n")
    VTT = ("WEBVTT\n\nNOTE una nota\n\ncue-1\n"
           "00:00:02.000 --> 00:00:03.250 align:start position:10%\nHola\n\n"
           "00:10:00.000 --> 00:10:02.000\n<v Ana>Texto\n\n"
           "00:02.000 --> 00:05.000\nSin horas\n")

    def test_srt_and_vtt_become_segments_without_words(self):
        srt = video.subtitles(self.SRT)
        self.assertEqual([(s["start"], s["end"]) for s in srt], [(1.0, 4.5), (62.25, 65.0)])
        self.assertEqual(srt[0]["text"], "Primera línea segunda línea")
        self.assertEqual(srt[0]["words"], [])
        vtt = video.subtitles(self.VTT)
        # WebVTT admite un cue de menos de una hora sin componente de horas (MM:SS.mmm).
        self.assertEqual([(s["start"], s["end"]) for s in vtt],
                         [(2.0, 3.25), (2.0, 5.0), (600.0, 602.0)])
        self.assertEqual([s["text"] for s in vtt], ["Hola", "Sin horas", "Texto"])
        self.assertEqual(video.subtitles("sin ningún tiempo"), [])

    def test_the_subtitle_branch_publishes_a_transcription_with_its_warning(self):
        with tempfile.TemporaryDirectory(prefix="resumir-video-") as temporary:
            root = Path(temporary)
            source = root / "clase.srt"
            source.write_text(self.SRT, encoding="utf-8")
            out = root / "transcripcion.json"
            arguments = video.build_parser().parse_args(
                ["transcribe", str(root / "audio.wav"), "--out", str(out),
                 "--subtitles", str(source), "--language", "es"])
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(video.transcribe(arguments), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["language"], "es")
            self.assertEqual(data["settings"]["origen"], "subtitulos")
            self.assertEqual(data["settings"]["archivo"], "clase.srt")
            self.assertEqual(len(data["segments"]), 2)
            self.assertEqual([w["codigo"] for w in data["warnings"]], ["sin_marcas_por_palabra"])
            self.assertFalse(data["warnings"][0]["bloquea"])
            empty = root / "vacio.srt"
            empty.write_text("sin tiempos\n", encoding="utf-8")
            arguments.subtitles, arguments.out = str(empty), str(root / "otra.json")
            with self.assertRaisesRegex(video.Refused, "no contiene"):
                video.transcribe(arguments)


if __name__ == "__main__":
    unittest.main()
