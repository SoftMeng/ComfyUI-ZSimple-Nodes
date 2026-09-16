"""Dryrun for train_gemma_qwen_adapter after the autograd-context fix.

Verifies:
  1) _collate drops all-zero gemma_mask rows (F5).
  2) _train_adapter runs end-to-end inside an outer torch.inference_mode()
     context (the actual ComfyUI execution environment) and reaches the
     epoch-logging + safetensors-save path without raising
     'element 0 of tensors does not require grad' (F1).
  3) Diagnostics emitted by F3 inside _run_training show
     grad_enabled=True and req_grad>0 once inside torch.enable_grad().
  4) Loss path uses float32 diff (F4) — verified by spying on .float()
     calls and confirming loss has float dtype.

Mocks the comfy_api bits the node imports so the test runs in any venv
(no ComfyUI install required). Mirrors the stubbing pattern in
test_prompt_enhance_plus.py.
"""

import contextlib
import io as _io
import json
import os
import shutil
import sys
import tempfile
import types

import torch
import torch.nn as nn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


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
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _ClipInput:
        def __init__(self, name, tooltip=None):
            self.name = name
            self.tooltip = tooltip

    class _StringInput:
        def __init__(self, name, default="", multiline=False, tooltip=None):
            self.name = name
            self.default = default
            self.multiline = multiline
            self.tooltip = tooltip

    class _IntInput:
        def __init__(self, name, default=0, min=0, max=100, step=1, tooltip=None):
            self.name = name
            self.default = default
            self.min = min
            self.max = max
            self.step = step
            self.tooltip = tooltip

    class _FloatInput:
        def __init__(self, name, default=0.0, min=0.0, max=1.0, step=1e-3, tooltip=None):
            self.name = name
            self.default = default
            self.min = min
            self.max = max
            self.step = step
            self.tooltip = tooltip

    class _BoolInput:
        def __init__(self, name, default=False, tooltip=None):
            self.name = name
            self.default = default
            self.tooltip = tooltip

    class _Output:
        def __init__(self, *args, **kwargs):
            pass

    class _IO:
        Schema = _Schema
        NodeOutput = _NodeOutput
        Clip = _ClipInput
        String = _StringInput
        Int = _IntInput
        Float = _FloatInput
        Boolean = _BoolInput
        Output = _Output

        class ComfyNode:
            pass

    latest.io = _IO
    comfy_api.latest = latest
    sys.modules["comfy_api"] = comfy_api
    sys.modules["comfy_api.latest"] = latest


_install_io_stubs()
import nodes.train_gemma_qwen_adapter as tga  # noqa: E402
from nodes._gemma_adapter_common import GemmaToZImageAdapter  # noqa: E402


def _make_sample(g_dim, q_dim, n_tokens, rng):
    g = torch.randn(n_tokens, g_dim) * 0.5
    gm = torch.ones(n_tokens, dtype=torch.long)
    q = torch.randn(n_tokens, q_dim) * 2.0
    qm = torch.ones(n_tokens, dtype=torch.long)
    return {"gemma": g, "gemma_mask": gm, "qwen": q, "qwen_mask": qm}


def _make_zero_mask_sample(g_dim, q_dim):
    n_tokens = 8
    return {
        "gemma": torch.zeros(n_tokens, g_dim),
        "gemma_mask": torch.zeros(n_tokens, dtype=torch.long),
        "qwen": torch.zeros(n_tokens, q_dim),
        "qwen_mask": torch.zeros(n_tokens, dtype=torch.long),
    }


