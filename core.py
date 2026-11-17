import io
import json
import os
import subprocess
import wave
import zipfile

import imageio_ffmpeg
import numpy as np
import pyzipper
from PIL import Image

MANIFEST_NAME = "steganos.json"
VIDEO_FORMATS = ["mp4", "webm", "gif"]
VIDEO_EXTENSIONS = (".mp4", ".webm", ".gif", ".mkv", ".mov", ".avi")
# Already-compressed files are stored as-is; deflating them only costs time.
STORED_EXTENSIONS = VIDEO_EXTENSIONS + (".png", ".jpg", ".jpeg", ".webp", ".zip", ".7z", ".rar", ".mp3", ".m4a", ".ogg", ".flac")


class PasswordError(Exception):
    pass


def run_ffmpeg(args, input_bytes=None):
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args],
                            input=input_bytes, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def write_wav(path, waveform, sample_rate):
    """waveform: float array [channels, samples] in [-1, 1]."""
    pcm = (np.clip(waveform, -1.0, 1.0) * 32767).astype("<i2").T
    with wave.open(path, "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(np.ascontiguousarray(pcm).tobytes())


def encode_video(frames, fps, fmt, quality, out_path, audio_path=None):
    """frames: uint8 array [N, H, W, 3]. Audio is muxed for mp4/webm and trimmed to the video length."""
    n, h, w, _ = frames.shape
    args = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if audio_path:
        args += ["-i", audio_path, "-map", "0:v", "-map", "1:a", "-t", f"{n / fps:.6f}"]
    # yuv420p needs even dimensions; the padding is cropped off again when decoding.
    pad_even = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    if fmt == "mp4":
        args += ["-vf", pad_even, "-c:v", "libx264", "-crf", str(quality), "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if audio_path:
            args += ["-c:a", "aac", "-b:a", "192k"]
    elif fmt == "webm":
        args += ["-vf", pad_even, "-c:v", "libvpx-vp9", "-crf", str(quality), "-b:v", "0", "-pix_fmt", "yuv420p"]
        if audio_path:
            args += ["-c:a", "libopus", "-b:a", "160k"]
    elif fmt == "gif":
        args += ["-vf", "split[a][b];[a]palettegen[p];[b][p]paletteuse", "-loop", "0"]
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    run_ffmpeg(args + [out_path], input_bytes=np.ascontiguousarray(frames).tobytes())


def decode_video(path, width=None, height=None):
    """Returns (uint8 frames [N, H, W, 3], fps), cropped to width x height when given."""
    # passthrough keeps one output frame per stored frame; GIF delays would otherwise trigger duplicates.
    reader = imageio_ffmpeg.read_frames(path, pix_fmt="rgb24", output_params=["-fps_mode", "passthrough"])
    meta = next(reader)
    w, h = meta["size"]
    frames = np.stack([np.frombuffer(f, dtype=np.uint8).reshape(h, w, 3) for f in reader])
    if width and height:
        frames = frames[:, :height, :width]
    return frames, float(meta["fps"])


def decode_audio(path, sample_rate, channels):
    """Returns float32 [channels, samples] decoded from any audio/video file."""
    raw = run_ffmpeg(["-i", path, "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(channels), "-ar", str(sample_rate), "-"])
    return np.frombuffer(raw, dtype="<i2").reshape(-1, channels).T.astype(np.float32) / 32768.0


def png_bytes(image):
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return buf.getvalue()


def write_polyglot(out_path, cover_png, entries, manifest, password=""):
    """Writes the cover PNG followed by a ZIP of entries + manifest.

    entries: (arcname, source) pairs; source is bytes or a file path.
    With a password the ZIP uses AES-256, which 7-Zip/WinRAR/Bandizip can open.
    """
    with open(out_path, "wb") as f:
        f.write(cover_png)
    # Mode "a" on a non-ZIP file appends an archive whose offsets include the PNG prefix.
    encryption = pyzipper.WZ_AES if password else None
    with pyzipper.AESZipFile(out_path, "a", compression=zipfile.ZIP_DEFLATED, encryption=encryption) as zf:
        if password:
            zf.setpassword(password.encode("utf-8"))
        for arcname, source in entries:
            compress = zipfile.ZIP_STORED if arcname.lower().endswith(STORED_EXTENSIONS) else zipfile.ZIP_DEFLATED
            if isinstance(source, bytes):
                zf.writestr(arcname, source, compress_type=compress)
            else:
                zf.write(source, arcname, compress_type=compress)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))


def extract_payload(path, extract_dir, password=""):
    """Extracts the hidden ZIP into extract_dir and returns its manifest.

    v1 files carry no manifest, so one is built from the archive listing.
    """
    if not zipfile.is_zipfile(path):
        raise ValueError("No hidden payload found in this file.")
    with pyzipper.AESZipFile(path) as zf:
        if any(info.flag_bits & 0x1 for info in zf.infolist()):
            if not password:
                raise PasswordError("This file is password-protected; enter the password.")
            zf.setpassword(password.encode("utf-8"))
        try:
            zf.extractall(extract_dir)
        except RuntimeError as e:
            raise PasswordError("Wrong password.") from e
        names = zf.namelist()
    manifest_path = os.path.join(extract_dir, MANIFEST_NAME)
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    video = next((n for n in names if n.lower().endswith(VIDEO_EXTENSIONS)), None)
    return {"version": 1, "video": video, "files": [n for n in names if n != video]}
