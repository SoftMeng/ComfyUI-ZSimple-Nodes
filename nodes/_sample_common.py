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


def _parse_multiline_sigmas(text: str) -> list[list[float]]:
    result: list[list[float]] = []
    for line in text.strip().splitlines():
        line = line.strip().strip("[]")
        if not line:
            continue
        sigmas = [float(x.strip()) for x in line.split(",") if x.strip()]
        result.append(sigmas)
    if not result:
        raise ValueError("sigmas_pipe is empty (no valid lines)")
    return result


def _validate_multiline_sigmas(stages: list[list[float]], *, require_last_end_zero: bool = True) -> None:
    for idx, sigmas in enumerate(stages):
        if len(sigmas) < 2:
            raise ValueError(f"stage {idx} schedule must have >=2 sigmas, got {len(sigmas)}")
        for i in range(1, len(sigmas)):
            if sigmas[i] > sigmas[i - 1] + 1e-6:
                raise ValueError(
                    f"stage {idx} sigmas must be monotonically non-increasing: "
                    f"{sigmas[i-1]} -> {sigmas[i]} at index {i}"
                )
        if sigmas[0] <= 0.0 or sigmas[0] > 1.0 + 1e-6:
            raise ValueError(f"stage {idx} first sigma must be in (0, 1], got {sigmas[0]}")
    if require_last_end_zero and stages[-1][-1] != 0.0:
        raise ValueError(f"last stage must end at sigma 0.0, got {stages[-1][-1]}")