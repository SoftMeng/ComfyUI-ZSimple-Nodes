"""Z-Image Turbo 3-stage progressive sampling."""
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

_SAMPLER_CACHE: dict[str, object] = {}


def _cached_sampler(name: str):
    s = _SAMPLER_CACHE.get(name)
    if s is None:
        s = comfy.samplers.sampler_object(name)
        _SAMPLER_CACHE[name] = s
    return s

_SIGMA_PRESETS_BY_NAME = {
    "alpha_3" : [(0.991, 0.920), (0.942, 0.000), (0.710, 0.000)],
    "alpha_4" : [(0.991, 0.920), (0.935, 0.789, 0.000), (0.710, 0.000)],
    "alpha_5" : [(0.991, 0.920), (0.935, 0.789, 0.000), (0.658, 0.302, 0.000)],
    "alpha_6" : [(0.991, 0.920), (0.935, 0.770, 0.690, 0.000), (0.658, 0.302, 0.000)],
    "alpha_7" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.800, 0.000), (0.658, 0.302, 0.000)],
    "alpha_8" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.000), (0.658, 0.302, 0.000)],
    "alpha_9" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.000), (0.658, 0.4556, 0.200, 0.000)],
}

_BASE_S1 = (0.991, 0.920)
_BASE_S2 = (0.935, 0.900, 0.875, 0.820, 0.750, 0.000)
_BASE_S3 = (0.658, 0.4556, 0.200, 0.000)

_ALPHA_INSERT_COUNTS: dict[int, tuple[int, int]] = {
    10: (1, 1),
    11: (2, 2),
    12: (3, 3),
    13: (4, 4),
    14: (5, 5),
    15: (6, 6),
}


def _refine_sigma_sequence(sigmas, insert_count: int):
    if not sigmas or len(sigmas) < 2:
        sigmas = [1.0, 0.0]
    sigmas = list(sigmas)
    while insert_count > 0:
        new_sequence = [sigmas[0]]
        for i in range(len(sigmas) - 1):
            if insert_count > 0:
                new_sequence.append((sigmas[i] + sigmas[i + 1]) / 2)
                insert_count -= 1
            new_sequence.append(sigmas[i + 1])
        sigmas = new_sequence
    return sigmas


def _get_sigma_preset(steps: int):
    if 10 <= steps <= 15:
        s2_inserts, s3_inserts = _ALPHA_INSERT_COUNTS[steps]
        return (
            _BASE_S1,
            tuple(_refine_sigma_sequence(_BASE_S2, s2_inserts)),
            tuple(_refine_sigma_sequence(_BASE_S3, s3_inserts)),
        )
    if 3 <= steps <= 9:
        return _SIGMA_PRESETS_BY_NAME[f"alpha_{steps}"]
    return _SIGMA_PRESETS_BY_NAME["alpha_8"]

_LATENT_SCALING = {
    "fast"      : (0.25, 0.50, 1.00),
    "quality"   : (0.50, 0.75, 1.00),
    "aggressive": (0.5, 0.5, 1.00),
    "none"      : (1.00, 1.00, 1.00),
}

_REFINE_ENTER_SIGMA = 0.658


def _slice_sigmas_at_entry(sigmas, enter_sigma: float):
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


def adjust_latent_size(latent, factor: float = 1.0, target_size: tuple[int, int] | None = None):
    latent = _coerce_latent(latent)
    samples = latent["samples"]
    _, _, hh, ww = samples.shape
    if target_size is not None:
        new_h, new_w = target_size
    else:
        new_h = max(8, round(hh * factor / 8) * 8)
        new_w = max(8, round(ww * factor / 8) * 8)
    if new_h == hh and new_w == ww:
        return latent
    out = comfy.utils.common_upscale(samples, new_w, new_h, "bilinear", "disabled")
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


