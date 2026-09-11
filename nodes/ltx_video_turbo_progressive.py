"""Z-LTX Video Turbo Progressive — LTX2.5 2-stage progressive video sampler.

Wraps 2 native ComfyUI operators (no image/audio preprocessing, no zimage-specific
mechanisms): stage1 euler_ancestral @ 0.5x spatial → LTXVLatentUpsampler x2 →
stage2 sa_solver @ 1.0x. Conditioning comes pre-encoded; image / audio preprocessing
and σ schedule are upstream nodes — see examples/.
"""

from __future__ import annotations

import logging

import torch
import torch.nn.functional as F

from comfy_api.latest import io

import comfy.utils

logger = logging.getLogger(__name__)


SIGMA_PRESETS: dict[str, dict[str, list[float]]] = {
    "distilled_default": {
        "stage1": [1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0],
        "stage2": [0.85, 0.725, 0.4219, 0.0],
    },
}


_LATENT_SCALING_VIDEO: dict[str, tuple[float, float]] = {
    "fast": (0.5, 1.0),
    "quality": (0.5, 1.0),
    "aggressive": (0.25, 1.0),
    "none": (1.0, 1.0),
}


_SAMPLER_CACHE: dict[str, object] = {}


def _cached_sampler(name: str):
    import comfy.samplers
    s = _SAMPLER_CACHE.get(name)
    if s is None:
        s = comfy.samplers.sampler_object(name)
        _SAMPLER_CACHE[name] = s
    return s


