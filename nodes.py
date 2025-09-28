import os
import numpy as np
import torch
import folder_paths
import imageio
from PIL import Image
import tempfile
import zipfile

class SteganosNode:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        # Define the path to the carrier image relative to this script's location
        script_directory = os.path.dirname(__file__)
        self.carrier_image_path = os.path.join(script_directory, "test.png")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 16.0, "min": 0.1, "max": 120.0}),
                "filename_prefix": ("STRING", {"default": "Steganos"}),
            },
            "optional": {
                 "usage_notes": ("STRING", {"default": "本节点将视频隐藏在图片中。\n它使用一个固定的【test.png】作为封面，并将【整个图像序列】编码为MP4视频，然后将视频压缩成ZIP文件并附加到封面图片末尾。\n生成的PNG文件既可以作为普通图片查看，也可以使用'unzip'等工具提取出隐藏的视频文件。", "multiline": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "process_images_steganography"
    CATEGORY = "Steganos"
    OUTPUT_NODE = False

    def process_images_steganography(self, images, filename_prefix, fps=16.0, usage_notes=None):
        # Check if the static carrier image exists
        if not os.path.exists(self.carrier_image_path):
            print(f"错误：载体图片 'test.png' 在脚本目录中未找到。")
            print(f"预期路径: {self.carrier_image_path}")
            return {}

        if images.nelement() > 0:
            full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, self.output_dir)
            
            final_filename = f"{filename}_{counter:05d}.png"
            final_filepath = os.path.join(full_output_folder, final_filename)

            numpy_images = self._batch_convert_images(images)

            with tempfile.TemporaryDirectory() as temp_dir:
                # 1. The carrier is the static "代替图片.png"
                carrier_path = self.carrier_image_path

                # 2. Save the entire sequence as a secret MP4
                secret_mp4_path = os.path.join(temp_dir, "secret.mp4")
                imageio.mimsave(secret_mp4_path, numpy_images, fps=fps, codec="libx264")

                # 3. Create a zip file containing the secret MP4
                secret_zip_path = os.path.join(temp_dir, "secret.zip")
                with zipfile.ZipFile(secret_zip_path, 'w') as zf:
                    zf.write(secret_mp4_path, os.path.basename(secret_mp4_path))

                # 4. Concatenate the static carrier PNG and the new secret ZIP
                with open(final_filepath, 'wb') as f_out, open(carrier_path, 'rb') as f_carrier, open(secret_zip_path, 'rb') as f_secret:
                    f_out.write(f_carrier.read())
                    f_out.write(f_secret.read())

            if usage_notes:
                print(f"=== Steganos Node 使用说明 ===")
                print(usage_notes)
                print(f"=== 处理完成 ===")
            
            # The file saving is a side-effect. Now, load and return the carrier image.
            carrier_pil = Image.open(self.carrier_image_path).convert("RGB")
            carrier_np = np.array(carrier_pil).astype(np.float32) / 255.0
            carrier_tensor = torch.from_numpy(carrier_np)[None,]
            
            return (carrier_tensor,)
            
        # Return an empty tensor if there were no input images
        return (torch.zeros((1, 64, 64, 3)),)

    def _batch_convert_images(self, images):
        """Converts a batch of tensors to numpy arrays."""
        return (images.cpu().numpy() * 255).astype(np.uint8)

# Node class definition complete