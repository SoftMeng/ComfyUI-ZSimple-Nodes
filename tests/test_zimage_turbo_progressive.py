"""Pure-function tests for ZImageTurboProgressive helpers."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.zimage_turbo_progressive import (
    _stage_split,
    _scramble_counts,
    adjust_latent_size,
    SPECTRAL_TILT_PRESETS,
    CREATIVITY_MODES,
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


def test_scramble_counts_even():
    assert _scramble_counts(2) == (2, -1, 2, -1)


def test_scramble_counts_mod10():
    assert _scramble_counts(10) == (-2, -2, -2, -2)


def test_scramble_counts_odd():
    assert _scramble_counts(3) == (1, 0, 1, 0)


def test_adjust_latent_size_identity():
    import torch
    samples = torch.zeros(1, 4, 16, 32)
    latent = {"samples": samples}
    out = adjust_latent_size(latent, factor=1.0)
    assert out["samples"].shape == samples.shape


def test_adjust_latent_size_upscales():
    import torch
    latent = {"samples": torch.zeros(1, 4, 16, 16)}
    out = adjust_latent_size(latent, factor=2.0)
    _, _, h, w = out["samples"].shape
    assert h == 32 and w == 32


def test_adjust_latent_size_accepts_tensor():
    import torch
    t = torch.zeros(1, 4, 16, 16)
    out = adjust_latent_size(t, factor=2.0)
    assert isinstance(out, dict)
    assert out["samples"].shape == (1, 4, 32, 32)


def test_define_schema_inputs_count():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.inputs) == 23


def test_define_schema_field_names():
    schema = ZImageTurboProgressive.define_schema()
    names = set()
    for inp in schema.inputs:
        name = getattr(inp, "name", None) or (inp.get("name") if isinstance(inp, dict) else None)
        if name:
            names.add(name)
    expected = {
        "latent_input", "model", "positive", "positive_stg2", "positive_stg3",
        "cfg", "seed", "shift", "add_noise", "return_leftover_noise",
        "steps", "start_step", "end_step", "creativity_mode", "upscale_factor",
        "detailed_refiner", "spectral_tilt",
        "stage1_sampler", "stage1_scheduler",
        "stage2_sampler", "stage2_scheduler",
        "stage3_sampler", "stage3_scheduler",
    }
    missing = expected - names
    assert not missing, f"Missing IO: {missing}"


def test_spectral_tilt_presets_5():
    assert len(SPECTRAL_TILT_PRESETS) == 5
    for preset in SPECTRAL_TILT_PRESETS:
        assert len(preset) == 4


def test_creativity_modes_5():
    assert len(CREATIVITY_MODES) == 5
    assert "off" in CREATIVITY_MODES
    assert "scrambled" in CREATIVITY_MODES