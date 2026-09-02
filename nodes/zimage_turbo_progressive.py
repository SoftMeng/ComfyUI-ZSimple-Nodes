"""Z-Image Turbo 3-stage progressive upscaling sampler.

Architecture mirrors ComfyUI-ZImagePowerNodes/zsampler_turbo_core for correctness:
- 3-stage sigma slicing (alpha preset pattern)
- stage2 scramble (creativity_mode = scrambled)
- stage2 preproc with extra noise injection (refined_1/2/3)
- stage3 dpmpp_sde refiner
- SpectralAdjustedSampler wrapper for spectral tilt
- noise_scale / noise_bias for initial noise calibration
"""
from typing import Any

import torch
import torch.nn.functional as F

from comfy_api.latest import io

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils
from comfy.samplers import KSAMPLER, ksampler, sampler_object

import latent_preview


SAMPLER_NAMES = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "dpmpp_2m_sde", "dpmpp_3m_sde", "uni_pc", "ddim"]
SCHEDULER_NAMES = ["normal", "karras", "exponential", "sgm_uniform", "ddim_uniform", "beta"]
CREATIVITY_MODES = ["off", "scrambled", "refined_1", "refined_2", "refined_3"]
SPECTRAL_TILT_PRESETS = [
    ("none", "", (0.0, 0.0), 1.0),
    ("stage3_H", "3", (-0.3, -0.3), 1.0),
    ("stages12x_H", "12x", (0.2, -0.9), 0.7),
    ("stages12x_l", "12x", (0.2, -2.0), 0.8),
    ("stages123_H", "123", (0.2, -0.9), 0.7),
]


def _stage_split(total_steps: int) -> tuple[int, int, int]:
    s = max(2, total_steps)
    s1 = max(1, round(s * 0.25))
    s3 = max(1, round(s * 0.25))
    s2 = max(1, s - s1 - s3)
    return s1, s2, s3


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


def _locked_noise_from_prev(eps_prev, target_shape, seed_new):
    """Inject new noise while keeping prev stage's coarse anchor.

    Three components:
      1. eps_prev lifted to target size via bilinear — the coarse
         anchor that ties this stage to the previous one's layout.
      2. Fresh eta sampled at target size — the new stochasticity.
      3. eta minus its 2x2-pooled version — high-frequency novelty
         only; the coarse band is dropped to avoid re-noising the
         regions already pinned by the lifted anchor.

    Std-normalize so the returned tensor has unit variance per
    channel, matching the typical `randn_like` convention used
    elsewhere in this file.
    """
    device = eps_prev.device
    dtype = eps_prev.dtype
    B, C, H1, W1 = target_shape

    g = torch.Generator(device=device)
    g.manual_seed(seed_new)
    eta = torch.randn((B, C, H1, W1), generator=g, device=device, dtype=dtype)

    lifted = F.interpolate(eps_prev, size=(H1, W1), mode='bilinear', align_corners=False)

    eta_low = F.interpolate(F.avg_pool2d(eta, kernel_size=2),
                             size=(H1, W1), mode='bilinear', align_corners=False)
    eta_high = eta - eta_low

    out = lifted + eta_high
    return out / out.std(dim=(2, 3), keepdim=True).clamp(min=1e-6)


def _adjust_spectral_distribution(noise: torch.Tensor, alpha: float, power_gamma: float = 0.5) -> torch.Tensor:
    B, C, H, W = noise.shape
    u = torch.fft.fftfreq(H, device=noise.device, dtype=noise.dtype).view(H, 1)
    v = torch.fft.fftfreq(W, device=noise.device, dtype=noise.dtype).view(1, W)
    grid = u ** 2 + v ** 2
    grid[0, 0] = 1.0
    filt = grid ** (power_gamma * alpha)
    n_fft = torch.fft.fft2(noise, dim=(-2, -1))
    n_fft = n_fft / filt
    filtered = torch.fft.ifft2(n_fft, dim=(-2, -1)).real
    std = filtered.std(dim=(1, 2, 3), keepdim=True).clamp(min=1e-6)
    return filtered / std


