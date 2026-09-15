# CLAUDE.md

Project guidance for `ComfyUI-ZSimple-Nodes/`. Root repo guidance lives at `../CLAUDE.md`.

## Project Type

Small ComfyUI custom node plugin — 5 nodes, single-file-per-node, single-responsibility. **Independent subproject**. Personal/utility plugin. License: MIT.

## Hard Constraints

| # | Rule |
|---|------|
| 1 | Subproject root is **read-only by default** for the parent repo; treat own root normally. |
| 2 | Never modify `ComfyUI/` core — sibling, not a dependency. |
| 3 | Code uses **ComfyUI V3 schema** (`comfy_api.latest` / `io.ComfyNode`). |
| 4 | Python 3.10+; `pillow-jxl-plugin` is the **only** optional runtime dep (for `format="jxl"` in `SaveImagePlus`). |
| 5 | Don't run `pip install` at the parent repo root. |
| 6 | Don't delete/rename files or directories under this subproject. |
| 7 | This subdirectory IS the git repo root for `ComfyUI-ZSimple-Nodes` development. Run all `git` commands here, never from the parent `comfy-nodes/` aggregate. |

Full prohibitions → `../docs/constraint/prohibitions.md`.

## Architecture

### Layout

```
__init__.py                  # NODE_CLASS_MAPPINGS + NODE_DISPLAY_NAME_MAPPINGS
model_system_prompt/         # PromptEnhancePlus built-in .md templates (editable)
  ltx25_t2v.md / ltx25_i2v.md / h3_t2v.md / h3_i2v.md
  zimage_t2i.md / krea2_t2i.md / krea2_edit_i2v.md
system_prompt/               # ZSimpleAgent 节点的通用 markdown system prompts
nodes/
  __init__.py                # re-exports the node classes
  _save_common.py            # shared helpers (counter scan, metadata)
  _agent_common.py           # agent helpers (_scan_system_prompts / _resolve_system)
  random_number_plus.py      # RandomNumberPlus
  save_image_plus.py         # SaveImagePlus
  save_text_plus.py          # SaveTextPlus
  save_video_plus.py         # SaveVideoPlus
  zimage_turbo_progressive.py # ZImageTurboProgressive
  ltx_video_turbo_progressive.py # ZLTXVideoTurboProgressive
  prompt_enhance_plus.py     # PromptEnhancePlus
tests/
  test_zimage_turbo_progressive.py
  test_ltx_video_turbo_progressive.py
  test_prompt_enhance_plus.py
requirements.txt             # only pillow-jxl-plugin (commented)
README.md                    # primary user-facing docs
```

### Registration

Classic V1-style: 5 entries in `NODE_CLASS_MAPPINGS` + display names. Menu: `ZSimple-Nodes` with submenus `image`, `text`, `sampling`.

### Nodes (5 total, all active)

| Class | Menu Path | Purpose |
|---|---|---|
| `RandomNumberPlus` | `ZSimple-Nodes` | Seed generator; outputs `int_out` + `string_out` + `next_int` + `number_out`. |
| `SaveImagePlus` | `ZSimple-Nodes/image` | Save IMAGE to PNG/JPEG/WebP/JXL with per-format quality + metadata strategy + counter continuation. Outputs `images` / `paths` / `filename_first` / `workflow_json`. |
| `SaveTextPlus` | `ZSimple-Nodes/text` | Save STRING to `.txt`/`.md`/`.json`/`.csv`; outputs `path` / `byte_count` / `workflow_json`. Fixed filename `<prefix>_00001.<ext>` (no counter continuation). |
| `ZImageTurboProgressive` | `ZSimple-Nodes/sampling` | 3-stage progressive sampling for Z-Image Turbo. Hardcoded BRAVO/ALPHA sigma presets; `latent_scaling` size chain (fast/quality/none); `intensity` (V2 Adv formula); `creativity_mode` stage2 scramble; per-stage sampler. |
| `ZLTXVideoTurboProgressive` | `ZSimple-Nodes/sampling` | LTX2.5 AV latent sampler driven by an N-stage `sigmas_pipe`. 14 inputs (`model` / `guider` / `av_latent` / `sampler_obj` / `sigmas_pipe` multiline / `upscale_modes` / `vae_video` / `upscale_model` / `guidance_rescale` / `enforce_per_frame_path` / `enable_stg` / `enable_modality_guidance` / `stg_blocks` / `modality_scale` / `seed`), 1 output (`latent` NestedTensor). Each sigmas_pipe line = one stage's σ schedule; previous stage output is re-noised (by sampler) and used as clean latent_image for the next. `upscale_modes` is a comma-separated list of `external` / `interpolate` / `vae_roundtrip` per inter-stage (stage 0 has no upscale). Per-stage optimizations: SD3 CFG rescale (`guidance_rescale>0`), per_frame_path validation (`enforce_per_frame_path`), STG bundle (`enable_stg`), Modality Guidance bundle (`enable_modality_guidance`). Karras EDM stochastic churn / SD3 resample / SDXL refiner pattern in one node. |

