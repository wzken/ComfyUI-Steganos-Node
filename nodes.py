import hashlib
import json
import os
import tempfile

import numpy as np
import torch
from PIL import Image

import folder_paths

from . import core

DEFAULT_COVER = os.path.join(os.path.dirname(__file__), "test.png")


def _to_uint8(images):
    return (images.cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)


def _to_tensor(frames):
    return torch.from_numpy(frames.astype(np.float32) / 255.0)


def _common_payload(message, embed_workflow, prompt, extra_pnginfo):
    entries = []
    if message:
        entries.append(("message.txt", message.encode("utf-8")))
    if embed_workflow:
        if prompt is not None:
            entries.append(("prompt.json", json.dumps(prompt).encode("utf-8")))
        if extra_pnginfo and "workflow" in extra_pnginfo:
            entries.append(("workflow.json", json.dumps(extra_pnginfo["workflow"]).encode("utf-8")))
    return entries


def _save_polyglot(filename_prefix, cover, entries, manifest, password):
    """Saves the cover + payload to the output folder and returns (path, ui preview, cover tensor)."""
    if cover is None:
        with open(DEFAULT_COVER, "rb") as f:
            cover_png = f.read()
        cover_uint8 = np.array(Image.open(DEFAULT_COVER).convert("RGB"))
    else:
        cover_uint8 = _to_uint8(cover[0])
        cover_png = core.png_bytes(cover_uint8)
    output_dir = folder_paths.get_output_directory()
    h, w = cover_uint8.shape[:2]
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, output_dir, w, h)
    file = f"{filename}_{counter:05}_.png"
    path = os.path.join(full_output_folder, file)
    core.write_polyglot(path, cover_png, entries, manifest, password)
    preview = {"images": [{"filename": file, "subfolder": subfolder, "type": "output"}]}
    return path, preview, _to_tensor(cover_uint8[None])


class SteganosNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 16.0, "min": 0.1, "max": 120.0}),
                "filename_prefix": ("STRING", {"default": "Steganos"}),
                "format": (core.VIDEO_FORMATS, {"default": "mp4"}),
                "quality": ("INT", {"default": 19, "min": 0, "max": 63, "tooltip": "CRF for mp4 (0-51) / webm (0-63): lower means better quality and a bigger file. Ignored for gif."}),
            },
            "optional": {
                "cover": ("IMAGE", {"tooltip": "Image shown when the file is opened as a picture. Defaults to the bundled test.png."}),
                "audio": ("AUDIO", {"tooltip": "Muxed into mp4/webm; stored as audio.wav next to a gif."}),
                "password": ("STRING", {"default": "", "tooltip": "Encrypts the hidden archive with AES-256. Open it with 7-Zip, WinRAR or Bandizip."}),
                "message": ("STRING", {"default": "", "multiline": True, "tooltip": "Hidden as message.txt."}),
                "embed_workflow": ("BOOLEAN", {"default": False, "tooltip": "Also hide this workflow as workflow.json / prompt.json."}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("cover", "file_path")
    FUNCTION = "encode"
    CATEGORY = "Steganos"
    OUTPUT_NODE = True
    DESCRIPTION = "Encodes the image sequence as a video and hides it, ZIP-compressed, at the end of a PNG cover. Extract it with any unzip tool or the Steganos Decoder node."

    def encode(self, images, fps, filename_prefix, format, quality, cover=None, audio=None, password="", message="", embed_workflow=False, prompt=None, extra_pnginfo=None):
        if images.shape[0] == 0:
            raise ValueError("Steganos: no images to encode.")
        frames = _to_uint8(images)
        n, h, w, _ = frames.shape
        video_name = f"secret.{format}"
        manifest = {"version": 2, "video": video_name, "fps": fps, "width": w, "height": h, "frames": n}
        if format == "mp4":
            quality = min(quality, 51)
        with tempfile.TemporaryDirectory() as temp_dir:
            entries = []
            audio_path = None
            if audio is not None:
                waveform = audio["waveform"][0].cpu().float().numpy()
                audio_path = os.path.join(temp_dir, "audio.wav")
                core.write_wav(audio_path, waveform, audio["sample_rate"])
                audio_file = video_name
                if format == "gif":
                    entries.append(("audio.wav", audio_path))
                    audio_file = "audio.wav"
                manifest["audio"] = {"file": audio_file, "sample_rate": int(audio["sample_rate"]), "channels": waveform.shape[0]}
            video_path = os.path.join(temp_dir, video_name)
            core.encode_video(frames, fps, format, quality, video_path, audio_path if format != "gif" else None)
            entries.insert(0, (video_name, video_path))
            entries += _common_payload(message, embed_workflow, prompt, extra_pnginfo)
            path, preview, cover_tensor = _save_polyglot(filename_prefix, cover, entries, manifest, password)
        return {"ui": preview, "result": (cover_tensor, path)}


class SteganosFilePacker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cover": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "SteganosFiles"}),
                "files": ("STRING", {"default": "", "multiline": True, "tooltip": "One file or folder per line, relative to the ComfyUI input folder. Append ' [output]' to pick from the output folder, e.g. 'video/clip.mp4 [output]'."}),
            },
            "optional": {
                "password": ("STRING", {"default": ""}),
                "message": ("STRING", {"default": "", "multiline": True}),
                "embed_workflow": ("BOOLEAN", {"default": False}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "pack"
    CATEGORY = "Steganos"
    OUTPUT_NODE = True
    DESCRIPTION = "Hides arbitrary files from the ComfyUI input/output folders, plus an optional message, inside a PNG cover."

    def pack(self, cover, filename_prefix, files, password="", message="", embed_workflow=False, prompt=None, extra_pnginfo=None):
        entries = []
        for line in files.splitlines():
            if not line.strip():
                continue
            # get_annotated_filepath keeps paths inside the input/output/temp folders.
            path = folder_paths.get_annotated_filepath(line.strip())
            if os.path.isdir(path):
                root = os.path.dirname(path.rstrip(os.sep))
                for dirpath, _, filenames in os.walk(path):
                    for name in sorted(filenames):
                        file_path = os.path.join(dirpath, name)
                        entries.append((os.path.relpath(file_path, root).replace(os.sep, "/"), file_path))
            elif os.path.isfile(path):
                entries.append((os.path.basename(path), path))
            else:
                raise FileNotFoundError(f"Steganos: file not found: {line.strip()}")
        manifest = {"version": 2, "video": None, "files": [name for name, _ in entries]}
        entries += _common_payload(message, embed_workflow, prompt, extra_pnginfo)
        if not entries:
            raise ValueError("Steganos: nothing to hide; list some files or enter a message.")
        path, preview, _ = _save_polyglot(filename_prefix, cover, entries, manifest, password)
        return {"ui": preview, "result": (path,)}


def _resolve_input(image, file_path):
    if not file_path:
        return folder_paths.get_annotated_filepath(image)
    path = os.path.abspath(file_path)
    allowed = (folder_paths.get_input_directory(), folder_paths.get_output_directory(), folder_paths.get_temp_directory())
    if not any(os.path.commonpath([os.path.abspath(d), path]) == os.path.abspath(d) for d in allowed):
        raise ValueError("Steganos: file_path must be inside the ComfyUI input, output or temp folder.")
    return path


class SteganosDecoder:
    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {
            "required": {
                "image": (sorted(files), {"image_upload": True}),
                "password": ("STRING", {"default": ""}),
            },
            "optional": {
                "file_path": ("STRING", {"default": "", "tooltip": "Overrides `image`. Connect the encoder's file_path output to decode in the same workflow."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("images", "audio", "fps", "message", "extracted_dir")
    FUNCTION = "decode"
    CATEGORY = "Steganos"
    DESCRIPTION = "Extracts everything hidden in a Steganos PNG into output/steganos_extracted and loads the hidden video, audio and message. Without a hidden video, `images` is the cover."

    def decode(self, image, password, file_path=""):
        path = _resolve_input(image, file_path)
        extract_dir = os.path.join(folder_paths.get_output_directory(), "steganos_extracted", os.path.splitext(os.path.basename(path))[0])
        manifest = core.extract_payload(path, extract_dir, password)

        fps = 0.0
        if manifest.get("video"):
            frames, fps = core.decode_video(os.path.join(extract_dir, manifest["video"]), manifest.get("width"), manifest.get("height"))
            fps = float(manifest.get("fps", fps))
        else:
            frames = np.array(Image.open(path).convert("RGB"))[None]

        audio_info = manifest.get("audio")
        if audio_info:
            waveform = core.decode_audio(os.path.join(extract_dir, audio_info["file"]), audio_info["sample_rate"], audio_info["channels"])
            audio = {"waveform": torch.from_numpy(waveform.copy())[None], "sample_rate": audio_info["sample_rate"]}
        else:
            audio = {"waveform": torch.zeros((1, 1, 1)), "sample_rate": 44100}

        message = ""
        message_path = os.path.join(extract_dir, "message.txt")
        if os.path.exists(message_path):
            with open(message_path, encoding="utf-8") as f:
                message = f.read()
        return (_to_tensor(frames), audio, fps, message, extract_dir)

    @classmethod
    def IS_CHANGED(cls, image, password, file_path=""):
        m = hashlib.sha256(password.encode("utf-8"))
        with open(_resolve_input(image, file_path), "rb") as f:
            m.update(f.read())
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, image, file_path=""):
        if not file_path and not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"
        return True
