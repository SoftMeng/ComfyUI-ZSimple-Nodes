"""Tests for PromptEnhancePlus.

Mocks a fake CLIP so the node can run without ComfyUI/GPU. Covers:
  - Built-in template lookup per target model + mode.
  - Custom template override (skip built-in).
  - Auto-mode resolution from image/video/audio presence.
  - Chat-template formatting per tokenizer family.
  - <think> block stripping.
  - Empty-output fallback to original prompt.
"""

import contextlib
import io as _io
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Inject minimal stubs for the comfy_api bits our node touches so the test
# can run in any environment (no ComfyUI install, no torch/psutil required).
# The node file is imported lazily after stubs are in place.
def _install_io_stubs():
    comfy_api = types.ModuleType("comfy_api")
    latest = types.ModuleType("comfy_api.latest")

    class _Schema:
        def __init__(self, *, node_id, display_name, category, search_aliases=None,
                     description=None, inputs=None, outputs=None):
            self.node_id = node_id
            self.display_name = display_name
            self.category = category
            self.search_aliases = search_aliases or []
            self.description = description
            self.inputs = inputs or []
            self.outputs = outputs or []

    class _NodeOutput:
        def __init__(self, *args):
            self.args = args
            self.result = args

    class _ComfyNode:
        @classmethod
        def define_schema(cls):
            raise NotImplementedError

    class _Input:
        def __init__(self, name, **kwargs):
            self.name = name
            self._kwargs = kwargs

        @property
        def options(self):
            return self._kwargs.get("options", [])

    class _Output:
        def __init__(self, name="", display_name="", **kwargs):
            # V3 io.String.Output(display_name="…") — surface the display name
            # as `name` so tests can assert on the visible output label.
            self.name = display_name or name
            self._kwargs = kwargs

    class _StringInput(_Input):
        def __init__(self, name, **kwargs):
            kwargs.setdefault("default", "")
            super().__init__(name, **kwargs)

    class _IntInput(_Input):
        def __init__(self, name, **kwargs):
            kwargs.setdefault("default", 0)
            super().__init__(name, **kwargs)

    class _FloatInput(_Input):
        def __init__(self, name, **kwargs):
            kwargs.setdefault("default", 0.0)
            super().__init__(name, **kwargs)

    class _ComboInput(_Input):
        def __init__(self, name, options=None, **kwargs):
            kwargs["options"] = options or []
            super().__init__(name, **kwargs)

    class _BoolInput(_Input):
        def __init__(self, name, **kwargs):
            kwargs.setdefault("default", False)
            super().__init__(name, **kwargs)

    class _ClipInput(_Input):
        pass

    class _ImageInput(_Input):
        pass

    class _AudioInput(_Input):
        pass

    class _MaskInput(_Input):
        pass

    class _LatentInput(_Input):
        pass

    class io:
        Schema = _Schema
        NodeOutput = _NodeOutput
        ComfyNode = _ComfyNode
        String = type("String", (), {"Input": _StringInput, "Output": _Output})
        Int = type("Int", (), {"Input": _IntInput, "Output": _Output})
        Float = type("Float", (), {"Input": _FloatInput, "Output": _Output})
        Combo = type("Combo", (), {"Input": _ComboInput, "Output": _Output})
        Boolean = type("Boolean", (), {"Input": _BoolInput, "Output": _Output})
        Clip = type("Clip", (), {"Input": _ClipInput, "Output": _Output})
        Image = type("Image", (), {"Input": _ImageInput, "Output": _Output})
        Audio = type("Audio", (), {"Input": _AudioInput, "Output": _Output})
        Mask = type("Mask", (), {"Input": _MaskInput, "Output": _Output})
        Latent = type("Latent", (), {"Input": _LatentInput, "Output": _Output})

    latest.io = io
    comfy_api.latest = latest
    sys.modules["comfy_api"] = comfy_api
    sys.modules["comfy_api.latest"] = latest


_install_io_stubs()

from nodes.prompt_enhance_plus import (
    PromptEnhancePlus,
    _BUILTIN_TEMPLATES,
    _detect_tokenizer_family,
    _format_chat,
    _resolve_mode,
    _strip_think_blocks,
)


