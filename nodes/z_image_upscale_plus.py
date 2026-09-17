"""Z-Image Turbo 渐进放大 + 末级精修（v2）。"""
from typing import Any

import torch

from comfy_api.latest import io

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils

import latent_preview

from ._noise_inverse import _noise_inverse
from ._partition_common import _locked_noise_from_prev
from ._sample_common import _stage_sample_with_sigmas, _stage_seed
from ._sigma_presets import _SIGMA_PRESETS_BY_NAME, _get_sigma_preset
from .zimage_turbo_progressive import adjust_latent_size


SAMPLER_NAMES = comfy.samplers.SAMPLER_NAMES

_SAMPLER_CACHE: dict[str, object] = {}


def _cached_sampler(name: str):
    s = _SAMPLER_CACHE.get(name)
    if s is None:
        s = comfy.samplers.sampler_object(name)
        _SAMPLER_CACHE[name] = s
    return s


def _resolve_sigma_tuples(upscale_factor: float, max_step_scale: float,
                          sigma_preset: str) -> list[tuple[float, ...]]:
    if sigma_preset in _SIGMA_PRESETS_BY_NAME:
        s1_tuple, s2_tuple, s3_tuple = _SIGMA_PRESETS_BY_NAME[sigma_preset]
    else:
        s1_tuple, s2_tuple, s3_tuple = _get_sigma_preset(8, "middle")
    scales = []
    s = 1.0
    while s < upscale_factor - 1e-6:
        s = min(s * max_step_scale, upscale_factor)
        scales.append(s)
    return [s1_tuple] + [s2_tuple] * (len(scales) - 1)


def _upscale_image_with_model(img_bhwc, upscale_model, target_h, target_w, device):
    tile = 512
    overlap = 32
    try:
        oom = True
        while oom:
            try:
                steps = img_bhwc.shape[0] * comfy.utils.get_tiled_scale_steps(
                    img_bhwc.shape[3], img_bhwc.shape[2], tile_x=tile, tile_y=tile, overlap=overlap)
                pbar = comfy.utils.ProgressBar(steps)
                s = comfy.utils.tiled_scale(
                    img_bhwc.to(device), lambda a: upscale_model(a),
                    tile_x=tile, tile_y=tile, overlap=overlap,
                    upscale_amount=upscale_model.scale, pbar=pbar)
                oom = False
            except comfy.model_management.OOM_EXCEPTION:
                tile //= 2
                if tile < 128:
                    raise
    finally:
        if hasattr(upscale_model, "model"):
            upscale_model.model.to(comfy.model_management.vae_offload_device())
        elif hasattr(upscale_model, "to"):
            upscale_model.to(comfy.model_management.vae_offload_device())
    if s.shape[2] != target_h or s.shape[3] != target_w:
        s = torch.nn.functional.interpolate(s, size=(target_h, target_w), mode="bicubic", align_corners=False)
    return torch.clamp(s, 0.0, 1.0)


