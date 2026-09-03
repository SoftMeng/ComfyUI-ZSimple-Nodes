# CLAUDE.md

Project guidance for `ComfyUI-ZSimple-Nodes/`. Root repo guidance lives at `../CLAUDE.md`.

## Project Type

Small ComfyUI custom node plugin — 4 nodes, single-file-per-node, single-responsibility. **Independent subproject**. Personal/utility plugin. License: MIT.

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
nodes/
  __init__.py                # re-exports the 4 node classes
  _save_common.py            # shared helpers (counter scan, metadata)
  random_number_plus.py      # RandomNumberPlus
  save_image_plus.py         # SaveImagePlus
  save_text_plus.py          # SaveTextPlus
  zimage_turbo_progressive.py # ZImageTurboProgressive
tests/
  test_zimage_turbo_progressive.py
requirements.txt             # only pillow-jxl-plugin (commented)
README.md                    # primary user-facing docs
```

### Registration

Classic V1-style: 4 entries in `NODE_CLASS_MAPPINGS` + display names. Menu: `ZSimple-Nodes` with submenus `image`, `text`, `sampling`.

### Nodes (4 total, all active)

| Class | Menu Path | Purpose |
|---|---|---|
| `RandomNumberPlus` | `ZSimple-Nodes` | Seed generator; outputs `int_out` + `string_out` + `next_int` + `number_out`. |
| `SaveImagePlus` | `ZSimple-Nodes/image` | Save IMAGE to PNG/JPEG/WebP/JXL with per-format quality + metadata strategy + counter continuation. Outputs `images` / `paths` / `filename_first` / `workflow_json`. |
| `SaveTextPlus` | `ZSimple-Nodes/text` | Save STRING to `.txt`/`.md`/`.json`/`.csv`; outputs `path` / `byte_count` / `workflow_json`. Fixed filename `<prefix>_00001.<ext>` (no counter continuation). |
| `ZImageTurboProgressive` | `ZSimple-Nodes/sampling` | 3-stage progressive sampling for Z-Image Turbo. Hardcoded BRAVO/ALPHA sigma presets; `latent_scaling` size chain (fast/quality/none); `intensity` (V2 Adv formula); `creativity_mode` stage2 scramble; per-stage sampler. |

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
| Run tests | `python -m pytest tests/` (one test file currently) |

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

- **No CI / no linter config in repo.** Tests are minimal (one file for progressive sampler).
- **`requirements.txt` is effectively a no-op** by default — only enable `pillow-jxl-plugin` if a user picks `format="jxl"`.
- **No frontend extensions** (`WEB_DIRECTORY` not set) — pure backend nodes.
- **Author chose `aggressive` scaling** in addition to `fast`/`quality`/`none` — README doesn't document this key; behavior is `stage3` still forced to input size like the others.