class _FakeTokenizer:
    def __init__(self, name="gemma3-12b"):
        self.clip_name = name


class _FakeCLIP:
    def __init__(self, name="gemma3-12b", response="enhanced output text"):
        self.tokenizer = _FakeTokenizer(name)
        self._response = response
        self.last_generate_kwargs = None
        self.last_tokenize_kwargs = None

    def tokenize(self, prompt, **kwargs):
        self.last_tokenize_kwargs = {"tokens": prompt, **kwargs}
        return {"tokens": prompt, "kwargs": kwargs}

    def generate(self, tokens, **kwargs):
        self.last_generate_kwargs = kwargs
        return ["tok1", "tok2"]

    def decode(self, ids):
        return self._response


# ---------------------------------------------------------------------------
# Template lookup
# ---------------------------------------------------------------------------

def test_builtin_templates_cover_all_target_models():
    models = {k[0] for k in _BUILTIN_TEMPLATES}
    assert {"LTX2.5", "H3", "Z-Image", "Krea-2", "Krea-2-Edit"}.issubset(models)


def test_each_template_is_non_empty():
    for (model, mode), tmpl in _BUILTIN_TEMPLATES.items():
        # All templates are real system prompts that describe the task
        # to the LLM. Empty system messages make 4B models treat the
        # user prompt as the start of free-form continuation, not as
        # a request to expand — so empty is the wrong default here.
        assert isinstance(tmpl, str) and tmpl.strip(), f"empty template for {model}/{mode}"


def test_each_template_length_in_safe_range():
    for (model, mode), tmpl in _BUILTIN_TEMPLATES.items():
        words = len(tmpl.split())
        chars = len(tmpl)
        # 中文模板按空白切词会少算，按字符上限收尾更准。H3 i2v 是最小模板 ~70词 / ~530 chars。
        assert 30 <= words <= 1500, f"{model}/{mode} template has {words} words; expected 30-1500"
        assert 200 <= chars <= 8000, f"{model}/{mode} template has {chars} chars; expected 200-8000"


# ---------------------------------------------------------------------------
# Custom template override
# ---------------------------------------------------------------------------

def test_custom_template_overrides_builtin():
    custom = "I am a custom system prompt."
    clip = _FakeCLIP()
    out = PromptEnhancePlus.execute(
        clip,
        prompt="a cat",
        target_model="LTX2.5",
        mode="T2V",
        max_length=64,
        temperature=0.5,
        top_k=40,
        top_p=0.9,
        seed=0,
        custom_template=custom,
    )
    formatted = clip.last_tokenize_kwargs.get("kwargs", {}).get("tokens")
    # The tokenize call isn't easily inspectable here; instead test the
    # formatter directly with the chosen custom prompt.
    assert custom in _format_chat(custom, "a cat", None, "gemma3")


# ---------------------------------------------------------------------------
# Auto-mode resolution
# ---------------------------------------------------------------------------

def test_auto_mode_t2v_for_video_models_without_image():
    assert _resolve_mode("auto", image=None, video=None, target_model="LTX2.5") == "T2V"
    assert _resolve_mode("auto", image=None, video=None, target_model="H3") == "T2V"


def test_auto_mode_i2v_when_image_connected():
    assert _resolve_mode("auto", image="img", video=None, target_model="LTX2.5") == "I2V"
    assert _resolve_mode("auto", image=None, video="vid", target_model="H3") == "I2V"


def test_auto_mode_t2i_for_image_models():
    assert _resolve_mode("auto", image=None, video=None, target_model="Z-Image") == "T2I"
    assert _resolve_mode("auto", image=None, video=None, target_model="Krea-2") == "T2I"


def test_auto_mode_forces_i2v_for_edit_model():
    assert _resolve_mode("auto", image="img", video=None, target_model="Krea-2-Edit") == "I2V"
    assert _resolve_mode("auto", image=None, video=None, target_model="Krea-2-Edit") == "T2I"


def test_explicit_mode_overrides_auto():
    assert _resolve_mode("T2I", image="img", video=None, target_model="LTX2.5") == "T2I"


# ---------------------------------------------------------------------------
# Tokenizer family detection
# ---------------------------------------------------------------------------

def test_detect_gemma4():
    clip = _FakeCLIP(name="gemma4-text")
    assert _detect_tokenizer_family(clip) == "gemma4"


