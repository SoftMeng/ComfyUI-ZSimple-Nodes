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

## ✨ Five nodes, each solves one specific pain point

| Node | Pain point | Key features |
|---|---|---|
| **RandomNumberPlus** | Inconsistent seed types across nodes | Outputs the seed in both number and text format, plus the next seed — drop into any downstream node without type conversions |
| **SaveImagePlus** | Built-in save node locks you into PNG / fixed compression | Save in PNG / JPG / WebP / JXL, tune each format's quality independently. Auto-numbers every file so nothing ever gets overwritten |
| **SaveTextPlus** | Need to dump prompts / workflow JSON to disk fast | Save prompts and workflow JSON to disk — never lose a working version again |
| **ZImageTurboProgressive** | No single-node 3-stage progressive sampler for Z-Image Turbo | A 3-stage progressive sampler for Z-Image Turbo: rough pass → refine → final, all in one node — no manual chaining required |
| **ZLTXVideoTurboProgressive** | LTX2.5 multimodal video workflows require 14+ LTXV operator nodes | LTX2.5 two-stage progressive video sampler (Stage1 low-res + ×2 upscale + Stage2 high-res); multimodal text/image/audio in single node config |

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
git clone https://github.com/SoftMeng/ComfyUI-ZSimple-Nodes.git
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

### 🎞️ ZLTXVideoTurboProgressive (Menu: `ZSimple-Nodes/sampling`)

Single-stage AV latent sampler for LTX2.5. Receives a pre-built `Guider` and AV latent, runs sampling on a preset sigma schedule.

#### Design principles

- **Focused on sampling**: the node does not handle AV lifecycle (concat/separate), CFG construction, or mask routing — those live in upstream nodes.
- **Guider as parameter**: built upstream by `CFGGuider` or `DualCFGGuider`, then passed in.
- **Chainable**: 2-stage progressive = two single-stage calls + native upscale between them.

#### 2-stage workflow example

```
LoadImage
  → LTXVAddGuide (inject frame N reference)
  → CLIPTextEncode × 2 (positive / negative)
  → CFGGuider / DualCFGGuider (model + cond + cfg)
  → EmptyLTXVLatent (starting video latent)
  → LTXVAudioVAEEncode (audio → audio_latent)
  → LTXVConcatAVLatent (video latent + audio latent)
  → ZLTXVideoTurboProgressive(stage="stage1")
  → LTXVLatentUpscaler (official ×2 latent upscale)
  → ZLTXVideoTurboProgressive(stage="stage2")
  → LTXVSeparateAVLatent (split video + audio)
  → VAEDecodeTiled + LTXVAudioVAEDecode
  → CreateVideo
```

#### Inputs (14)

| Name | Type | Default | Description |
|---|---|---|---|
| `model` | MODEL | — | For latent preview callback |
| `guider` | GUIDER | — | Pre-built upstream CFGGuider / DualCFGGuider |
| `av_latent` | LATENT | — | Concatenated AV latent (NestedTensor) |
| `sampler_obj` | SAMPLER | — | Sampling algorithm (e.g. `euler_ancestral_cfg_pp`) |
| `sigmas_pipe` | STRING (multiline) | (2-line distilled_default) | One σ schedule per line = one stage. Previous stage's output is re-noised and used as input for the next. Stage 0 must start at 1.0; subsequent stages may start at any σ ≤ 1.0. All stages end at 0.0 and are monotonically non-increasing. |
| `upscale_modes` | STRING | `external` | Per-stage upscale mode, comma-separated. Single value broadcasts. `external` is only valid for stage 0 (use 'interpolate' or 'vae_roundtrip' between stages). |
| `vae_video` | VAE | — | Required when any upscale_mode is 'interpolate' or 'vae_roundtrip' |
| `upscale_model` | LATENT_UPSCALE_MODEL | — | Reserved |
| `guidance_rescale` | FLOAT | 0.7 | SD3 CFG rescale; applied per stage |
| `enforce_per_frame_path` | BOOL | false | Reject noise_masks with spatial extent; triggers model's per_frame_path optimization |
| `enable_stg` | BOOL | false | Auto-bundle STG for every stage |
| `enable_modality_guidance` | BOOL | false | Auto-bundle Modality Guidance for every stage |
| `stg_blocks` | STRING | `29` | STG self-attention block indices (comma-separated) |
| `modality_scale` | FLOAT | 3.0 | Modality guidance scale; 1.0 disables |
| `seed` | INT | 0 | Noise seed; each stage adds stage-index offset (seed+i) |

