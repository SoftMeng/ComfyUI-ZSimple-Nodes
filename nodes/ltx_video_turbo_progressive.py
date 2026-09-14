"""Z-LTX Video Turbo Progressive — AV latent sampler with arbitrary N-stage σ-pipe.

Multi-stage progressive sampling via `sigmas_pipe` (one sigma schedule per line).
Each stage's output is re-noised (by the sampler) and fed to the next stage as
its clean latent_image, enabling iterative refinement à la Karras EDM
stochastic churn / SD3 resample / SDXL refiner.

Per-stage options (apply to every stage):
- A. SD3-style CFG rescale (`guidance_rescale` > 0): debiases high-σ CFG
    saturation.
- B. per_frame_path validation (`enforce_per_frame_path=True`): reject latents
    whose noise_mask forces `has_spatial_mask=True` in
    `_prepare_timestep` (`comfy/ldm/lightricks/av_model.py:738-848`).
- C. STG bundle (`enable_stg=True`): auto-inject `LTXVSpatioTemporalGuidance`
    (`comfy_extras/nodes_lt.py:940-990`) as a post_cfg_function.
- D. Modality Guidance bundle (`enable_modality_guidance=True`):
    auto-inject `LTXVModalityGuidance` (`nodes_lt.py:994-1050`).

Per-stage upscale (`upscale_modes`):
- "interpolate": pure F.interpolate in latent space (zero new model deps).
- "vae_roundtrip": VAE decode → bilinear pixel upscale → VAE encode.
- "external" is rejected for stages other than the first (inter-stage upscale
    must happen in-node when running N>1 stages in one call).
"""

from __future__ import annotations

import math
import re

import torch
import torch.nn.functional as F

from comfy_api.latest import io


_LTXV_DEFAULT_MAX_SHIFT = 2.05
_LTXV_DEFAULT_BASE_SHIFT = 0.95
_LTXV_DEFAULT_X1 = 1024
_LTXV_DEFAULT_X2 = 4096

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


def _parse_upscale_modes(s: str, n_stages: int) -> list[str]:
    modes = [m.strip() for m in s.split(",") if m.strip()]
    if len(modes) == 1:
        modes = modes * n_stages
    elif len(modes) != n_stages:
        raise ValueError(
            f"upscale_modes has {len(modes)} entries but sigmas_pipe has "
            f"{n_stages} stages (need 1 or {n_stages})"
        )
    for m in modes:
        if m not in ("external", "interpolate", "vae_roundtrip"):
            raise ValueError(
                f"unknown upscale_mode '{m}' (must be external/interpolate/vae_roundtrip)"
            )
    return modes


