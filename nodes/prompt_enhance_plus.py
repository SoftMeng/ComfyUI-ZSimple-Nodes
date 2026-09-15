"""Prompt Enhance Plus — multi-model prompt optimizer driven by a local LLM.

Mirrors ComfyUI's TextGenerate pattern; independent implementation. The node
accepts a short user prompt plus optional image/video/audio, picks the right
system prompt for the chosen target model (LTX 2.5 / H3 / Z-Image / Krea-2 /
Krea-2-Edit), formats it in the chat template expected by the loaded local
LLM (gemma3 / gemma4 / qwen), and returns the expanded prompt as a single
STRING.
"""

import re

from comfy_api.latest import io


# ---------------------------------------------------------------------------
# Built-in system prompts (target model specific)
# ---------------------------------------------------------------------------

# LTX 2.5 prompts: prefer the upstream ComfyUI constant when available (so
# upstream edits propagate), fall back to a local copy in dev environments
# without ComfyUI installed.
try:
    from comfy_extras.nodes_textgen import (
        LTX24_T2V_SYSTEM_PROMPT as _LTX25_T2V_SYSTEM_PROMPT,
        LTX24_I2V_SYSTEM_PROMPT as _LTX25_I2V_SYSTEM_PROMPT,
    )
except ImportError:
    _LTX25_T2V_SYSTEM_PROMPT = """You write LTX 2.5 video prompts. Output a single paragraph that starts immediately with the action or visual and weaves in shot type, camera motion, camera viewpoint, soundscape, and chronological flow in prose.

Example:
User: a woman walks into a cafe
Output: A cinematic medium shot frames a woman in her early thirties, cream linen blazer, shoulder-length dark hair, as she pushes through the brass-handled glass door of a corner cafe, captured from a front-facing angle as the camera slowly tracks her forward. The soft bell above the door chimes twice, footsteps cross worn wooden floorboards, the espresso machine hisses in the background as the warm amber light from the window catches her face, and she pauses, scans the room, smiles, and walks toward an empty table by the rain-streaked window while rain taps the glass.

CRITICAL: Your response IS the prompt paragraph. Start the first word of your response with the visual/action. No "First, I need to", no "Let me think", no preamble. No planning. Output ONLY the paragraph above-style.
"""

    _LTX25_I2V_SYSTEM_PROMPT = """You write LTX 2.5 image-to-video prompts. The first frame is already given. Continue chronologically from that frame in one prose paragraph that weaves in shot type, camera motion, camera viewpoint, soundscape, and chronological flow.

Example:
User first frame + request: woman in a red coat at a bus stop
Output: From the same front-facing medium shot, a woman in her mid-thirties with shoulder-length auburn hair, wearing a tailored red wool coat, stands under the weathered awning of a city bus stop as evening traffic streams past in soft bokeh behind her, captured from a static eye-level angle as the camera holds steady. The distant rumble of city buses, the click-clack of heels on wet pavement, and the hiss of a passing car wash over the muted sound of the rain as a yellow-orange bus rounds the corner and slows, its brakes hissing. She glances up, tucks a loose strand behind her ear, gathers her bag, and steps forward toward the opening doors as the bus driver waves her on and a soft chime sounds.

CRITICAL: Your response IS the prompt paragraph. Start the first word with the visual/action continuing from the first frame. No "First, I need to", no "Let me think", no preamble. Output ONLY the paragraph above-style.
"""