#### Output (1)

| Name | Type | Description |
|---|---|---|
| `latent` | LATENT | Sampled AV latent (NestedTensor); downstream uses `LTXVSeparateAVLatent` to split |

#### sigmas_pipe multi-stage

Each line is one stage's σ schedule. The previous stage's output is re-noised (by the sampler) and fed to the next as clean latent_image. This is the direct expression of Karras EDM stochastic churn / SD3 resample / SDXL refiner inside one node.

**First σ of each line** must be in `(0, 1]`:
- `1.0` = full noise (pure T2V / multi-stage refinement)
- `<1.0` = V2V denoise strength: source-video latent is blended as `x = latent × (1-σ₀) + noise × σ₀`; lower σ₀ follows the source more (0.3-0.4 light repaint; 0.5-0.6 medium transform; 0.7-0.8 heavy repaint)

**Last σ of each line**: only the LAST line must end at `0.0` (VAE decode needs a fully denoised latent); intermediate lines may stop at σ > 0 for trajectory segmentation (below). All lines monotonically non-increasing.

#### Trajectory segmentation (Z-Image style)

When an intermediate line stops at σ_end > 0, the next line's handoff semantics:

| Next line's first σ vs previous line's last σ | Handoff behavior |
|---|---|
| **Equal** (1e-6 tolerance) | **Exact continuation**: the partially-noised latent passes through unchanged (`noise = latent` makes `x_init = latent×(1-σ₀)+latent×σ₀ = latent`, an identity); trajectories splice seamlessly |
| **A jump** | Re-noise approximation (previous output blended with fresh noise as if clean — the Z-Image `_noise_inverse` technique); smaller jumps approximate better, keep \|Δσ\| ≤ 0.05 |

Compared to "denoise every stage to 0 then re-noise", segmentation avoids the destructive noise round-trip and **preserves detail much better** — ideal for "coarse denoise at low res → upscale → continue at high res":

```
sigmas_pipe:
  [1.0, 0.98, 0.94, 0.86, 0.80]           ← stage 0 @ half resolution, stops at σ=0.80
  [0.80, 0.72, 0.60, 0.42, 0.20, 0.0]     ← stage 1 @ full resolution, exact continuation to 0

upscale_modes: "external,interpolate"      ← ×2 interpolate between stages (works on noisy latents)
```

Z-Image Turbo's `alpha_8` preset uses exactly this shape: stage1 `(0.991→0.920)` stops at high σ, stage2 continues `(0.935→0)` with a tiny +0.015 bump.

Example (distilled_default 2-stage):
```
[1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]
[0.909375, 0.725, 0.4219, 0.0]
```

Example (3-stage iterative refinement):
```
[1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]
[0.5, 0.25, 0.0]
[0.357, 0.125, 0.0]
```

Example (V2V medium transform — source video encoded via VAEEncode feeds av_latent):
```
[0.6, 0.5, 0.4, 0.0]
```

#### upscale_modes × sigmas_pipe

`upscale_modes` length should equal `sigmas_pipe` lines (single value broadcasts). **Stage 0 never upscales** (no predecessor); stage i > 0 executes the upscale.

| Mode | Requires | Behavior |
|---|---|---|
| `external` | stage 0 only | No in-node upscale (user wires `LTXVLatentUpscaler` between two node calls) |
| `interpolate` | stage > 0 + `vae_video` | Pure `F.interpolate(scale=(1,2,2))` in latent space |
| `vae_roundtrip` | stage > 0 + `vae_video` | VAE decode → bilinear pixel upscale → VAE encode |

**Example**: 3-stage progressive + interpolate between stage 1→2:
```
sigmas_pipe:
  [1.0, ..., 0.725, 0.0]      # stage 0: full-resolution generation
  [0.42, 0.21, 0.0]          # stage 1: re-noise + upscale + refine
  [0.357, 0.125, 0.0]        # stage 2: refine (no upscale)

upscale_modes: "external,interpolate,external"
```

#### Per-stage optimizations (A / B / C / D)