class SpectralAdjustedSampler(KSAMPLER):
    def __init__(self, alpha_tilting=(0.1, -1.0), alpha_sharpness=1.0, sigma_range=(0.9999, 0.0), *, inner_sampler: KSAMPLER):
        self._inner = inner_sampler
        self._alpha = alpha_tilting
        self._sharp = alpha_sharpness
        self._range = sigma_range
        super().__init__(
            sampler_function=(lambda *a, **kw: self._run(*a, **kw)),
            extra_options=inner_sampler.extra_options.copy(),
            inpaint_options=inner_sampler.inpaint_options.copy(),
        )

    def _run(self, model, noise, sigmas, *args, **kwargs):
        base_noise_sampler = kwargs.pop("noise_sampler", None)
        if base_noise_sampler is None:
            base_noise_sampler = (lambda *a, **kw: torch.randn_like(noise))
        sig = float(sigmas[0].mean().detach().cpu())
        if isinstance(self._alpha, (list, tuple)) and len(self._alpha) == 2:
            s0, s1 = self._range
            r = s1 - s0
            prog = max(0.0, min(1.0, (sig - s0) / r)) if r != 0 else 1.0
            alpha = self._alpha[0] + (prog ** self._sharp) * (self._alpha[1] - self._alpha[0])
        else:
            alpha = float(self._alpha)
        custom = (lambda *a, **kw: _adjust_spectral_distribution(
            base_noise_sampler(*a, **kw), alpha=alpha))
        return self._inner.sampler_function(model, noise, sigmas, *args,
                                            noise_sampler=custom, **kwargs)


class EulerAss(SpectralAdjustedSampler):
    def __init__(self, alpha_tilting=(0.1, -1.0), alpha_sharpness=1.0, sigma_range=(0.9999, 0.0)):
        super().__init__(alpha_tilting, alpha_sharpness, sigma_range,
                         inner_sampler=ksampler("euler_ancestral"))


class DPMPP_SDEss(SpectralAdjustedSampler):
    def __init__(self, alpha_tilting=(0.1, -1.0), alpha_sharpness=1.0, sigma_range=(0.9999, 0.0)):
        super().__init__(alpha_tilting, alpha_sharpness, sigma_range,
                         inner_sampler=ksampler("dpmpp_sde"))


def _resolve_sampler(name_or):
    if isinstance(name_or, KSAMPLER):
        return name_or
    if not isinstance(name_or, str):
        return sampler_object("euler")
    if name_or == "euler_ass":
        return EulerAss()
    if name_or == "dpmpp_sde_ss":
        return DPMPP_SDEss()
    return sampler_object(name_or)


def _resolve_spectral_for_stage(stage_idx: int, tilt_stages: str,
                                 alpha_tilting, alpha_sharpness,
                                 base_name: str) -> KSAMPLER:
    if str(stage_idx + 1) not in tilt_stages:
        return _resolve_sampler(base_name)
    if "dpmpp_sde" in base_name:
        return DPMPP_SDEss(alpha_tilting=tuple(alpha_tilting), alpha_sharpness=alpha_sharpness)
    return EulerAss(alpha_tilting=tuple(alpha_tilting), alpha_sharpness=alpha_sharpness)


def _generate_noise(seed: int, shape, *, noise_scale=1.0, noise_bias=0.0, dtype, device):
    g = torch.Generator().manual_seed(seed)
    noise = torch.randn(shape, generator=g, dtype=dtype, device="cpu").to(device=device)
    if noise_scale != 1.0:
        noise = noise * noise_scale
    if noise_bias != 0.0:
        bias = torch.full((shape[0], shape[1], 1, 1), float(noise_bias),
                          dtype=dtype, device=device)
        noise = noise + bias
    return noise


def _slice_sigmas_by_steps(sigmas, start_step: int, num_steps: int):
    if sigmas is None or sigmas.numel() < 2:
        return sigmas
    n_total = sigmas.numel() - 1
    i0 = max(0, min(start_step, n_total))
    i1 = max(i0 + 1, min(start_step + num_steps + 1, sigmas.numel()))
    return sigmas[i0:i1]


