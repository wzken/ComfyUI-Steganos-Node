# Steganos Node for ComfyUI

# Import the node class from the nodes.py file
from .nodes import SteganosNode

# A dictionary that maps the node's class name to its display name
NODE_DISPLAY_NAME_MAPPINGS = {
    "SteganosNode": "Steganos Video Encoder"
}

# A dictionary that maps the node's class name to the node's class itself
NODE_CLASS_MAPPINGS = {
    "SteganosNode": SteganosNode
}

# A tuple containing the names of all custom nodes to be exported
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

print("### Steganos Node: Loaded ###")