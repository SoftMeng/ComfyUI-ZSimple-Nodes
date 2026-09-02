"""Z-Image Turbo 3-stage progressive sampling.

Architecture mirrors ComfyUI-ZImagePowerNodes/zsampler_turbo_core:
- BRAVO/ALPHA hardcoded sigma presets (author-tuned; empirically
  beat any scheduler formula at 8-step) — schedule option removed.
- Stage sizes follow X21 max_quality gentle progression (driven by
  the latent_scaling IO: fast | quality | none).
- Stage2 scramble + 1-step coherence preproc (creativity_mode
  boolean, X21-style). seed%3==0 disables preproc for higher
  creativity.
- Probe-calibrated initial noise bias to compensate for preset
  sigmas starting below 1.0.
"""
from typing import Any

import torch
import torch.nn.functional as F

from comfy_api.latest import io

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils

import latent_preview


SAMPLER_NAMES = comfy.samplers.SAMPLER_NAMES

_SIGMA_PRESETS_BY_NAME = {
    "alpha_3" : [(0.991, 0.920), None, None],
    "alpha_4" : [(0.991, 0.920, 0.500), None, None],
    "alpha_5" : [(0.991, 0.920, 0.793, 0.500), None, None],
    "alpha_6" : [(0.991, 0.920, 0.870, 0.793, 0.500, 0.300), None, None],
    "alpha_7" : [(0.991, 0.980, 0.920, 0.870, 0.793, 0.500, 0.300), None, None],
    "bravo_8" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.300), (0.658, 0.302, 0.0)],
}

_LATENT_SCALING = {
    # (stage1_factor, stage2_factor, stage3_factor) relative to input size
    "fast"   : (0.25, 0.50, 0.75),
    "quality": (0.50, 0.75, 1.00),
    "none"   : (1.00, 1.00, 1.00),
}


def _get_sigma_preset(steps: int):
    clamped = max(3, min(steps, 7))
    return _SIGMA_PRESETS_BY_NAME[f"alpha_{clamped}"] if clamped <= 7 else _SIGMA_PRESETS_BY_NAME["bravo_8"]


def _slice_sigmas_at_entry(sigmas, enter_sigma: float):
    """Return tail of `sigmas` at-or-below enter_sigma (ZTPLU semantics)."""
    if sigmas is None or sigmas.numel() == 0:
        return sigmas
    if enter_sigma is None:
        return sigmas
    for i, s in enumerate(sigmas):
        if float(s) <= float(enter_sigma):
            return sigmas[i:]
    return sigmas


def _coerce_latent(latent):
    if isinstance(latent, dict):
        return latent
    if torch.is_tensor(latent):
        return {"samples": latent}
    raise TypeError(f"latent must be dict or Tensor, got {type(latent).__name__}")


def adjust_latent_size(latent, factor: float):
    latent = _coerce_latent(latent)
    if factor == 1.0:
        return latent
    samples = latent["samples"]
    _, _, hh, ww = samples.shape
    new_h = max(8, round(hh * factor / 8) * 8)
    new_w = max(8, round(ww * factor / 8) * 8)
    out = comfy.utils.common_upscale(samples, new_w, new_h, "bislerp", "disabled")
    return {**latent, "samples": out}


def _generate_noise(seed: int, shape, *, noise_scale=1.0, noise_bias=0.0, dtype, device):
    g = torch.Generator().manual_seed(seed)
    noise = torch.randn(shape, generator=g, dtype=dtype, device="cpu").to(device=device)
    if isinstance(noise_scale, torch.Tensor):
        noise = noise * noise_scale.to(device=device, dtype=noise.dtype)
    elif noise_scale != 1.0:
        noise = noise * noise_scale
    if isinstance(noise_bias, torch.Tensor) and noise_bias.numel() > 0:
        noise = noise + noise_bias.to(device=device, dtype=noise.dtype)
    elif isinstance(noise_bias, torch.Tensor):
        pass
    elif noise_bias != 0.0:
        bias = torch.full((shape[0], shape[1], 1, 1), float(noise_bias),
                          dtype=dtype, device=device)
        noise = noise + bias
    return noise


def _scramble_counts(seed: int) -> tuple[int, int, int, int]:
    if seed % 10 == 0:
        return (-2, -2, -2, -2)
    if seed % 2 == 0:
        return (2, -1, 2, -1)
    return (1, 0, 1, 0)


