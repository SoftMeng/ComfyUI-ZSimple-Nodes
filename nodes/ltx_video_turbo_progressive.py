"""Z-LTX Video Turbo Progressive — AV latent sampler with arbitrary N-stage sigma pipe.

Multi-stage progressive sampling driven by `sigmas_pipe` (one sigma schedule
per line). The input av_latent is the FINAL resolution; per-stage working
scale is computed from the stage count so the model denoises at a coarser
resolution in early stages and refines to full size in the last stage.

Stage scale chain (user-defined):
  1 stage : [1.00]
  2 stages: [0.75, 1.00]
  3 stages: [0.50, 0.75, 1.00]
  4 stages: [0.50, 0.50, 0.75, 1.00]
  5 stages: [0.50, 0.50, 0.50, 0.75, 1.00]
  N >= 6  : [0.50] * (N - 3) + [0.75, 1.00]

The chain is selected by `upscale_model`:
  none: ignore the chain, every stage runs at the input (1.0) scale
  fast: apply the chain above

Inter-stage handoff: each stage runs to sigma=0 (denoised). The next stage's
entrance noise phase is seeded from the previous stage's x0 via
`_stage_handoff(video, audio, sigma_next, seed) = (1 - s) * x0 + s * noise`,
which matches the flow-matching blend `latent * (1 - s) + noise * s` that
ModelSamplingDiscreteFlow applies internally when sigma-scaling a fresh
input — so passing this blended tensor as both `noise` and `latent_image`
produces the same effective x0 that the model would see on a sigma-rescale
boundary (mirrors Z-Image `_noise_inverse` with sigma_target=next stage
first sigma).

Per-stage options (apply to every stage):
- SD3 CFG rescale (`guidance_rescale` > 0): debiases high-sigma CFG saturation.
- STG bundle (`enable_stg=True`).
- Modality Guidance bundle (`enable_modality_guidance=True`).
"""

from __future__ import annotations

import math
import re

import torch

from comfy_api.latest import io


_DISTILLED_DEFAULT_SIGMAS_PIPE = (
    "[1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]\n"
    "[0.909375, 0.725, 0.4219, 0.0]"
)


def _parse_sigmas_pipe(s: str) -> list[list[float]]:
    result = []
    for line in s.strip().splitlines():
        line = line.strip().strip("[]")
        if not line:
            continue
        sigmas = [float(x.strip()) for x in line.split(",") if x.strip()]
        result.append(sigmas)
    if not result:
        raise ValueError("sigmas_pipe is empty (no valid lines)")
    return result


def _stage_scale_chain(n: int) -> list[float]:
    """Per-stage working-scale chain (relative to the input latent's spatial size).

    Stage 0 always runs at the chain's first scale. The chain always ends
    at 1.0 so the final stage restores the input resolution. Intermediate
    scales repeat 0.50 for stability; the last two are 0.75 and 1.00.
    """
    if n <= 0:
        raise ValueError(f"stage count must be >= 1, got {n}")
    if n == 1:
        return [1.0]
    if n == 2:
        return [0.75, 1.0]
    if n == 3:
        return [0.5, 0.75, 1.0]
    if n == 4:
        return [0.5, 0.5, 0.75, 1.0]
    if n == 5:
        return [0.5, 0.5, 0.5, 0.75, 1.0]
    return [0.5] * (n - 3) + [0.75, 1.0]


def _validate_stage_sigmas(sigmas: list[float]) -> None:
    """Validate a single stage's sigma schedule.

    Constraints:
    - >= 2 values
    - monotonically non-increasing

    A stage may end at sigma_end > 0 (trajectory segmentation, Z-Image style);
    only the last pipe line must end at 0.0 (checked in validate_inputs).
    """
    if len(sigmas) < 2:
        raise ValueError(f"stage schedule must have >=2 sigmas, got {len(sigmas)}")
    for i in range(1, len(sigmas)):
        if sigmas[i] > sigmas[i - 1] + 1e-6:
            raise ValueError(
                f"sigmas must be monotonically non-increasing: "
                f"{sigmas[i-1]} -> {sigmas[i]} at index {i}"
            )


def _make_rescale_cfg_post_cfg(guidance_rescale: float):
    def post_cfg(args):
        denoised = args["denoised"]
        cond = args["cond_denoised"]
        sigma = args["sigma"]
        sigma_val = float(sigma[0].item()) if hasattr(sigma, "shape") else float(sigma)
        if sigma_val <= 0.5 or guidance_rescale <= 0.0:
            return denoised
        return denoised * guidance_rescale + cond * (1.0 - guidance_rescale)

    return post_cfg


