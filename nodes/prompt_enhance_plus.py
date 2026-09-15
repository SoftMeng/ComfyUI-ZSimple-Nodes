"""Prompt Enhance Plus — multi-model prompt optimizer driven by a local LLM.

Mirrors ComfyUI's TextGenerate pattern; independent implementation. The node
accepts a short user prompt plus optional image/video/audio, picks the right
system prompt for the chosen target model (LTX 2.5 / H3 / Z-Image / Krea-2 /
Krea-2-Edit), formats it in the chat template expected by the loaded local
LLM (gemma3 / gemma4 / qwen), and returns the expanded prompt as a single
STRING.
"""

import os
import re

from comfy_api.latest import io


# ---------------------------------------------------------------------------
# Built-in system prompts — stored as editable .md files
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "model_system_prompt",
)

_TEMPLATE_FILES = {
    ("LTX2.5", "T2V"): "ltx25_t2v",
    ("LTX2.5", "I2V"): "ltx25_i2v",
    ("H3", "T2V"): "h3_t2v",
    ("H3", "I2V"): "h3_i2v",
    ("Z-Image", "T2I"): "zimage_t2i",
    ("Krea-2", "T2I"): "krea2_t2i",
    ("Krea-2-Edit", "I2V"): "krea2_edit_i2v",
}


def _load_builtin_templates() -> dict[tuple[str, str], str]:
    templates = {}
    for key, stem in _TEMPLATE_FILES.items():
        path = os.path.join(_TEMPLATE_DIR, f"{stem}.md")
        with open(path, "r", encoding="utf-8") as f:
            templates[key] = f.read().strip()
    return templates


_BUILTIN_TEMPLATES: dict[tuple[str, str], str] = _load_builtin_templates()


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

    Image handling: we never embed image placeholders in the text.
    The image tensor is passed to clip.tokenize(image=image), and the
    tokenizer (qwen35 / gemma4 / gemma3) appends the correct vision
    tokens itself. Embedding image-soft placeholders here is wrong:
    qwen expects <|vision_start|><|image_pad|><|vision_end|>, gemma4
    expects <start_of_image>, gemma3 expects <start_of_image> — none
    of which are raw strings we should hand-write.
    """
    if family == "gemma4":
        return (
            f"<|turn>system\n{system}<turn|>\n"
            f"<|turn>user\n{user_text}<turn|>\n"
            f"<|turn>model\n"
        )
    if family == "qwen":
        prefix = "" if thinking else "/no_think "
        return f"{system}\n\n{prefix}{user_text}"
    return (
        f"<start_of_turn>system\n{system}<end_of_turn>\n"
        f"<start_of_turn>user\nUser Raw Input Prompt: {user_text}.<end_of_turn>\n"
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

    # 2) unclosed thinking tag: an unclosed <think> means the output was
    # truncated mid-reasoning — everything after it is think content with
    # no answer yet. Delete to end of string (not just end of line).
    text = re.sub(r"<think>.*\Z", "", text, flags=re.DOTALL)

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
                io.Int.Input(
                    "max_length",
                    default=1024,
                    min=64,
                    max=32768,
                    step=32,
                    tooltip=(
                        "Qwen3-thinking models spend the first few hundred tokens "
                        "inside <think>...</think> before writing the answer. 1024 gives "
                        "the model room to finish thinking AND write the final prompt; "
                        "the think block is stripped from the output."
                    ),
                ),
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