def _scramble_tensor(x: torch.Tensor, counts: tuple, seed: int) -> torch.Tensor:
    if x.dim() != 4 or not any(counts):
        return x
    x_scale = x.std(dim=(2, 3), keepdim=True)
    x_bias = x.mean(dim=(2, 3), keepdim=True)
    generator = torch.Generator().manual_seed(seed)
    B, C, H, W = x.shape
    result = torch.zeros_like(x)
    anchors = ('left', 'top', 'right', 'bottom')
    for anchor_idx, anchor in enumerate(anchors):
        for _ in range(abs(counts[anchor_idx])):
            fh = int(H * (0.50 + 0.25 * torch.rand(1, generator=generator).item()))
            fw = int(W * (0.50 + 0.25 * torch.rand(1, generator=generator).item()))
            fh = max(8, min(fh, H))
            fw = max(8, min(fw, W))
            if anchor in ('left', 'right'):
                fy = torch.randint(0, max(1, H - fh + 1), (1,), generator=generator).item()
                fx = 0 if anchor == 'left' else W - fw
            else:
                fy = 0 if anchor == 'top' else H - fh
                fx = torch.randint(0, max(1, W - fw + 1), (1,), generator=generator).item()
            frag = x[:, :, fy:fy + fh, fx:fx + fw].clone()
            if counts[anchor_idx] < 0:
                if torch.rand(1, generator=generator).item() > 0.5:
                    frag = torch.flip(frag, dims=[-1])
                if torch.rand(1, generator=generator).item() > 0.5:
                    frag = torch.flip(frag, dims=[-2])
            frag_resized = F.interpolate(frag, size=(H, W), mode='bicubic', align_corners=False)
            result = result + frag_resized
    r_scale = result.std(dim=(2, 3), keepdim=True).clamp(min=1e-6)
    r_bias = result.mean(dim=(2, 3), keepdim=True)
    scale = x_scale / r_scale
    bias = x_bias - r_bias * scale
    return result * scale + bias


def _stage2_preproc(model, latent, cfg, preproc_steps, preproc_positive,
                     sampler, noise_seed):
    if preproc_steps <= 0:
        return latent
    latents = latent["samples"]
    sigmas = torch.tensor((0.949, 0.0), dtype=latents.dtype, device=latents.device)
    out_dict = _stage_denoise(
        model, {"samples": latents}, preproc_positive, preproc_positive, cfg,
        sampler, sigmas,
        noise_seed=noise_seed,
        noise_scale=1.0, noise_bias=0.0,
        add_noise=True,
        force_final_denoise=True,
    )
    return {"samples": out_dict["samples"]}


def _estimate_initial_noise_features(model, positive, negative, sampler_obj,
                                     sigma_first, seed, sample_hw, reference_tensor):
    dtype = reference_tensor.dtype
    B, C = reference_tensor.shape[0], reference_tensor.shape[1]
    H, W = sample_hw
    probe = torch.zeros((B, C, H, W), dtype=dtype, layout=reference_tensor.layout, device="cpu")
    sigmas = torch.tensor([1.0, float(sigma_first)], dtype=torch.float32)
    out = _stage_denoise(
        model, {"samples": probe}, positive, negative, 1.0, sampler_obj, sigmas,
        noise_seed=seed, add_noise=True, force_final_denoise=False,
    )
    result = out["samples"].to(dtype)
    bias = result.mean(dim=(2, 3), keepdim=True)
    scale = result.std(dim=(2, 3), keepdim=True)
    return bias, scale


def _stage_denoise(model, latent, conditioning, negative, cfg, sampler_obj, sigmas,
                   noise_seed, noise_scale=1.0, noise_bias=0.0,
                   add_noise=True, force_final_denoise=False):
    latent = _coerce_latent(latent)
    device = comfy.model_management.get_torch_device()
    x0 = latent["samples"].to(device)
    sigmas = sigmas.to(device) if isinstance(sigmas, torch.Tensor) else torch.tensor(sigmas, dtype=x0.dtype, device=device)
    eps = _generate_noise(noise_seed, x0.shape, noise_scale=noise_scale,
                          noise_bias=noise_bias, dtype=x0.dtype, device=device)
    if not add_noise:
        eps = torch.zeros_like(eps)
    if force_final_denoise and sigmas[-1] != 0:
        sigmas = sigmas.clone()
        sigmas[-1] = 0
    callback = latent_preview.prepare_callback(model, max(1, len(sigmas) - 1))
    samples = comfy.sample.sample_custom(
        model, eps, cfg, sampler_obj, sigmas,
        conditioning, negative, x0,
        noise_mask=None, callback=callback,
        disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
        seed=noise_seed,
    )
    return {"samples": samples}