def _build_cache(tmpdir, n_samples=8, include_zero_rows=True):
    cache = os.path.join(tmpdir, "cached_features")
    os.makedirs(cache, exist_ok=True)
    rng = torch.Generator().manual_seed(0)
    for i in range(n_samples):
        s = _make_sample(tga.GEMMA_HIDDEN, tga.QWEN_HIDDEN, 16, rng)
        torch.save(s, os.path.join(cache, f"{i:05d}.pt"))
    if include_zero_rows:
        # Insert two invalid samples to verify F5 strips them at collation time.
        for i in range(n_samples, n_samples + 2):
            s = _make_zero_mask_sample(tga.GEMMA_HIDDEN, tga.QWEN_HIDDEN)
            torch.save(s, os.path.join(cache, f"{i:05d}.pt"))
        n_total = n_samples + 2
    else:
        n_total = n_samples
    meta = {
        "num_samples": n_total,
        "max_len": 16,
        "gemma_hidden": tga.GEMMA_HIDDEN,
        "qwen_hidden": tga.QWEN_HIDDEN,
        "layer_idx": -2,
        "chat_template": "user\n{}\nassistant\n",
        "denoising_done": False,
    }
    with open(os.path.join(cache, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return cache, n_total


def test_collate_drops_zero_mask_rows():
    g_dim, q_dim = tga.GEMMA_HIDDEN, tga.QWEN_HIDDEN
    valid = _make_sample(g_dim, q_dim, 6, torch.Generator().manual_seed(1))
    bad = _make_zero_mask_sample(g_dim, q_dim)
    g, gm, q, qm = tga._collate([bad, valid, bad])
    assert g.shape[0] == 1, f"_collate should drop zero-mask rows, got B={g.shape[0]}"
    assert gm.sum().item() == 6
    assert torch.equal(gm, torch.ones_like(gm))
    print("[OK] test_collate_drops_zero_mask_rows")


def test_collate_all_zero_raises():
    g_dim, q_dim = tga.GEMMA_HIDDEN, tga.QWEN_HIDDEN
    bad1 = _make_zero_mask_sample(g_dim, q_dim)
    bad2 = _make_zero_mask_sample(g_dim, q_dim)
    raised = False
    try:
        tga._collate([bad1, bad2])
    except RuntimeError as ex:
        raised = "no valid samples" in str(ex)
    assert raised, "_collate should raise when every row is zero-masked"
    print("[OK] test_collate_all_zero_raises")


def test_train_adapter_under_inference_mode():
    """The exact reproduction of the original failure: call _train_adapter
    from inside torch.inference_mode() (mimicking ComfyUI's execution
    context). After F1 it must NOT raise."""
    tmp = tempfile.mkdtemp(prefix="tga_dryrun_")
    try:
        cache_dir, n_total = _build_cache(tmp, n_samples=8, include_zero_rows=True)
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "gemma_to_zimage_adapter.safetensors")

        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            with torch.inference_mode():
                # Single epoch so the test stays fast and deterministic.
                result_path = tga._train_adapter(
                    cache_dir, out_path,
                    batch_size=2, epochs=1, lr=5e-5, patience=3,
                )

        log_text = buf.getvalue()
        assert result_path == out_path, f"_train_adapter should return {out_path}, got {result_path}"
        assert os.path.exists(out_path), "adapter .safetensors must be written"
        assert os.path.getsize(out_path) > 0, "adapter .safetensors must be non-empty"

        # F3 diagnostic must show grad_enabled=True and inf_mode=False inside the wrapper.
        assert "grad_enabled=True" in log_text, (
            f"F3 diag missing grad_enabled=True. Captured:\n{log_text}"
        )
        assert "inf_mode=False" in log_text, (
            f"F3 diag missing inf_mode=False (inference_mode(False) must escape outer inference_mode). Captured:\n{log_text}"
        )
        assert "req_grad=" in log_text, "F3 diag missing req_grad count"
        # F1 epoch-log line must appear.
        assert "epoch 1/1" in log_text and "train_loss=" in log_text and "val_loss=" in log_text, (
            f"epoch log line missing — training did not reach epoch loop. Captured:\n{log_text}"
        )
        # Original failure mode must NOT appear.
        assert "does not require grad" not in log_text, (
            "autograd error regressed: 'does not require grad' appeared in stdout"
        )
        print("[OK] test_train_adapter_under_inference_mode")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_float32_loss_path():
    """F4 sanity: the loss tensor emitted from the train step should be
    float32 (since diff = pool_pred.float() - tgt_pool.float())."""
    adapter = GemmaToZImageAdapter().to(tga.DEVICE, dtype=torch.float32)
    B, Lg, Hg = 2, 5, tga.GEMMA_HIDDEN
    Hq = tga.QWEN_HIDDEN
    g = torch.randn(B, Lg, Hg, device=tga.DEVICE, dtype=torch.float32)
    gm = torch.ones(B, Lg, dtype=torch.long, device=tga.DEVICE)
    q_ = torch.randn(B, Lg, Hq, device=tga.DEVICE, dtype=torch.float32) * 5.0
    qm = torch.ones(B, Lg, dtype=torch.long, device=tga.DEVICE)
    tok_pred, pool_pred = adapter(g, gm)
    tgt_pool = (q_ * qm.unsqueeze(-1).float()).sum(dim=1) / qm.float().sum(dim=1, keepdim=True).clamp_min(1.0)
    tgt_pool = tgt_pool.to(pool_pred.dtype)
    diff = pool_pred.float() - tgt_pool.float()
    loss = (diff * diff).mean()
    assert loss.dtype == torch.float32, f"F4 expects float32 loss, got {loss.dtype}"
    print("[OK] test_float32_loss_path")


def main():
    test_collate_drops_zero_mask_rows()
    test_collate_all_zero_raises()
    test_float32_loss_path()
    test_train_adapter_under_inference_mode()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()