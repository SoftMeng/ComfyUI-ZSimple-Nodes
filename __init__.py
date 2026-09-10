from nodes.random_number_plus import RandomNumberPlus
from nodes.save_image_plus import SaveImagePlus
from nodes.save_text_plus import SaveTextPlus
from nodes.save_video_plus import SaveVideoPlus
from nodes.z_simple_anthropic_agent import ZSimpleAnthropicAgent
from nodes.z_simple_openai_agent import ZSimpleOpenAIAgent
from nodes.zimage_turbo_progressive import ZImageTurboProgressive

NODE_CLASS_MAPPINGS = {
    "RandomNumberPlus": RandomNumberPlus,
    "SaveImagePlus": SaveImagePlus,
    "SaveTextPlus": SaveTextPlus,
    "SaveVideoPlus": SaveVideoPlus,
    "ZImageTurboProgressive": ZImageTurboProgressive,
    "ZSimpleAnthropicAgent": ZSimpleAnthropicAgent,
    "ZSimpleOpenAIAgent": ZSimpleOpenAIAgent,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomNumberPlus": "Random Number Plus",
    "SaveImagePlus": "Save Image Plus",
    "SaveTextPlus": "Save Text Plus",
    "SaveVideoPlus": "Save Video Plus",
    "ZImageTurboProgressive": "Z-Image Turbo Progressive",
    "ZSimpleAnthropicAgent": "ZSimple Anthropic Agent",
    "ZSimpleOpenAIAgent": "ZSimple OpenAI Agent",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]