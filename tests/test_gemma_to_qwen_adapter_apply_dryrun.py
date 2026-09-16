"""Dryrun for GemmaToQwenAdapterApply.

Verifies:
  1) Forward shape: GemmaToZImageAdapter outputs tokens [B,77,2560], pooled [B,2560].
  2) Full execute under CPU: writes a random adapter.safetensors, constructs
     a fake Gemma4 CONDITIONING, calls execute(), checks output shape & dtype.
  3) dim collapse: 4D [B,layer,N,H] and 2D [N,H] inputs are tolerated.
  4) Error paths: wrong hidden_size -> RuntimeError; missing path -> FileNotFoundError.
  5) Metadata WARNING when denoising_done != "True".

Mocks comfy_api so the test runs in any venv (no ComfyUI install required).
Mirrors the stubbing pattern in test_train_gemma_qwen_adapter_dryrun.py.
"""

import contextlib
import io as _io
import os
import sys
import tempfile
import types

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _install_io_stubs():
    comfy_api = types.ModuleType("comfy_api")
    latest = types.ModuleType("comfy_api.latest")

    def _make_type(name):
        cls = type(name, (), {})
        @classmethod
        def Input(cls_inner, *a, **kw):
            return ("input", name, a, kw)
        @classmethod
        def Output(cls_inner, *a, **kw):
            return ("output", name, a, kw)
        cls.Input = Input
        cls.Output = Output
        return cls

    class IO:
        class ComfyNode: pass
        Schema = type("S", (object,), {"__init__": lambda self, **kw: setattr(self, "__dict__", kw)})

        class NodeOutput:
            def __init__(self, *a, **kw):
                self.args = a
                self.kwargs = kw
            def __iter__(self):
                return iter(self.args)
            def __getitem__(self, i):
                return self.args[i]

        Conditioning = _make_type("Conditioning")
        Clip = _make_type("Clip")
        String = _make_type("String")
        Int = _make_type("Int")
        Float = _make_type("Float")
        Boolean = _make_type("Boolean")
        Output = _make_type("Output")
        Mask = _make_type("Mask")
        Model = _make_type("Model")
        Vae = _make_type("Vae")
        Latents = _make_type("Latents")
        Image = _make_type("Image")
        Combo = _make_type("Combo")

    latest.io = IO
    comfy_api.latest = latest
    sys.modules["comfy_api"] = comfy_api
    sys.modules["comfy_api.latest"] = latest


_install_io_stubs()
from nodes._gemma_adapter_common import (  # noqa: E402
    DEFAULT_DTYPE,
    GEMMA_HIDDEN,
    NUM_LATENTS,
    QWEN_HIDDEN,
    GemmaToZImageAdapter,
)
from nodes.gemma_to_qwen_adapter_apply import GemmaToQwenAdapterApply  # noqa: E402
from safetensors.torch import save_file  # noqa: E402


def _make_adapter_state_dict():
    m = GemmaToZImageAdapter().to(DEFAULT_DTYPE)
    return {k: v.detach().clone() for k, v in m.state_dict().items()}


def _write_fake_adapter(tmpdir, denoising_done="True", phase="text-align-mse-warmup"):
    path = os.path.join(tmpdir, "gemma_to_zimage_adapter.safetensors")
    state = _make_adapter_state_dict()
    save_file(
        state,
        path,
        metadata={
            "format": "comfyui-text-encoder-adapter",
            "in_dim": str(GEMMA_HIDDEN),
            "out_dim": str(QWEN_HIDDEN),
            "num_latents": str(NUM_LATENTS),
            "source_te": "gemma4_e2b_it_int8_convrot",
            "target_te": "qwen_3_4b",
            "phase": phase,
            "denoising_done": denoising_done,
        },
    )
    return path


def _make_cond_pair(B=1, N=24, hidden=GEMMA_HIDDEN, dtype=torch.bfloat16, dim=3, layer=1):
    if dim == 2:
        cond = torch.randn(N, hidden, dtype=dtype)
    elif dim == 3:
        cond = torch.randn(B, N, hidden, dtype=dtype)
    elif dim == 4:
        cond = torch.randn(B, layer, N, hidden, dtype=dtype)
    else:
        raise ValueError(f"unsupported dim={dim}")
    pooled = {"pooled_output": torch.randn(B, QWEN_HIDDEN, dtype=dtype)}
    return [cond, pooled]


