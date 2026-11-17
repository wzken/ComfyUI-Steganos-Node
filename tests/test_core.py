import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402

COVER_PATH = os.path.join(os.path.dirname(core.__file__), "test.png")
with open(COVER_PATH, "rb") as f:
    COVER = f.read()


def frames(n=6, h=33, w=47):
    base = np.random.default_rng(0).integers(0, 255, (1, h, w, 3), dtype=np.uint8)
    return np.repeat(base, n, axis=0)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_video_roundtrip_with_odd_size_and_audio(self):
        audio = self.path("a.wav")
        core.write_wav(audio, np.sin(np.linspace(0, 4000, 2 * 32000)).reshape(2, -1) * 0.5, 16000)
        for fmt in core.VIDEO_FORMATS:
            with self.subTest(fmt=fmt):
                video = self.path(f"secret.{fmt}")
                core.encode_video(frames(), 8.0, fmt, 20, video, None if fmt == "gif" else audio)
                out, fps = core.decode_video(video, 47, 33)
                self.assertEqual(out.shape, (6, 33, 47, 3))
                # GIF frame delays are whole centiseconds, so 8 fps reads back as ~8.33.
                self.assertAlmostEqual(fps, 8.0, delta=0.5)
                if fmt != "gif":
                    wav = core.decode_audio(video, 16000, 2)
                    self.assertEqual(wav.shape[0], 2)
                    # 2 s of audio is trimmed to the 0.75 s video.
                    self.assertLess(abs(wav.shape[1] - 6 / 8 * 16000), 1000)

    def test_polyglot_is_valid_png_and_zip(self):
        out = self.path("out.png")
        core.write_polyglot(out, COVER, [("message.txt", "你好".encode())], {"version": 2, "video": None})
        with open(out, "rb") as f:
            self.assertTrue(f.read().startswith(COVER))
        Image.open(out).verify()
        # Offsets must include the PNG prefix, otherwise unzip warns about extra bytes.
        result = subprocess.run(["unzip", "-t", out], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = core.extract_payload(out, self.path("x"))
        self.assertEqual(manifest["version"], 2)
        with open(self.path("x/message.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "你好")

    def test_password(self):
        out = self.path("out.png")
        core.write_polyglot(out, COVER, [("message.txt", b"secret")], {"version": 2, "video": None}, password="pw")
        with self.assertRaises(core.PasswordError):
            core.extract_payload(out, self.path("a"))
        with self.assertRaises(core.PasswordError):
            core.extract_payload(out, self.path("b"), "wrong")
        core.extract_payload(out, self.path("c"), "pw")
        with open(self.path("c/message.txt"), "rb") as f:
            self.assertEqual(f.read(), b"secret")

    def test_v1_file_without_manifest(self):
        video = self.path("secret.mp4")
        core.encode_video(frames(), 8.0, "mp4", 20, video)
        zip_path = self.path("secret.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(video, "secret.mp4")
        out = self.path("v1.png")
        with open(out, "wb") as f, open(zip_path, "rb") as z:
            f.write(COVER + z.read())
        self.assertEqual(core.extract_payload(out, self.path("x"))["video"], "secret.mp4")

    def test_plain_png_has_no_payload(self):
        with self.assertRaises(ValueError):
            core.extract_payload(COVER_PATH, self.tmp)


if __name__ == "__main__":
    unittest.main()
