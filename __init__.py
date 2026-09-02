from .nodes.random_number_plus import RandomNumberPlus
from .nodes.save_image_plus import SaveImagePlus
from .nodes.save_text_plus import SaveTextPlus
from .nodes.zimage_turbo_progressive import ZImageTurboProgressive

NODE_CLASS_MAPPINGS = {
    "RandomNumberPlus": RandomNumberPlus,
    "SaveImagePlus": SaveImagePlus,
    "SaveTextPlus": SaveTextPlus,
    "ZImageTurboProgressive": ZImageTurboProgressive,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomNumberPlus": "Random Number Plus",
    "SaveImagePlus": "Save Image Plus",
    "SaveTextPlus": "Save Text Plus",
    "ZImageTurboProgressive": "Z-Image Turbo Progressive",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]