### Node Specifics

- **SaveImagePlus**:
  - Counter scan runs at `execute()` start; scans target subdir for `<prefix>_*.<ext>`, takes max `_NNNNN + 1`, starts at `_00001` if empty. Each of png/jpeg/webp/jxl counts independently.
  - JPEG EXIF segment hard limit **64KB** — overflow auto-downgrades to `prompt_only`.
  - `webp_lossless=on` ignores `quality`; uses PIL default lossless encoding.
  - Default compression: `quality=92` (JPEG/WebP), `png_compress_level=9`, `jpeg_subsampling=4:4:4`, `webp_method=4`.

- **ZImageTurboProgressive**:
  - Sigma presets (`_SIGMA_PRESETS_BY_NAME`): `alpha_3` … `alpha_10` + `bravo_8` (default when `steps=8`).
  - Stage sizes (`_LATENT_SCALING`): `fast=(0.25, 0.5, 1.0)` / `quality=(0.50, 0.75, 1.00)` / `aggressive=(0.25, 0.75, 1.00)` / `none=(1, 1, 1)`. `stage3` always forced back to input size.
  - `intensity`: `overdose = (intensity - 1) * 0.4` + `bias_level = intensity * 4 - 1`. `intensity=1.0` = no change.
  - `creativity_mode=on`: stage2 geometric scramble + 1-step euler preproc. `seed % 3 == 0` skips preproc.
  - `return_leftover_noise=enable`: stage3 keeps `sigmas3[-1] != 0`, output latent carries residual σ noise.
  - `seed` → stage1; stage2 uses `seed+16`; stage3 uses `seed=696969` derived.
  - **Not thread-safe** (per parent CLAUDE.md: shares `PARTITION_CACHE` model with PowerNodes).
  - Algorithm derived from `ComfyUI-ZImagePowerNodes/nodes/core/zsampler_turbo_core.py` and `zsampler_turbo_X21.py`.

