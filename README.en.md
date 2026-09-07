<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### A minimal, practical set of custom nodes for ComfyUI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-4-orange?style=for-the-badge)](#-node-list)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**Tackle everyday ComfyUI workflow pain points · One file per node · Modern compression & quality defaults**

🌐 **[中文版本](./README.md)**

</div>

---

## ✨ Four nodes, each solves one specific pain point

| Node | Pain point | Key features |
|---|---|---|
| **RandomNumberPlus** | Inconsistent seed types across nodes | Outputs the seed in both number and text format, plus the next seed — drop into any downstream node without type conversions |
| **SaveImagePlus** | Built-in save node locks you into PNG / fixed compression | Save in PNG / JPG / WebP / JXL, tune each format's quality independently. Auto-numbers every file so nothing ever gets overwritten |
| **SaveTextPlus** | Need to dump prompts / workflow JSON to disk fast | Save prompts and workflow JSON to disk — never lose a working version again |
| **ZImageTurboProgressive** | No single-node 3-stage progressive sampler for Z-Image Turbo | A 3-stage progressive sampler for Z-Image Turbo: rough pass → refine → final, all in one node — no manual chaining required |

> [!NOTE]
> The project is actively iterated; nodes are added on demand. If you have a workflow pain point you'd like solved, open an Issue.

---

## 🚀 Quick Start

### Via ComfyUI Manager (recommended)

1. Open ComfyUI Manager
2. Search `ComfyUI-ZSimple-Nodes`
3. Click Install
4. Restart ComfyUI