| Optimization | Trigger | Effect |
|---|---|---|
| A. SD3 CFG rescale | `guidance_rescale>0` | Applied per stage; debiases high-σ CFG output |
| B. per_frame_path validation | `enforce_per_frame_path=True` | Rejects noise_masks with spatial extent |
| C. STG bundle | `enable_stg=True` | Auto-bundles Spatio-Temporal Guidance per stage |
| D. Modality Guidance bundle | `enable_modality_guidance=True` | Auto-bundles Modality Guidance per stage |

#### Quick Start (minimum nodes)

1. **Load models**: UNETLoader + VAELoader × 2 + CLIPLoader
2. **Build Guider**: `CLIPTextEncode × 2` → `CFGGuider` (cfg=1.0)
3. **Build AV latent**: `EmptyLTXVLatentVideo` → `LTXVConcatAVLatent`
4. **Single call sampling** (2-stage, default sigmas_pipe):
   `ZLTXVideoTurboProgressive(sigmas_pipe="<2-line distilled_default>")`
5. **Decode + save**: `LTXVSeparateAVLatent` → `VAEDecodeTiled` + `LTXVAudioVAEDecode` → `CreateVideo`

Reference workflow: `examples/use_new_node.json`.

##### 4. Full multimodal (Text + Image + Audio)

Combine 1+2+3, all optional inputs connected, `stages` defaults to `auto_2stage`.

##### 5. Out of VRAM?

- Change `latent_scaling` from `quality` to `aggressive` (Stage1 runs at 0.25× spatial, saves ~4× VRAM)
- Change `intensity` from 1.0 to 0.8 (lower noise)
- Change `stages` from `auto_2stage` to `stage1_only` (skip upscale + Stage2)

##### 6. Want a quick preview?

- `stages=stage1_only` + `steps_s1=4` → 4-step Stage1-only preview, ~30 seconds

---

## ❓ FAQ

### Why is CFG default 1.0?

LTX2.5-distilled models are trained **without** classifier-free guidance (CFG=1.0 is not a typo). Set `cfg=1.0` on the upstream `CFGGuider` node; changing to 1.5 or 2.0 will significantly degrade video quality.

> Upstream `LTXVDualCFGGuider` (if used) defaults to `video_cfg=3.0, audio_cfg=7.0`; for distilled workflows override both to 1.0. For dev / SFT models, see [HuggingFace Lightricks/LTX-2.5-Diffusers](https://huggingface.co/Lightricks/LTX-2.5-Diffusers) for modality_scale / guidance_rescale guidance.

### Why is my video all black/noise?

Most common causes:

1. **CFG not locked at 1.0** — set cfg=1.0 on the upstream Guider node
2. **Sigma preset overwritten** — schedule input must use default `distilled_default` for distilled models
3. **Frame count does not satisfy `(length-1) % 8 == 0`** — valid values: 9, 17, 25, 33, ..., 97, 121, 241, 361
4. **Empty latent dimensions not divisible by 32** — e.g. 800×800 should be 768×768 or 832×832

### How do I inject a reference image?

This node does not handle image injection — use upstream `LTXVAddGuide(frame_idx=N, strength=...)` to inject the reference into the conditioning and latent before they reach `LTXVConcatAVLatent`. The patched conditioning and noise_mask flow into the Guider naturally.

### Why does frame 48 (or any guided frame) lose the reference after upscale?

Because `LTXVLatentUpscaler` drops the noise_mask during spatial ×2 upscaling. To keep the reference, run a second `LTXVAddGuide` between the upscaler and `ZLTXVideoTurboProgressive(stage="stage2")`, OR ensure the noise_mask in the model patches is preserved through upscale.

### How do I save audio?

The node outputs a single `latent` (NestedTensor AV latent). Downstream must use `LTXVSeparateAVLatent` to split into `video_latent` + `audio_latent`, then:
- video → `VAEDecodeTiled` → `CreateVideo`
- audio → `LTXVAudioVAEDecode` → `CreateVideo` (audio slot)

### Can I customize sigma?

The current schedule is locked to `distilled_default` to guarantee distilled correctness. **Custom sigma input is not yet exposed** — if you need customization, use native `KSampler` + `comfy.sample.sample_custom` and wire manually.

### Can I use 361 frames?

Yes, but it is "long-form" usage (>121 single-shot default). Recommendations:

- Use `latent_scaling=aggressive` to save VRAM
- Use `intensity=0.9` to lower noise_overdose
- Or segment: split into 2 segments of 181 frames (~7.5 seconds each), continue with same seed

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