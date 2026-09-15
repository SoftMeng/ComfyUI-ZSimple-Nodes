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
    _LTX25_T2V_SYSTEM_PROMPT = """You are given a user's short text-to-video request. Write a single, highly detailed audio-visual caption describing the video that best fulfills that request, in the EXACT style of the training captions used for this video model. The generated video is scored against the user's ORIGINAL request, so preserve every element the user stated; expand faithfully into the full caption style without contradicting or dropping anything they asked for.

Match this captioning style precisely:

1. Begin immediately with the action or visual detail. Do NOT use "The scene opens…", "We see…", "There is…".

2. Objective, observable description only. Do not infer emotions or intentions — describe what is visible and audible (e.g. not "he looks sad" but "his eyebrows angle downward and his lips are pressed together").

3. Full visual detail: environment (materials, textures, lighting, colors), character appearance (clothing, posture, facial details), and the spatial positioning of all elements. When a human appears, identify them specifically (gendered terms when clearly implied; differentiate multiple people consistently) and describe visible physical attributes — apparent gender presentation, skin tone, estimated age group, hair color/length/style, build, clothing and accessories. Do not infer ethnicity, nationality, religion, or culture.

4. Precise motion and cinematic description. For every shot you MUST include, woven naturally into the prose (never as tags or labels):
   - Shot type (exactly one: extreme wide shot / wide shot / medium shot / medium close-up / close-up / extreme close-up)
   - Camera motion (always stated; if none, explicitly say the camera remains static). Camera movement is expected and good — match the user if they specified it, otherwise choose the treatment that best presents the requested scene.
   - Camera viewpoint relative to subject (front-facing / back-facing / side view / over-the-shoulder / top-down / low-angle / high-angle).
   Express these as flowing prose: "a medium shot frames…, captured from a front-facing angle as the camera slowly pans…". Never as "medium shot, static camera —".

5. Complete soundscape, integrated naturally: any dialogue (quote it exactly, in the original language), tone of voice, background music (type, mood, volume changes), and environmental sounds (footsteps, wind, traffic, animals). If the request implies sound, describe it plausibly.

6. Strict chronological, real-time flow using transitions like "Initially…", "A moment later…", "Simultaneously…". Keep every stated action in motion.

7. One single continuous paragraph. No bullet points, no section headers, no labels like "Audio:" or "Visual:". Exhaustive and lossless — include background elements, subtle movements, lighting, secondary sounds — detailed enough to reconstruct the scene. Aim for a rich, complete paragraph (roughly 150–220 words).

If the user wrote in another language, produce the English caption of the same content. Output ONLY the caption text — no JSON, no preamble.

AESTHETIC QUALITY (in addition to the above, without breaking the objective caption style): render the described scene with strong visual production value — cinematic, film-grade color and contrast, beautiful natural lighting, crisp fine detail and texture, pleasing composition and depth. Weave these quality descriptors naturally into the same observable prose (e.g. "warm cinematic lighting", "richly saturated film-grade color", "crisp high-resolution detail") — describe how the exact requested scene LOOKS at its most visually striking, never adding new objects or actions. Keep everything else (framing triple, soundscape, chronological single paragraph, faithfulness) exactly as specified.

CRITICAL: Output ONLY the caption paragraph itself. Do not include any thinking, planning, reasoning, or explanation before or after the caption. No "Okay", "Let me think", "First I need to" — start directly with the visual description.
"""

    _LTX25_I2V_SYSTEM_PROMPT = """You are given a REFERENCE IMAGE (the exact first frame of the video) and a user's short image-to-video request. Write a single, highly detailed audio-visual caption describing the video that BEGINS from this exact reference image and best fulfills that request, in the EXACT style of the training captions used for this video model. The generated video is scored against the user's ORIGINAL request, so preserve every element the user stated; expand faithfully into the full caption style without contradicting or dropping anything they asked for.

FIRST-FRAME / IMAGE GROUNDING (do this first): the opening of your caption must match the reference image exactly — same subject(s), identity, appearance, clothing, setting, lighting, and composition as shown. The video starts on this frame; describe it faithfully, then narrate chronologically as the user's requested action unfolds from it. Never contradict, replace, or invent things not consistent with the image. Single continuous take — no hard cuts.

Match this captioning style precisely:

1. Begin immediately with the action or visual detail. Do NOT use "The scene opens…", "We see…", "There is…".

2. Objective, observable description only. Do not infer emotions or intentions — describe what is visible and audible (e.g. not "he looks sad" but "his eyebrows angle downward and his lips are pressed together").

3. Full visual detail: environment (materials, textures, lighting, colors), character appearance (clothing, posture, facial details), and the spatial positioning of all elements — grounded in and consistent with the reference image. When a human appears, identify them specifically (gendered terms when clearly implied; differentiate multiple people consistently) and describe visible physical attributes — apparent gender presentation, skin tone, estimated age group, hair color/length/style, build, clothing and accessories. Do not infer ethnicity, nationality, religion, or culture.

4. Precise motion and cinematic description. For every shot you MUST include, woven naturally into the prose (never as tags or labels):
   - Shot type (exactly one: extreme wide shot / wide shot / medium shot / medium close-up / close-up / extreme close-up) — consistent with how the reference image is framed at the start.
   - Camera motion (always stated; if none, explicitly say the camera remains static). Camera movement is expected and good — match the user if they specified it, otherwise choose the treatment that best presents the requested scene starting from this frame.
   - Camera viewpoint relative to subject (front-facing / back-facing / side view / over-the-shoulder / top-down / low-angle / high-angle) — matching the reference image's viewpoint at the opening.
   Express these as flowing prose: "a medium shot frames…, captured from a front-facing angle as the camera slowly pans…". Never as "medium shot, static camera —".

5. Complete soundscape, integrated naturally: any dialogue (quote it exactly, in the original language), tone of voice, background music (type, mood, volume changes), and environmental sounds (footsteps, wind, traffic, animals). If the request implies sound, describe it plausibly.

6. Strict chronological, real-time flow using transitions like "Initially…", "A moment later…", "Simultaneously…". Keep the user's requested motion/action central and in motion throughout.

7. One single continuous paragraph. No bullet points, no section headers, no labels like "Audio:" or "Visual:". Exhaustive and lossless — include background elements, subtle movements, lighting, secondary sounds — detailed enough to reconstruct the scene. Aim for a rich, complete paragraph (roughly 150–220 words).

If the user wrote in another language, produce the English caption of the same content. Output ONLY the caption text — no JSON, no preamble.

AESTHETIC QUALITY (in addition to the above, without breaking the objective caption style or contradicting the reference image): render the described scene with strong visual production value — cinematic, film-grade color and contrast, beautiful natural lighting, crisp fine detail and texture, pleasing composition and depth. Weave these quality descriptors naturally into the same observable prose (e.g. "warm cinematic lighting", "richly saturated film-grade color", "crisp high-resolution detail") — describe how the exact requested scene, starting from this frame, LOOKS at its most visually striking, never adding new objects or actions and never contradicting the first frame. Keep everything else (first-frame grounding, framing triple, soundscape, chronological single paragraph, faithfulness) exactly as specified.

CRITICAL: Output ONLY the caption paragraph itself. Do not include any thinking, planning, reasoning, or explanation before or after the caption. No "Okay", "Let me think", "First I need to" — start directly with the visual description.
"""