class ZImageTurboProgressive(io.ComfyNode):

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ZImageTurboProgressive",
            display_name="Z-Image Turbo Progressive",
            category="ZSimple-Nodes/sampling",
            description="3-stage progressive sampler for Z-Image Turbo with BRAVO/ALPHA sigma presets, X21 gentle size progression, and probe-calibrated initial bias.",
            inputs=[
                io.Latent.Input("latent_input"),
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Float.Input("cfg", default=1.0, min=0.0, max=15.0, step=0.1,
                                tooltip="CFG scale. Z-Image Turbo is distilled; recommended 1.0 (positive == negative)."),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True,
                             tooltip="Seed for stage1. Stage2/3 use deterministic offsets (seed+16, 696969)."),
                io.Float.Input("shift", default=3.5, min=0.0, max=100.0, step=0.01,
                                tooltip="Logit-normal time shift. 0 disables. Z-Image Turbo ≈3.5."),
                io.Combo.Input("add_noise", options=["enable", "disable"], default="enable",
                                tooltip="Add initial noise at stage1. Disable for inpainting."),
                io.Combo.Input("return_leftover_noise", options=["disable", "enable"], default="disable",
                                tooltip="Stage3 leaves residual sigma noise in the output latent for downstream nodes."),
                io.Int.Input("steps", default=8, min=2, max=64,
                             tooltip="Total denoise steps. 8 selects bravo_8; 3-7 selects alpha_N; >8 clamps to alpha_8."),
                io.Combo.Input("creativity_mode", options=["off", "on"], default="off",
                                tooltip="On: stage2 scramble + 1-step coherence preproc (X21 behavior). seed%3==0 skips preproc for higher creativity."),
                io.Float.Input("initial_bias", default=0.0, min=-0.5, max=0.5, step=0.1,
                                tooltip="Additive initial noise bias. Non-zero runs a small probe to compute per-channel low-frequency calibration."),
                io.Combo.Input("latent_scaling", options=list(_LATENT_SCALING.keys()), default="fast",
                                tooltip="Stage size chain. fast=(0.25,0.5,0.75) quality=(0.5,0.75,1.0) none=(1,1,1). X21 max_quality/fast/max."),
                io.Float.Input("intensity", default=1.0, min=0.0, max=2.0, step=0.1,
                                tooltip="Initial noise overdose (intensity-1)*0.4 + bias level (intensity*4-1). 1.0 = no change."),
                io.Float.Input("refine_enter_sigma", default=0.658, min=0.0, max=2.0, step=0.05,
                                tooltip="Stage3 entry sigma — slices sigmas3 tail at ≤ this value. Lower = more detail preservation."),
                io.Combo.Input("stage1_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage2_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage3_sampler", options=SAMPLER_NAMES, default="dpmpp_sde"),
            ],
            outputs=[io.Latent.Output("latent_output")],
        )

    @classmethod
    def execute(cls, latent_input: dict, model: Any, cfg: float, seed: int, shift: float,
                add_noise: str, return_leftover_noise: str, steps: int,
                creativity_mode: str, initial_bias: float, latent_scaling: str,
                intensity: float, refine_enter_sigma: float,
                stage1_sampler: str, stage2_sampler: str, stage3_sampler: str,
                positive: list | None = None) -> io.NodeOutput:

        add_noise_bool = add_noise == "enable"
        return_noise_bool = return_leftover_noise == "enable"
        negative = positive or [] if cfg > 0 else []
        cond = positive or []

        s1_factor, s2_factor, s3_factor = _LATENT_SCALING[latent_scaling]
        sigmas1_tuple, sigmas2_tuple, sigmas3_tuple = _get_sigma_preset(steps)

        def _to_tensor(tup):
            if not tup:
                return None
            return torch.tensor(list(tup), dtype=torch.float32, device=model.load_device)

        sigmas1 = _to_tensor(sigmas1_tuple)
        sigmas2 = _to_tensor(sigmas2_tuple)
        sigmas3 = _to_tensor(sigmas3_tuple)
        if sigmas3 is not None and refine_enter_sigma > 0:
            sigmas3 = _slice_sigmas_at_entry(sigmas3, refine_enter_sigma)
        if sigmas1 is None or sigmas1.numel() < 2:
            print("[ZImageTurboProgressive] ERROR: sigma preset returned no stage1 sigmas.")
            return io.NodeOutput(latent_input)

        noise_overdose = (intensity - 1.0) * 0.4
        noise_bias_level_from_intensity = intensity * 4 - 1
        initial_noise_scale = 1.0 + noise_overdose
        initial_bias_level = min(max(20.0 * initial_bias + noise_bias_level_from_intensity,
                                    -10.0), 10.0)

        sampler1 = comfy.samplers.sampler_object(stage1_sampler)
        sampler2 = comfy.samplers.sampler_object(stage2_sampler)
        sampler3 = comfy.samplers.sampler_object(stage3_sampler)

        latent_input = {
            **latent_input,
            "samples": comfy.sample.fix_empty_latent_channels(model, latent_input["samples"]),
        }

        model_sampling = model.get_model_object("model_sampling")
        original_shift = getattr(model_sampling, "shift", None)
        if shift > 0:
            model_sampling.shift = shift

        try:
            creativity_on = creativity_mode == "on"
            high_as_a_kite = (seed % 3) == 0
            scramble_on = creativity_on
            preproc_n = 0 if (not creativity_on or high_as_a_kite) else 1

            probe_noise_bias = torch.zeros(0, device=model.load_device)
            probe_noise_scale = initial_noise_scale
            if initial_bias_level != 0 and add_noise_bool and sigmas1 is not None:
                probe_hw = (min(64, latent_input["samples"].shape[-2]),
                            min(64, latent_input["samples"].shape[-1]))
                pbias, pscale = _estimate_initial_noise_features(
                    model, cond, negative, sampler1,
                    sigma_first=float(sigmas1[0].item() if hasattr(sigmas1[0], "item") else sigmas1[0]),
                    seed=seed, sample_hw=probe_hw,
                    reference_tensor=latent_input["samples"],
                )
                probe_noise_bias = (pbias / pscale.clamp(min=1e-6)).clamp(-0.005, 0.005)
                probe_noise_bias = probe_noise_bias * initial_bias_level

            if add_noise_bool and creativity_on:
                t = latent_input["samples"]
                t = _scramble_tensor(t, _scramble_counts(seed), seed)
                latent_input = {**latent_input, "samples": t}

            latent_s1_in = adjust_latent_size(latent_input, factor=s1_factor)

            latent_s1 = _stage_denoise(
                model, latent_s1_in, cond, negative, cfg, sampler1, sigmas1,
                noise_seed=seed,
                noise_scale=probe_noise_scale,
                noise_bias=probe_noise_bias,
                add_noise=add_noise_bool,
                force_final_denoise=True,
            )

            if sigmas2 is not None:
                latent_s2_in = adjust_latent_size(latent_s1, factor=s2_factor / s1_factor)
                if creativity_on:
                    t = latent_s2_in["samples"]
                    t = _scramble_tensor(t, _scramble_counts(seed), seed)
                    latent_s2_in = {**latent_s2_in, "samples": t}
                if preproc_n > 0:
                    latent_s2_in = _stage2_preproc(
                        model, latent_s2_in, cfg, preproc_n, cond,
                        sampler2, seed + 16,
                    )

                latent_s2 = _stage_denoise(
                    model, latent_s2_in, cond, negative, cfg, sampler2, sigmas2,
                    noise_seed=seed + 16,
                    noise_scale=probe_noise_scale,
                    noise_bias=probe_noise_bias,
                    add_noise=True,
                    force_final_denoise=True,
                )
            else:
                latent_s2 = latent_s1

            if sigmas3 is not None:
                latent_s3_in = adjust_latent_size(latent_s2, factor=s3_factor / s2_factor)
                latent_s3 = _stage_denoise(
                    model, latent_s3_in, cond, negative, cfg, sampler3, sigmas3,
                    noise_seed=696969,
                    noise_scale=probe_noise_scale,
                    noise_bias=probe_noise_bias,
                    add_noise=True,
                    force_final_denoise=not return_noise_bool,
                )
            else:
                latent_s3 = latent_s2
        finally:
            model_sampling.shift = original_shift

        return io.NodeOutput(latent_s3)