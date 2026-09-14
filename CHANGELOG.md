# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **ZLTXVideoTurboProgressive lost reference frame on in-node upscale**: the previous "crop guide + clear conds" before each inter-stage upscale dropped `keyframe_idxs`/`guide_attention_entries` entirely, so stage 1 had no guide attention — the reference frame drifted (often landing on the last frame or disappearing). The new `resize_keyframe_tokens=int` parameter instead pads `keyframe_idxs` tokens AND scales each `guide_attention_entries[*]["pre_filter_count"]` by the spatial resolution ratio (typically 4 for a 2x upscale), keeping the reference frame at the same temporal position while satisfying the model's per-frame token-count divisibility check (`comfy/ldm/lightricks/model.py:1122`). The execute loop computes the actual `(post_H*post_W) / (pre_H*pre_W)` ratio from the latent shape around the upscale and applies it.

- **ZLTXVideoTurboProgressive bilinear interpolate mode** (added per user feedback): `_upscale_interpolate` reshapes the 5D video latent `(B, C, T, H, W)` to `(B*T, C, H, W)` so `F.interpolate` accepts it (bilinear is 4D-only), then restores the 5D shape. Time dim is untouched. Uses `scale_factor=(2, 2)` (spatial only, matches the 4D tensor) instead of `(1, 2, 2)` (which is the 5D convention). Nearest on noisy/intermediate latents produces visible blocky edges; bilinear smooths the upscale and avoids the "model learns hard cut as signal" failure mode during stage-1 re-denoise.

- **ZLTXVideoTurboProgressive guide crop over-counted 4x**: `_count_guide_frames` used the stale `H*W//4` tokens-per-frame formula (patch-size-2 era); current ComfyUI uses `SymmetricPatchifier(1)` everywhere (`nodes_lt.py:251`, `model.py:1106`), so tokens per latent frame is exactly `H*W` (`get_keyframe_idxs`, `nodes_lt.py:238`). A single-frame guide (e.g. 480 tokens at H*W=480) was miscounted as 4 frames — cropping 4 latent frames (~1.3s of video) instead of 1. This was also the root cause of the earlier "set 121 frames, got 97 frames" mystery: 17 latent − 4 = 13 → decode = 97. Now `n_guides=1` → 16 latent → decode = 121 frames as configured.

- **ZLTXVideoTurboProgressive guide/upscale resolution conflict**: with `LTXVAddGuide` in the workflow plus an inter-stage `interpolate`/`vae_roundtrip` upscale, stage ≥ 1 crashed at `model.py:1122` — `keyframe_idxs` tokens are recorded at the pre-upscale resolution (e.g. 480) and don't divide the post-upscale per-frame token count (e.g. 1920). The node now crops appended guide frames from the video stream AND nulls `keyframe_idxs`/`guide_attention_entries` in the guider's conds right before the first in-node upscale (new `_crop_guides(current_latent, guider, clear_conds=True)`). Reference influence from stage 0 stays baked into the latent structure; later stages run guide-free. The final-output crop reuses the same helper.