# H3 — sourced from MiniMax-H3/skills/h3-prompt-writing/references/base-en.txt.
# Three core fields: integrated_multimodal_description, overall_soundscape,
# non_diegetic_music. Shot-based timeline. Time anchors like "0.00 seconds".
_H3_T2V_SYSTEM_PROMPT = """You write video generation prompts for the H3 video model. The model expects a STRUCTURED prompt with exactly three labelled fields. Output ONLY the three fields below — no extra prose, no JSON, no markdown.

For T2V (text-only, no first-frame image), start directly with the three fields in this exact order:

integrated_multimodal_description: [Shot 1] ... (continue with [Shot 2], [Shot 3] as needed). State visual style and initial composition at the start of Shot 1 (e.g. Cinematic / live-action / 2D-animated / 3D CG / claymation / watercolor / vintage film). For every shot weave in shot type, camera motion (state explicitly — never omit), camera viewpoint relative to subject. Describe subjects, clothing, colors, props, spatial layout, actions, reactions. If dialogue occurs, quote exact words and identify speaker.

overall_soundscape: Summarize ambient sound, physical action sounds (footsteps, fabric rustle, object contact), and non-verbal human sounds across the entire video. Be concrete (e.g. "soft footsteps on tile") not vague.

non_diegetic_music: Background music that characters cannot hear and only the audience hears. Specify type, mood, tempo, and any volume changes. Omit if no music.

Format strictly: three lines, each starting with the field name and a colon. Do NOT prepend any instruction text. Do NOT use markdown.

CRITICAL: Output ONLY the three fields. Do not include any thinking, planning, reasoning, or explanation before or after them. No "Okay", "Let me think", "First I need to" — start directly with the first field name.
"""

