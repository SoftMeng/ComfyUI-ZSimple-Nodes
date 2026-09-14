# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **ZLTXVideoTurboProgressive: rewrite multi-stage handoff (Z-Image style noise_inverse)**. The previous design used `_upscale_interpolate` (latent-space bilinear) or `_upscale_vae_roundtrip` (VAE decode → bilinear → encode) between stages, which produced visibly softer / blocky output because the next stage rebuilt detail from a low-pass-filtered latent. The new design treats each stage as running at a different *working scale* of the same final-size input latent and joins stages through Karras-EDM-style noise-phase handoff (mirrors Z-Image's `_noise_inverse`).

  - **Per-stage scale chain** (`upscale_model="fast"`): the input av_latent is the FINAL resolution; stages run at a coarser scale in early stages and refine to full size in the last stage. Rule (user-defined):
    - 1 stage : `[1.00]`
    - 2 stages: `[0.75, 1.00]`
    - 3 stages: `[0.50, 0.75, 1.00]`
    - 4 stages: `[0.50, 0.50, 0.75, 1.00]`
    - 5 stages: `[0.50, 0.50, 0.50, 0.75, 1.00]`
    - N >= 6  : `[0.50] * (N - 3) + [0.75, 1.00]`
  - **Inter-stage handoff** (`_stage_handoff`): each stage runs to sigma=0 (denoised x0). The next stage's entrance noise phase is seeded from that x0 via `(1 - s) * x0 + s * noise` (video and audio are re-noised independently) and passed as both `noise` and `latent_image` to the next sampler. This matches the flow-matching blend `latent * (1 - s) + noise * s` that ModelSamplingDiscreteFlow applies internally when sigma-scaling a fresh input, so the next sampler sees a noise-phase-aligned starting point instead of a re-rolled random one.
  - **Video resize**: `comfy.utils.common_upscale(samples, new_w, new_h, "bilinear", "disabled")` per stage (Z-Image pattern). Spatial dims are rounded to multiples of 8 so the VAE stays happy.
  - **Audio**: never resized. Audio time dim matches video; audio spatial (frequency bins) is unrelated to video H/W. The handoff re-noises audio independently.

  - **API changes**:
    - Removed `upscale_modes` String input (replaced by `upscale_model` combo).
    - Removed `vae_video` Vae.Input (no longer needed — `_upscale_*` paths deleted).
    - Removed `upscale_model` LatentUpscaleModel.Input (semantics changed; reserved external 5GB checkpoint is no longer used by this node).
    - Added `upscale_model` Combo: `["none", "fast"]` (`none` keeps every stage at scale 1.0; `fast` applies the per-stage scale chain).
    - Other inputs unchanged: `sigmas_pipe`, `guidance_rescale`, `enforce_per_frame_path`, `enable_stg`, `enable_modality_guidance`, `stg_blocks`, `modality_scale`, `seed`.
    - File size: 555 → 536 lines (after removing the three `_upscale_*` helpers and `_parse_upscale_modes`, adding `_stage_scale_chain` / `_stage_handoff` / `_resize_video_for_scale`).
    - Examples (`use_new_node.json`, `use_old_node.json`) updated: removed `vae_video` input port, replaced `upscale_modes` widget with `upscale_model="fast"`.

  - **Kept verbatim**: sigmas_pipe multiline STRING format, trajectory segmentation (intermediate lines may stop at sigma > 0; only last line ends at 0.0), exact-continuation handoff when next line's first sigma equals previous line's last sigma (1e-6 tolerance), per-stage options (SD3 CFG rescale / per_frame_path / STG bundle / Modality Guidance bundle), strict NestedTensor validation on av_latent, `_crop_guides` final-output guide-frame crop (LTXVAddGuide appends guide latent at the temporal end of the video latent — without cropping, the locked guide frame VAE-decodes into the last frames of the video).