def _resolve_sigmas(model, scheduler_name: str, sampler_name: str, steps: int):
    model_sampling = model.get_model_object("model_sampling")
    discard_set = ("dpm_2", "dpm_2_ancestral", "uni_pc", "uni_pc_bh2")
    do_discard = sampler_name in discard_set
    calc_steps = steps + 1 if do_discard else steps
    sigmas = comfy.samplers.calculate_sigmas(model_sampling, scheduler_name, calc_steps)
    if do_discard and sigmas is not None and sigmas.numel() >= 2:
        sigmas = torch.cat([sigmas[:-2], sigmas[-1:]])
    return sigmas


def _coerce_latent(latent):
    """Accept LATENT dict OR raw Tensor; always return dict."""
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
    if new_h % hh == 0 and new_w % ww == 0:
        out = F.interpolate(samples, size=(new_h, new_w), mode='area')
    else:
        out = F.interpolate(samples, size=(new_h, new_w), mode='bicubic', align_corners=False)
        orig_var = samples.var()
        new_var = out.var().clamp(min=1e-6)
        out = out * (orig_var / new_var).sqrt()
    return {**latent, "samples": out}


def _stage2_preproc(model, latent, cfg, preproc_steps, preproc_positive,
                     sampler, noise_seed, noise_scale, noise_bias,
                     stage2_sigmas=None,
                     extra_noise_freqs=(1024,), extra_noise_scales=(0.8,)):
    latent = _coerce_latent(latent)
    if preproc_steps <= 0:
        return latent, False
    latents = latent["samples"]
    add_noise = True
    for i in range(preproc_steps):
        if i == 0:
            sigmas = torch.tensor((0.949, 0.0))
        elif stage2_sigmas is not None and stage2_sigmas.numel() >= 2:
            sigmas = stage2_sigmas[:2]
        else:
            sigmas = comfy.samplers.calculate_sigmas(
                model.get_model_object("model_sampling"), "normal", 2)
        freqs = extra_noise_freqs if i == 0 else (0,)
        scales = extra_noise_scales if i == 0 else (0,)
        out_dict = _stage_denoise(
            model, {"samples": latents}, preproc_positive, preproc_positive, cfg,
            sampler, sigmas,
            noise_seed=noise_seed + i,
            noise_scale=noise_scale, noise_bias=noise_bias,
            add_noise=add_noise,
            force_final_denoise=True,
            extra_noise_freqs=freqs, extra_noise_scales=scales,
        )
        latents = out_dict["samples"]
    return {"samples": latents}, add_noise


