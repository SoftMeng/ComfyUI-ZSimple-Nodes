# 公共 sample helper；zimage_turbo_progressive 和 z_image_upscale_plus v2/v3 共用。
# 形参命名对齐 comfy.sample.sample_custom：latent_image（不是 latent dict）。

import torch

import comfy.model_management
import comfy.sample
import comfy.utils
import latent_preview


def _stage_sample_with_sigmas(
    model,
    latent_image: torch.Tensor,
    noise: torch.Tensor,
    cfg: float,
    sampler_obj,
    sigmas,
    callback,
    seed: int,
    force_full_denoise: bool = True,
    conditioning=[],
    negative=[],
    sampler_name: str = "",
) -> torch.Tensor:
    if sampler_name and hasattr(model, "model_options") and isinstance(model.model_options, dict):
        model.model_options["sampler_name"] = sampler_name
    sigmas = list(sigmas)
    if force_full_denoise and sigmas[-1] != 0:
        sigmas = sigmas.copy()
        sigmas[-1] = 0.0
    sigmas = torch.tensor(sigmas, dtype=latent_image.dtype, device=latent_image.device)
    if callback is None:
        callback = latent_preview.prepare_callback(model, max(1, len(sigmas) - 1))
    return comfy.sample.sample_custom(
        model, noise.to(device=latent_image.device, dtype=latent_image.dtype),
        cfg, sampler_obj, sigmas,
        conditioning, negative, latent_image,
        noise_mask=None, callback=callback,
        disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
        seed=seed,
    )


def _stage_seed(base_seed: int, stage_idx: int, *, is_refinement: bool = False) -> int:
    return base_seed + 9999 if is_refinement else base_seed + stage_idx + 1