class ZImageUpscalePlus(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ZImageUpscalePlus",
            display_name="Z-Image Upscale Plus",
            category="ZSimple-Nodes/image",
            description="Z-Image Turbo 渐进放大 + 末级精修（v2）。支持 BRAVO/ALPHA sigma preset 选择、tiled upscale_model 接通、partial denoise 末级精修。",
            inputs=[
                io.Latent.Input("latent_input"),
                io.Model.Input("model"),
                io.Vae.Input("vae", optional=True,
                             tooltip="tiled upscale_model 需要 VAE 做 latent↔image round-trip。不连则 upscale_model 不生效，走 bilinear 兜底。"),
                io.UpscaleModel.Input("upscale_model", optional=True,
                                     tooltip="像素 upscale 模型（RealESRGAN 等）。需 vae 同时连接。"),
                io.Float.Input("upscale_factor", default=6.0, min=1.0, max=24.0, step=0.25),
                io.Float.Input("max_step_scale", default=1.6, min=1.1, max=6.0, step=0.05),
                io.Combo.Input("sigma_preset", options=list(_SIGMA_PRESETS_BY_NAME.keys()), default="alpha_8",
                               tooltip="Z-Image Turbo 蒸馏 sigma preset。每 stage 起点对应 sigma。"),
                io.Int.Input("tail_steps_first_upscale", default=6, min=1, max=12,
                             tooltip="非末级 stage 采样步数。"),
                io.Int.Input("tail_steps_last_upscale", default=3, min=1, max=12,
                            tooltip="末级精修采样步数。"),
                io.Model.Input("refinement_model", optional=True,
                                tooltip="末级精修 model。默认走 `model` 参数。"),
                io.Combo.Input("sampler", optional=True, default="euler", options=SAMPLER_NAMES),
                io.Combo.Input("scheduler", optional=True, default="normal"),
                io.Float.Input("denoise", optional=True, default=0.6, min=0.0, max=1.0, step=0.01,
                               tooltip="末级精修 denoise。1.0 = full schedule；0.6 = 保留 40% 内容。"),
                io.Float.Input("cfg", optional=True, default=1.0, min=1.0, max=20.0, step=0.1,
                               tooltip="Classifier-free guidance scale。Z-Image Turbo 推荐 1.0；提高此值并连 positive/negative 可让 prompt 影响 upscale。"),
                io.Conditioning.Input("positive", optional=True,
                                      tooltip="正向条件。cfg>1.0 时生效。"),
                io.Conditioning.Input("negative", optional=True,
                                      tooltip="负向条件。cfg>1.0 时生效。"),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
            ],
            outputs=[
                io.Latent.Output("latent"),
            ],
        )

    @classmethod
    def execute(cls, latent_input, model, vae=None, upscale_model=None,
                upscale_factor=6.0, max_step_scale=1.6,
                sigma_preset="alpha_8",
                tail_steps_first_upscale=6, tail_steps_last_upscale=3,
                refinement_model=None, sampler="euler", scheduler="normal",
                denoise=0.6, cfg=1.0, seed=0, positive=None, negative=None) -> io.NodeOutput:
        # TODO thread-safety: _PARTITION_CACHE shared with zimage_turbo_progressive
        samples_in = latent_input["samples"]
        B, C, H, W = samples_in.shape
        dtype = samples_in.dtype
        device = comfy.model_management.get_torch_device()

        target_h = max(8, round(H * upscale_factor / 8) * 8)
        target_w = max(8, round(W * upscale_factor / 8) * 8)

        refinement_model_obj: Any = refinement_model if refinement_model is not None else model
        sampler_obj = _cached_sampler(sampler)
        positive = positive or []
        negative = negative or []

        sigma_tuples = _resolve_sigma_tuples(
            upscale_factor, max_step_scale, sigma_preset,
        )

        current_samples = samples_in
        gen = torch.Generator().manual_seed(seed)
        current_eps = torch.randn(samples_in.shape, generator=gen, dtype=dtype)

        for i, scale in enumerate(_progressive_scales_for_factor(upscale_factor, max_step_scale)):
            if upscale_factor > 1.0 + 1e-6:
                if scale <= 1.0 + 1e-6:
                    continue

                target_sigma = sigma_tuples[i + 1] if i + 1 < len(sigma_tuples) else sigma_tuples[-1]
                enter_sigma = target_sigma[0]
                new_h = max(8, round(H * scale / 8) * 8)
                new_w = max(8, round(W * scale / 8) * 8)

                if upscale_model is not None and vae is not None:
                    current_samples = _vae_roundtrip_upscale(
                        current_samples, upscale_model, vae, new_h, new_w,
                    )
                else:
                    sized = adjust_latent_size(
                        {"samples": current_samples}, factor=scale, target_size=(new_h, new_w),
                    )
                    current_samples = sized["samples"]

                current_eps = _locked_noise_from_prev(current_eps, (B, C, new_h, new_w),
                                                   _stage_seed(seed, i))

                current_samples = _stage_sample_with_sigmas(
                    model=model,
                    latent_image=current_samples,
                    noise=current_eps,
                    cfg=1.0,
                    sampler_obj=sampler_obj,
                    sigmas=target_sigma,
                    callback=None,
                    seed=_stage_seed(seed, i),
                    force_full_denoise=True,
                    conditioning=positive,
                    negative=negative,
                    sampler_name=sampler,
                )

        current_samples = _stage_sample_with_sigmas(
            model=refinement_model_obj,
            latent_image=current_samples,
            noise=current_eps,
            cfg=1.0,
            sampler_obj=sampler_obj,
            sigmas=sigma_tuples[-1] if sigma_tuples else (1.0, 0.0),
            callback=None,
            seed=_stage_seed(seed, 0, is_refinement=True),
            force_full_denoise=False,
            conditioning=positive,
            negative=negative,
            sampler_name=sampler,
        )

        if (current_samples.shape[-2], current_samples.shape[-1]) != (target_h, target_w):
            current_samples = comfy.utils.common_upscale(
                current_samples, target_w, target_h, "bilinear", "disabled",
            )

        return io.NodeOutput({"samples": current_samples})


def _progressive_scales_for_factor(upscale_factor: float, max_step_scale: float) -> list[float]:
    if upscale_factor <= 1.0:
        return [1.0]
    s = 1.0
    out = []
    while s < upscale_factor - 1e-6:
        s = min(s * max_step_scale, upscale_factor)
        out.append(s)
    return out


def _vae_roundtrip_upscale(samples: torch.Tensor, upscale_model, vae,
                            target_h: int, target_w: int) -> torch.Tensor:
    device = comfy.model_management.get_torch_device()
    img = vae.decode(samples.to(device))
    if img.shape[2] != target_h or img.shape[3] != target_w:
        img = _upscale_image_with_model(img.movedim(1, -1), upscale_model,
                                       target_h, target_w, device).movedim(-1, 1)
    encoded = vae.encode(img)
    if hasattr(encoded, "sample"):
        encoded = encoded.sample
    return encoded.to(samples.device, dtype=samples.dtype)