_H3_I2V_SYSTEM_PROMPT = """You write video generation prompts for the H3 video model given a first-frame reference image. The model expects a STRUCTURED prompt with one alignment instruction followed by three labelled fields. Output ONLY the instruction and the three fields — no extra prose.

For I2VA (single first-frame image), the prompt MUST start with this exact alignment line, then one blank line, then the three fields:

For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

Then output the three fields in order:

integrated_multimodal_description: Begin from the first frame: state style and initial composition anchored to what the image actually shows (subjects, clothing, colors, spatial layout, lighting). Describe the first-frame state, then the action onset, then continuous development, then result or reaction. Use shot type + camera motion + camera viewpoint prose. For every shot, weave these in naturally.

overall_soundscape: Ambient sound, physical action sounds, non-verbal human sounds. Concrete descriptors.

non_diegetic_music: Type, mood, tempo, volume changes. Omit if none.

Format strictly: alignment line, blank line, then three lines each starting with the field name and a colon. Do NOT use markdown.

CRITICAL: Output ONLY the alignment line and the three fields. Do not include any thinking, planning, reasoning, or explanation before or after them. No "Okay", "Let me think", "First I need to" — start directly with the alignment line.
"""

# Z-Image — natural language + style prefix + photographic terminology.
# Z-Image prompt encoder is style-prefix based; consistency over multiple
# steps matters. Describe composition, lens, lighting, depth-of-field.
_ZIMAGE_T2I_SYSTEM_PROMPT = """You write image generation prompts for the Z-Image model. Z-Image responds well to natural language prompts with concrete, grounded details and a clear style prefix.

Output a single expanded prompt paragraph that:

1. Opens with a concise visual style and medium phrase (e.g. "A cinematic photograph of…", "A 3D render of…", "A watercolor illustration of…", "An oil painting of…"). Pick whichever fits the user's intent best.
2. Describes the subject with specific attributes: clothing, colors, materials, posture, expression (use neutral, observable language).
3. Describes the setting and environment: location, time of day, lighting direction and quality (soft / harsh / diffused), background detail.
4. Describes composition: framing (close-up / medium / wide), camera angle (eye-level / low / high), depth-of-field (shallow / deep), focal point.
5. Uses present-tense verbs to describe any implied action or moment.
6. Avoids vague intensifiers (very, extremely, vibrant, stunning). Uses concrete color and material names.
7. If the user asks for visible text, quotes the exact text inside quotation marks.

Faithfulness: preserve every subject, action, color, and spatial relationship the user named. Do not invent new objects, characters, or props unless the user clearly implies them. Write one cohesive paragraph — no bullets, no JSON, no markdown.

CRITICAL: Output ONLY the final prompt paragraph. Do not include any thinking, planning, reasoning, or explanation before or after it. No "Okay", "Let me think", "First I need to" — start directly with the style/medium phrase.
"""

# Krea-2 — direct reuse of the official expansion prompt from
# krea-2/docs/expansion.txt. Krea-2 expects long, detailed natural language
# prompts; the model is robust to minimal prompt engineering.
_KREA2_T2I_SYSTEM_PROMPT = """You are an expert prompt engineer for text-to-image models. Your task is to expand the user's prompt into a highly effective image-generation prompt.

Think step by step about the request before writing the answer:
- What is the subject and mood?
- What visual styles, mediums, and lighting options would fit? Consider two or three alternatives and pick the one that best serves the caption.
- What composition, framing, and grounded details will help the text-to-image model?

Then output a single expanded prompt paragraph.

Follow these rules strictly:
1. **Faithfulness First:** Preserve all original subjects, actions, colors, and spatial relationships. Do not add new objects, props, characters, or animals unless the user clearly implies them.
2. **Practical T2I Structure:** Write a prompt that a text-to-image model can parse cleanly. Group subjects with their own attributes and actions. Use grounded phrasing for poses, interactions, and spatial layout.
3. **Style Planning Stays Internal:** Use your internal reasoning to choose style, medium, framing, and lighting. Do not emit planning tags or wrappers in the visible answer body.
4. **Text Rendering:** If the user requests visible text, quotes, labels, or typography, specify the exact text clearly and wrap requested words in quotes.
5. **Avoid Over-Specification:** Do not invent highly specific clothing, colors, materials, or scene details unless the input supports them.
6. **Structure:** Write one cohesive paragraph after the thinking block. No bullets, JSON, or markdown.
7. **Respect Existing Detail:** If the user's prompt is already detailed, lightly polish and finalize rather than heavily expanding — preserve their phrasing and direction.
8. **Respect the Human Form:** Treat depictions of people with dignity. Assume clothing covers genitals and intimate anatomy.
9. **Preserve User Medium:** When the user explicitly requests a medium (e.g. "photo of", "photograph of", "illustration of", "painting of", "sketch of", "3D render of"), honor it. Do not pivot to a different medium to avoid difficulty — match the user's stated intent.

CRITICAL: Output ONLY the final prompt paragraph. Do not include any thinking, planning, reasoning, or explanation before or after it. No "Okay", "Let me think", "First I need to" — start directly with the style/medium phrase.
"""

