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


def test_get_sigma_preset_steps_8_is_alpha():
    s1, s2, s3 = _get_sigma_preset(8)
    assert s1 is not None and len(s1) >= 2
    assert s2 is not None and len(s2) >= 2
    assert s3 is not None and len(s3) >= 2
    assert _SIGMA_PRESETS_BY_NAME["alpha_8"] == (s1, s2, s3)


def test_get_sigma_preset_steps_5_is_alpha():
    s1, s2, s3 = _get_sigma_preset(5)
    assert s1 is not None and len(s1) == 2
    assert s2 is not None and len(s2) >= 2
    assert s3 is not None and len(s3) >= 2
    assert _SIGMA_PRESETS_BY_NAME["alpha_5"] == (s1, s2, s3)


def test_alpha_8_sigmas2_ends_at_zero():
    s1, s2, s3 = _SIGMA_PRESETS_BY_NAME["alpha_8"]
    assert s2[-1] == 0.0, f"alpha_8 sigmas2 must end at 0 (full denoise), got {s2[-1]}"
    assert s3[-1] == 0.0


def test_get_sigma_preset_steps_over_15_falls_back_to_alpha_8():
    s1, s2, s3 = _get_sigma_preset(20)
    assert _SIGMA_PRESETS_BY_NAME["alpha_8"] == (s1, s2, s3)


def test_get_sigma_preset_clamps_below_3_to_alpha_8():
    s1, s2, s3 = _get_sigma_preset(2)
    assert _SIGMA_PRESETS_BY_NAME["alpha_8"] == (s1, s2, s3)


def test_get_sigma_preset_alpha_9_exact():
    assert _get_sigma_preset(9) == (
        _SIGMA_PRESETS_BY_NAME["alpha_9"][0],
        _SIGMA_PRESETS_BY_NAME["alpha_9"][1],
        _SIGMA_PRESETS_BY_NAME["alpha_9"][2],
    )


def test_get_sigma_preset_alpha_10_through_alpha_15_valid():
    for steps in range(10, 16):
        s1, s2, s3 = _get_sigma_preset(steps)
        assert s1 == (0.991, 0.920), f"alpha_{steps} stage1 must be (0.991, 0.920)"
        assert s2[-1] == 0.0, f"alpha_{steps} stage2 must end at 0"
        assert s3[-1] == 0.0, f"alpha_{steps} stage3 must end at 0"
        assert all(s2[i] > s2[i+1] for i in range(len(s2)-1)), f"alpha_{steps} s2 not strictly descending"
        assert all(s3[i] > s3[i+1] for i in range(len(s3)-1)), f"alpha_{steps} s3 not strictly descending"
        assert len(s2) >= 6 and len(s3) >= 4, f"alpha_{steps} sequences shorter than base"


def test_refine_sigma_sequence_invariants():
    from nodes.zimage_turbo_progressive import _refine_sigma_sequence
    result = _refine_sigma_sequence([0.935, 0.900, 0.875, 0.820, 0.750, 0.000], 1)
    assert result[0] == 0.935
    assert result[-1] == 0.0
    assert all(result[i] > result[i+1] for i in range(len(result)-1))
    assert (0.935 + 0.900) / 2 in result, "midpoint must be inserted"


def test_latent_scaling_four_modes():
    assert set(_LATENT_SCALING.keys()) == {"fast", "quality", "aggressive", "none"}
    assert _LATENT_SCALING["none"] == (1.0, 1.0, 1.0)
    assert _LATENT_SCALING["fast"] == (0.25, 0.50, 1.00)
    assert _LATENT_SCALING["quality"] == (0.50, 0.75, 1.00)
    assert _LATENT_SCALING["aggressive"] == (0.75, 0.75, 1.00)


def test_latent_scaling_stage3_input_except_aggressive():
    for name, scales in _LATENT_SCALING.items():
        if name == "aggressive":
            assert scales[2] == 1.00, f"{name} stage3 = input size (1.00)"
            assert scales[1] != 1.00, f"{name} stage2 != 1.00 (shrink from stage1)"
        else:
            assert scales[2] == 1.0, f"{name} stage3 must = input size (1.0)"


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


def test_define_schema_outputs_count():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.outputs) == 3


def test_define_schema_output_names():
    schema = ZImageTurboProgressive.define_schema()
    names = set()
    for out in schema.outputs:
        name = getattr(out, "name", None) or (out.get("name") if isinstance(out, dict) else None)
        if name:
            names.add(name)
    assert names == {"latent_stage1", "latent_stage2", "latent_stage3"}


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
        "steps", "creativity_mode", "noise_bias_offset",
        "stage_resolution_chain", "noise_strength", "noise_inversion",
        "stage1_sampler", "stage2_sampler", "stage3_sampler",
    }
    missing = expected - names
    extra = names - expected
    assert not missing, f"Missing IO: {missing}"
    assert not extra, f"Unexpected IO: {extra}"