- **ZLTXVideoTurboProgressive vae_video validation false positive**: removed the `vae_video is None` check from `validate_inputs` — ComfyUI passes `None` for link-connected inputs during the validation phase (upstream hasn't executed yet), so a properly-wired vae_video always triggered "vae_video input is required". The check now runs at `execute` time when the actual value is available, raising a clear error only when the mode genuinely needs a VAE and none was provided.

- **ZLTXVideoTurboProgressive trajectory-segmentation validation restored**: the strict-validator rewrite accidentally reintroduced the per-line "last sigma must be 0.0" check, rejecting legitimate segmentation pipes (`[1.0, ..., 0.909375]` + `[0.909375, ..., 0.0]`). `_validate_stage_sigmas` now only enforces len≥2 + monotonic non-increase; `validate_inputs` enforces that only the LAST pipe line ends at 0.0. Also restored the exact-continuation handoff in `execute`: when the next stage's first σ equals the previous line's σ_end (1e-6 tolerance), `noise = current_latent["samples"]` (identity under the flow-matching blend); a jump re-noises fresh.

- **ZLTXVideoTurboProgressive guide-frame tail leak**: `LTXVAddGuide` appends the guide latent to the temporal end of the video latent (it is NOT placed at `frame_idx` — the model only re-addresses it there via `keyframe_idxs` spatial coords). Without a downstream `LTXVCropGuides`, the locked guide frame survives sampling and VAE-decodes into the last frames of the video, making the reference image appear at the tail. The node now counts appended guide frames from `guider.original_conds["positive"][*]["keyframe_idxs"]` (tokens ÷ `H*W//4`, mirroring `get_keyframe_idxs` in `comfy_extras/nodes_lt.py:237`) and crops them from the video stream (and its noise_mask) before output — equivalent to an inline `LTXVCropGuides` on the latent side.

### Changed

- **ZLTXVideoTurboProgressive strict NestedTensor validation (no fabrication)**: replaced the `_ensure_av_samples` defensive fallback with a strict `_validate_av_samples` validator. The node now requires `av_latent['samples']` to be a proper `NestedTensor` from `LTXVConcatAVLatent` with exactly 2 streams (`video` 5D `[B,C,T,H,W]` + `audio` 4D `[B,C,T,F]`). Validation runs in `validate_inputs` (pre-execution, friendly error) and at the top of `execute`. After every `guider.sample()` the output is validated too — invalid output raises a clear error pointing the user at the upstream wiring problem instead of silently fabricating a malformed stream that crashes downstream `a_patchifier.patchify` with `ValueError: too many values to unpack (expected 4)`.

### Fixed

- **ZLTXVideoTurboProgressive upstream wiring surfaced via clear errors**: previous `_ensure_av_samples` fallback silently fabricated a 5D `(B, 8, T, H, W)` placeholder when the upstream latent was missing audio, which propagated through `latent_shapes` into `_token_grid_masks` and made stage 2's `audio_denoise_mask` 5D → `a_patchifier.patchify` crash. The strict validator surfaces the root cause immediately ("av_latent must be NestedTensor from LTXVConcatAVLatent") instead of patching the symptom.

- **ZLTXVideoTurboProgressive AV output preservation**: added `_ensure_av_samples(out, ref)` guard after `guider.sample()` that re-wraps a flat or 1-stream output as `NestedTensor((video, audio))` using the original audio stream from the input av_latent. Defends against the `LTXVSeparateAVLatent.execute` `IndexError: tuple index out of range` when the upstream `CFGGuider.sample` repack path drops the audio stream.

### Changed

- **examples/use_new_node.json node 5**: replaced the broken `LTXVAudioVAEEncode` reference (whose schema doesn't match `frames_number/frame_rate/width/height` widgets — they belong to a different node) with `LTXVEmptyLatentAudio` (correct schema: `frames_number` + `frame_rate` + `batch_size` widgets + `audio_vae` connection). Ensures `LTXVConcatAVLatent` receives a real 4D audio latent instead of an empty/mismatched one.

### Added

- **ZLTXVideoTurboProgressive trajectory segmentation** (Z-Image style): intermediate sigmas_pipe lines may now stop at σ_end > 0 instead of denoising to 0. Handoff: next line's first σ equal to previous line's last σ (1e-6 tolerance) → exact continuation (`noise = latent` identity under the flow-matching blend, noisy latent passes through unchanged); a jump → fresh-noise re-blend (Z-Image `_noise_inverse` approximation, keep |Δσ| ≤ ~0.05). Avoids the destructive "denoise to 0 then re-noise" round-trip between stages; ideal for coarse-denoise-low-res → upscale → continue-high-res. Only the last line must end at 0.0.

### Changed

- **ZLTXVideoTurboProgressive V2V support**: relaxed sigmas_pipe validation — first σ of each stage may now be any value in `(0, 1]` instead of stage-0-only `1.0`. `1.0` = full-noise T2V; `<1.0` = video-to-video denoise strength (source latent blended as `latent×(1-σ₀) + noise×σ₀`; lower σ₀ follows source more). Enables V2V Path A (low-σ denoise) alongside existing Path B (LTXVAddGuide keyframes) and Path C (noise_mask locking).

- **ZLTXVideoTurboProgressive sigmas_pipe refactor** — replaced fixed `stages`/`schedule`/`stage`/`variant` combo inputs with a single multiline `sigmas_pipe` STRING input. Each line is one σ schedule; previous stage's output is re-noised by the sampler and passed as clean latent_image to the next. Removed `SIGMA_PRESETS` and `_resolve_sigmas` (default value embedded in the schema default field).
  - New `sigmas_pipe` (multiline STRING) replaces `schedule` + `stage` + `variant`.
  - New `upscale_modes` (comma-separated STRING) replaces `upscale_mode` (combo). `external` rejected for stages ≥ 1.
  - Per-stage optimizations retained: `guidance_rescale` (A), `enforce_per_frame_path` (B), `enable_stg` (C), `enable_modality_guidance` (D).
  - Total IO: 18 → 14. File: 474 → 416 lines.
  - Examples JSON uses the new schema (`widgets_values` updated to 9 fields).

### Added

- **ZLTXVideoTurboProgressive alternative upscale modes (B + A)**: node now supports internal 2-stage sampling with three upscale strategies, eliminating the dependency on the 5GB `ltx-2.5-latent-spatial-upscaler-x2` checkpoint when the user does not have it.
  - New `stages` combo input (`single_stage` / `auto_2stage`, default `single_stage` for backward compat).
  - New `upscale_mode` combo input (`external` / `interpolate` / `vae_roundtrip`, default `external`).
  - New `vae_video` Vae.Input (required by `interpolate` and `vae_roundtrip` modes).
  - New `upscale_model` LatentUpscaleModel.Input (reserved for external mode pre-checks).
  - `_upscale_interpolate()`: pure `F.interpolate(scale=(1,2,2), mode='nearest')` between `per_channel_statistics.un_normalize/normalize`. Zero new model dependency.
  - `_upscale_vae_roundtrip()`: `vae.first_stage_model.decode` → `F.interpolate(scale=(1,2,2), mode='bilinear')` on pixels → `vae.first_stage_model.encode`. Preserves temporal coherence; needs the existing CausalDiffusionVAE only.
  - Helper `_sample_one()` extracted so `single_stage` and `auto_2stage` share sampling logic.
  - File size: 312 → 474 lines (still focused, single-responsibility: AV latent sampling with optional internal upscale).

- **ZLTXVideoTurboProgressive architectural optimizations (A/B/C/E)** — node upgraded from "σ-list shortcut" to "LTX2.5-aware sampler".
  - **A. Dynamic SD3 shift sigmas**: new `variant="dev"` mode uses `_ltxv_shift_sigmas(num_steps, token_count)` with max_shift=2.05, base_shift=0.95 to compute resolution-aware σ schedules (mirrors ComfyUI `LTXVScheduler` `nodes_lt.py:645-675`). Stage2 still uses hardcoded 4σ list (publisher-locked).
  - **B. SD3 CFG rescale**: new `guidance_rescale` input (default 0.7). When `variant=dev` + `guidance_rescale>0`, injects `_make_rescale_cfg_post_cfg(...)` via `set_model_sampler_post_cfg_function`. High-σ half of CFG output is rescaled with `cond` to debias saturation (Lin et al. 2024).
  - **C. per_frame_path validation**: new `enforce_per_frame_path` BOOL input. When True, `_spatial_mask_present(av_latent)` raises ValueError if noise_mask has spatial extent (H≠1 or W≠1 in 5D). Triggers the model's `_prepare_timestep` per_frame_path optimization (`av_model.py:738-848`).
  - **E. STG + Modality Guidance bundle**: new `enable_stg` / `enable_modality_guidance` / `stg_blocks` / `modality_scale` inputs. On Stage2, `_make_stg_post_cfg(blocks="29", start=0.0, end=0.5)` and `_make_modality_post_cfg(scale=3.0)` are injected via `set_model_sampler_post_cfg_function` (pattern matches `LTXVSpatioTemporalGuidance` and `LTXVModalityGuidance` at `nodes_lt.py:940-1050`).

### Changed

- **ZLTXVideoTurboProgressive refactored** — node now focused on single-stage AV latent sampling only.
  - IO reduced from **18 inputs / 2 outputs → 7 inputs / 1 output**
  - Removed inputs: `vae_video`, `vae_audio`, `clip`, `video_latent`, `audio_latent`, `image_ref`, `positive`, `negative`, `video_cfg`, `audio_cfg`, `frame_rate`, `latent_scaling`, `intensity`, `creativity_mode`, `creativity_attenuation`, `image_strength_s1/s2`, `image_compression`, `steps_s1/s2`, `sampler_s1/s2`, `return_leftover_noise`, `positive_s2_preproc/negative_s2_preproc`, `stage_handoff_mode`, `stage_handoff_sigma`
  - Added inputs: `guider` (io.Guider.Input — pre-built CFGGuider from upstream)
  - Removed outputs: `latent_video` and `latent_audio` split — node now outputs single `latent` (NestedTensor); downstream uses `LTXVSeparateAVLatent` to split
  - Removed combo inputs: `latent_scaling`, `stages` — replaced with simpler `stage` (stage1 / stage2)
  - Responsibilities moved to upstream nodes:
    - **AV lifecycle** (concat/separate): `LTXVConcatAVLatent` + `LTXVSeparateAVLatent`
    - **CFG construction**: `CFGGuider` or `DualCFGGuider`
    - **Image / audio preprocessing**: `LTXVAddGuide`, `LTXVAudioVAEEncode`, `LTXVPreprocess`, etc.
    - **Latent upscale**: `LTXVLatentUpscaler` (between two stage calls)
  - 2-stage workflow = two `ZLTXVideoTurboProgressive` calls with `LTXVLatentUpscaler` between them
  - File size: **446 → 76 lines**
  - Removed methods: `_concat_av`, `_separate_av`, `_fit_audio`, `_audio_ref_samples` / `_video_ref_samples` carrying, post-sample video/audio blend, frame_rate auto-injection, `_upscale_latent` (delegated to native `LTXVLatentUpscaler`), `_SAMPLER_CACHE`, `_cached_sampler`, `validate_inputs` complexity
  - Migrated `examples/use_new_node.json` to new architecture

## [1.1.0] - 2026-09-10

### Added

- **ZLTXVideoTurboProgressive** node: LTX2.5 视频渐进式采样节点封装
  - Menu: `ZSimple-Nodes/sampling`
  - 32 inputs / 3 outputs (`latent_video` + `latent_audio` + `workflow_json`)
  - Multimodal input: text + reference image + audio
  - 2-stage progressive: Stage1 low-res (default 8 steps euler_ancestral) + spatial ×2 upscale + Stage2 high-res (default 3 steps sa_solver)
  - Built-in distilled sigma presets (Stage1 = 9 σ, Stage2 = 4 σ; Stage2 starting σ ≈ 0.909375 inferred from R2 research, NOT directly verified in ComfyUI core `LTXVScheduler` source which generates sigmas dynamically)
  - 4-level `latent_scaling` (fast/quality/aggressive/none) — only spatial dimension, T fixed
  - 4-level `creativity_mode` + `creativity_attenuation` for video-specific attenuation
  - `stages` parameter (auto_2stage / stage1_only / stage2_only)
  - 9-item `validate_inputs` pre-execution validation (CFG / steps / intensity / scaling / attenuation / required inputs)
  - 8 GPU integration placeholder methods (`_encode_audio` / `_preprocess_image` / `_inject_image` / `_concat_av` / `_separate_av` / `_upscale_latent` / `_sample` / `_apply_creativity_stage1`); each raises `NotImplementedError` with explicit fix hints pointing to the corresponding ComfyUI core node's `execute(cls, ...)` method (with source line numbers). **KEY**: `_concat_av` returns `comfy.nested_tensor.NestedTensor((video_samples, audio_samples))`, NOT a regular tensor — AV lifecycle must handle NestedTensor.
  - Single file `nodes/ltx_video_turbo_progressive.py` (~551 lines)
  - Tests `tests/test_ltx_video_turbo_progressive.py` (39 tests, all passing)
  - 4 example workflows in `examples/`: basic / i2v / a2v / full_mv
  - README bilingual update (Chinese + English new node sections + Quick Start + FAQ with corrected facts)
  - Subproject `CLAUDE.md` update (node table + Node Specifics sub-section with ComfyUI source line references)
  - Cross-project doc `docs/principle/02-video.md` (E9)

### Changed

- README structure: 5 → 8 nodes section (Chinese: "四个节点" → "八个节点"; English: "Four nodes" → "Five nodes")
- `validate_inputs`: allow `audio_cfg=0` to mean "disable audio" (was contradictory before)
- 8 NotImplementedError messages: corrected to reference ComfyUI core `execute(cls, ...)` methods with source line numbers (was previously citing non-existent `.preprocess()` / `.apply()` / `.concat()` etc.)
- Default values reconciled: `image_compression=18` and `video_cfg=audio_cfg=1.0` documented as workflow overrides vs upstream node defaults (`LTXVPreprocess` default 35; `LTXVDualCFGGuider` defaults 3.0/7.0)

### Fixed

- `_round_to_32` formula off-by-one (was returning 0 for n=1..16; fixed to `((n+31)//32)*32`)
- `io.Sampler.Input` rejected `default=` kwarg, preventing node registration (removed; KSamplerSelect must wire sampler)

## [1.0.0] - 2025-XX-XX

### Added

- Initial release of ZSimple-Nodes plugin: `RandomNumberPlus`, `SaveImagePlus`, `SaveTextPlus`, `SaveVideoPlus`, `ZImageTurboProgressive`

[1.1.0]: https://github.com/yourname/ComfyUI-ZSimple-Nodes/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/yourname/ComfyUI-ZSimple-Nodes/releases/tag/v1.0.0