# H3 — sourced from MiniMax-H3/skills/h3-prompt-writing/references/base-en.txt.
# Three core fields: integrated_multimodal_description, overall_soundscape,
# non_diegetic_music. Shot-based timeline. Time anchors like "0.00 seconds".
_H3_T2V_SYSTEM_PROMPT = """You are an expert prompt engineer for the MiniMax H3 video model. Given a brief user request describing a scene, expand it into a complete H3 prompt.

Output EXACTLY these three labelled fields in this order, with no other text before or after:

integrated_multimodal_description: [Shot 1] ... (continue with [Shot 2], [Shot 3] as needed when the scene has natural cuts).

For every shot, weave these elements in natural prose (never as tags):
- Shot type: extreme wide shot, wide shot, medium shot, medium close-up, close-up, or extreme close-up.
- Camera motion: state explicitly (pan, tilt, dolly, track, push-in, pull-out, static, etc.). If none, write "the camera remains static".
- Camera viewpoint: front-facing, back-facing, side view, over-the-shoulder, top-down, low-angle, or high-angle.
- Visual style: cinematic, live-action, 2D-animated, 3D CG, claymation, watercolor, vintage film, etc.
- Subjects, clothing, colors, props, spatial layout, actions, reactions.
- Dialogue: quote exact words and identify speaker.

overall_soundscape: Summarize the ambient sound, physical action sounds (footsteps, fabric rustle, object contact), and non-verbal human sounds across the entire video. Be concrete ("soft footsteps on tile"), not vague ("ambient sound").

non_diegetic_music: Background music that characters cannot hear and only the audience hears. Specify type, mood, tempo, and any volume changes. Omit if no music is implied.
"""

_H3_I2V_SYSTEM_PROMPT = """You are an expert prompt engineer for the MiniMax H3 video model. The user has supplied a first-frame reference image plus a brief request. Expand it into a complete H3 image-to-video prompt.

Output EXACTLY this alignment line, then three labelled fields, with no other text:

For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: Begin from the first-frame state — describe the framing, subjects, clothing, colors, lighting exactly as shown in the reference. Then narrate how the user's requested action unfolds chronologically. For every shot, weave in shot type, camera motion, camera viewpoint, visual style, subjects, actions, and dialogue (if any) in natural prose.

overall_soundscape: Ambient and physical action sounds for the whole clip.

non_diegetic_music: Background music if any. Omit if none.
"""

# Z-Image. After 13 failed prompt-engineering attempts on a 4B base
# model, the right move is to stop listing rules. Small models see
# "1. ... 2. ... 3. ..." and start EXPLAINING each rule back instead
# of writing a prompt. The system message below just sets the
# role and the required output shape; the user's brief is the
# only thing the model has to act on.
_ZIMAGE_T2I_SYSTEM_PROMPT = """You write Z-Image prompts. Reply with one paragraph that starts with a style phrase such as "A cinematic photograph of" and continues with the subject, setting, lighting, and composition."""

# Krea-2. Same minimal pattern as Z-Image; the Krea-2 official
# expansion prompt is preserved as a custom_template default in
# the README but the built-in default is the single-line minimal
# version because small models restate numbered rules instead of
# writing the prompt.
_KREA2_T2I_SYSTEM_PROMPT = """You write Krea-2 prompts. Reply with one paragraph that starts with a style phrase such as "A cinematic photograph of" and continues with the subject, setting, lighting, and composition."""

# Krea-2 Edit.
_KREA2_EDIT_SYSTEM_PROMPT = """You write Krea-2 Edit / Qwen-Edit instructions. Reply with one paragraph that opens with a grounding sentence describing the current image state, then states the change as a concrete imperative such as "change X to Y" or "replace A with B"."""




_BUILTIN_TEMPLATES: dict[tuple[str, str], str] = {
    ("LTX2.5", "T2V"): _LTX25_T2V_SYSTEM_PROMPT,
    ("LTX2.5", "I2V"): _LTX25_I2V_SYSTEM_PROMPT,
    ("H3", "T2V"): _H3_T2V_SYSTEM_PROMPT,
    ("H3", "I2V"): _H3_I2V_SYSTEM_PROMPT,
    ("Z-Image", "T2I"): _ZIMAGE_T2I_SYSTEM_PROMPT,
    ("Krea-2", "T2I"): _KREA2_T2I_SYSTEM_PROMPT,
    ("Krea-2-Edit", "I2V"): _KREA2_EDIT_SYSTEM_PROMPT,
}


