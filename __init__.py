from .nodes import SteganosDecoder, SteganosFilePacker, SteganosNode

NODE_CLASS_MAPPINGS = {
    "SteganosNode": SteganosNode,
    "SteganosFilePacker": SteganosFilePacker,
    "SteganosDecoder": SteganosDecoder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SteganosNode": "Steganos Video Encoder",
    "SteganosFilePacker": "Steganos File Packer",
    "SteganosDecoder": "Steganos Decoder",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