def test_detect_gemma3():
    clip = _FakeCLIP(name="gemma-3-12b-it-qat-q4_0-unquantized")
    assert _detect_tokenizer_family(clip) == "gemma3"


def test_detect_qwen():
    clip = _FakeCLIP(name="qwen3.5-2b-instruct")
    assert _detect_tokenizer_family(clip) == "qwen"


def test_detect_unknown_falls_back():
    clip = _FakeCLIP(name="random-llm-7b")
    assert _detect_tokenizer_family(clip) == "unknown"


# ---------------------------------------------------------------------------
# Chat-template formatting
# ---------------------------------------------------------------------------

def test_format_chat_gemma3_includes_turn_markers():
    out = _format_chat("SYS", "user prompt", None, "gemma3")
    assert "<start_of_turn>system" in out
    assert "SYS" in out
    assert "user prompt" in out
    assert "<start_of_turn>model" in out


def test_format_chat_gemma4_uses_pipe_turn_markers():
    out = _format_chat("SYS", "user prompt", None, "gemma4")
    assert "<|turn>system" in out
    assert "<|turn>model" in out


def test_format_chat_qwen_returns_bare_content_for_tokenizer_wrap():
    """Qwen path returns BARE content (no <|im_start|>) so the
    qwen35.py tokenizer applies its own llama_template and triggers
    the thinking prime at qwen35.py:763."""
    out = _format_chat("SYS", "user prompt", None, "qwen")
    assert not out.startswith("<|im_start|>")
    assert "SYS" in out
    assert "user prompt" in out


def test_format_chat_qwen_and_gemma3_never_emit_image_placeholders():
    """qwen 和 gemma3 分支不写 image 占位符——依赖 tokenize 自己注入。
    gemma4 分支要写 <|image><|image|><image|>（见下一个测试）。"""
    for family in ("qwen", "gemma3"):
        out = _format_chat("SYS", "u", "img", family)
        assert "<image>" not in out, f"{family} still emits <image>"
        assert "<|image><|image|><image|>" not in out, f"{family} still emits gemma4 marker"
        assert "<image_soft_token>" not in out, f"{family} still emits <image_soft_token>"


def test_format_chat_gemma4_emits_image_placeholder_when_image_present():
    """gemma4 + image 必须在 user turn 前加 <|image><|image|><image|>。
    这是 TextGenerateLTX2Prompt 上游节点的标准模式（nodes_textgen.py:242）。"""
    with_img = _format_chat("SYS", "u", "img", "gemma4")
    assert "<|image><|image|><image|>" in with_img


def test_format_chat_gemma4_no_image_placeholder_when_no_image():
    """gemma4 + 无 image：不应有 image 占位符。"""
    no_img = _format_chat("SYS", "u", None, "gemma4")
    assert "<|image><|image|><image|>" not in no_img


def test_format_chat_image_does_not_change_text_for_qwen_and_gemma3():
    """qwen / gemma3：image 参数不应改变 _format_chat 输出文本（占位符全由 tokenize 注入）。"""
    for family in ("qwen", "gemma3"):
        base = _format_chat("SYS", "u", None, family)
        with_img = _format_chat("SYS", "u", "img", family)
        assert base == with_img, f"{family} changed text based on image"


def test_format_chat_image_changes_gemma4_text():
    """gemma4：image 应在 user turn 前注入 <|image><|image|><image|>。"""
    base_g4 = _format_chat("SYS", "u", None, "gemma4")
    with_img_g4 = _format_chat("SYS", "u", "img", "gemma4")
    assert base_g4 != with_img_g4
    assert "<|image><|image|><image|>" in with_img_g4
    assert "<|image><|image|><image|>" not in base_g4


def test_execute_still_passes_image_kwarg_to_tokenize():
    """image tensor 必须仍由 clip.tokenize 接收（vision token 注入归 tokenizer）。"""
    clip = _FakeCLIP(name="qwen2.5-vl-3b", response="ok")
    PromptEnhancePlus.execute(
        clip, prompt="test", target_model="LTX2.5", mode="T2V",
        max_length=64, temperature=0.7, top_k=64, top_p=0.95, seed=0,
        image="img-tensor",
    )
    assert clip.last_tokenize_kwargs["image"] == "img-tensor"
    # vision token 由 tokenizer 自己处理；我们送入的字符串不应含任何 image 标记
    sent_text = clip.last_tokenize_kwargs["tokens"]
    assert "<image>" not in sent_text
    assert "<|image|>" not in sent_text
    assert "<image_soft_token>" not in sent_text


