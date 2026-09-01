from .nodes.random_number_plus import RandomNumberPlus
from .nodes.save_image_plus import SaveImagePlus

NODE_CLASS_MAPPINGS = {
    "RandomNumberPlus": RandomNumberPlus,
    "SaveImagePlus": SaveImagePlus,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomNumberPlus": "Random Number Plus",
    "SaveImagePlus": "Save Image Plus",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]