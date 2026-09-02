"""Z-Image Turbo 3-stage progressive upscaling.

Each stage runs its own hardcoded sigma sequence; stage-to-stage
relay is the previous stage's latent, not a slice of a single
shared sigma schedule. This is the model ZImagePowerNodes uses
in its BRAVO/ALPHA presets and is the only relay semantic that
survives upscale_factor > 1.0.
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


SIGMA_PRESETS = {
    "alpha_8": (
        (0.991, 0.980, 0.920),
        (0.935, 0.900, 0.875, 0.750, 0.000),
        (0.658, 0.302, 0.000),
    ),
    "bravo_8": (
        (0.991, 0.920),
        (0.935, 0.900, 0.875, 0.820, 0.750, 0.000),
        (0.658, 0.302, 0.000),
    ),
}


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
    sigmas = torch.tensor(sigmas, dtype=x0.dtype, device=device)
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
            description="3-stage progressive upscale for Z-Image Turbo.",
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
                io.Combo.Input("sigma_preset", options=list(SIGMA_PRESETS.keys()), default="bravo_8",
                                tooltip="Per-stage sigma sequences. alpha_8 has stronger refiner; bravo_8 is the default."),
                io.Float.Input("upscale_factor", default=2.0, min=1.0, max=4.0, step=0.1,
                                tooltip="Latent size multiplier per stage. 2.0 = 4x total."),
                io.Combo.Input("sampler", options=SAMPLER_NAMES, default="euler",
                                tooltip="Solver used for all three stages."),
            ],
            outputs=[io.Latent.Output("latent_output")],
        )

    @classmethod
    def execute(cls, latent_input: dict, model: Any, cfg: float, seed: int, shift: float,
                add_noise: str, sigma_preset: str, upscale_factor: float, sampler: str,
                positive: list | None = None,
                positive_stg2: list | None = None,
                positive_stg3: list | None = None) -> io.NodeOutput:

        add_noise_bool = add_noise == "enable"
        cond_s1 = positive or []
        cond_s2 = positive_stg2 or cond_s1
        cond_s3 = positive_stg3 or cond_s2
        negative = cond_s1 if cfg > 0 else []

        sigmas1, sigmas2, sigmas3 = SIGMA_PRESETS[sigma_preset]

        model_sampling = model.get_model_object("model_sampling")
        original_shift = getattr(model_sampling, "shift", None)
        if shift > 0:
            model_sampling.shift = shift

        try:
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