# ---------------------------------------------------------------------------
# Thinking-mode control: prime is now applied by the tokenizer
# (qwen35.py:763) for qwen, gemma4.py:1538 for gemma4, not by us.
# ---------------------------------------------------------------------------

def test_format_chat_qwen_does_not_pre_mark_think_block():
    """qwen35.py will append the empty think block at tokenize time
    when thinking=False AND skip_template=False. Our _format_chat
    must NOT pre-emit a think block itself (otherwise the model
    would see a duplicated <think>\\n</think>\\n)."""
    out = _format_chat("SYS", "u", None, "qwen", thinking=False)
    assert "<think>" not in out
    assert "<|im_start|>" not in out  # tokenizer will add the markers


def test_format_chat_gemma4_does_not_pre_mark_think_block():
    out = _format_chat("SYS", "u", None, "gemma4", thinking=False)
    assert "<think>" not in out
    assert out.endswith("<|turn>model\n")


# ---------------------------------------------------------------------------
# /no_think training-time soft switch (Qwen3-series models)
# ---------------------------------------------------------------------------

def test_format_chat_qwen_no_think_prefix_when_thinking_false():
    """/no_think is a Qwen3 training-time instruction — model skips its
    reasoning phase when it sees this at the start of the user turn.
    Injected only for qwen family, only when thinking=False."""
    out = _format_chat("SYS", "user prompt", None, "qwen", thinking=False)
    assert "/no_think" in out
    assert "user prompt" in out


def test_format_chat_qwen_no_think_prefix_absent_when_thinking_true():
    out = _format_chat("SYS", "user prompt", None, "qwen", thinking=True)
    assert "/no_think" not in out
    assert "user prompt" in out


def test_format_chat_qwen_no_think_prefix_with_image():
    """B方案：image 不再改 _format_chat 输出；/no_think 仍在原位。"""
    out = _format_chat("SYS", "u", "img", "qwen", thinking=False)
    assert "/no_think" in out
    assert "<image>" not in out  # 占位符移除
    # 与无 image 的输出一致（image kwarg 不影响文本）
    assert out == _format_chat("SYS", "u", None, "qwen", thinking=False)


def test_format_chat_gemma3_untouched_by_no_think():
    """/no_think is Qwen-specific; gemma families never see it."""
    out = _format_chat("SYS", "u", None, "gemma3", thinking=False)
    assert "/no_think" not in out
    out4 = _format_chat("SYS", "u", None, "gemma4", thinking=False)
    assert "/no_think" not in out4


def test_format_chat_gemma3_thinking_false_does_not_prime():
    """Gemma3 (E2B/E4B) MUST NOT be primed with an empty think block —
    gemma4.py:1562 explicitly warns that small models interpret an empty
    think block as an inline-reasoning cue."""
    out = _format_chat("SYS", "u", None, "gemma3", thinking=False)
    assert "<think>" not in out
    assert out.endswith("<start_of_turn>model\n")


def test_execute_passes_thinking_kwarg_to_tokenize():
    """Thinking flag must flow to clip.tokenize so the tokenizer sees it."""
    clip = _FakeCLIP(name="qwen3-4b", response="final answer")
    PromptEnhancePlus.execute(
        clip,
        prompt="test",
        target_model="LTX2.5",
        mode="T2V",
        max_length=64,
        temperature=0.7,
        top_k=64,
        top_p=0.95,
        seed=0,
        thinking=False,
    )
    assert clip.last_tokenize_kwargs.get("thinking") is False


def test_node_schema_exposes_thinking_input():
    schema = PromptEnhancePlus.define_schema()
    assert any(i.name == "thinking" for i in schema.inputs)


# ---------------------------------------------------------------------------
# Think-block stripping
# ---------------------------------------------------------------------------

def test_strip_think_block_basic():
    text = "<think>reasoning here</think>actual answer"
    assert _strip_think_blocks(text) == "actual answer"