def _stage_denoise(model, latent, conditioning, negative, cfg, sampler_obj, sigmas,
                   noise_seed, noise_scale=1.0, noise_bias=0.0,
                   add_noise=True, force_final_denoise=True, extra_noise_freqs=0, extra_noise_scales=0,
                   prev_eps=None):
    latent = _coerce_latent(latent)
    device = comfy.model_management.get_torch_device()
    x0 = latent["samples"].to(device)
    if prev_eps is not None:
        locked = _locked_noise_from_prev(prev_eps.to(device), x0.shape, noise_seed + 10007).to(dtype=x0.dtype)
        x0 = x0 + locked
    eps = _generate_noise(noise_seed, x0.shape, noise_scale=noise_scale,
                          noise_bias=noise_bias, dtype=x0.dtype, device=device)
    if not add_noise:
        eps = torch.zeros_like(eps)
    B, C, H, W = x0.shape
    if extra_noise_freqs and extra_noise_scales:
        freqs = extra_noise_freqs if isinstance(extra_noise_freqs, tuple) else (extra_noise_freqs,)
        scales = extra_noise_scales if isinstance(extra_noise_scales, tuple) else (extra_noise_scales,)
        for freq, scale in zip(freqs, scales):
            if scale <= 0.0:
                continue
            lr_shape = (B, C, max(1, H * freq // 1024), max(1, W * freq // 1024))
            noise_seed += 1
            low_noise = _generate_noise(noise_seed, lr_shape, noise_scale=scale,
                                       noise_bias=0.0, dtype=x0.dtype, device=device)
            eps = eps + F.interpolate(low_noise, size=(H, W), mode='bicubic', align_corners=False)
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
            description="3-stage progressive upscale (2:4:2 step split) for Z-Image Turbo with shift, spectral tilt, creativity, detailed_refiner.",
            inputs=[
                io.Latent.Input("latent_input"),
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("positive_stg2", optional=True),
                io.Conditioning.Input("positive_stg3", optional=True),
                io.Float.Input("cfg", default=1.0, min=0.0, max=15.0, step=0.1,
                                tooltip="CFG scale. Z-Image Turbo is distilled; recommended 1.0 (positive == negative)."),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True,
                             tooltip="Seed for stage1. Stage2/3 use seed+16, 696969 (fixed)."),
                io.Float.Input("shift", default=3.5, min=0.0, max=100.0, step=0.01,
                                tooltip="Logit-normal time shift (ModelSamplingSD3 style). 0 disables. Z-Image Turbo ≈3.5."),
                io.Combo.Input("add_noise", options=["enable", "disable"], default="enable",
                                tooltip="Add initial noise at stage1. Disable for inpainting."),
                io.Combo.Input("return_leftover_noise", options=["disable", "enable"], default="disable",
                                tooltip="Stage3 leave residual sigma noise in output (for downstream nodes)."),
                io.Int.Input("steps", default=8, min=2, max=64,
                             tooltip="Total denoise steps, split 2:4:2 across 3 stages."),
                io.Int.Input("start_step", default=0, min=0, max=10000,
                             tooltip="Stage1 sigma slice start (advanced)."),
                io.Int.Input("end_step", default=8, min=1, max=10000,
                             tooltip="Stage1 sigma slice end (advanced)."),
                io.Combo.Input("creativity_mode", options=CREATIVITY_MODES, default="off",
                                tooltip="off=clean. scrambled=structure variation. refined_N=N-step coherence recovery."),
                io.Float.Input("upscale_factor", default=2.0, min=1.0, max=4.0, step=0.1,
                                tooltip="Latent size multiplier per stage. 2.0=4x, √2=2x, etc."),
                io.Boolean.Input("detailed_refiner", default=True,
                                 tooltip="Stage3 switches to dpmpp_sde for high-freq detail recovery."),
                io.Combo.Input("spectral_tilt", options=[p[0] for p in SPECTRAL_TILT_PRESETS], default="none",
                                tooltip="Colored Noise Sampling style freq-domain noise shaping."),
                io.Combo.Input("stage1_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage1_scheduler", options=SCHEDULER_NAMES, default="normal"),
                io.Combo.Input("stage2_sampler", options=SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage2_scheduler", options=SCHEDULER_NAMES, default="normal"),
                io.Combo.Input("stage3_sampler", options=SAMPLER_NAMES, default="dpmpp_sde"),
                io.Combo.Input("stage3_scheduler", options=SCHEDULER_NAMES, default="normal"),
            ],
            outputs=[io.Latent.Output("latent_output")],
        )

    @classmethod
    def execute(cls, latent_input: dict, model: Any, cfg: float, seed: int, shift: float,
                add_noise: str, return_leftover_noise: str, steps: int,
                start_step: int, end_step: int, creativity_mode: str,
                upscale_factor: float, detailed_refiner: bool, spectral_tilt: str,
                stage1_sampler: str, stage1_scheduler: str,
                stage2_sampler: str, stage2_scheduler: str,
                stage3_sampler: str, stage3_scheduler: str,
                positive: list | None = None,
                positive_stg2: list | None = None,
                positive_stg3: list | None = None) -> io.NodeOutput:

        s1_steps, s2_steps, s3_steps = _stage_split(steps)
        add_noise_bool = add_noise == "enable"
        return_noise_bool = return_leftover_noise == "enable"
        cond_s1 = positive or []
        cond_s2 = positive_stg2 or cond_s1
        cond_s3 = positive_stg3 or cond_s2
        negative = cond_s1 if cfg > 0 else []
        preproc_n = {"off": 0, "scrambled": 0, "refined_1": 1,
                     "refined_2": 2, "refined_3": 3}.get(creativity_mode, 0)
        scramble_on = creativity_mode == "scrambled"

        tilt_entry = next(p for p in SPECTRAL_TILT_PRESETS if p[0] == spectral_tilt)
        _, tilt_stages, alpha_tilting, alpha_sharpness = tilt_entry

        sampler1 = _resolve_spectral_for_stage(0, tilt_stages, alpha_tilting, alpha_sharpness, stage1_sampler)
        sampler2 = _resolve_spectral_for_stage(1, tilt_stages, alpha_tilting, alpha_sharpness, stage2_sampler)
        s3_base = "dpmpp_sde" if detailed_refiner else stage3_sampler
        sampler3 = _resolve_spectral_for_stage(2, tilt_stages, alpha_tilting, alpha_sharpness, s3_base)

        model_sampling = model.get_model_object("model_sampling")
        original_shift = getattr(model_sampling, "shift", None)
        if shift > 0:
            model_sampling.shift = shift

        try:
            sigmas_full = _resolve_sigmas(model, stage1_scheduler, stage1_sampler, steps)
            if sigmas_full is None:
                print("[ZImageTurboProgressive] ERROR: sigma generation failed; check scheduler name.")
                return io.NodeOutput(latent_input)
            if stage2_scheduler != stage1_scheduler or stage3_scheduler != stage1_scheduler:
                print("[ZImageTurboProgressive] WARNING: stage2/stage3 scheduler ignored in sigma-step-range mode; all stages use stage1_scheduler.")
            if stage2_sampler != stage1_sampler or s3_base != stage1_sampler:
                print("[ZImageTurboProgressive] WARNING: stage2/stage3 sampler ignored in sigma-step-range mode; all stages use stage1_sampler.")

            sigmas1 = _slice_sigmas_by_steps(sigmas_full, 0,                s1_steps)
            sigmas2 = _slice_sigmas_by_steps(sigmas_full, s1_steps,         s2_steps)
            sigmas3 = _slice_sigmas_by_steps(sigmas_full, s1_steps+s2_steps, s3_steps)
            if sigmas1 is None or sigmas2 is None or sigmas3 is None:
                print("[ZImageTurboProgressive] ERROR: sigma slicing failed.")
                return io.NodeOutput(latent_input)

            latent_input = {**latent_input, "samples": comfy.sample.fix_empty_latent_channels(model, latent_input["samples"])}

            if add_noise_bool and scramble_on:
                t = latent_input["samples"]
                t = _scramble_tensor(t, _scramble_counts(seed), seed)
                latent_input = {**latent_input, "samples": t}

            force_denoise_stg1_stg2 = preproc_n > 0 or scramble_on

            latent_s1 = _stage_denoise(
                model, latent_input, cond_s1, negative, cfg, sampler1, sigmas1,
                noise_seed=seed,
                add_noise=add_noise_bool,
                force_final_denoise=force_denoise_stg1_stg2 or s2_steps == 0,
            )
            eps_s1 = latent_s1["samples"].clone()

            latent_s2_in = adjust_latent_size(latent_s1, factor=upscale_factor)
            preproc_pos = positive_stg2 or cond_s1
            if scramble_on:
                t = latent_s2_in["samples"]
                t = _scramble_tensor(t, _scramble_counts(seed), seed)
                latent_s2_in = {**latent_s2_in, "samples": t}
            if preproc_n > 0:
                latent_s2_in, _ = _stage2_preproc(
                    model, latent_s2_in, cfg, preproc_n, preproc_pos,
                    sampler2, seed + 16, 1.0, 0.0,
                    stage2_sigmas=sigmas2,
                )

            latent_s2 = _stage_denoise(
                model, latent_s2_in, cond_s2, negative, cfg, sampler2, sigmas2,
                noise_seed=seed + 16,
                add_noise=False,
                force_final_denoise=True,
                prev_eps=eps_s1,
            )

            if upscale_factor <= 1.0:
                latent_s3_in = latent_s2
            else:
                latent_s3_in = adjust_latent_size(latent_s2, factor=upscale_factor)
            eps_s2 = latent_s2["samples"].clone()
            latent_s3 = _stage_denoise(
                model, latent_s3_in, cond_s3, negative, cfg, sampler3, sigmas3,
                noise_seed=696969,
                add_noise=False,
                force_final_denoise=not return_noise_bool,
                prev_eps=eps_s2,
            )
        finally:
            model_sampling.shift = original_shift

        return io.NodeOutput(latent_s3)