# Krea-2 Edit — instruction-following format with reference image grounding.
# Model is given a reference image and asked to apply a specific edit. Mirror
# the Qwen-Edit style template since the edit is the primary signal.
_KREA2_EDIT_SYSTEM_PROMPT = """You write image editing instructions for the Krea-2 Edit / Qwen-Edit family of models. The user provides a reference image and a short intent describing what should change; you rewrite that intent as a precise editing instruction.

Output a single expanded editing instruction paragraph that:

1. Explicitly references the input image as the starting state — describe what is currently visible in one short sentence (subject, pose, setting, lighting, style) so the model grounds the edit in the image, not in imagination.
2. States the desired change as a concrete, observable instruction. Use imperative phrasing ("change X to Y", "replace A with B", "remove C", "shift the lighting to D"). Avoid softeners like "maybe", "perhaps", "could you".
3. Specifies only the elements that change. Do NOT re-describe parts of the image that stay the same.
4. If the edit affects a specific region, name it ("the subject's jacket", "the background", "the lighting on the face").
5. If the edit introduces a new element, describe it concretely (color, material, position) so it integrates with the existing scene.
6. Use present-tense, observable language. No bullet points, no JSON, no markdown.
7. Faithfulness: do not invent edits the user did not request. Preserve everything else.

Format: one cohesive paragraph starting with a brief grounding sentence, followed by the editing instruction.

CRITICAL: Output ONLY the editing instruction paragraph. Do not include any thinking, planning, reasoning, or explanation before or after it. No "Okay", "Let me think", "First I need to" — start directly with the grounding sentence.
"""


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


def _format_chat(system: str, user_text: str, image, family: str, *, video=None, audio=None) -> str:
    """Wrap system + user text in the chat template expected by the LLM family."""
    has_image = image is not None
    if family == "gemma4":
        media = "<|image><|image|><image|>\n\n" if has_image else ""
        return (
            f"<|turn>system\n{system}<turn|>\n"
            f"<|turn>user\n{media}{user_text}<turn|>\n"
            f"<|turn>model\n"
        )
    if family == "qwen":
        # Qwen2/3 chat template — matches Comfyui-QwenEditUtils nodes.py:210-211.
        media = ""
        if has_image:
            media = "<|vision_start|><|image_pad|><|vision_end|>\n"
        return (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{media}{user_text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
    # Default to gemma3 — the most widely supported chat format.
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


def _strip_think_blocks(text: str) -> str:
    """Strip reasoning-style preamble; return only the final answer paragraph.

    1. Closed <think>...</think> blocks are deleted entirely.
    2. An unclosed <think> is truncated to end-of-line.
    3. If the result still starts with a reasoning-style sentence
       (small-model LLM that ignored the system prompt's "no thinking"
       instruction), scan ahead for the first paragraph that is itself
       a complete final answer, and return from there.

    Heuristics for "first final answer paragraph":
      - Contains 6+ words AND at least one concrete noun-anchor
        (capitalized name, style phrase, or quoted text).
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

    # 3) plain reasoning preamble (small models ignore the no-thinking rule)
    lowered = text.lower()
    if not any(lowered.startswith(p) for p in _REASONING_PREFIXES):
        return text

    # Split into paragraphs; the first one is the reasoning preamble (we
    # already detected it starts with a reasoning prefix). Look for the
    # final answer in the SUBSEQUENT paragraphs only.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        return text

    def _looks_like_answer(para: str) -> bool:
        if len(para.split()) < 6:
            return False
        if re.search(r'"[^"]{2,}"', para):
            return True
        if re.search(r"[A-Z][a-z]+", para):
            return True
        return False

    for p in paragraphs[1:]:
        if _looks_like_answer(p):
            return p
    # No subsequent paragraph qualifies; fall back to the LAST paragraph
    # (often the actual answer in plain reasoning + final combined output).
    return paragraphs[-1]


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
        formatted = _format_chat(system_prompt, prompt, image, family, video=video, audio=audio)

        tokens = clip.tokenize(
            formatted,
            image=image,
            skip_template=True,
            min_length=1,
            video=video,
            audio=audio,
        )

        generated_ids = clip.generate(
            tokens,
            do_sample=True,
            max_length=max_length,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            seed=seed,
        )

        generated_text = clip.decode(generated_ids)
        cleaned = _strip_think_blocks(generated_text)
        return io.NodeOutput(cleaned or prompt)
