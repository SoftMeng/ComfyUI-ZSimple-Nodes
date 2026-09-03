"""Pure-function tests for ZImageTurboProgressive helpers."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.zimage_turbo_progressive import (
    _scramble_counts,
    _get_sigma_preset,
    _generate_noise,
    _noise_inverse,
    _slice_sigmas_at_entry,
    _LATENT_SCALING,
    adjust_latent_size,
    _SIGMA_PRESETS_BY_NAME,
    ZImageTurboProgressive,
)


def test_get_sigma_preset_steps_8_is_bravo():
    s1, s2, s3 = _get_sigma_preset(8)
    assert s1 is not None and len(s1) >= 2
    assert s2 is not None and len(s2) >= 2
    assert s3 is not None and len(s3) >= 2
    assert _SIGMA_PRESETS_BY_NAME["bravo_8"] == (s1, s2, s3)


def test_get_sigma_preset_steps_5_is_alpha():
    s1, s2, s3 = _get_sigma_preset(5)
    assert s1 is not None and len(s1) == 3
    assert s2 is not None and len(s2) == 3
    assert s3 is not None and len(s3) == 2
    assert _SIGMA_PRESETS_BY_NAME["alpha_5"] == (s1, s2, s3)


def test_bravo_8_sigmas2_ends_at_zero():
    s1, s2, s3 = _SIGMA_PRESETS_BY_NAME["bravo_8"]
    assert s2[-1] == 0.0, f"bravo_8 sigmas2 must end at 0 (full denoise), got {s2[-1]}"
    assert s3[-1] == 0.0


def test_get_sigma_preset_steps_over_8_falls_back_to_bravo():
    s1, s2, s3 = _get_sigma_preset(20)
    assert _SIGMA_PRESETS_BY_NAME["bravo_8"] == (s1, s2, s3)


def test_get_sigma_preset_clamps_below_3_to_alpha_3():
    s1, s2, s3 = _get_sigma_preset(2)
    assert _SIGMA_PRESETS_BY_NAME["alpha_3"] == (s1, s2, s3)


def test_latent_scaling_three_modes():
    assert set(_LATENT_SCALING.keys()) == {"fast", "quality", "none"}
    assert _LATENT_SCALING["none"] == (1.0, 1.0, 1.0)
    assert _LATENT_SCALING["fast"] == (0.25, 0.50, 1.00)
    assert _LATENT_SCALING["quality"] == (0.50, 0.75, 1.00)


def test_latent_scaling_stage3_always_one():
    for name, scales in _LATENT_SCALING.items():
        assert scales[2] == 1.0, f"{name} stage3 must = input size (1.0), got {scales[2]}"


def test_slice_sigmas_at_entry_below_threshold():
    import torch
    sigmas = torch.tensor([1.0, 0.8, 0.5, 0.2, 0.0])
    tail = _slice_sigmas_at_entry(sigmas, enter_sigma=0.5)
    assert torch.allclose(tail, torch.tensor([0.5, 0.2, 0.0]))


def test_slice_sigmas_at_entry_no_match_returns_full():
    import torch
    sigmas = torch.tensor([1.0, 0.8, 0.5])
    tail = _slice_sigmas_at_entry(sigmas, enter_sigma=0.01)
    assert torch.allclose(tail, sigmas)


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


def test_adjust_latent_size_target_size_forces_resize():
    import torch
    out = adjust_latent_size(
        {"samples": torch.zeros(1, 4, 32, 32)},
        factor=1.0, target_size=(16, 16),
    )
    assert out["samples"].shape == (1, 4, 16, 16)


def test_define_schema_inputs_count():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.inputs) == 16


def test_define_schema_field_names():
    schema = ZImageTurboProgressive.define_schema()
    names = set()
    for inp in schema.inputs:
        name = getattr(inp, "name", None) or (inp.get("name") if isinstance(inp, dict) else None)
        if name:
            names.add(name)
    expected = {
        "latent_input", "model", "positive",
        "cfg", "seed",
        "add_noise", "return_leftover_noise",
        "steps", "creativity_mode", "initial_bias",
        "latent_scaling", "intensity", "noise_inversion",
        "stage1_sampler", "stage2_sampler", "stage3_sampler",
    }
    missing = expected - names
    extra = names - expected
    assert not missing, f"Missing IO: {missing}"
    assert not extra, f"Unexpected IO: {extra}"


def test_creativity_mode_is_boolean():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "creativity_mode")
    opts = getattr(field, "options", None)
    assert opts is not None
    assert set(opts) == {"off", "on"}


def test_latent_scaling_field_default_fast():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "latent_scaling")
    assert getattr(field, "default", None) == "fast"


def test_generate_noise_empty_tensor_sentinel_is_noop():
    import torch
    out = _generate_noise(
        seed=0, shape=(1, 4, 8, 8),
        noise_bias=torch.zeros(0), noise_scale=1.0,
        dtype=torch.float32, device="cpu",
    )
    assert out.shape == (1, 4, 8, 8)


def test_generate_noise_4d_bias_adds_correctly():
    import torch
    bias = torch.zeros(1, 4, 1, 1)
    bias[..., 0, 0] = 0.5
    out = _generate_noise(
        seed=0, shape=(1, 4, 8, 8),
        noise_bias=bias, noise_scale=1.0,
        dtype=torch.float32, device="cpu",
    )
    assert out.shape == (1, 4, 8, 8)
    assert torch.allclose(out.mean(dim=(2, 3), keepdim=True), torch.full((1, 4, 1, 1), 0.5), atol=0.05)


def test_noise_inverse_half_blends_x0_and_noise():
    import torch
    x0 = torch.ones(1, 4, 8, 8)
    out = _noise_inverse(x0, sigma_target=0.5, noise_seed=0)
    assert out.shape == x0.shape
    assert torch.allclose(out.mean(), torch.tensor(1.0), atol=0.05)


def test_noise_inverse_zero_returns_x0():
    import torch
    x0 = torch.full((1, 4, 4, 4), 0.3)
    out = _noise_inverse(x0, sigma_target=0.0, noise_seed=0)
    assert torch.allclose(out, x0)


def test_noise_inverse_one_returns_pure_noise():
    import torch
    x0 = torch.zeros(1, 4, 4, 4)
    out = _noise_inverse(x0, sigma_target=1.0, noise_seed=42)
    assert out.shape == x0.shape
    assert out.std() > 0.5