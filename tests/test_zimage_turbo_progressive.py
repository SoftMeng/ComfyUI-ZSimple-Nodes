"""Pure-function tests for ZImageTurboProgressive helpers."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.zimage_turbo_progressive import (
    _stage_split,
    _scramble_counts,
    _get_sigma_preset,
    adjust_latent_size,
    SIGMA_PRESETS_BY_NAME,
    SPECTRAL_TILT_PRESETS,
    ZImageTurboProgressive,
)


def test_stage_split_default():
    s1, s2, s3 = _stage_split(8)
    assert s1 == 2
    assert s2 == 4
    assert s3 == 2


def test_get_sigma_preset_steps_8_is_bravo():
    s1, s2, s3 = _get_sigma_preset(8)
    assert s1 is not None and len(s1) >= 2
    assert s2 is not None and len(s2) >= 2
    assert s3 is not None and len(s3) >= 2
    assert SIGMA_PRESETS_BY_NAME["bravo_8"] == (s1, s2, s3)


def test_get_sigma_preset_steps_5_is_alpha():
    s1, s2, s3 = _get_sigma_preset(5)
    assert s1 is not None and len(s1) == 3
    assert s2 is not None and len(s2) == 2
    assert SIGMA_PRESETS_BY_NAME["alpha_5"] == (s1, s2, s3)


def test_get_sigma_preset_clamped():
    s1, s2, s3 = _get_sigma_preset(2)
    assert SIGMA_PRESETS_BY_NAME["alpha_3"] == (s1, s2, s3)
    s1, s2, s3 = _get_sigma_preset(20)
    assert s1 is not None
    assert SIGMA_PRESETS_BY_NAME["bravo_8"] == (s1, s2, s3)


def test_scramble_counts_even():
    assert _scramble_counts(2) == (2, -1, 2, -1)


def test_scramble_counts_mod10():
    assert _scramble_counts(10) == (-2, -2, -2, -2)


def test_adjust_latent_size_identity():
    import torch
    samples = torch.zeros(1, 4, 16, 32)
    out = adjust_latent_size({"samples": samples}, factor=1.0)
    assert out["samples"].shape == samples.shape


def test_adjust_latent_size_upscales():
    import torch
    out = adjust_latent_size({"samples": torch.zeros(1, 4, 16, 16)}, factor=2.0)
    _, _, h, w = out["samples"].shape
    assert h == 32 and w == 32


def test_adjust_latent_size_accepts_tensor():
    import torch
    out = adjust_latent_size(torch.zeros(1, 4, 16, 16), factor=2.0)
    assert isinstance(out, dict) and out["samples"].shape == (1, 4, 32, 32)


def test_define_schema_inputs_count():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.inputs) == 23


def test_define_schema_field_names():
    schema = ZImageTurboProgressive.define_schema()
    names = set()
    for inp in schema.inputs:
        name = getattr(inp, "name", None) or (inp.get("name") if isinstance(inp, dict) else None)
        if name:
            names.add(name) if False else names.add(name)
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


def test_creativity_mode_is_boolean():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "creativity_mode")
    assert getattr(field, "default", None) in (True, False)