def _make_stg_post_cfg(blocks_str: str):
    block_set = frozenset(int(b) for b in re.findall(r"\d+", blocks_str or ""))

    def post_cfg(args):
        if not block_set:
            return args["denoised"]

        sigma_ = float(args["sigma"][0].item())
        sigma_norm = max(0.0, min(1.0, sigma_))
        if sigma_norm < 0.5 or sigma_norm > 1.0:
            return args["denoised"]

        cond_pred = args["cond_denoised"]
        cfg_result = args["denoised"]
        x = args["input"]
        cond = args["cond"]

        import comfy.samplers

        model_options = args["model_options"].copy()
        transformer_options = model_options.get("transformer_options", {}).copy()
        transformer_options["stg_self_attn_blocks"] = block_set
        model_options["transformer_options"] = transformer_options

        (perturbed,) = comfy.samplers.calc_cond_batch(args["model"], [cond], x, args["sigma"], model_options)
        return cfg_result + (cond_pred - perturbed)

    return post_cfg


def _make_modality_post_cfg(modality_scale: float):
    def post_cfg(args):
        if math.isclose(modality_scale, 1.0):
            return args["denoised"]

        cond_pred = args["cond_denoised"]
        cfg_result = args["denoised"]
        x = args["input"]
        cond = args["cond"]

        import comfy.samplers

        model_options = args["model_options"].copy()
        transformer_options = model_options.get("transformer_options", {}).copy()
        transformer_options["a2v_cross_attn"] = False
        transformer_options["v2a_cross_attn"] = False
        model_options["transformer_options"] = transformer_options

        (mod_pred,) = comfy.samplers.calc_cond_batch(args["model"], [cond], x, args["sigma"], model_options)
        return cfg_result + (cond_pred - mod_pred) * (modality_scale - 1.0)

    return post_cfg


def _count_guide_frames(guider, video_shape) -> int:
    """Count appended guide latent frames from guider conditioning (LTXVAddGuide appends them at the temporal end).

    Mirrors `get_keyframe_idxs` in comfy_extras/nodes_lt.py — tokens_per_frame
    is `latent_shape[-2] * latent_shape[-1]` for SymmetricPatchifier(1).
    """
    conds = guider.original_conds
    _, _, _, H, W = video_shape
    tokens_per_frame = max(1, H * W)
    for c in conds.get("positive", []):
        kf = c.get("keyframe_idxs", None) if isinstance(c, dict) else None
        if kf is not None and kf.dim() >= 3 and kf.shape[2] > 0:
            n = kf.shape[2] // tokens_per_frame
            if n > 0:
                return n
    return 0


def _validate_av_samples(samples) -> tuple:
    """Validate NestedTensor with (video 5D, audio 4D). Returns (video, audio) or raises ValueError."""
    if not getattr(samples, "is_nested", False):
        shape_info = tuple(samples.shape) if hasattr(samples, "shape") else "?"
        raise ValueError(
            f"av_latent['samples'] must be a NestedTensor from LTXVConcatAVLatent; "
            f"got {type(samples).__name__} shape={shape_info}. "
            f"Wire upstream through LTXVConcatAVLatent (video_latent + audio_latent -> NestedTensor)."
        )
    parts = samples.unbind()
    if len(parts) != 2:
        raise ValueError(
            f"av_latent['samples'] NestedTensor must have exactly 2 streams (video + audio); got {len(parts)}."
        )
    video, audio = parts
    if video.ndim != 5:
        raise ValueError(
            f"video stream must be 5D [B, C, T, H, W]; got ndim={video.ndim} shape={tuple(video.shape)}."
        )
    if audio.ndim != 4:
        raise ValueError(
            f"audio stream must be 4D [B, C, T, F]; got ndim={audio.ndim} shape={tuple(audio.shape)}."
        )
    return video, audio