_TARGET_MODELS = list({k[0] for k in _BUILTIN_TEMPLATES})
_MODE_OPTIONS = ["auto", "T2V", "T2I", "I2V"]


# ---------------------------------------------------------------------------
# Chat-template formatters (per tokenizer family)
# ---------------------------------------------------------------------------

def _detect_tokenizer_family(clip) -> str:
    """Return 'gemma4', 'gemma3', 'qwen', or 'unknown'."""
    name = getattr(getattr(clip, "tokenizer", None), "clip_name", "") or ""
    name = name.lower()
    if "gemma4" in name:
        return "gemma4"
    if "gemma" in name:
        return "gemma3"
    if "qwen" in name:
        return "qwen"
    return "unknown"


def _format_chat(
    system: str,
    user_text: str,
    image,
    family: str,
    *,
    video=None,
    audio=None,
    thinking=False,
) -> str:
    """Format the system + user text for the local LLM.

    IMPORTANT on thinking mode (Qwen 3.5 / Gemma 4 path):

    qwen35.py:744 detects "text starts with <|im_start|>" and skips the
    llama_template. If we hand the tokenizer a string that already
    contains <|im_start|>, it takes our text as-is and the
    thinking-mode prime at qwen35.py:763 (which adds an empty
    <think>\\n</think>\\n to the chat template) is bypassed.

    To make thinking=False actually work for Qwen 3.5, this function
    returns the BARE content (system + user concatenated) without
    any chat-template markers. The qwen35.py tokenizer will then
    detect "no <|im_start|> prefix" → apply its own llama_template →
    append the thinking prime when thinking=False.

    For gemma4 (which has its own template at gemma4.py:1530), the
    <|turn>...<|turn|> markers are required by the tokenizer, so we
    keep emitting them.

    For gemma3 / unknown (no native thinking mode), the existing
    <start_of_turn>...<end_of_turn> format is harmless and we keep it.
    """
    has_image = image is not None
    if family == "gemma4":
        media = "<|image><|image|><image|>\n\n" if has_image else ""
        return (
            f"<|turn>system\n{system}<turn|>\n"
            f"<|turn>user\n{media}{user_text}<turn|>\n"
            f"<|turn>model\n"
        )
    if family == "qwen":
        # Bare content: qwen35.py will wrap with llama_template and
        # append the thinking prime. The image placeholder is inserted
        # by the tokenizer when image kwarg is set.
        if image is not None:
            return f"{system}\n\n<image>{user_text}"
        return f"{system}\n\n{user_text}"
    # Default to gemma3 format.
    media = "\n<image_soft_token>\n" if has_image else ""
    return (
        f"<start_of_turn>system\n{system}<end_of_turn>\n"
        f"<start_of_turn>user\n{media}\nUser Raw Input Prompt: {user_text}.<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_mode(mode: str, *, image, video, target_model: str) -> str:
    if mode != "auto":
        return mode
    has_visual = image is not None or video is not None  # OR-combined
    if target_model == "Krea-2-Edit":
        return "I2V" if has_visual else "T2I"
    if target_model in ("Z-Image", "Krea-2"):
        return "T2I"
    # LTX2.5, H3 — video models
    return "I2V" if has_visual else "T2V"


_REASONING_PREFIXES = (
    "okay,",
    "ok,",
    "let me",
    "first,",
    "first i",
    "the user",
    "i need to",
    "i should",
    "i will",
    "thinking:",
    "step 1:",
    "step 2:",
    "step 3:",
    "to begin",
    "alright,",
)


_REASONING_KEYWORDS = (
    "i need to",
    "i should",
    "i will",
    "i'll",
    "i must",
    "let's",
    "let me",
    "maybe",
    "perhaps",
    "the user",
    "the user wants",
    "user wants",
    "user asked",
    "user didn't",
    "user did not",
    "user specified",
    "they want",
    "they need",
    "first,",
    "first i",
    "next,",
    "then,",
    "finally,",
    "since the user",
    "as the user",
    "given the",
    "consider",
    "note:",
    "step 1:",
    "step 2:",
    "step 3:",
    "to begin",
    "thinking:",
    "thought:",
    "reasoning:",
    "okay,",
    "ok,",
    "alright,",
    "so the user",
)


def _sentence_looks_like_reasoning(sentence: str) -> bool:
    """True if the sentence reads like model reasoning rather than the
    expanded prompt answer."""
    lowered = sentence.lower().strip()
    if not lowered:
        return True
    return any(kw in lowered for kw in _REASONING_KEYWORDS)


def _strip_think_blocks(text: str) -> str:
    """Strip reasoning-style preamble; return only the final answer.

    Strategy (defense in depth):
      1. Closed <think>...</think> blocks are deleted.
      2. Unclosed <think> truncated to end of line.
      3. If output starts with a reasoning prefix, split into sentences and
         return from the first non-reasoning sentence. Falls back to the
         longest non-reasoning sentence if no clean "answer" sentence is
         found. Falls back to the original text if every sentence is
         reasoning.
    """
    # 1) closed thinking tags
    while True:
        m = re.search(r"<think>.*?</think>", text, flags=re.DOTALL)
        if not m:
            break
        text = text[: m.start()] + text[m.end():]

    # 2) unclosed thinking tag (truncate to end of current line)
    text = re.sub(r"<think>[^\n]*", "", text)

    text = text.strip()
    if not text:
        return text

    lowered = text.lower()
    if not any(lowered.startswith(p) for p in _REASONING_PREFIXES):
        return text

    # 3) split into sentences; keep the period/whitespace as the splitter
    # so the rebuilt answer is grammatically correct.
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p for p in parts if p.strip()]

    # First pass: find first sentence that doesn't look like reasoning.
    for p in parts:
        if not _sentence_looks_like_reasoning(p):
            return " ".join(parts[parts.index(p):]).strip()

    # Second pass: return the longest sentence (often the actual answer
    # even when the model used reasoning-y openers throughout).
    if parts:
        longest = max(parts, key=len)
        if len(longest.split()) >= 6:
            return longest

    return text


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class PromptEnhancePlus(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PromptEnhancePlus",
            display_name="Prompt Enhance Plus",
            category="ZSimple-Nodes/text",
            search_aliases=["prompt enhance", "LLM", "prompt expander", "gemma", "qwen"],
            description=(
                "Expands a short prompt using a local LLM (Gemma / Qwen / etc.) "
                "into a training-style caption for LTX 2.5 / H3 / Z-Image / Krea-2 / "
                "Krea-2-Edit. Supports image / video / audio context and a custom "
                "system-prompt override."
            ),
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input(
                    "prompt",
                    multiline=True,
                    dynamic_prompts=True,
                    default="",
                    tooltip="Short user prompt to expand.",
                ),
                io.Combo.Input(
                    "target_model",
                    options=_TARGET_MODELS,
                    default="LTX2.5",
                    tooltip="Target model whose training caption style the LLM should mimic.",
                ),
                io.Combo.Input(
                    "mode",
                    options=_MODE_OPTIONS,
                    default="auto",
                    tooltip="auto = inferred from image/video/audio; otherwise force T2V/T2I/I2V.",
                ),
                io.Image.Input("image", optional=True, tooltip="Optional first-frame reference (I2V)."),
                io.Image.Input(
                    "video",
                    optional=True,
                    tooltip="Optional video frames as image batch (24 FPS assumed, subsampled to 1 FPS internally).",
                ),
                io.Audio.Input("audio", optional=True, tooltip="Optional audio context."),
                io.String.Input(
                    "custom_template",
                    multiline=True,
                    optional=True,
                    default="",
                    tooltip="Override the built-in system prompt with your own. Leave empty to use the built-in template.",
                ),
                io.Int.Input("max_length", default=512, min=64, max=32768, step=32),
                io.Float.Input("temperature", default=0.7, min=0.01, max=2.0, step=0.01),
                io.Int.Input("top_k", default=64, min=0, max=1000, step=1),
                io.Float.Input("top_p", default=0.95, min=0.0, max=1.0, step=0.01),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.Float.Input(
                    "min_p",
                    default=0.0,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    advanced=True,
                    tooltip=(
                        "min_p sampling — pass through to clip.generate. Default 0.0 "
                        "disables; 0.05-0.1 recommended for slightly tighter sampling."
                    ),
                ),
                io.Float.Input(
                    "repetition_penalty",
                    default=1.0,
                    min=1.0,
                    max=2.0,
                    step=0.01,
                    advanced=True,
                    tooltip=(
                        "Penalize tokens that already appeared. Values > 1.0 discourage "
                        "repetition. Useful to fight the planning-loop pattern where "
                        "4B models restate the same opening over and over."
                    ),
                ),
                io.Float.Input(
                    "presence_penalty",
                    default=0.0,
                    min=0.0,
                    max=5.0,
                    step=0.01,
                    advanced=True,
                    tooltip="Pass-through to clip.generate. See TextGenerate node.",
                ),
                io.Boolean.Input(
                    "thinking",
                    default=False,
                    tooltip=(
                        "For Qwen3.5 / Gemma4 12B+ that support thinking mode, "
                        "passes thinking=thinking to clip.tokenize. Has no effect on "
                        "Qwen2.5 / Gemma 3 4B base models (they have no thinking "
                        "mode and cannot be silenced via this flag). Leave False for "
                        "clean outputs; set True only if you want the model to use "
                        "its native reasoning mode (then enable thinking_mode on the "
                        "model loader and pick a thinking-capable checkpoint)."
                    ),
                ),
            ],
            outputs=[
                io.String.Output(display_name="enhanced_prompt"),
            ],
        )

    @classmethod
    def execute(
        cls,
        clip,
        prompt,
        target_model,
        mode,
        max_length,
        temperature,
        top_k,
        top_p,
        seed,
        image=None,
        video=None,
        audio=None,
        custom_template="",
        thinking=False,
        min_p=0.0,
        repetition_penalty=1.0,
        presence_penalty=0.0,
    ) -> io.NodeOutput:
        custom_template = (custom_template or "").strip()

        if custom_template:
            system_prompt = custom_template
        else:
            effective_mode = _resolve_mode(
                mode, image=image, video=video, target_model=target_model
            )
            system_prompt = _BUILTIN_TEMPLATES.get((target_model, effective_mode))
            if system_prompt is None:
                raise ValueError(
                    f"No built-in template for {target_model}/{effective_mode}. "
                    f"Either connect an image/video (for I2V modes), change target_model, "
                    f"or supply a custom_template."
                )

        family = _detect_tokenizer_family(clip)
        if (video is not None or audio is not None) and family not in ("qwen", "gemma4"):
            print(
                f"[PromptEnhancePlus] warning: {family} tokenizer does not support "
                f"video/audio input; ignoring."
            )
            video = None
            audio = None
        formatted = _format_chat(
            system_prompt, prompt, image, family,
            video=video, audio=audio, thinking=thinking,
        )

        # For qwen / gemma4 we use skip_template=False so the tokenizer
        # applies its own chat template (which is what carries the
        # thinking-mode prime at qwen35.py:763 / gemma4.py:1538). For
        # gemma3 / unknown we hand the tokenizer a complete chat
        # template string already, so skip_template=True is required to
        # avoid double-wrapping.
        use_skip_template = family not in ("qwen", "gemma4")

        tokens = clip.tokenize(
            formatted,
            image=image,
            skip_template=use_skip_template,
            min_length=1,
            video=video,
            audio=audio,
            thinking=thinking,
        )

        generated_ids = clip.generate(
            tokens,
            do_sample=True,
            max_length=max_length,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            min_p=min_p,
            repetition_penalty=repetition_penalty,
            seed=seed,
            presence_penalty=presence_penalty,
        )

        generated_text = clip.decode(generated_ids)
        cleaned = _strip_think_blocks(generated_text)
        return io.NodeOutput(cleaned or prompt)