def test_creativity_mode_is_boolean():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "creativity_mode")
    assert field.__class__.__name__ == "Boolean", f"creativity_mode must be Boolean, got {field.__class__.__name__}"


def test_noise_inversion_is_boolean():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "noise_inversion")
    assert field.__class__.__name__ == "Boolean", f"noise_inversion must be Boolean, got {field.__class__.__name__}"


def test_stage_resolution_chain_default_fast():
    schema = ZImageTurboProgressive.define_schema()
    field = next(i for i in schema.inputs if getattr(i, "name", None) == "stage_resolution_chain")
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


def test_noise_inverse_zero_returns_x0():
    """σ=0 → output equals x0 (no noise added)."""
    import torch
    torch.manual_seed(0)
    x0 = torch.randn(1, 4, 8, 8)
    out = _noise_inverse(None, x0, sigma_target=0.0, noise_seed=42)
    assert out.shape == x0.shape
    assert out.dtype == x0.dtype
    assert torch.allclose(out, x0, atol=1e-6)


def test_noise_inverse_one_returns_pure_noise():
    """σ=1 → output equals pure noise, x0 contribution vanishes."""
    import torch
    torch.manual_seed(42)
    x0 = torch.randn(1, 4, 8, 8)
    out = _noise_inverse(None, x0, sigma_target=1.0, noise_seed=7)
    # Reconstruct the noise the function should have used.
    noise = torch.randn(x0.shape, dtype=x0.dtype, device=x0.device,
                        generator=torch.Generator(device=x0.device).manual_seed(7))
    assert torch.allclose(out, noise, atol=1e-6)


def test_noise_inverse_uses_flow_convex_combination():
    """σ=0.5 → output equals (1-σ)*x0 + σ*noise (rectified-flow trajectory).

    Regression: previous implementation routed through
    model_sampling.inverse_noise_scaling + noise_scaling, which for CONST
    (Z-Image's ModelSamplingDiscreteFlow) evaluated to `x0 + σ*noise`,
    breaking the convex-combination semantics and producing blurry output.
    """
    import torch
    torch.manual_seed(0)
    x0 = torch.randn(1, 4, 8, 8)
    sigma = 0.5
    out = _noise_inverse(None, x0, sigma_target=sigma, noise_seed=123)
    noise = torch.randn(x0.shape, dtype=x0.dtype, device=x0.device,
                        generator=torch.Generator(device=x0.device).manual_seed(123))
    expected = (1.0 - sigma) * x0 + sigma * noise
    assert torch.allclose(out, expected, atol=1e-6)
    broken = x0 + sigma * noise
    assert not torch.allclose(out, broken, atol=1e-3), (
        "output matches the broken x0 + σ*noise formula; the fix did not take"
    )


def test_noise_inverse_seed_determinism():
    """Same seed → same output; different seed → different output."""
    import torch
    x0 = torch.zeros(1, 4, 4, 4)
    a = _noise_inverse(None, x0, sigma_target=0.5, noise_seed=1)
    b = _noise_inverse(None, x0, sigma_target=0.5, noise_seed=1)
    c = _noise_inverse(None, x0, sigma_target=0.5, noise_seed=2)
    assert torch.allclose(a, b)
    assert not torch.allclose(a, c)


def test_noise_inverse_shape_contract():
    """Output shape must equal input shape. Callers are responsible for
    pre-sizing x0 to the receiving stage's latent dims; passing a mismatched
    size produces blurred artifacts downstream."""
    import torch
    for shape in [(1, 4, 8, 8), (1, 4, 16, 32), (1, 4, 64, 64), (1, 4, 128, 256)]:
        x0 = torch.randn(*shape)
        out = _noise_inverse(None, x0, sigma_target=0.5, noise_seed=0)
        assert out.shape == shape, f"shape contract violated: in={shape} out={tuple(out.shape)}"


def test_noise_inverse_preserves_stage_size_chain():
    """Regression: handoff tensor must arrive at the next stage with that
    stage's size. Simulate the fast-mode chain: stage1 (H/4) -> handoff at
    stage2 size (H/2). A bug where handoff kept stage1's size would let
    stage2's model see a mismatched latent — the prior source of 'blur'."""
    import torch
    H, W = 32, 32
    stage1 = torch.randn(1, 4, H // 4, W // 4)
    stage2_target_size = (H // 2, W // 2)
    s2_sized = adjust_latent_size({"samples": stage1}, target_size=stage2_target_size)["samples"]
    assert s2_sized.shape == (1, 4, H // 2, W // 2)
    handoff = _noise_inverse(None, s2_sized, sigma_target=0.935, noise_seed=0)
    assert handoff.shape == s2_sized.shape, (
        f"handoff must carry stage2 size {(1, 4, H // 2, W // 2)}; "
        f"got {tuple(handoff.shape)} — model would receive a mismatched latent"
    )