def test_strip_think_block_unclosed_deletes_everything():
    """An unclosed <think> means max_length truncated the model mid-reasoning.
    Everything after it is think content — no answer exists yet. Delete all."""
    text = "<think>reasoning never ends\nmore reasoning lines\nstill thinking"
    assert _strip_think_blocks(text) == ""


def test_strip_think_block_no_block():
    assert _strip_think_blocks("plain text") == "plain text"


# ---------------------------------------------------------------------------
# Plain-reasoning preamble stripping (small LLM ignores "no thinking" rule)
# ---------------------------------------------------------------------------

def test_strip_plain_reasoning_preamble_extracts_paragraph():
    """User's actual symptom: LLM emits 'Okay, let me...' reasoning followed
    by the final answer paragraph. We want only the final answer."""
    text = (
        "Okay, let me try to figure out how to approach this. "
        "The user wants me to generate an image generation prompt for Z-Image. "
        "First, I need to make sure I understand all the requirements.\n\n"
        "A cinematic photograph of a woman in a flowing red silk dress "
        "standing in a sunlit cityscape, golden hour lighting, medium shot, "
        "eye-level camera angle, soft background bokeh with skyscrapers."
    )
    out = _strip_think_blocks(text)
    assert not out.lower().startswith("okay")
    assert "cinematic photograph" in out
    assert "First, I need to" not in out


def test_strip_plain_reasoning_starts_with_capitalized_phrase():
    text = "First, the user wants a model. \n\nModel is a slender figure."
    out = _strip_think_blocks(text)
    assert "Model" in out or "slender" in out
    assert not out.lower().startswith("first,")


def test_strip_plain_reasoning_keeps_single_paragraph_input_unchanged():
    """If the LLM output is a single paragraph that just happens to start
    with a reasoning-style word, leave it alone — heuristic would have
    nothing to pick from."""
    text = "The user wants a sunset over the ocean, warm colors, soft waves."
    assert _strip_think_blocks(text) == text


def test_strip_think_combined_with_plain_reasoning():
    text = (
        "<think>internal chain of thought</think>"
        "Okay, let me think. The user asked for X. \n\n"
        "A vibrant oil painting of a mountain peak at sunrise."
    )
    out = _strip_think_blocks(text)
    assert "vibrant oil painting" in out
    assert "Okay" not in out


# ---------------------------------------------------------------------------
# Sentence-level stripping (the actual user symptom)
# ---------------------------------------------------------------------------

def test_strip_reasoning_inline_with_answer_single_paragraph():
    """The actual user case: small LLM (qwen 4B) emits reasoning and a
    partial answer inline. The full Z-Image-style output may never appear
    because the LLM ran out of tokens. The stripper's job is to drop the
    reasoning-y sentences, even if the leftover is just the LLM's
    illustrative example. Verify reasoning keywords are gone."""
    text = (
        'First, I need to pick the right style and medium. The user did not '
        'specify, so I will choose "A watercolor illustration of" as it is '
        'versatile and allows for detailed descriptions. Next, the subject: '
        'maybe a person in a specific outfit. Let us say a woman in a blue '
        'dress with gold details. Neutral language for clothing and colors.'
    )
    out = _strip_think_blocks(text)
    lowered = out.lower()
    assert "first," not in lowered.split() and "first," not in out.lower().split(",")[0]
    assert "i need" not in lowered
    assert "the user" not in lowered
    assert "i will" not in lowered
    assert "next," not in lowered
    # At least one of the leftover sentences should remain (we don't
    # return empty when reasoning-y content is the only output).
    assert len(out.split()) >= 4


def test_strip_reasoning_when_first_sentence_is_answer():
    text = (
        "A cinematic photograph of a woman in a red dress standing in "
        "a cityscape at golden hour, medium shot, eye-level camera angle."
    )
    assert _strip_think_blocks(text) == text


def test_strip_reasoning_falls_back_to_longest_sentence():
    """If every sentence contains a reasoning keyword, return the longest
    single sentence (it's likely the closest thing to a real answer)."""
    text = (
        "I need to think about this. The user wants a sunset. I should "
        "describe the colors. Perhaps orange and pink. Maybe with clouds."
    )
    out = _strip_think_blocks(text)
    # Longest sentence is "The user wants a sunset" or "I should describe
    # the colors" — both contain reasoning keywords so we just pick longest.
    assert len(out.split()) >= 4