### Via Git Clone

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/your-username/ComfyUI-ZSimple-Nodes.git
cd ComfyUI-ZSimple-Nodes
pip install -r requirements.txt
```

> [!TIP]
> After restart, the new nodes appear under the **ZSimple-Nodes** category, with submenus: `image` / `text` / `sampling`.

---

## 📦 Node List

### 🎲 RandomNumberPlus (Menu: `ZSimple-Nodes`)

Generates random seeds. Each run gives you a fresh seed value in **both number and text formats** (plug into any downstream node without manual type conversion), plus the **next seed** so you can chain "draw again" actions seamlessly.

**Typical usage**: feed the number-form seed into a KSampler to reproduce the same image; feed the text-form seed into SaveImagePlus's `filename_prefix` and the filename will automatically include the seed number.

#### Key knobs

| Knob | What it does |
|---|---|
| `seed` | The seed value. The UI gives you "randomize / increment / decrement / lock" controls, so you don't have to type anything |

<details>
<summary>📋 Full parameter & output reference (click to expand)</summary>

**Inputs**

| Name | Type | Default | Range | Description |
|---|---|---|---|---|
| `seed` | INT | 0 | 0 ~ 2⁶⁴-1 | Seed value; the UI controls are enabled via `control_after_generate` |

**Outputs**

| Name | Type | Value |
|---|---|---|
| `int_out` | INT | `int(seed)` |
| `string_out` | STRING | `str(seed)` |
| `number_out` | INT | `seed` |
| `next_int` | INT | `seed + 1` |

**Search aliases**: `random` / `seed` / `rng`

</details>

---

### 🖼️ SaveImagePlus (Menu: `ZSimple-Nodes/image`)

One node, every image format: PNG (lossless), JPG (compressed), WebP (smaller), JXL (newest and best). Tune quality, compression, and whether to embed prompts and workflow inside the image — all from the node. Files are auto-organized by date and auto-numbered, so you never overwrite old runs.

**Typical usage**: drop it right after your image-generation node, pick a format and quality, done.

#### Key knobs

| Knob | What it does |
|---|---|
| `format` | Output format: PNG / JPG / WebP / JXL (default: PNG lossless) |
| `quality` | JPG/WebP quality (default 92 — already very high, visually indistinguishable from lossless for most images) |
| `filename_prefix` | Filename prefix; files are auto-sorted into date-based subfolders |
| `embed_metadata` | Whether to embed prompts + workflow into the image (default: embed everything; when JPG workflow is too large, auto-falls back to prompt-only) |

<details>
<summary>📋 Full parameter & output reference (click to expand)</summary>

#### Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `images` | IMAGE | — | Image(s) to save |
| `filename_prefix` | STRING | `"ZSimple"` | Filename prefix |
| `subfolder_template` | STRING | `"%date:yyyy-MM-dd%"` | Subfolder template under `output/`; supports `%date%` / `%seed%` / `%width%` / `%height%`; empty string saves to `output_dir` root |
| `filename_number_padding` | INT (1–9) | 5 | Zero-padding width for the file counter (5 → `_00001`) |
| `format` | COMBO | `png` | `png` / `jpeg` / `webp` / `jxl` |
| `quality` | INT (1–100) | 92 | JPEG / WebP quality (ignored when `webp_lossless=on`) |
| `png_compress_level` | INT (0–9) | 9 | PNG compression level (9 = max compression) |
| `webp_lossless` | COMBO (`off`/`on`) | `off` | When on, uses PIL's default lossless encoder |
| `webp_method` | INT (0–6) | 4 | WebP encoder speed/size tradeoff |
| `jpeg_subsampling` | COMBO (`4:4:4`/`4:2:0`) | `4:4:4` | Recommended `4:4:4` when Q ≥ 90 |
| `embed_metadata` | COMBO (`none`/`prompt_only`/`all`) | `all` | PNG tEXt + JPEG EXIF embedding strategy |

> [!WARNING]
> **JPEG EXIF segment has a hard cap of ~60KB** (`_JPEG_EXIF_SAFETY_BYTES = 60000`). Large workflow + prompt JSON often overflows, causing metadata to be silently dropped. SaveImagePlus auto-downgrades to `prompt_only` when overflow is detected — but for archival, prefer PNG or lossless WebP.

#### Counter resume (avoid overwrites)

Each `execute()` scans the target subfolder for files matching `<filename_prefix>_<NNNNN>.<ext>`, takes the max counter + 1, and starts there; if the folder is empty, starts at `_00001`. **All four formats (png / jpeg / webp / jxl) count independently** — switching formats with the same prefix won't cross-contaminate.

#### JXL support

`format="jxl"` requires `pillow-jxl-plugin`. Without it, execution fails immediately:

```
RuntimeError: JPEG XL save requires pillow-jxl-plugin.
Install with: pip install pillow-jxl-plugin
```

JXL `distance` formula: `distance = max(0.0, (100 - quality) / 20.0)`.

#### Outputs

| Name | Type | Description |
|---|---|---|
| `images` | IMAGE | Original images passed through, chainable to downstream nodes |
| `paths` | STRING | All saved file paths (relative), comma-separated |
| `filename_first` | STRING | Filename of the first image in this batch |
| `workflow_json` | STRING | API workflow JSON dumped from `extra_pnginfo`; empty string when unavailable |

</details>

---

### 📝 SaveTextPlus (Menu: `ZSimple-Nodes/text`)

Saves prompts, workflow JSON, or any multi-line text to a local `.txt` / `.md` / `.json` / `.csv` file. JSON output is auto-formatted with indentation for easy reading.

**Typical usage**: archive your current prompt and workflow while debugging; change the filename prefix to keep multiple history versions.

#### Key knobs

| Knob | What it does |
|---|---|
| `text` | The text to save (required, multi-line) |
| `format` | Output format: txt / md / json / csv (default: txt) |
| `filename_prefix` | Filename prefix; files are auto-sorted into date-based subfolders |

<details>
<summary>📋 Full parameter & output reference (click to expand)</summary>

#### Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `text` | STRING | — | Main text (multiline, forced input) |
| `extra_texts` | STRING | `""` | Optional appended text (multiline); when present, prepended with a newline |
| `filename_prefix` | STRING | `"ComfyUI"` | Filename prefix |
| `subfolder_template` | STRING | `"%date:yyyy-MM-dd%"` | Subfolder template (same as SaveImagePlus) |
| `filename_number_padding` | INT (1–9) | 5 | Zero-padding width for the filename counter (**not actually used**, see warning below) |
| `format` | COMBO | `txt` | `txt` / `md` / `json` / `csv` |
| `embed_json_keys` | COMBO (`none`/`pretty`) | `pretty` | Only effective when `format=json`; `pretty` pretty-prints valid JSON, `none` writes text verbatim |

#### Outputs

| Name | Type | Description |
|---|---|---|
| `path` | STRING | Full path of the saved file |
| `byte_count` | INT | Bytes written |
| `workflow_json` | STRING | API workflow JSON dumped from `extra_pnginfo` |

> [!WARNING]
> **Filename is fixed to `<prefix>_00001.<ext>` and does NOT auto-resume counters** (unlike SaveImagePlus). Repeated saves will **overwrite** the same-named file. To keep multiple snapshots, change `filename_prefix` between runs.

</details>

---

### 🎯 ZImageTurboProgressive (Menu: `ZSimple-Nodes/sampling`)

A **one-click 3-stage sampler** for Z-Image Turbo: sketch at low resolution (fast structure pass) → upscale and refine → final image at target resolution. All in a single block — no need to manually chain three KSamplers.

**Typical usage**: use `quality` chain for "fast-then-refined"; bump `creativity_mode` to `middle` or `high` for more variety; set `stage3_count=4` to get four candidates at once.

#### Key knobs

| Knob | What it does |
|---|---|
| `steps` | How many sampling steps (default 8 — the sweet spot for speed vs quality) |
| `creativity_mode` | How much the model "thinks outside the box": `off`=stays on template / `lite`=slight variation (default) / `middle`=original X21 (some creative flair) / `high`=bold and adventurous |
| `stage_resolution_chain` | Speed vs detail tradeoff: `fast`=quick sketch (stage 1 at 1/4 size) / `quality`=quality-first (default, stage 1 at 1/2) / `aggressive`=progressive upscale through all 3 stages / `none`=no resizing |
| `stage_handoff_mode` | How stages hand off between each other: `off`=fully independent / `legacy`=standard handoff (default) / `locked`=tightly anchored to previous stage (experimental) |
| `stage3_count` | How many candidate images the final stage produces (1–4, can be chain-refined) |

<details>
<summary>📋 Full parameter & output reference (click to expand)</summary>

#### All inputs (18)

| Name | Type | Default | Description |
|---|---|---|---|
| `latent_input` | LATENT | — | Empty Latent output |
| `model` | MODEL | — | Z-Image Turbo loader output |
| `positive` | CONDITIONING | — | Single prompt (shared across all stages) |
| `cfg` | FLOAT (0.0–15.0) | 1.0 | Z-Image Turbo is CFG-distilled; 1.0 recommended |
| `seed` | INT | 0 | Stage 1 uses this seed; stage 2 uses `seed+16`; stage 3 uses `696969 + i` (i = slot index) |
| `add_noise` | COMBO (`enable`/`disable`) | `enable` | Whether stage 1 adds noise; set to `disable` for inpainting |
| `return_leftover_noise` | COMBO (`enable`/`disable`) | `disable` | Whether stage 3 retains residual σ noise for downstream samplers |
| `steps` | INT (2–64) | 8 | Total steps; 8 selects `alpha_8`; 3–7 / 9–15 select `alpha_N` or interpolated presets; >15 falls back to `alpha_8` |
| `creativity_mode` | COMBO (`off`/`lite`/`middle`/`high`) | `lite` | See "Four levels" table below |
| `noise_bias_offset` | FLOAT (-0.5–0.5) | 0.0 | Extra bias; clamped together with `noise_strength*4-1` to ±10. **Non-zero triggers a 64×64 noise probe.** For single-knob control, keep at 0 and use `noise_strength` |
| `stage_resolution_chain` | COMBO (`fast`/`quality`/`aggressive`/`none`) | `quality` | X21-style `(s1, s2, s3)` scaling factors; final resize back to input size |
| `noise_strength` | FLOAT (0.0–2.0) | 1.0 | overdose=`(noise_strength-1)*0.4` + bias level=`noise_strength*4-1`; 1.0 = no change |
| `stage_handoff_mode` | COMBO (`off`/`legacy`/`locked`) | `legacy` | Stage-to-stage σ noise handoff mode; see below |
| `stage3_count` | INT (1–4) | 1 | Stage 1/2 each run once; stage 3 runs N times, producing `latent_stage3_0..3` (slots beyond N = `None`) |
| `stage3_chain_mode` | COMBO (`off`/`chain`) | `chain` | `off` = N independent candidates; `chain` = N serial refinements (uses `_STAGE3_CHAIN_SIGMAS`) |
| `stage1_sampler` | COMBO | `euler` | Stage 1 sampler (full `comfy.samplers.SAMPLER_NAMES` set) |
| `stage2_sampler` | COMBO | `euler` | Stage 2 sampler |
| `stage3_sampler` | COMBO | `dpmpp_sde` | Stage 3 sampler |

#### `stage_resolution_chain` — four presets

| Preset | (s1, s2, s3) | Behavior |
|---|---|---|
| `fast` | (0.25, 0.50, 1.00) | X21 default speed preset; stage 1 shrinks to 1/4 |
| `quality` | (0.50, 0.75, 1.00) | Quality preset; stage 1 starts at 1/2 |
| `aggressive` | (0.25, 0.50, 0.75) | Progressive upscale through stages; stage 3 sized at 0.75 then resized back to input |
| `none` | (1, 1, 1) | Skip size adjustments; samplers decide per stage |

#### `creativity_mode` — four levels

| Level | Stage 1 s1 start σ | Scramble stage 2 | Preproc (1-step euler) | Notes |
|---|---|---|---|---|
| `off` | 0.991 | ❌ | ❌ | Fully disable X21 scramble+refine; stage 2 silently passes through |
| `lite` (default) | 0.960 | ❌ | ✅ | Lower s1 start σ (low-frequency fill) + preproc for stability |
| `middle` | 0.991 | ✅ | ✅ | Original X21 behavior: 0.991 s1 + scramble + preproc |
| `high` | 0.960 | ✅ | ✅ | All on: 0.960 s1 + scramble + preproc |

> [!NOTE]
> When `seed % 3 == 0`, **preproc is skipped** (`high_as_a_kite` short-circuit); the same rule applies to all four levels.

#### `stage_handoff_mode` — three modes

| Mode | Behavior |
|---|---|
| `off` | Fully skip `_noise_inverse`; each stage samples fresh noise — no signal continuity between stages |
| `legacy` (default) | `_noise_inverse(model, x0, sigma_target=0, ...)`; with `sigma_target=0` it returns `x0` directly. Stage entrance internally re-noises via `ModelSamplingDiscreteFlow.noise_scaling`, so the previous stage's signal survives into the next without double noising |
| `locked` | `_noise_inverse(model, x0, sigma_target=stage_{i+1}'s first σ, ...)`; output fed directly as `epsilon` to `_stage_denoise(eps_external=...)` of the next stage. **Tightest signal continuity, but experimental** |

#### `stage3_chain_mode`

- **`off`** (batch): stage 3 produces N **independent candidates** from the same stage 2 latent, each with `noise_seed = 696969 + i`.
- **`chain`** (default, N serial refinements): slot `i` refines slot `i-1`'s output latent; the sigma sequence follows `_STAGE3_CHAIN_SIGMAS[min(i, 3)]` (4 sigma triplets indexed by slot).

> [!WARNING]
> **Not thread-safe**: module-level `_PARTITION_CACHE` (shared with `ComfyUI-ZImageTurboProgressiveLockedUpscale`) will race between concurrent instances. **Run only one `ZImageTurboProgressive` instance at a time.**

#### All outputs (7)

| Name | Type | Description |
|---|---|---|
| `latent_stage1` | LATENT | Stage 1 clean latent (force-final-denoised to σ=0); ready for downstream VAE Decode |
| `latent_stage2` | LATENT | Stage 2 clean latent (force-final-denoised to σ=0) |
| `latent_stage3_0` | LATENT | Stage 3 slot 0 (`noise_seed = 696969+0`); `None` when `stage3_count < 1` |
| `latent_stage3_1` | LATENT | Slot 1 (`696969+1`); `None` when `stage3_count < 2` |
| `latent_stage3_2` | LATENT | Slot 2 (`696969+2`); `None` when `stage3_count < 3` |
| `latent_stage3_3` | LATENT | Slot 3 (`696969+3`); `None` when `stage3_count < 4` |
| `debug_scrambled_latent` | LATENT | Debug-only: under `creativity_mode`, the latent right after scramble and before stage2 preproc/denoise; under no-creativity, right after `noise_inversion`. `None` when there's no stage 2. Feed to VAE Decode to inspect |

#### Sigma preset quick reference

- `alpha_3` ~ `alpha_10`: 8 hardcoded presets (`_SIGMA_PRESETS_BY_NAME`)
- `steps = 11` ~ `15`: insert intermediate σ per `_ALPHA_INSERT_COUNTS = {(11,(1,1)), ..., (15,(5,5))}`
- `steps ∈ [16, 99]`: `extra = steps-9`; `n1 = int(0.4 + 0.6*extra)`, `n2 = extra - n1`; insert rules generate the schedule
- Anything else: fall back to `alpha_8`
- `_REFINE_ENTER_SIGMA = 0.658`: stage 3 sigma sequence is sliced from the first σ ≤ 0.658

</details>

---

## 🛠️ Adding a New Node

The plugin follows the **one-file-per-node** single-responsibility convention.

```bash
# 1. Create the node file
touch nodes/my_new_node.py

# 2. Implement the class in that file
# Reference nodes/random_number_plus.py or nodes/save_image_plus.py

# 3. Register in root __init__.py
# from .nodes.my_new_node import MyNewNode
# NODE_CLASS_MAPPINGS["MyNewNode"] = MyNewNode

# 4. Restart ComfyUI
```

---

## 📦 Dependencies

> [!NOTE]
> ComfyUI's built-in dependencies (`comfy_api`, `Pillow`, `numpy`) don't need to be declared in `requirements.txt`. This plugin only pulls an external dep when:

| Type | Package | Required? | Notes |
|---|---|---|---|
| Optional | `pillow-jxl-plugin` | ❌ | Needed only for `SaveImagePlus` `format="jxl"`; install with `pip install pillow-jxl-plugin` |

See [`requirements.txt`](requirements.txt) for the full declaration (default contains only a commented example).

---

## 🧪 Running Tests

```bash
python -m pytest tests/
```

There is currently one test file: `tests/test_zimage_turbo_progressive.py`.

---

## 📝 Compatibility

- **ComfyUI**: V3 schema (`comfy_api.latest` / `io.ComfyNode`, latest stable recommended)
- **Python**: 3.10+
- **OS**: Windows / macOS / Linux

---

## 📝 License

This project is open-sourced under the [MIT License](LICENSE).

---

## 🙏 Acknowledgements

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — for making node-based workflows possible
- Everyone who has filed suggestions, feedback, and Issues

<div align="center">

**If this project helps you, a ⭐ Star keeps development going!**

</div>