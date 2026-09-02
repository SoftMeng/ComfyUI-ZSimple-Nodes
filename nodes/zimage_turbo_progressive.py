"""Z-Image Turbo 3-stage progressive upscaling.

Three sampling stages share one sigma sequence (2:4:2 step split).
Each stage takes the previous stage's latent, upscales it, then
runs the slice of sigmas that was assigned to it.
"""
from typing import Any

import torch

from comfy_api.latest import io

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils

import latent_preview


SAMPLER_NAMES = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "dpmpp_2m_sde", "dpmpp_3m_sde", "uni_pc", "ddim"]
SCHEDULER_NAMES = ["normal", "karras", "exponential", "sgm_uniform", "ddim_uniform", "beta"]


def _stage_split(total_steps: int) -> tuple[int, int, int]:
    s = max(2, total_steps)
    s1 = max(1, round(s * 0.25))
    s3 = max(1, round(s * 0.25))
    s2 = max(1, s - s1 - s3)
    return s1, s2, s3


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
    if isinstance(latent, dict):
        return latent
    if torch.is_tensor(latent):
        return {"samples": latent}
    raise TypeError(f"latent must be dict or Tensor, got {type(latent).__name__}")


def _upscale_latent(latent, factor: float):
    latent = _coerce_latent(latent)
    if factor == 1.0:
        return latent
    samples = latent["samples"]
    _, _, hh, ww = samples.shape
    new_h = max(8, round(hh * factor / 8) * 8)
    new_w = max(8, round(ww * factor / 8) * 8)
    out = comfy.utils.common_upscale(samples, new_w, new_h, "area", "disabled")
    return {**latent, "samples": out}


def _stage_denoise(model, latent, conditioning, negative, cfg, sampler_obj, sigmas,
                   noise_seed, add_noise):
    latent = _coerce_latent(latent)
    device = comfy.model_management.get_torch_device()
    x0 = latent["samples"].to(device)
    g = torch.Generator().manual_seed(noise_seed)
    eps = torch.randn(x0.shape, generator=g, dtype=x0.dtype, device="cpu").to(device=device)
    if not add_noise:
        eps = torch.zeros_like(eps)
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
            description="3-stage progressive upscale (2:4:2 step split) for Z-Image Turbo.",
            inputs=[
                io.Latent.Input("latent_input"),
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("positive_stg2", optional=True),
                io.Conditioning.Input("positive_stg3", optional=True),
                io.Float.Input("cfg", default=1.0, min=0.0, max=15.0, step=0.1,
                                tooltip="CFG scale. Z-Image Turbo is distilled; recommended 1.0 (positive == negative)."),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True,
                             tooltip="Seed for stage1. Stage2/3 use deterministic offsets."),
                io.Float.Input("shift", default=3.5, min=0.0, max=100.0, step=0.01,
                                tooltip="Logit-normal time shift. 0 disables. Z-Image Turbo ≈3.5."),
                io.Combo.Input("add_noise", options=["enable", "disable"], default="enable",
                                tooltip="Add initial noise at stage1. Disable for inpainting."),
                io.Int.Input("steps", default=8, min=2, max=64,
                             tooltip="Total denoise steps, split 2:4:2 across 3 stages."),
                io.Float.Input("upscale_factor", default=2.0, min=1.0, max=4.0, step=0.1,
                                tooltip="Latent size multiplier per stage. 2.0 = 4x total."),
                io.Combo.Input("sampler", options=SAMPLER_NAMES, default="euler",
                                tooltip="Solver used for all three stages."),
                io.Combo.Input("scheduler", options=SCHEDULER_NAMES, default="normal",
                                tooltip="Sigma scheduler. Shared by all stages."),
            ],
            outputs=[io.Latent.Output("latent_output")],
        )

    @classmethod
    def execute(cls, latent_input: dict, model: Any, cfg: float, seed: int, shift: float,
                add_noise: str, steps: int, upscale_factor: float,
                sampler: str, scheduler: str,
                positive: list | None = None,
                positive_stg2: list | None = None,
                positive_stg3: list | None = None) -> io.NodeOutput:

        s1_steps, s2_steps, s3_steps = _stage_split(steps)
        add_noise_bool = add_noise == "enable"
        cond_s1 = positive or []
        cond_s2 = positive_stg2 or cond_s1
        cond_s3 = positive_stg3 or cond_s2
        negative = cond_s1 if cfg > 0 else []

        model_sampling = model.get_model_object("model_sampling")
        original_shift = getattr(model_sampling, "shift", None)
        if shift > 0:
            model_sampling.shift = shift

        try:
            sigmas_full = _resolve_sigmas(model, scheduler, sampler, steps)
            if sigmas_full is None:
                print("[ZImageTurboProgressive] sigma generation failed; check scheduler.")
                return io.NodeOutput(latent_input)

            sigmas1 = _slice_sigmas_by_steps(sigmas_full, 0, s1_steps)
            sigmas2 = _slice_sigmas_by_steps(sigmas_full, s1_steps, s2_steps)
            sigmas3 = _slice_sigmas_by_steps(sigmas_full, s1_steps + s2_steps, s3_steps)

            latent_input = {
                **latent_input,
                "samples": comfy.sample.fix_empty_latent_channels(model, latent_input["samples"]),
            }

            sampler_obj = comfy.samplers.sampler_object(sampler)

            latent_s1 = _stage_denoise(
                model, latent_input, cond_s1, negative, cfg, sampler_obj, sigmas1,
                noise_seed=seed, add_noise=add_noise_bool,
            )

            latent_s2_in = _upscale_latent(latent_s1, factor=upscale_factor)
            latent_s2 = _stage_denoise(
                model, latent_s2_in, cond_s2, negative, cfg, sampler_obj, sigmas2,
                noise_seed=seed + 16, add_noise=False,
            )

            latent_s3_in = _upscale_latent(latent_s2, factor=upscale_factor)
            latent_s3 = _stage_denoise(
                model, latent_s3_in, cond_s3, negative, cfg, sampler_obj, sigmas3,
                noise_seed=seed + 32, add_noise=False,
            )
        finally:
            model_sampling.shift = original_shift

        return io.NodeOutput(latent_s3)