def test_adapter_forward_shape():
    adapter = GemmaToZImageAdapter().to(DEFAULT_DTYPE)
    B, N = 2, 30
    g = torch.randn(B, N, GEMMA_HIDDEN, dtype=DEFAULT_DTYPE)
    gm = torch.ones(B, N, dtype=torch.long)
    tok, pooled = adapter(g, gm)
    assert tok.shape == (B, NUM_LATENTS, QWEN_HIDDEN), f"tokens {tok.shape}"
    assert pooled.shape == (B, QWEN_HIDDEN), f"pooled {pooled.shape}"
    print("[OK] test_adapter_forward_shape")


def test_execute_basic():
    tmp = tempfile.mkdtemp(prefix="gqa_dryrun_")
    try:
        path = _write_fake_adapter(tmp, denoising_done="True")
        cond_pair = _make_cond_pair(B=2, N=24)
        out = GemmaToQwenAdapterApply.execute([cond_pair], path)
        out_list = list(out)[0]
        assert isinstance(out_list, list) and len(out_list) >= 1
        cond_t, pooled_d = out_list[0]
        assert cond_t.shape == (2, NUM_LATENTS, QWEN_HIDDEN), f"cond {cond_t.shape}"
        assert pooled_d["pooled_output"].shape == (2, QWEN_HIDDEN)
        assert cond_t.dtype == torch.bfloat16
        assert pooled_d["pooled_output"].dtype == torch.bfloat16
        print("[OK] test_execute_basic")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_dim_collapse_4d():
    tmp = tempfile.mkdtemp(prefix="gqa_4d_")
    try:
        path = _write_fake_adapter(tmp)
        cond_pair = _make_cond_pair(B=2, N=24, dim=4, layer=3)
        out_list = list(GemmaToQwenAdapterApply.execute([cond_pair], path))[0]
        cond_t, _ = out_list[0]
        assert cond_t.shape == (2, NUM_LATENTS, QWEN_HIDDEN)
        print("[OK] test_dim_collapse_4d")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_dim_collapse_2d():
    tmp = tempfile.mkdtemp(prefix="gqa_2d_")
    try:
        path = _write_fake_adapter(tmp)
        cond_pair = _make_cond_pair(B=1, N=18, dim=2)
        out_list = list(GemmaToQwenAdapterApply.execute([cond_pair], path))[0]
        cond_t, _ = out_list[0]
        assert cond_t.shape == (1, NUM_LATENTS, QWEN_HIDDEN)
        print("[OK] test_dim_collapse_2d")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_wrong_hidden_size_raises():
    tmp = tempfile.mkdtemp(prefix="gqa_err_")
    try:
        path = _write_fake_adapter(tmp)
        cond_pair = _make_cond_pair(B=1, N=10, hidden=2560)
        raised = False
        try:
            GemmaToQwenAdapterApply.execute([cond_pair], path)
        except RuntimeError as ex:
            raised = "expected hidden_size" in str(ex) or "wrong CLIP" in str(ex)
        assert raised, "wrong hidden_size should raise RuntimeError"
        print("[OK] test_wrong_hidden_size_raises")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_adapter_raises():
    cond_pair = _make_cond_pair(B=1, N=10)
    raised = False
    try:
        GemmaToQwenAdapterApply.execute([cond_pair], "/nonexistent/path/adapter.safetensors")
    except FileNotFoundError:
        raised = True
    assert raised, "missing adapter_path should raise FileNotFoundError"
    print("[OK] test_missing_adapter_raises")


def test_denoising_warning_logged():
    tmp = tempfile.mkdtemp(prefix="gqa_warn_")
    try:
        path = _write_fake_adapter(tmp, denoising_done="False", phase="text-align-mse-warmup")
        cond_pair = _make_cond_pair(B=1, N=10)
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            list(GemmaToQwenAdapterApply.execute([cond_pair], path))
        log = buf.getvalue()
        assert "WARNING" in log, f"expected WARNING, got: {log!r}"
        assert "denoising-loss stage" in log, f"expected stage hint, got: {log!r}"
        print("[OK] test_denoising_warning_logged")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_adapter_forward_shape()
    test_execute_basic()
    test_dim_collapse_4d()
    test_dim_collapse_2d()
    test_wrong_hidden_size_raises()
    test_missing_adapter_raises()
    test_denoising_warning_logged()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()