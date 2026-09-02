"""Pure-function tests for ZImageTurboProgressive helpers."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.zimage_turbo_progressive import (
    _upscale_latent,
    _stage_denoise,
    _coerce_latent,
    SIGMA_PRESETS,
    ZImageTurboProgressive,
)


def test_preset_keys():
    assert set(SIGMA_PRESETS.keys()) == {"alpha_8", "bravo_8"}


def test_preset_stage_counts():
    for name, (s1, s2, s3) in SIGMA_PRESETS.items():
        assert len(s1) >= 1
        assert len(s2) >= 1
        assert len(s3) >= 1


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


def test_upscale_factor_15():
    import torch
    latent = {"samples": torch.zeros(1, 16, 32, 32)}
    out = _upscale_latent(latent, factor=1.5)
    _, _, h, w = out["samples"].shape
    assert h == 48 and w == 48


def test_coerce_latent_dict():
    latent = {"samples": object()}
    assert _coerce_latent(latent) is latent


def test_coerce_latent_tensor():
    import torch
    t = torch.zeros(1, 4, 8, 8)
    out = _coerce_latent(t)
    assert isinstance(out, dict)
    assert out["samples"] is t


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
        "cfg", "seed", "shift", "add_noise", "sigma_preset",
        "upscale_factor", "sampler",
    }
    missing = expected - names
    assert not missing, f"Missing IO: {missing}"