def _round_to_32(n: int) -> int:
    if n <= 0:
        return 0
    return ((n + 31) // 32) * 32


def _adjust_video_latent_size(latent: dict, factor: float) -> dict:
    samples = latent["samples"]
    B, C, T, H, W = samples.shape
    new_H_lat = max(2, _round_to_32(round(H * factor) * 32) // 32)
    new_W_lat = max(2, _round_to_32(round(W * factor) * 32) // 32)
    reshaped = samples.reshape(B * T, C, H, W)
    upscaled = comfy.utils.common_upscale(reshaped, new_W_lat, new_H_lat, "bilinear", "disabled")
    new_samples = upscaled.reshape(B, C, T, new_H_lat, new_W_lat)
    return {**latent, "samples": new_samples}


class ZLTXVideoTurboProgressive(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ZLTXVideoTurboProgressive",
            display_name="Z-LTX Video Turbo Progressive",
            category="ZSimple-Nodes/sampling",
            inputs=[
                io.Model.Input("model"),
                io.Vae.Input("vae_video"),
                io.Conditioning.Input("positive_cond"),
                io.Conditioning.Input("negative_cond"),
                io.Latent.Input("video_latent"),
                io.LatentUpscaleModel.Input("latent_upscale_model"),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF),
                io.Latent.Input("audio_latent", optional=True),
                io.Sampler.Input("sampler_s1"),
                io.Sampler.Input("sampler_s2"),
                io.Int.Input("steps_s1", default=8, min=1, max=20),
                io.Int.Input("steps_s2", default=3, min=1, max=10),
                io.Float.Input("video_cfg", default=1.0),
                io.Float.Input("audio_cfg", default=1.0),
                io.Combo.Input(
                    "latent_scaling",
                    options=["fast", "quality", "aggressive", "none"],
                    default="quality",
                ),
                io.Combo.Input(
                    "stages",
                    options=["auto_2stage", "stage1_only", "stage2_only"],
                    default="auto_2stage",
                ),
            ],
            outputs=[
                io.Latent.Output("latent_video"),
                io.Latent.Output("latent_audio"),
            ],
        )

    @classmethod
    def validate_inputs(cls, **kwargs) -> bool | str:
        steps_s1 = kwargs.get("steps_s1", 8)
        if steps_s1 is not None and not (1 <= int(steps_s1) <= 20):
            return f"[ZLTXVideoTurboProgressive] steps_s1 must be 1-20. Got {steps_s1}."
        steps_s2 = kwargs.get("steps_s2", 3)
        if steps_s2 is not None and not (1 <= int(steps_s2) <= 10):
            return f"[ZLTXVideoTurboProgressive] steps_s2 must be 1-10. Got {steps_s2}."
        latent_scaling = kwargs.get("latent_scaling", "quality")
        if latent_scaling not in {"fast", "quality", "aggressive", "none"}:
            return f"[ZLTXVideoTurboProgressive] latent_scaling must be one of fast/quality/aggressive/none."
        return True

    def _fit_audio(self, reference, audio, noise_mask):
        dims = [i for i in range(reference.ndim) if reference.shape[i] != audio.shape[i]]
        if len(dims) == 0:
            return audio, noise_mask
        if len(dims) > 1 or dims[0] < 2:
            raise ValueError(
                f"audio latent {tuple(audio.shape)} cannot be fitted to {tuple(reference.shape)}"
            )
        dim = dims[0]
        length = reference.shape[dim]
        if noise_mask is not None:
            noise_mask = comfy.utils.reshape_mask(noise_mask, audio.shape)
        if audio.shape[dim] > length:
            audio = audio.narrow(dim, 0, length)
            if noise_mask is not None:
                noise_mask = noise_mask.narrow(dim, 0, length)
        else:
            pad = torch.zeros_like(audio.narrow(dim, 0, 1)).repeat(
                [length - audio.shape[dim] if i == dim else 1 for i in range(audio.ndim)]
            )
            audio = torch.cat([audio, pad], dim=dim)
            if noise_mask is not None:
                noise_mask = torch.cat([noise_mask, torch.ones_like(pad)], dim=dim)
        return audio, noise_mask

    def _concat_av(self, video_latent, audio_latent):
        import comfy.nested_tensor
        output = {}
        output.update(video_latent)
        output.update(audio_latent)
        vs = video_latent["samples"]
        as_ = audio_latent["samples"]
        vm = video_latent.get("noise_mask", None)
        am = audio_latent.get("noise_mask", None)
        if getattr(vs, "is_nested", False):
            streams = vs.unbind()
            vs = streams[0]
            if vm is not None:
                vm = vm.unbind()[0]
            as_, am = self._fit_audio(streams[1], as_, am)
        if vm is not None or am is not None:
            if vm is None:
                vm = torch.ones_like(vs)
            if am is None:
                am = torch.ones_like(as_)
            output["noise_mask"] = comfy.nested_tensor.NestedTensor((vm, am))
        output["samples"] = comfy.nested_tensor.NestedTensor((vs, as_))
        return output

    def _separate_av(self, av_latent):
        latents = av_latent["samples"].unbind()
        video_latent = av_latent.copy()
        video_latent["samples"] = latents[0]
        audio_latent = av_latent.copy()
        audio_latent["samples"] = latents[1]
        if av_latent.get("noise_mask", None) is not None:
            masks = av_latent["noise_mask"].unbind()
            video_latent["noise_mask"] = masks[0]
            audio_latent["noise_mask"] = masks[1]
        return video_latent, audio_latent

    def _upscale_latent(self, video_latent, upscale_model, vae_video):
        import math
        from comfy import model_management
        device = upscale_model.load_device
        model = upscale_model.model
        model_dtype = upscale_model.model_dtype()
        latents = video_latent["samples"]
        input_dtype = latents.dtype
        memory_required = math.prod(latents.shape) * 3000.0
        model_management.load_models_gpu([upscale_model], memory_required=memory_required)
        latents = latents.to(dtype=model_dtype, device=device)
        stats = vae_video.first_stage_model.per_channel_statistics
        latents = stats.un_normalize(latents)
        upsampled = model(latents)
        upsampled = stats.normalize(upsampled)
        upsampled = upsampled.to(
            dtype=input_dtype, device=model_management.intermediate_device()
        )
        out = video_latent.copy()
        out["samples"] = upsampled
        out.pop("noise_mask", None)
        return out

    def _sample(self, model, positive, negative, av_latent, sigmas_list, sampler_obj,
                seed, cfg_video, cfg_audio):
        # V3 schema passes sampler_s1/sampler_s2 as KSAMPLER objects (sockets),
        # not strings. Pass directly to comfy.sample.sample_custom.
        sigmas = torch.tensor(sigmas_list, dtype=torch.float32)
        device = comfy.model_management.get_torch_device()
        x0 = av_latent["samples"].to(device)
        eps = comfy.sample.prepare_noise(x0, seed, None)
        import latent_preview as _lp
        callback = _lp.prepare_callback(model, max(1, len(sigmas) - 1))
        cfg = cfg_video if cfg_video == cfg_audio else cfg_video
        samples = comfy.sample.sample_custom(
            model, eps, cfg, sampler_obj, sigmas,
            positive, negative, x0,
            noise_mask=None, callback=callback,
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
            seed=seed,
        )
        samples = samples.to(comfy.model_management.intermediate_device())
        return {"samples": samples}

    def _run_stage(self, *, model, positive_cond, negative_cond, video_latent, audio_latent,
                   sampler_obj, seed, video_cfg, audio_cfg, sigmas):
        if audio_latent is None:
            av = video_latent
        else:
            av = self._concat_av(video_latent, audio_latent)
        out = self._sample(
            model, positive_cond, negative_cond, av, sigmas,
            sampler_obj, seed, video_cfg, audio_cfg,
        )
        if audio_latent is None:
            return out, {"samples": None}
        v, a = self._separate_av(out)
        return v, a

    @classmethod
    def execute(
        cls,
        model,
        vae_video,
        positive_cond,
        negative_cond,
        video_latent,
        latent_upscale_model,
        seed,
        audio_latent=None,
        sampler_s1="euler_ancestral",
        sampler_s2="sa_solver",
        steps_s1=8,
        steps_s2=3,
        video_cfg=1.0,
        audio_cfg=1.0,
        latent_scaling="quality",
        stages="auto_2stage",
    ) -> io.NodeOutput:
        # V3 schema requires execute to be a classmethod.
        self = cls()

        logger.info(
            "[ZLTXVideoTurboProgressive] start stages=%s s1=%d s2=%d scaling=%s",
            stages, steps_s1, steps_s2, latent_scaling,
        )

        scale_factor_s1, _ = _LATENT_SCALING_VIDEO[latent_scaling]

        if stages == "stage2_only":
            v_in = video_latent
        else:
            v_in = _adjust_video_latent_size(video_latent, scale_factor_s1)

        if stages in ("auto_2stage", "stage1_only"):
            v1, a1 = self._run_stage(
                model=model,
                positive_cond=positive_cond,
                negative_cond=negative_cond,
                video_latent=v_in,
                audio_latent=audio_latent,
                sampler_obj=sampler_s1,
                seed=seed,
                video_cfg=video_cfg,
                audio_cfg=audio_cfg,
                sigmas=SIGMA_PRESETS["distilled_default"]["stage1"],
            )
        else:
            v1, a1 = v_in, audio_latent

        if stages == "stage1_only":
            return io.NodeOutput(v1, a1 or {"samples": None})

        if latent_scaling != "none":
            v_upscaled = self._upscale_latent(v1, latent_upscale_model, vae_video)
        else:
            v_upscaled = v1

        v2, a2 = self._run_stage(
            model=model,
            positive_cond=positive_cond,
            negative_cond=negative_cond,
            video_latent=v_upscaled,
            audio_latent=a1 if audio_latent is not None else None,
            sampler_obj=sampler_s2,
            seed=seed + 1,
            video_cfg=video_cfg,
            audio_cfg=audio_cfg,
            sigmas=SIGMA_PRESETS["distilled_default"]["stage2"],
        )
        return io.NodeOutput(v2, a2 or {"samples": None})