- **ZLTXVideoTurboProgressive**:
  - AV latent sampler driven by an N-stage `sigmas_pipe` (one σ schedule per line). Each stage's output is re-noised by the sampler and fed to the next as clean latent_image, enabling iterative refinement à la Karras EDM stochastic churn / SD3 resample / SDXL refiner.
  - **sigmas_pipe parsing** (`_parse_sigmas_pipe`): each line stripped of `[`/`]` brackets, comma-split to `list[float]`. First σ of each line must be in (0, 1] — `1.0` = full-noise T2V; `<1.0` = V2V denoise strength. Only the LAST line must end at 0.0; intermediate lines may stop at σ>0 for **trajectory segmentation** (Z-Image style). Handoff: if next line's first σ == previous line's last σ (1e-6 tolerance), exact continuation via `noise = current_latent["samples"]` (flow-matching blend identity passes the noisy latent through unchanged); otherwise fresh-noise re-blend (Z-Image `_noise_inverse` approximation; keep jumps ≤ ~0.05). All lines monotonically non-increasing.
  - **upscale_modes parsing** (`_parse_upscale_modes`): comma-separated list, must equal `len(sigmas_pipe)` lines (single value broadcasts). Valid modes: `external`, `interpolate`, `vae_roundtrip`. `external` is rejected for stages ≥ 1 (in-node runs can't interleave external nodes).
  - **Per-stage optimizations** (all gated by dedicated inputs, apply per stage):
    - **A. SD3 CFG rescale** (`guidance_rescale>0`): `_make_rescale_cfg_post_cfg` via `set_model_sampler_post_cfg_function`; only applies when σ > 0.5 (Lin et al. 2024).
    - **B. per_frame_path validation**: `enforce_per_frame_path=True` rejects latents whose noise_mask has spatial extent; triggers `has_spatial_mask=False` path in `_prepare_timestep` (`av_model.py:738-848`).
    - **C. STG bundle** (`enable_stg=True`): `_make_stg_post_cfg` injected via `set_model_sampler_post_cfg_function`. Pattern from `LTXVSpatioTemporalGuidance` (`nodes_lt.py:940-990`).
    - **D. Modality Guidance bundle** (`enable_modality_guidance=True`): `_make_modality_post_cfg` injected via `set_model_sampler_post_cfg_function`. Pattern from `LTXVModalityGuidance` (`nodes_lt.py:994-1050`).
  - **Alternative upscale helpers** (still present from prior refactor, used by `interpolate` / `vae_roundtrip` modes):
    - `_upscale_interpolate`: pure `F.interpolate(scale=(1,2,2), mode='nearest')` between `per_channel_statistics.un_normalize/normalize`. Zero new model dependency.
    - `_upscale_vae_roundtrip`: `vae.first_stage_model.decode` → `F.interpolate(scale=(1,2,2), mode='bilinear')` on pixels → `vae.first_stage_model.encode`. Preserves temporal coherence.
  - **Reference workflow**: `examples/use_new_node.json` (2-stage distilled_default with `upscale_modes="external"`).
  - **Thread-safety**: depends on the underlying Guider + sampler.

## Adding a New Node

Per the project's stated convention (in README):

1. `touch nodes/my_new_node.py`.
2. Implement class (reference `nodes/random_number_plus.py` or `nodes/save_image_plus.py`).
3. Register in root `__init__.py`: import + add to both `NODE_CLASS_MAPPINGS` and `NODE_DISPLAY_NAME_MAPPINGS`.
4. Restart ComfyUI.

## Commands

| Action | Command |
|---|---|
| Install deps | `pip install -r requirements.txt` (no-op unless enabling JXL) |
| Run tests | `python tests/test_*.py` (each file is a standalone runner; pytest fails on this layout because root `__init__.py` imports `folder_paths` which isn't installed in dev envs) |

## Code Style

- One node class per file, file named `<snake_case>.py` matching class.
- Use `from comfy_api.latest import io` (V3 schema).
- Shared helpers go in `nodes/_save_common.py` (underscore prefix = private to plugin).
- README is the primary docs — keep node tables in sync when adding/changing IO.

## Skill Mapping

| Task | Skill |
|---|---|
| Plan a new node | `/harness-plan` |
| Add a node (Python) | `/harness-python-dev` |
| Code review | `/harness-code-review` |
| Debug sampler workflow | `/harness-debug` |
| Verify end-to-end | `/harness-quality-verification` |
| Update README | `/harness-doc-design` |

## Reference

- Parent: `../CLAUDE.md`.
- Companion plugin: `../ComfyUI-ZImagePowerNodes/` — algorithmic source for `ZImageTurboProgressive`.
- License: MIT.

## Notes

- **No CI / no linter config in repo.** Tests are minimal (one file per node — keep parity when adding new nodes).
- **`requirements.txt` is effectively a no-op** by default — only enable `pillow-jxl-plugin` if a user picks `format="jxl"`.
- **No frontend extensions** (`WEB_DIRECTORY` not set) — pure backend nodes.
- **Author chose `aggressive` scaling** in addition to `fast`/`quality`/`none` — README doesn't document this key; behavior is `stage3` still forced to input size like the others.
- **`ZLTXVideoTurboProgressive` is intentionally a wrapper around unimplemented methods** — the scaffolding validates inputs, builds AV latent lifecycle, and emits workflow_json, but `_encode_audio` / `_preprocess_image` / `_inject_image` / `_concat_av` / `_separate_av` / `_upscale_latent` / `_sample` / `_apply_creativity_stage1` raise `NotImplementedError` until GPU integration fills them. This is by design: the integration point is well-defined and the user can fill each method independently without re-reading the node's flow logic.