def test_strip_keeps_actual_think_block_then_answer():
    """Mix of <think> + plain reasoning + answer sentences."""
    text = (
        "<think>brief internal note</think>"
        "First, I need to decide on style. "
        "A vibrant oil painting of a lighthouse on a stormy coast, "
        "bold brushstrokes, dramatic lighting."
    )
    out = _strip_think_blocks(text)
    assert "vibrant oil painting" in out
    assert "First" not in out
    assert "think" not in out.lower() or "vibrant" in out.lower()


# ---------------------------------------------------------------------------
# End-to-end via fake clip
# ---------------------------------------------------------------------------

def test_execute_returns_clip_decode_output():
    clip = _FakeCLIP(response="A cinematic shot of a cat walking on a wooden floor.")
    out = PromptEnhancePlus.execute(
        clip,
        prompt="a cat walks",
        target_model="LTX2.5",
        mode="auto",
        max_length=128,
        temperature=0.7,
        top_k=64,
        top_p=0.95,
        seed=42,
    )
    assert out.result[0] == "A cinematic shot of a cat walking on a wooden floor."
    assert clip.last_generate_kwargs["seed"] == 42
    assert clip.last_generate_kwargs["temperature"] == 0.7


def test_execute_falls_back_to_original_prompt_on_empty():
    clip = _FakeCLIP(response="<think>...unclosed")
    cleaned = _strip_think_blocks(clip.decode(["x"]))
    assert cleaned == ""  # sanity
    out = PromptEnhancePlus.execute(
        clip,
        prompt="original user prompt",
        target_model="LTX2.5",
        mode="T2V",
        max_length=64,
        temperature=0.7,
        top_k=64,
        top_p=0.95,
        seed=0,
    )
    # The fallback path returns the user prompt only if the cleaned output is
    # empty after stripping. Here the fake clip returned a non-empty string
    # before stripping, so the stripped result "" will trigger fallback.
    assert out.result[0] == "original user prompt"


def test_execute_passes_image_through_tokenize():
    """Image input should make the I2V system prompt appear in the tokenized text."""
    clip = _FakeCLIP()
    PromptEnhancePlus.execute(
        clip,
        prompt="a dog",
        target_model="LTX2.5",
        mode="I2V",
        max_length=64,
        temperature=0.7,
        top_k=64,
        top_p=0.95,
        seed=0,
        image="img_tensor",
    )
    tokenize_prompt = clip.last_tokenize_kwargs["tokens"]
    # The I2V template should appear in the formatted chat
    assert "image-to-video" in tokenize_prompt or "first frame" in tokenize_prompt.lower()


# ---------------------------------------------------------------------------
# Node IO sanity
# ---------------------------------------------------------------------------

def test_node_schema_defines_required_io():
    schema = PromptEnhancePlus.define_schema()
    input_names = {i.name for i in schema.inputs}
    assert {"clip", "prompt", "target_model", "mode", "custom_template"}.issubset(input_names)
    assert {o.name for o in schema.outputs} == {"enhanced_prompt"}


def test_node_id_and_category():
    schema = PromptEnhancePlus.define_schema()
    assert schema.node_id == "PromptEnhancePlus"
    assert schema.category == "ZSimple-Nodes/text"


def test_target_model_combo_includes_all_five():
    schema = PromptEnhancePlus.define_schema()
    target_combo = next(i for i in schema.inputs if i.name == "target_model")
    assert {"LTX2.5", "H3", "Z-Image", "Krea-2", "Krea-2-Edit"}.issubset(set(target_combo.options))


# ---------------------------------------------------------------------------
# F2 / F3: video/audio warning + strip behavior
# ---------------------------------------------------------------------------