def _crop_guides(current_latent, guider):
    """Crop appended guide frames from the video stream (LTXVAddGuide appends them at the temporal end)."""
    import comfy.nested_tensor

    video, audio = _validate_av_samples(current_latent["samples"])
    n = _count_guide_frames(guider, video.shape)
    if n <= 0 or video.shape[2] <= n:
        return current_latent
    video = video[:, :, :-n]
    nm = current_latent.get("noise_mask", None)
    if nm is not None:
        if getattr(nm, "is_nested", False):
            v_nm, a_nm = nm.unbind()
            nm = comfy.nested_tensor.NestedTensor((v_nm[:, :, :-n], a_nm))
        else:
            nm = nm[:, :, :-n]
    out = {**current_latent, "samples": comfy.nested_tensor.NestedTensor((video, audio))}
    if nm is not None:
        out["noise_mask"] = nm
    return out


def _stage_handoff(video_5d: torch.Tensor, audio_4d: torch.Tensor,
                   sigma_next: float, seed: int):
    """Stage boundary noise-phase handoff (Z-Image _noise_inverse equivalent).

    Caller must pass a denoised (sigma=0) latent. Given stage i's x0 and the
    next stage's entrance sigma, return the (video, audio) pair to hand to
    the next sampler. The formula `(1 - s) * x0 + s * noise` matches the
    flow-matching blend that ModelSamplingDiscreteFlow applies internally
    when sigma-scaling a fresh input; passing this blended tensor as the
    next stage's noise gives the next sampler a noise-phase-aligned starting
    point instead of a re-rolled random one.
    """
    if sigma_next <= 0.0:
        return video_5d, audio_4d
    s = float(sigma_next)
    one_minus_s = 1.0 - s
    device = video_5d.device
    dtype = video_5d.dtype
    g_v = torch.Generator(device=device).manual_seed(int(seed))
    g_a = torch.Generator(device=device).manual_seed(int(seed) + 1)
    noise_v = torch.randn(video_5d.shape, generator=g_v, device=device, dtype=dtype)
    noise_a = torch.randn(audio_4d.shape, generator=g_a, device=device, dtype=dtype)
    return one_minus_s * video_5d + s * noise_v, one_minus_s * audio_4d + s * noise_a


def _resize_video_for_scale(video_5d: torch.Tensor, scale: float):
    """Bilinearly resize a 5D video latent to `scale` of its spatial dims, rounded to multiples of 8.

    Returns the input unchanged when scale == 1.0 or when the rounded
    target size already matches.
    """
    import comfy.utils

    if scale == 1.0:
        return video_5d
    _, _, _, H, W = video_5d.shape
    new_h = max(8, round(H * scale / 8) * 8)
    new_w = max(8, round(W * scale / 8) * 8)
    if new_h == H and new_w == W:
        return video_5d
    return comfy.utils.common_upscale(video_5d, new_w, new_h, "bilinear", "disabled")


def _scale_video_stream(samples_or_mask, scale: float):
    """Resize the video stream inside an AV samples / noise_mask NT(2). Audio stream unchanged."""
    import comfy.nested_tensor

    if not getattr(samples_or_mask, "is_nested", False):
        return _resize_video_for_scale(samples_or_mask, scale)
    video, audio = samples_or_mask.unbind()
    new_video = _resize_video_for_scale(video, scale)
    return comfy.nested_tensor.NestedTensor((new_video, audio))