def _validate_stage_sigmas(sigmas: list[float]) -> None:
    """Validate a single stage's σ schedule.

    Constraints:
    - ≥ 2 values
    - monotonically non-increasing

    A stage may end at σ_end > 0 (trajectory segmentation, Z-Image style);
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


def _make_rescale_cfg_post_cfg(guidance_rescale: float, threshold: float = 0.5):
    def post_cfg(args):
        denoised = args["denoised"]
        cond = args["cond_denoised"]
        sigma = args["sigma"]
        sigma_val = float(sigma[0].item()) if hasattr(sigma, "shape") else float(sigma)
        if sigma_val <= threshold or guidance_rescale <= 0.0:
            return denoised
        return denoised * guidance_rescale + cond * (1.0 - guidance_rescale)

    return post_cfg


def _make_stg_post_cfg(blocks_str: str, scale: float, start_percent: float = 0.0, end_percent: float = 0.5):
    block_set = frozenset(int(b) for b in re.findall(r"\d+", blocks_str or ""))

    def post_cfg(args):
        if scale == 0 or not block_set:
            return args["denoised"]

        sigma_ = float(args["sigma"][0].item())
        sigma_norm = max(0.0, min(1.0, sigma_))
        if sigma_norm < (1.0 - end_percent) or sigma_norm > (1.0 - start_percent):
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
        return cfg_result + (cond_pred - perturbed) * scale

    return post_cfg


def _make_modality_post_cfg(modality_scale: float, start_percent: float = 0.0, end_percent: float = 1.0):
    def post_cfg(args):
        if math.isclose(modality_scale, 1.0):
            return args["denoised"]

        sigma_ = float(args["sigma"][0].item())
        sigma_norm = max(0.0, min(1.0, sigma_))
        if sigma_norm < (1.0 - end_percent) or sigma_norm > (1.0 - start_percent):
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


def _spatial_mask_present(av_latent) -> bool:
    mask = av_latent.get("noise_mask", None)
    if mask is None:
        return False
    if getattr(mask, "is_nested", False):
        mask = mask.unbind()[0]
    if not hasattr(mask, "shape"):
        return False
    shape = tuple(mask.shape)
    if len(shape) == 5:
        return shape[-2] != 1 or shape[-1] != 1
    if len(shape) == 3:
        return shape[-2] != 1 or shape[-1] != 1
    if len(shape) == 2:
        return shape[-1] != 1
    return True


def _count_guide_frames(guider, video_shape) -> int:
    """Count appended guide latent frames from guider conditioning (LTXVAddGuide appends them at the temporal end).

    Mirrors get_keyframe_idxs logic from comfy_extras/nodes_lt.py — tokens_per_frame
    is (H//2)*(W//2) for the SymmetricPatchifier's (1,2,2) patch size.
    """
    conds = getattr(guider, "original_conds", None) or getattr(guider, "conds", None) or {}
    _, _, _, H, W = video_shape
    tokens_per_frame = max(1, H * W)
    for c in conds.get("positive", []):
        kf = None
        if isinstance(c, dict):
            kf = c.get("keyframe_idxs", None)
        if kf is not None and getattr(kf, "numel", lambda: 0)() > 0 and kf.dim() >= 3:
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


def _crop_guides(current_latent, guider, clear_conds=False, resize_keyframe_tokens=None):
    """Crop appended guide frames from the video stream (LTXVAddGuide appends them at the temporal end).

    clear_conds=True nulls keyframe_idxs/guide_attention_entries entirely — used when the
    reference should be dropped (e.g. the inter-stage upscale is so destructive that the
    pre-upscale attention map no longer applies). Reference influence from the previous
    stage remains only as baked-in latent structure.

    resize_keyframe_tokens=int scales the recorded token count in-place to match a new
    spatial resolution: multiplies both keyframe_idxs tokens AND each
    guide_attention_entry["pre_filter_count"] by the given factor. Used after an inter-stage
    upscale so the model's per-frame token-count divisibility check
    (comfy/ldm/lightricks/model.py:1122) passes while keeping the reference frame intact at
    the same temporal position. The factor should be (new_H*new_W) / (old_H*old_W).
    """
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
    for key in ("positive", "negative"):
        for c in getattr(guider, "original_conds", {}).get(key, []):
            if not isinstance(c, dict):
                continue
            if clear_conds:
                c["keyframe_idxs"] = None
                c["guide_attention_entries"] = None
            elif resize_keyframe_tokens and resize_keyframe_tokens > 1:
                kf = c.get("keyframe_idxs")
                if kf is not None and kf.shape[2] > 0:
                    cur_tok = kf.shape[2]
                    want_tok = cur_tok * resize_keyframe_tokens
                    pad = want_tok - cur_tok
                    if pad > 0:
                        # Replicate last guide token `pad` times so the spatial coord stays
                        # valid for the new resolution; the model only requires divisibility.
                        last = kf[:, :, -1:, :]
                        tail = last.expand(-1, -1, pad, -1)
                        c["keyframe_idxs"] = torch.cat([kf, tail], dim=2)
                entries = c.get("guide_attention_entries")
                if entries:
                    for e in entries:
                        if "pre_filter_count" in e:
                            e["pre_filter_count"] *= resize_keyframe_tokens
    return out


def _upscale_interpolate(av_latent, vae_video):
    import comfy.nested_tensor

    samples = av_latent["samples"]
    stats = vae_video.first_stage_model.per_channel_statistics

    def _interp(t):
        # t: (B, C, T, H, W) latent. F.interpolate bilinear is 4D-only; collapse to (B*T, C, H, W),
        # upsample, restore (B, C, T, H', W'). Time dim kept untouched.
        u = stats.un_normalize(t)
        B, C, T, H, W = u.shape
        u_4d = u.permute(0, 2, 1, 3, 4).reshape(B * T, C, H, W)
        u_up = F.interpolate(u_4d, scale_factor=(2, 2), mode="bilinear", align_corners=False)
        u_up = u_up.reshape(B, T, C, u_up.shape[-2], u_up.shape[-1]).permute(0, 2, 1, 3, 4)
        return stats.normalize(u_up)

    if getattr(samples, "is_nested", False):
        v_stream, a_stream = samples.unbind()
        new_samples = comfy.nested_tensor.NestedTensor((_interp(v_stream), a_stream))
    else:
        new_samples = _interp(samples)
    return {**av_latent, "samples": new_samples}


def _upscale_vae_roundtrip(av_latent, vae_video):
    import comfy.nested_tensor

    samples = av_latent["samples"]
    fs_model = vae_video.first_stage_model

    def _roundtrip(t):
        pixels = fs_model.decode(t)
        pixels_up = F.interpolate(pixels, scale_factor=(1, 2, 2), mode="bilinear")
        return fs_model.encode(pixels_up)

    if getattr(samples, "is_nested", False):
        v_stream, a_stream = samples.unbind()
        new_samples = comfy.nested_tensor.NestedTensor((_roundtrip(v_stream), a_stream))
    else:
        new_samples = _roundtrip(samples)
    return {**av_latent, "samples": new_samples}


class ZLTXVideoTurboProgressive(io.ComfyNode):

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ZLTXVideoTurboProgressive",
            display_name="Z-LTX Video Turbo Progressive",
            category="ZSimple-Nodes/sampling",
            description="AV latent sampler driven by an N-stage sigma pipe. Each line of sigmas_pipe is one stage's σ schedule; the previous stage's output is re-noised (by the sampler) and fed to the next as clean latent_image. Per-stage upscale via upscale_modes.",
            inputs=[
                io.Model.Input("model", tooltip="For latent preview callback."),
                io.Guider.Input("guider", tooltip="Pre-built Guider from upstream CFGGuider / DualCFGGuider node."),
                io.Latent.Input("av_latent", tooltip="NestedTensor AV latent from upstream LTXVConcatAVLatent."),
                io.Sampler.Input("sampler_obj"),
                io.String.Input("sigmas_pipe", multiline=True, default=_DISTILLED_DEFAULT_SIGMAS_PIPE,
                                 tooltip="One sigma schedule per line; each line is one stage. Intermediate lines may stop at sigma>0 (trajectory segmentation: coarse-denoise -> upscale -> continue). If the next line's first sigma equals the previous line's last sigma, the noisy latent continues exactly; a jump re-noises fresh (keep jumps <= ~0.05). Only the LAST line must end at 0.0."),
                io.String.Input("upscale_modes", default="external",
                                 tooltip="Per-stage upscale mode, comma-separated matching sigmas_pipe lines (e.g. 'external,interpolate,vae_roundtrip'). Single value broadcasts to all stages. 'external' is only valid for stage 0."),
                io.Vae.Input("vae_video", optional=True,
                              tooltip="Required when any upscale_mode is 'interpolate' or 'vae_roundtrip'."),
                io.LatentUpscaleModel.Input("upscale_model", optional=True, tooltip="Reserved."),
                io.Float.Input("guidance_rescale", default=0.7, min=0.0, max=1.0, step=0.05,
                                tooltip="SD3-style CFG rescale (Lin et al. 2024). 0 disables. Applied per stage."),
                io.Boolean.Input("enforce_per_frame_path", default=False,
                                  tooltip="Reject latents whose noise_mask forces has_spatial_mask=True; triggers per_frame_path in _prepare_timestep."),
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

        if kwargs.get("enforce_per_frame_path"):
            if av_latent is not None and _spatial_mask_present(av_latent):
                return ("[ZLTXVideoTurboProgressive] enforce_per_frame_path=True requires a purely "
                        "temporal noise_mask, but the supplied latent's noise_mask has spatial extent.")

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
        modes_str = kwargs.get("upscale_modes", "external")
        try:
            modes = _parse_upscale_modes(modes_str, n_stages)
        except Exception as e:
            return f"[ZLTXVideoTurboProgressive] upscale_modes: {e}"

        if any(m == "external" for m in modes[1:]):
            pass  # "external" between in-node stages is a no-op (no upscale); user may wire externally via separate node calls if desired

        return True

    @classmethod
    def execute(
        cls,
        model,
        guider,
        av_latent,
        sampler_obj,
        sigmas_pipe: str = _DISTILLED_DEFAULT_SIGMAS_PIPE,
        upscale_modes: str = "external",
        vae_video=None,
        upscale_model=None,
        guidance_rescale: float = 0.7,
        enforce_per_frame_path: bool = False,
        enable_stg: bool = False,
        enable_modality_guidance: bool = False,
        stg_blocks: str = "29",
        modality_scale: float = 3.0,
        seed: int = 0,
    ) -> io.NodeOutput:
        import comfy.sample
        import comfy.utils
        import latent_preview

        _ = upscale_model  # reserved, no-op
        _ = enforce_per_frame_path  # validated above

        stages_sigmas = _parse_sigmas_pipe(sigmas_pipe)
        stages_modes = _parse_upscale_modes(upscale_modes, len(stages_sigmas))

        _validate_av_samples(av_latent["samples"])

        current_latent = av_latent
        for i, (stage_sigmas, mode) in enumerate(zip(stages_sigmas, stages_modes)):
            if i > 0:
                if mode in ("interpolate", "vae_roundtrip") and vae_video is None:
                    raise ValueError(
                        f"[ZLTXVideoTurboProgressive] stage {i} upscale_mode '{mode}' requires the "
                        f"vae_video input; connect a VAE (e.g. from LTXVAddGuide / VAE Loader)."
                    )
                current_latent = _crop_guides(current_latent, guider, clear_conds=True)
                if mode == "interpolate":
                    current_latent = _upscale_interpolate(current_latent, vae_video)
                elif mode == "vae_roundtrip":
                    current_latent = _upscale_vae_roundtrip(current_latent, vae_video)
                _validate_av_samples(current_latent["samples"])

            sigmas = torch.tensor(stage_sigmas, dtype=torch.float32)
            prev_end = stages_sigmas[i - 1][-1] if i > 0 else None
            if prev_end is not None and prev_end > 1e-6 and abs(stage_sigmas[0] - prev_end) <= 1e-6:
                # Exact trajectory continuation: under the flow-matching blend
                # x = latent*(1-s0) + noise*s0, noise == latent is the identity,
                # so the still-noisy latent passes through unchanged.
                noise = current_latent["samples"]
            else:
                noise = comfy.sample.prepare_noise(current_latent["samples"], seed + i, None)
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
                latent_image=current_latent["samples"],
                sampler=sampler_obj,
                sigmas=sigmas,
                denoise_mask=denoise_mask,
                callback=callback,
                disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
                seed=seed + i,
            )
            video, audio = _validate_av_samples(out)
            import comfy.nested_tensor
            current_latent = {"samples": comfy.nested_tensor.NestedTensor((video, audio))}
            if denoise_mask is not None:
                current_latent["noise_mask"] = denoise_mask

        video, audio = _validate_av_samples(current_latent["samples"])
        n_guides = _count_guide_frames(guider, video.shape)
        print(f"[ZLTXVT] sampled_T={video.shape[2]} n_guides={n_guides} final_T={video.shape[2] - n_guides if video.shape[2] > n_guides else video.shape[2]} pixel_frames={(video.shape[2] - n_guides - 1) * 8 + 1 if video.shape[2] > n_guides else 'n/a'}")
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
            except Exception:
                patched_model = model

        if enable_stg:
            try:
                if patched_model is model:
                    patched_model = model.clone()
                patched_model.set_model_sampler_post_cfg_function(
                    _make_stg_post_cfg(stg_blocks, scale=1.0, start_percent=0.0, end_percent=0.5)
                )
            except Exception:
                pass

        if enable_modality_guidance and not math.isclose(modality_scale, 1.0):
            try:
                if patched_model is model:
                    patched_model = model.clone()
                patched_model.set_model_sampler_post_cfg_function(
                    _make_modality_post_cfg(modality_scale)
                )
            except Exception:
                pass

        return patched_model
