from .nodes.random_number_plus import RandomNumberPlus
from .nodes.save_image_plus import SaveImagePlus
from .nodes.save_text_plus import SaveTextPlus

NODE_CLASS_MAPPINGS = {
    "RandomNumberPlus": RandomNumberPlus,
    "SaveImagePlus": SaveImagePlus,
    "SaveTextPlus": SaveTextPlus,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomNumberPlus": "Random Number Plus",
    "SaveImagePlus": "Save Image Plus",
    "SaveTextPlus": "Save Text Plus",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]