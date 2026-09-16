# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **PromptEnhancePlus** — multi-model prompt optimizer driven by a local LLM (Gemma 3/4, Qwen, etc.). Accepts a short user prompt + optional image/video/audio, picks the right built-in system prompt for the chosen target model (LTX 2.5 / H3 / Z-Image / Krea-2 / Krea-2-Edit), formats it in the chat template expected by the loaded tokenizer, and returns the expanded prompt as a single STRING. Supports a custom template override that takes precedence over the built-in templates.

  - **Inputs**: `clip`, `prompt`, `target_model` (Combo), `mode` (Combo, auto/T2V/T2I/I2V), `image`, `video`, `audio` (all optional), `custom_template` (multiline, optional), plus standard sampling params (`max_length`, `temperature`, `top_k`, `top_p`, `seed`).
  - **Output**: `enhanced_prompt` STRING — `<think>` blocks stripped, empty output falls back to the original user prompt.
  - **Built-in templates**:
    - LTX 2.5 T2V / I2V — derived from ComfyUI's `TextGenerateLTX2Prompt` LTX24 system prompts (objective, framing triple, cinematic aesthetic).
    - H3 T2V / I2V — three-field structure (`integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`), shot-based timeline with time anchors; sourced from `MiniMax-H3/skills/h3-prompt-writing/references/base-en.txt`.
    - Z-Image T2I — natural language with style prefix + photographic terminology.
    - Krea-2 T2I — direct reuse of the official `krea-2/docs/expansion.txt` prompt.
    - Krea-2-Edit I2V — image-grounded editing instruction format, matching `Comfyui-QwenEditUtils` llama_template style.
  - **Chat-template auto-detection** (`_detect_tokenizer_family`): matches `gemma4` / `gemma` / `qwen` in `clip.tokenizer.clip_name`; falls back to gemma3 format with warning for unknown tokenizers.
  - **Auto-mode** (`_resolve_mode`): picks I2V when image or video is connected, T2I for image-only target models, T2V otherwise; Krea-2-Edit forces I2V when an image is supplied.
  - **Tests**: `tests/test_prompt_enhance_plus.py` — 27 tests covering template coverage, custom-template override, mode resolution, tokenizer-family detection, chat-format formatting per family, think-block stripping (closed + unclosed), end-to-end execute via fake CLIP, and node IO sanity. Self-contained via in-test `comfy_api.latest.io` stub so it runs without a real ComfyUI install.
  - **Example workflow**: `examples/prompt_enhance_plus_smoke_test.json` — minimal 3-node flow (LoadCLIP → PromptEnhancePlus → ShowText).

### Added (recent)

- **PromptEnhancePlus runtime diagnostics**: every execute() now prints the resolved tokenizer family, image/video/audio port state, image tensor shape/dtype/device, formatted-text length, and a structured summary of the tokenize output dict (batch / total_tokens / top token ids / vision-marker counts for qwen-vl `image_pad` / `vision_start` / `vision_end` and gemma4 `image` / `video` / `audio`). Lets you confirm at a glance whether the image you wired is actually being injected as vision tokens, instead of guessing from the final prompt text.

- **PromptEnhancePlus chat-residue stripping**: `_REASONING_PREFIXES` and `_REASONING_KEYWORDS` now cover English chat preamble (`assistant:` / `as an ai` / `as an assistant` / `as a language model` / `i'm an ai` / `i am an assistant`) and Chinese chat preamble (`好的，` / `首先，` / `作为一个人工智能` / `我是一个 AI` / `我是一个大语言模型` / `我需要` / `让我`). The LLM no longer leaks "assistant: ..." or "好的，我会..." as the first sentence of the expanded prompt.

### Fixed

- **PromptEnhancePlus image pipeline (Gemma4)** — `<|image><|image|><image|>` is now hardcoded in the user turn when `image` is connected on the Gemma4 family (mirrors ComfyUI's `TextGenerateLTX2Prompt` at `comfy_extras/nodes_textgen.py:242`). Earlier "B方案" refactor over-pruned all image placeholders, which left Gemma4's tokenize with no placeholders to replace — the LLM was receiving the user text but no vision tokens at all.

- **PromptEnhancePlus text-only CLIP guard** — when the loaded CLIP is a text-only encoder (`ZImageTEModel_` / `Lumina2` / `Qwen3_4B`) and an image is wired, the node now raises a clear `ValueError` with the fix suggestion ("load a vision-language CLIP such as Qwen2.5-VL-7B-Instruct or Qwen-Image-Edit"). Previously the image was silently dropped by the tokenizer's `tokenize_with_weights(**kwargs)` signature, producing zero-effect runs that looked successful.

- **zimage_t2i.md image-aware instruction** — the built-in Z-Image template now tells the LLM to explicitly describe the image's visual elements (subject, composition, lighting, style) when the `image` input port is connected, instead of focusing only on the text prompt. Without this, the LLM received vision tokens but its system prompt told it to ignore them.

### Changed

- **PromptEnhancePlus `_format_chat` per-family image handling**:
  - `gemma4` + image → `<|image><|image|><image|>\n\n` prepended to user turn (matches upstream pattern; gemma4 tokenize replaces 3 placeholders with 1 image embed).
  - `qwen` + image → user turn stays text-only (qwen35 tokenize injects `<|vision_start|><|image_pad|><|vision_end|>` itself; writing it manually would falsely trigger `qwen35.py:744`'s skip_template path).
  - `gemma3` + image → user turn stays text-only (gemma3 image-soft support is unverified; let upstream decide).

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