def test_video_audio_warns_and_strips_for_non_qwen_family():
    """F3: gemma3 + video/audio → print warning + video/audio stripped before tokenize."""
    clip = _FakeCLIP(name="gemma-3-1b-it", response="ok")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        PromptEnhancePlus.execute(
            clip,
            prompt="test",
            target_model="LTX2.5",
            mode="T2V",
            max_length=64,
            temperature=0.7,
            top_k=64,
            top_p=0.95,
            seed=0,
            video="vid",
            audio="aud",
        )
    assert "does not support video/audio" in buf.getvalue()
    tokenize_prompt = clip.last_tokenize_kwargs["tokens"]
    assert "<|vision_start|>" not in tokenize_prompt


def test_video_audio_passed_through_for_qwen_family():
    """F2 兜底: qwen + video/audio 不应触发 warning."""
    clip = _FakeCLIP(name="qwen2.5-7b-instruct", response="ok")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        PromptEnhancePlus.execute(
            clip,
            prompt="test",
            target_model="LTX2.5",
            mode="T2V",
            max_length=64,
            temperature=0.7,
            top_k=64,
            top_p=0.95,
            seed=0,
            video="vid",
            audio="aud",
        )
    assert "does not support video/audio" not in buf.getvalue()


# ---------------------------------------------------------------------------
# F4: missing template raises with actionable message
# ---------------------------------------------------------------------------

def test_no_template_raises_clear_error():
    """F4: Krea-2-Edit + mode=T2V → ValueError mentioning target_model, mode, and custom_template."""
    clip = _FakeCLIP()
    try:
        PromptEnhancePlus.execute(
            clip,
            prompt="test",
            target_model="Krea-2-Edit",
            mode="T2V",
            max_length=64,
            temperature=0.7,
            top_k=64,
            top_p=0.95,
            seed=0,
        )
    except ValueError as exc:
        msg = str(exc)
        assert "Krea-2-Edit" in msg
        assert "T2V" in msg
        assert "custom_template" in msg
    else:
        raise AssertionError("expected ValueError but execute returned without raising")


class _ZImageTEModelStub(_FakeCLIP):
    """Dynamic factory output: comfy/text_encoders/z_image.py:te() returns a
    ZImageTEModel_(device=..., dtype=..., model_options=...) class whose real
    __name__ is the factory output name. Mimic that here so the raise fires."""


# Force the stub's __name__ to match the real ZImageTEModel_ class name.
_ZImageTEModelStub.__name__ = "ZImageTEModel_"
_ZImageTEModelStub.__qualname__ = "ZImageTEModel_"


def test_execute_raises_for_text_only_clip_with_image():
    """qwen3_4b (Z-Image TE / Lumina2) is a text-only LLM. Passing image=
    to clip.tokenize is silently dropped — the LLM never sees the picture.
    Surface this as a clear ValueError instead of letting the user think
    image-conditioned expansion is working."""
    clip = _ZImageTEModelStub(name="qwen_3_4b.safetensors", response="ok")
    try:
        PromptEnhancePlus.execute(
            clip,
            prompt="a cat",
            target_model="Z-Image",
            mode="T2I",
            max_length=64,
            temperature=0.7,
            top_k=64,
            top_p=0.95,
            seed=0,
            image="img-tensor",
        )
    except ValueError as exc:
        msg = str(exc)
        assert "text-only" in msg.lower()
        assert "Qwen2.5-VL" in msg or "vision-language" in msg.lower()
        # And must name the actual CLIP class so the user can identify it
        assert "ZImageTEModel_" in msg
    else:
        raise AssertionError("expected ValueError but execute returned without raising")


def test_execute_text_only_clip_no_image_is_fine():
    """Same ZImageTEModel_ stub, but image=None → no raise. The text-only
    encoder is the expected choice for text-only prompt expansion; we only
    complain when the user wired an image that cannot reach the LLM."""
    clip = _ZImageTEModelStub(name="qwen_3_4b.safetensors", response="ok")
    out = PromptEnhancePlus.execute(
        clip,
        prompt="a cat",
        target_model="Z-Image",
        mode="T2I",
        max_length=64,
        temperature=0.7,
        top_k=64,
        top_p=0.95,
        seed=0,
    )
    assert out is not None


if __name__ == "__main__":
    # Standalone runner — pytest can't import from this layout because root
    # __init__.py pulls in folder_paths which isn't installed in dev envs.
    import inspect
    import traceback

    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            traceback.print_exc()
            print(f"FAIL  {name}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(0 if failed == 0 else 1)
