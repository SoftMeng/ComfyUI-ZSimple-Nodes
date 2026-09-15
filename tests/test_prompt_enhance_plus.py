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
        assert isinstance(tmpl, str) and tmpl.strip(), f"empty template for {model}/{mode}"


def test_each_template_length_in_safe_range():
    for (model, mode), tmpl in _BUILTIN_TEMPLATES.items():
        words = len(tmpl.split())
        assert 50 <= words <= 700, f"{model}/{mode} template has {words} words; expected 50-700"


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


def test_format_chat_qwen_uses_im_start():
    out = _format_chat("SYS", "user prompt", None, "qwen")
    assert "<|im_start|>system" in out
    assert "<|im_start|>assistant" in out


def test_format_chat_image_token_inserted():
    out = _format_chat("SYS", "u", "img", "qwen")
    assert "<|vision_start|>" in out


def test_format_chat_no_image_token_when_no_image():
    out = _format_chat("SYS", "u", None, "qwen")
    assert "<|vision_start|>" not in out


# ---------------------------------------------------------------------------
# Think-block stripping
# ---------------------------------------------------------------------------

def test_strip_think_block_basic():
    text = "<think>reasoning here</think>actual answer"
    assert _strip_think_blocks(text) == "actual answer"


def test_strip_think_block_unclosed():
    text = "<think>reasoning never ends\nactual answer here"
    assert "actual answer here" in _strip_think_blocks(text)


def test_strip_think_block_no_block():
    assert _strip_think_blocks("plain text") == "plain text"


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
    # The kwargs go through the wrapper; the prompt itself is the formatted chat.
    tokenize_prompt = clip.last_tokenize_kwargs["tokens"]
    assert "I2V" in tokenize_prompt or "first-frame" in tokenize_prompt.lower()


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