def _noise_inverse(model, x0: torch.Tensor, sigma_target: float, noise_seed: int) -> torch.Tensor:
    noise = torch.randn(x0.shape, dtype=x0.dtype, device=x0.device,
                        generator=torch.Generator(device=x0.device).manual_seed(noise_seed))
    return (1.0 - sigma_target) * x0 + sigma_target * noise


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
                io.Combo.Input("add_noise", options=["enable", "disable"], default="enable",
                                tooltip="Add initial noise at stage1. Disable for inpainting."),
                io.Combo.Input("return_leftover_noise", options=["enable", "disable"], default="disable",
                                tooltip="Stage3 leaves residual σ noise in the output latent so downstream sampler nodes can continue from a partially-denoised state."),
                io.Int.Input("steps", default=8, min=2, max=64,
                             tooltip="Total denoise steps. 8 selects alpha_8; 3-15 selects alpha_N; >15 falls back to alpha_8."),
                io.Boolean.Input("creativity_mode", default=False,
                                tooltip="On: stage2 scramble + 1-step coherence preproc (X21 behavior). seed%3==0 skips preproc for higher creativity."),
                io.Float.Input("noise_bias_offset", default=0.0, min=-0.5, max=0.5, step=0.1,
                                tooltip="Noise bias offset. Internally clamps 20*noise_bias_offset + noise_strength*4-1 to ±10. For single-knob control, keep `noise_bias_offset=0` and use `noise_strength` instead. Non-zero values trigger a 64x64 noise probe."),
                io.Combo.Input("stage_resolution_chain", options=list(_LATENT_SCALING.keys()), default="fast",
                                tooltip="Stage size chain. fast=(0.25,0.50,1.00) quality=(0.50,0.75,1.00) aggressive=(0.25,0.50,0.75) none=(1,1,1). aggressive shrinks stage3 to 0.75x then resizes back to input."),
                io.Float.Input("noise_strength", default=1.0, min=0.0, max=2.0, step=0.1,
                                tooltip="Initial noise overdose (noise_strength-1)*0.4 + bias level (noise_strength*4-1). 1.0 = no change. Combines with `noise_bias_offset`; for clean control set `noise_bias_offset=0`."),
                io.Boolean.Input("noise_inversion", default=True,
                                tooltip="Stage handoff: pass each prior stage's fully-denoised output as the next stage's clean starting latent. Skipped on none mode (all sizes equal). Stage entrance internally re-noises via ModelSamplingDiscreteFlow noise_scaling, so the previous stage's signal survives into the next stage without double noising."),
                io.Int.Input("stage3_count", default=1, min=1, max=4,
                             tooltip="Stage 3 batch count. stage1/stage2 run once; stage3 runs N times with different noise (seed+696968+i). latent_stage3 becomes a list of N."),
                io.Combo.Input("stage1_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage2_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage3_sampler", options=SAMPLER_NAMES, default="dpmpp_sde"),
            ],
            outputs=[
                io.Latent.Output("latent_stage1",
                                  tooltip="Stage 1 clean latent. Force-final-denoised to σ=0. Ready for downstream sampler or VAE Decode."),
                io.Latent.Output("latent_stage2",
                                  tooltip="Stage 2 clean latent. Force-final-denoised to σ=0. Ready for downstream sampler or VAE Decode."),
                io.Latent.Output("latent_stage3",
                                  tooltip="List of N latents (N=stage3_count). Each entry uses seed+696968+i. Clean (σ=0) when return_leftover_noise=disable; otherwise retains residual σ noise."),
            ],
        )

    @classmethod
    def execute(cls, latent_input: dict, model: Any, cfg: float, seed: int,
                add_noise: str, return_leftover_noise: str, steps: int,
                creativity_mode: bool, noise_bias_offset: float, stage_resolution_chain: str,
                noise_strength: float, noise_inversion: bool,
                stage1_sampler: str, stage2_sampler: str, stage3_sampler: str, stage3_count: int = 1,
                positive: list | None = None) -> io.NodeOutput:

        add_noise_bool = add_noise == "enable"
        return_noise_bool = return_leftover_noise == "enable"
        noise_inversion_bool = noise_inversion
        negative = positive or [] if cfg > 0 else []
        cond = positive or []

        s1_factor, s2_factor, s3_factor = _LATENT_SCALING[stage_resolution_chain]
        sigmas1_tuple, sigmas2_tuple, sigmas3_tuple = _get_sigma_preset(steps)

        def _to_tensor(tup):
            if not tup:
                return None
            return torch.tensor(list(tup), dtype=torch.float32, device=model.load_device)

        sigmas1 = _to_tensor(sigmas1_tuple)
        sigmas2 = _to_tensor(sigmas2_tuple)
        sigmas3 = _to_tensor(sigmas3_tuple)
        if sigmas3 is not None:
            sigmas3 = _slice_sigmas_at_entry(sigmas3, _REFINE_ENTER_SIGMA)
        if sigmas1 is None or sigmas1.numel() < 2:
            print("[ZImageTurboProgressive] ERROR: sigma preset returned no stage1 sigmas.")
            return io.NodeOutput(latent_input)

        noise_overdose = (noise_strength - 1.0) * 0.4
        noise_bias_level_from_strength = noise_strength * 4 - 1
        initial_noise_scale = 1.0 + noise_overdose
        initial_bias_level = min(max(20.0 * noise_bias_offset + noise_bias_level_from_strength,
                                    -10.0), 10.0)
        noise_inversion_effective = noise_inversion_bool and (abs(s1_factor - s2_factor) > 1e-6 or abs(s2_factor - s3_factor) > 1e-6)

        sampler1 = _cached_sampler(stage1_sampler)
        sampler2 = _cached_sampler(stage2_sampler)
        sampler3 = _cached_sampler(stage3_sampler)

        latent_input = {
            **latent_input,
            "samples": comfy.sample.fix_empty_latent_channels(model, latent_input["samples"]),
        }
        target_h, target_w = latent_input["samples"].shape[-2:]


        creativity_on = creativity_mode
        high_as_a_kite = (seed % 3) == 0
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
            if noise_inversion_effective:
                s2_input = adjust_latent_size(latent_s1, factor=s2_factor / s1_factor)
                skip_tensor = _noise_inverse(model, s2_input["samples"], 0.0, seed + 8)
                latent_s2_in = {**latent_s2_in, "samples": skip_tensor}

            latent_s2 = _stage_denoise(
                model, latent_s2_in, cond, negative, cfg, sampler2, sigmas2,
                noise_seed=seed + 16,
                noise_scale=probe_noise_scale,
                noise_bias=probe_noise_bias,
                add_noise=True,
                force_final_denoise=sigmas3 is None,
            )
        else:
            latent_s2 = latent_s1

        if sigmas3 is not None:
            latent_s3_base_in = adjust_latent_size(latent_s2, factor=s3_factor / s2_factor)
            latent_s3_list: list[dict] = []
            for i in range(stage3_count):
                s3_input = adjust_latent_size(latent_s2, factor=s3_factor / s2_factor)
                skip_tensor = (
                    _noise_inverse(model, s3_input["samples"], 0.0, 696968 + i)
                    if noise_inversion_effective
                    else None
                )
                s3_iter_in = {**latent_s3_base_in, "samples": skip_tensor} if skip_tensor is not None else latent_s3_base_in
                latent_s3 = _stage_denoise(
                    model, s3_iter_in, cond, negative, cfg, sampler3, sigmas3,
                    noise_seed=696969 + i,
                    noise_scale=probe_noise_scale,
                    noise_bias=probe_noise_bias,
                    add_noise=True,
                    force_final_denoise=not return_noise_bool,
                )
                latent_s3 = adjust_latent_size(latent_s3, target_size=(target_h, target_w))
                latent_s3_list.append(latent_s3)
            latent_s3_out = latent_s3_list
        else:
            latent_s3_out = [latent_s2]

        return io.NodeOutput(latent_s1, latent_s2, latent_s3_out)