class ZLTXVideoTurboProgressive(io.ComfyNode):

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ZLTXVideoTurboProgressive",
            display_name="Z-LTX Video Turbo Progressive",
            category="ZSimple-Nodes/sampling",
            description="AV latent sampler driven by an N-stage sigma pipe. Each line of sigmas_pipe is one stage's sigma schedule; the previous stage's denoised output is mixed with fresh noise (Z-Image _noise_inverse) for the next stage's entrance. Per-stage working scale (upscale_model=fast): 1 stage=[1.00], 2=[0.75,1.00], 3=[0.50,0.75,1.00], 4=[0.50,0.50,0.75,1.00], 5=[0.50,0.50,0.50,0.75,1.00], N>=6=[0.50]*(N-3)+[0.75,1.00].",
            inputs=[
                io.Model.Input("model", tooltip="For latent preview callback."),
                io.Guider.Input("guider", tooltip="Pre-built Guider from upstream CFGGuider / DualCFGGuider node."),
                io.Latent.Input("av_latent", tooltip="NestedTensor AV latent at the final resolution. Wire upstream through LTXVConcatAVLatent."),
                io.Sampler.Input("sampler_obj"),
                io.String.Input("sigmas_pipe", multiline=True, default=_DISTILLED_DEFAULT_SIGMAS_PIPE,
                                 tooltip="One sigma schedule per line; each line is one stage. Intermediate lines may stop at sigma>0 (trajectory segmentation: coarse-denoise -> upscale -> continue). If the next line's first sigma equals the previous line's last sigma, the noisy latent continues exactly; a jump re-noises fresh (keep jumps <= ~0.05). Only the LAST line must end at 0.0."),
                io.Combo.Input("upscale_model", options=["none", "fast"], default="fast",
                                tooltip="none: every stage runs at the input (1.0) scale. fast: apply the per-stage scale chain so the model denoises at a coarser resolution in early stages and refines to full size in the last stage. The chain is derived from the number of sigmas_pipe lines."),
                io.Float.Input("guidance_rescale", default=0.7, min=0.0, max=1.0, step=0.05,
                                tooltip="SD3-style CFG rescale (Lin et al. 2024). 0 disables. Applied per stage."),
                io.Boolean.Input("enable_stg", default=False,
                                  tooltip="Auto-bundle Spatio-Temporal Guidance as a post_cfg_function for every stage."),
                io.Boolean.Input("enable_modality_guidance", default=False,
                                  tooltip="Auto-bundle Modality Guidance as a post_cfg_function for every stage."),
                io.String.Input("stg_blocks", default="29", tooltip="STG self-attention block indices (comma-separated)."),
                io.Float.Input("modality_scale", default=3.0, min=1.0, max=10.0, step=0.1,
                                tooltip="Modality guidance scale. 1.0 disables."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF),
            ],
            outputs=[
                io.Latent.Output("latent", tooltip="Sampled AV latent (NestedTensor). Downstream LTXVSeparateAVLatent splits into video + audio."),
            ],
        )

    @classmethod
    def validate_inputs(cls, **kwargs) -> bool | str:
        av_latent = kwargs.get("av_latent")
        if av_latent is not None:
            try:
                _validate_av_samples(av_latent["samples"])
            except Exception as e:
                return f"[ZLTXVideoTurboProgressive] av_latent: {e}"

        pipe_str = kwargs.get("sigmas_pipe") or ""
        try:
            stages_sigmas = _parse_sigmas_pipe(pipe_str)
        except Exception as e:
            return f"[ZLTXVideoTurboProgressive] sigmas_pipe parse error: {e}"
        for idx, stage_sigmas in enumerate(stages_sigmas):
            try:
                _validate_stage_sigmas(stage_sigmas)
            except Exception as e:
                return f"[ZLTXVideoTurboProgressive] sigmas_pipe stage {idx}: {e}"

        n_stages = len(stages_sigmas)
        if stages_sigmas[-1][-1] != 0.0:
            return (f"[ZLTXVideoTurboProgressive] only the last sigmas_pipe line must end at 0.0 "
                    f"(line {n_stages - 1} ends at {stages_sigmas[-1][-1]}). Intermediate lines may "
                    f"stop at sigma>0 for trajectory segmentation.")
        if n_stages >= 1:
            if abs(stages_sigmas[0][0] - 1.0) > 1e-6:
                return (f"[ZLTXVideoTurboProgressive] sigmas_pipe stage 0 must start at 1.0 (full noise), "
                        f"got {stages_sigmas[0][0]}.")
            for idx, s in enumerate(stages_sigmas[1:], start=1):
                if s[0] > 1.0 + 1e-6 or s[0] < 0.0:
                    return (f"[ZLTXVideoTurboProgressive] sigmas_pipe stage {idx} first sigma must be in [0, 1], "
                            f"got {s[0]}.")

        return True

    @classmethod
    def execute(
        cls,
        model,
        guider,
        av_latent,
        sampler_obj,
        sigmas_pipe: str = _DISTILLED_DEFAULT_SIGMAS_PIPE,
        upscale_model: str = "fast",
        guidance_rescale: float = 0.7,
        enable_stg: bool = False,
        enable_modality_guidance: bool = False,
        stg_blocks: str = "29",
        modality_scale: float = 3.0,
        seed: int = 0,
    ) -> io.NodeOutput:
        import comfy.sample
        import comfy.utils
        import comfy.nested_tensor
        import latent_preview

        stages_sigmas = _parse_sigmas_pipe(sigmas_pipe)
        n_stages = len(stages_sigmas)
        scale_chain = _stage_scale_chain(n_stages) if upscale_model == "fast" else [1.0] * n_stages

        _validate_av_samples(av_latent["samples"])

        current_latent = av_latent
        for i, (stage_sigmas, scale) in enumerate(zip(stages_sigmas, scale_chain)):
            if scale != 1.0:
                current_latent = {**current_latent,
                                   "samples": _scale_video_stream(current_latent["samples"], scale)}
                if current_latent.get("noise_mask") is not None:
                    current_latent["noise_mask"] = _scale_video_stream(current_latent["noise_mask"], scale)
                _validate_av_samples(current_latent["samples"])

            sigmas = torch.tensor(stage_sigmas, dtype=torch.float32)
            prev_end = stages_sigmas[i - 1][-1] if i > 0 else None
            exact_handoff = (
                prev_end is not None
                and prev_end > 1e-6
                and abs(stage_sigmas[0] - prev_end) <= 1e-6
            )

            if i == 0:
                latent_image = current_latent["samples"]
                noise = comfy.sample.prepare_noise(latent_image, seed + i, None)
            elif exact_handoff:
                latent_image = current_latent["samples"]
                noise = latent_image
            else:
                video_x0, audio_x0 = _validate_av_samples(current_latent["samples"])
                prev_sigma_end = float(stages_sigmas[i - 1][-1])
                if prev_sigma_end > 1e-6:
                    # Trajectory segmentation: the previous stage stopped at sigma>0.
                    # Rescale the still-noisy latent back to its x0 estimate so the
                    # handoff formula below operates on clean input.
                    ms = model.model_sampling
                    sigma_t = torch.tensor([prev_sigma_end], device=video_x0.device, dtype=video_x0.dtype)
                    video_x0 = ms.calculate_input(sigma_t, video_x0)
                    audio_x0 = ms.calculate_input(sigma_t, audio_x0)
                sigma_next = float(stage_sigmas[0])
                video_next, audio_next = _stage_handoff(
                    video_x0, audio_x0, sigma_next, seed + i + 100
                )
                latent_image = comfy.nested_tensor.NestedTensor((video_next, audio_next))
                noise = latent_image

            patched_model = cls._patch_model(
                model=model,
                stage_index=i,
                guidance_rescale=guidance_rescale,
                enable_stg=enable_stg,
                enable_modality_guidance=enable_modality_guidance,
                stg_blocks=stg_blocks,
                modality_scale=modality_scale,
            )
            callback = latent_preview.prepare_callback(patched_model, max(1, len(sigmas) - 1))
            denoise_mask = current_latent.get("noise_mask", None)
            out = guider.sample(
                noise=noise,
                latent_image=latent_image,
                sampler=sampler_obj,
                sigmas=sigmas,
                denoise_mask=denoise_mask,
                callback=callback,
                disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
                seed=seed + i,
            )
            video, audio = _validate_av_samples(out)
            current_latent = {"samples": comfy.nested_tensor.NestedTensor((video, audio))}
            if denoise_mask is not None:
                current_latent["noise_mask"] = denoise_mask

        current_latent = _crop_guides(current_latent, guider)
        return io.NodeOutput({"samples": current_latent["samples"]})

    @classmethod
    def _patch_model(
        cls,
        *,
        model,
        stage_index,
        guidance_rescale,
        enable_stg,
        enable_modality_guidance,
        stg_blocks,
        modality_scale,
    ):
        patched_model = model
        if guidance_rescale > 0.0:
            try:
                patched_model = model.clone()
                patched_model.set_model_sampler_post_cfg_function(
                    _make_rescale_cfg_post_cfg(guidance_rescale)
                )
            except Exception as e:
                print(f"[ZLTXVT] WARNING: guidance_rescale post_cfg not applied ({e}); stage {stage_index} runs unpatched")
                patched_model = model

        if enable_stg:
            try:
                if patched_model is model:
                    patched_model = model.clone()
                patched_model.set_model_sampler_post_cfg_function(_make_stg_post_cfg(stg_blocks))
            except Exception as e:
                print(f"[ZLTXVT] WARNING: STG post_cfg not applied ({e}); stage {stage_index} runs without STG")

        if enable_modality_guidance and not math.isclose(modality_scale, 1.0):
            try:
                if patched_model is model:
                    patched_model = model.clone()
                patched_model.set_model_sampler_post_cfg_function(
                    _make_modality_post_cfg(modality_scale)
                )
            except Exception as e:
                print(f"[ZLTXVT] WARNING: modality guidance post_cfg not applied ({e}); stage {stage_index} runs without it")

        return patched_model
