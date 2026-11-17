# Steganos Node for ComfyUI

Hide a video (with audio), any files and a text message inside a PNG. The file opens as a normal picture, and any unzip tool — or the bundled **Steganos Decoder** node — gets the hidden content back.

The node writes the cover PNG and appends a ZIP archive to it. PNG viewers stop reading at the end of the image, and ZIP tools read the archive from the end of the file, so both see a valid file.

[中文说明](#中文说明)

## Installation

Install from the ComfyUI Manager / Comfy Registry, or:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/wzken/ComfyUI-Steganos-Node
pip install -r ComfyUI-Steganos-Node/requirements.txt
```

`imageio-ffmpeg` ships an ffmpeg binary, so no system ffmpeg is needed. `pyzipper` provides AES encryption.

## Nodes

### Steganos Video Encoder

Encodes `images` as a video and hides it in a PNG in the output folder. Runs on its own (no downstream node required) and previews the result.

| Input | Description |
| --- | --- |
| `images` | Frames to encode. |
| `fps` | Frame rate. |
| `filename_prefix` | Output file name prefix. |
| `format` | `mp4` (H.264), `webm` (VP9) or `gif`. |
| `quality` | CRF: lower is better quality and a bigger file. mp4 uses 0–51, webm 0–63; ignored for gif. |
| `cover` (optional) | Picture shown when the PNG is opened. Defaults to the bundled `test.png`. |
| `audio` (optional) | Muxed into mp4/webm; stored as `audio.wav` next to a gif. Trimmed to the video length. |
| `password` (optional) | Encrypts the archive with AES-256. |
| `message` (optional) | Hidden as `message.txt`. |
| `embed_workflow` (optional) | Also hides the workflow as `workflow.json` / `prompt.json`. |

Outputs: `cover` (the cover image) and `file_path` (the saved PNG).

### Steganos File Packer

Hides arbitrary files plus an optional message in a `cover` image. List one file or folder per line in `files`, relative to the ComfyUI `input` folder; append ` [output]` to pick from the `output` folder, e.g. `video/clip.mp4 [output]`. Paths outside the input/output/temp folders are rejected.

### Steganos Decoder

Pick or upload a Steganos PNG (or connect an encoder's `file_path`) and enter the password if one was set. Everything is extracted to `output/steganos_extracted/<file name>/`.

Outputs: `images` (video frames, or the cover when no video is hidden), `audio`, `fps`, `message` and `extracted_dir`. PNGs made by v1 of this node decode too.

## Extracting without ComfyUI

Open or extract the PNG with 7-Zip, WinRAR, Bandizip, or `unzip` / `7z x` on Linux and macOS. Password-protected files use AES-256 ZIP encryption, which 7-Zip, WinRAR and Bandizip support but Windows Explorer, macOS Archive Utility and Info-ZIP `unzip` do not.

## Sharing caveat

Many platforms (QQ, WeChat, Weibo, Twitter/X, Discord…) re-encode uploaded images, which drops the hidden archive. Send the PNG as a file or with the "original image" option.

## Upgrading from v1

The encoder's `usage_notes` widget was removed, and `format`, `quality` and the optional inputs were added after `filename_prefix`. Workflows saved with v1 may need `format` reselected after loading.

## 中文说明

把视频（可带音频）、任意文件和文字藏进一张 PNG 里：图片查看器里看到的是正常封面图，用解压软件或本插件的 **Steganos Decoder** 节点就能取出隐藏内容（俗称“图种”）。

- **Steganos Video Encoder**：把图像序列编码成 mp4 / webm / gif 藏进 PNG；可自定义封面、加音频、设置密码（AES-256）、附加文字或工作流。
- **Steganos File Packer**：把 ComfyUI `input`（或加 ` [output]` 后缀指定 `output`）目录下的任意文件/文件夹藏进封面图。
- **Steganos Decoder**：选择或上传图种 PNG，输入密码，输出视频帧、音频、帧率、文字，并解压到 `output/steganos_extracted/`。

加密的图种需要用 7-Zip、WinRAR 或 Bandizip 解压，Windows 自带解压和 macOS 归档实用工具不支持 AES。QQ、微信、微博等平台会压缩图片，导致隐藏内容丢失，请以“原图”或文件形式发送。
