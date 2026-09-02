"""Pure-function tests for ZImageTurboProgressive helpers."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.zimage_turbo_progressive import (
    _stage_split,
    _slice_sigmas_by_steps,
    _upscale_latent,
    ZImageTurboProgressive,
)


def test_stage_split_default():
    s1, s2, s3 = _stage_split(8)
    assert s1 == 2
    assert s2 == 4
    assert s3 == 2


def test_stage_split_min_steps():
    s1, s2, s3 = _stage_split(3)
    assert s1 >= 1 and s2 >= 1 and s3 >= 1


def test_slice_sigmas_seamless_handoff():
    import torch
    full = torch.linspace(1.0, 0.0, 9)
    sig1 = _slice_sigmas_by_steps(full, 0, 2)
    sig2 = _slice_sigmas_by_steps(full, 2, 4)
    sig3 = _slice_sigmas_by_steps(full, 6, 2)
    assert sig1[-1].item() == sig2[0].item()
    assert sig2[-1].item() == sig3[0].item()


def test_upscale_identity():
    import torch
    latent = {"samples": torch.zeros(1, 16, 32, 32)}
    out = _upscale_latent(latent, factor=1.0)
    assert out["samples"].shape == (1, 16, 32, 32)


def test_upscale_factor_2():
    import torch
    latent = {"samples": torch.zeros(1, 16, 32, 32)}
    out = _upscale_latent(latent, factor=2.0)
    _, _, h, w = out["samples"].shape
    assert h == 64 and w == 64


def test_define_schema_inputs_count():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.inputs) == 13


def test_define_schema_field_names():
    schema = ZImageTurboProgressive.define_schema()
    names = set()
    for inp in schema.inputs:
        name = getattr(inp, "name", None) or (inp.get("name") if isinstance(inp, dict) else None)
        if name:
            names.add(name)
    expected = {
        "latent_input", "model", "positive", "positive_stg2", "positive_stg3",
        "cfg", "seed", "shift", "add_noise", "steps",
        "upscale_factor", "sampler", "scheduler",
    }
    missing = expected - names
    assert not missing, f"Missing IO: {missing}"