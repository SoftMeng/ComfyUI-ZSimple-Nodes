<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### 简洁、实用的 ComfyUI 自定义节点合集

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-4-orange?style=for-the-badge)](#-节点列表)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**为 ComfyUI 工作流添砖加瓦 · 单文件单节点 · 现代压缩与质量参数**

🌐 **[English Version](./README.en.md)**

</div>

---

## ✨ 四个节点，各自解决一个具体痛点

| 节点 | 痛点 | 关键特性 |
|---|---|---|
| **RandomNumberPlus** | 节点间 seed 传递格式不统一 | INT 当前值 + STRING 当前值 + `next_int`（seed + 1）—— 可直接喂给下游需要字符串的输入 |
| **SaveImagePlus** | 同一节点只能写死 PNG / 固定压缩 | PNG / JPEG / WebP / JXL 四格式；每格式独立质量参数；metadata 策略可控；自动续接 counter 防覆盖；4 个 STRING 输出可链式 |
| **SaveTextPlus** | prompt / workflow 文本需要临时存档 | `txt` / `md` / `json` / `csv` 四格式；JSON 自动 pretty-print；返回完整路径与字节数 |
| **ZImageTurboProgressive** | Z-Image Turbo 单节点缺少统一的 3 阶段 progressive sampling 编排 | BRAVO/ALPHA hardcoded sigma preset；`stage_resolution_chain`（fast/quality/aggressive/none）尺寸链；`noise_strength`/`noise_bias_offset` 双旋钮；`creativity_mode` 4 档（off/lite/middle/high）；`stage_handoff_mode`（off/legacy/locked）；`stage3_chain_mode` 链式 refine；7 个 latent 输出 + 调试接口 |

> [!NOTE]
> 本项目处于活跃迭代阶段，节点按需添加。如果你有特定工作流痛点想要解决，欢迎提 Issue。

---

## 🚀 快速上手

### 通过 ComfyUI Manager（推荐）

1. 打开 ComfyUI Manager
2. 搜索 `ComfyUI-ZSimple-Nodes`
3. 点击 Install
4. 重启 ComfyUI

### 通过 Git Clone

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/your-username/ComfyUI-ZSimple-Nodes.git
cd ComfyUI-ZSimple-Nodes
pip install -r requirements.txt
```

> [!TIP]
> 重启 ComfyUI 后，新节点会出现在菜单的 **ZSimple-Nodes** 类目下，子目录：`image` / `text` / `sampling`。

---

## 📦 节点列表

### 🎲 RandomNumberPlus（菜单：`ZSimple-Nodes`）

**用途**：随机种子生成器，输出当前 seed（多种类型） + 下一值（seed + 1）。

| 特性 | 说明 |
|---|---|
| 多类型输出 | `int_out`（INT 当前 seed）+ `string_out`（STRING 当前 seed，可直接接到 `filename_prefix`）+ `number_out`（INT 同 int_out）+ `next_int`（seed + 1）|
| 搜索别名 | `random` / `seed` / `rng` |
| 控制后生成 | `randomize` / `increment` / `decrement` / `fixed` —— 由 ComfyUI 前端 widget 处理 |
| 零依赖 | 仅依赖 ComfyUI V3 API |

**输入**

| 名称 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| `seed` | INT | 0 | 0 ~ 2⁶⁴-1 | 种子值；`control_after_generate=True` 启用前端控制按钮 |

**输出**

| 名称 | 类型 | 值 |
|---|---|---|
| `int_out` | INT | `int(seed)` |
| `string_out` | STRING | `str(seed)` |
| `number_out` | INT | `seed` |
| `next_int` | INT | `seed + 1` |

**典型用法**：从 `int_out` / `next_int` 注入下一节点的 KSampler；从 `string_out` 注入 SaveTextPlus/SaveImagePlus 的 `filename_prefix`。

---

### 🖼️ SaveImagePlus（菜单：`ZSimple-Nodes/image`）

**用途**：单节点保存图像到多种格式，精细控制压缩参数与 metadata 嵌入策略。

#### 输入（11 项）

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `images` | IMAGE | — | 待保存图像（可多张）|
| `filename_prefix` | STRING | `"ZSimple"` | 文件名前缀 |
| `subfolder_template` | STRING | `"%date:yyyy-MM-dd%"` | output/ 下的子目录模板，支持 `%date%`/`%seed%`/`%width%`/`%height%`；空字符串 = 直接保存到 `output_dir` 根目录 |
| `filename_number_padding` | INT (1-9) | 5 | 文件计数器零填充宽度（5 → `_00001`）|
| `format` | COMBO | `png` | `png` / `jpeg` / `webp` / `jxl` |
| `quality` | INT (1-100) | 92 | JPEG / WebP 质量（`webp_lossless=on` 时忽略）|
| `png_compress_level` | INT (0-9) | 9 | PNG 压缩等级（9 = 最大压缩）|
| `webp_lossless` | COMBO (`off`/`on`) | `off` | 开启时走 PIL 默认无损编码 |
| `webp_method` | INT (0-6) | 4 | WebP 编码速度/大小平衡 |
| `jpeg_subsampling` | COMBO (`4:4:4`/`4:2:0`) | `4:4:4` | Q≥90 推荐 4:4:4 |
| `embed_metadata` | COMBO (`none`/`prompt_only`/`all`) | `all` | PNG tEXt + JPEG EXIF 嵌入策略 |

> [!WARNING]
> **JPEG EXIF 段硬限约 60KB**（`_JPEG_EXIF_SAFETY_BYTES = 60000`）。大 workflow + prompt JSON 经常超量，导致 metadata 静默截断。SaveImagePlus 检测到超量时会**自动降级到 `prompt_only`**——但仍建议**存档优先用 PNG 或 lossless WebP**。

#### Counter 续接（避免覆盖）

每次 `execute()` 启动时扫描目标子目录，按 `<filename_prefix>_<NNNNN>.<ext>` 过滤已有文件，取最大编号 + 1 作为起始 counter；目录为空时仍从 `_00001` 起算。**四种格式（png / jpeg / webp / jxl）各自独立计数**，同一 prefix 切换格式互不串扰。

#### JXL 支持

`format="jxl"` 需要 `pillow-jxl-plugin`。未安装时执行会立即报错：

```
RuntimeError: JPEG XL save requires pillow-jxl-plugin.
Install with: pip install pillow-jxl-plugin
```

JXL `distance` 公式：`distance = max(0.0, (100 - quality) / 20.0)`。

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `images` | IMAGE | 原图透传，可继续接到下游节点 |
| `paths` | STRING | 所有保存文件的相对路径，逗号分隔 |
| `filename_first` | STRING | 本批第一张的文件名 |
| `workflow_json` | STRING | 自动从 `extra_pnginfo` 导出 API workflow JSON；空字符串表示不可用 |

---

### 📝 SaveTextPlus（菜单：`ZSimple-Nodes/text`）

**用途**：保存任意文本到 `.txt` / `.md` / `.json` / `.csv`，单一职责字段，并暴露 `workflow_json` 输出。

#### 输入（7 项）

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | STRING | — | 主文本（多行，强制输入）|
| `extra_texts` | STRING | `""` | 可选追加文本，多行；存在则前置换行后追加 |
| `filename_prefix` | STRING | `"ComfyUI"` | 文件名前缀 |
| `subfolder_template` | STRING | `"%date:yyyy-MM-dd%"` | 子目录模板，同 SaveImagePlus |
| `filename_number_padding` | INT (1-9) | 5 | 文件名计数零填充宽度（**实际不使用**，见下方警告）|
| `format` | COMBO | `txt` | `txt` / `md` / `json` / `csv` |
| `embed_json_keys` | COMBO (`none`/`pretty`) | `pretty` | 仅 `format=json` 时生效；`pretty` 对合法 JSON pretty-print；`none` 按原文写入 |

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `path` | STRING | 保存的文件完整路径 |
| `byte_count` | INT | 写入字节数 |
| `workflow_json` | STRING | 自动从 `extra_pnginfo` 导出 API workflow JSON |

> [!WARNING]
> **文件名固定为 `<prefix>_00001.<ext>`，不会续接 counter**（与 SaveImagePlus 行为不同）。重复保存会**覆盖同名文件**——若需保留多份，请先切换 `filename_prefix`。

---

### 🎯 ZImageTurboProgressive（菜单：`ZSimple-Nodes/sampling`）

**用途**：Z-Image Turbo 专用 3 阶段 progressive sampling。Sigma 序列来自 **BRAVO/ALPHA hardcoded preset**（每 stage 独立、不连续 sigma），尺寸链由 `stage_resolution_chain` 四档控制，初始噪声由 `noise_strength`（overdose + bias level）+ `noise_bias_offset`（额外 probe 触发）双旋钮驱动。

算法参考 `ComfyUI-ZImagePowerNodes/zsampler_turbo_core.py` 与 `zsampler_turbo_X21.py`。

> [!WARNING]
> **不线程安全**：模块级 `_PARTITION_CACHE`（与 `ComfyUI-ZImageTurboProgressiveLockedUpscale` 共享）会在并发实例间竞争。**同时只跑一个 `ZImageTurboProgressive` 实例**。

#### 输入（18 项）

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `latent_input` | LATENT | — | Empty Latent 输出 |
| `model` | MODEL | — | Z-Image Turbo loader 输出 |
| `positive` | CONDITIONING | — | 单 prompt（三 stage 共用）|
| `cfg` | FLOAT (0.0-15.0) | 1.0 | Z-Image Turbo 是 CFG-distilled，推荐 1.0 |
| `seed` | INT | 0 | stage1 用此 seed；stage2 用 `seed+16`，stage3 用 `696969 + i`（i = slot 索引）|
| `add_noise` | COMBO (`enable`/`disable`) | `enable` | stage1 是否加噪；inpainting 设为 `disable` |
| `return_leftover_noise` | COMBO (`enable`/`disable`) | `disable` | stage3 是否保留残 σ 噪波给下游 sampler 续接 |
| `steps` | INT (2-64) | 8 | 总步数；8 选 `alpha_8`，3–7/9–15 选 `alpha_N` 或插值生成；>15 回落 `alpha_8` |
| `creativity_mode` | COMBO (`off`/`lite`/`middle`/`high`) | `lite` | 见下方"四档差异"表 |
| `noise_bias_offset` | FLOAT (-0.5~0.5) | 0.0 | 额外 bias；与 `noise_strength*4-1` 一起 clamp 到 ±10。**非零触发 64x64 noise probe**。单旋钮控制时保持 0，使用 `noise_strength` |
| `stage_resolution_chain` | COMBO (`fast`/`quality`/`aggressive`/`none`) | `quality` | X21 风格三元组 `(s1, s2, s3)` 缩放因子；最终 resize 回输入尺寸 |
| `noise_strength` | FLOAT (0.0-2.0) | 1.0 | overdose=`(noise_strength-1)*0.4` + bias level=`noise_strength*4-1`；1.0 = 无变化 |
| `stage_handoff_mode` | COMBO (`off`/`legacy`/`locked`) | `legacy` | stage→stage 的 σ 噪波接力方式；见下方说明 |
| `stage3_count` | INT (1-4) | 1 | stage1/stage2 各跑 1 次；stage3 跑 N 次，输出 `latent_stage3_0..3`（超出 N 的槽位 = `None`）|
| `stage3_chain_mode` | COMBO (`off`/`chain`) | `chain` | `off` = N 个独立候选；`chain` = N 次串行 refine（走 `_STAGE3_CHAIN_SIGMAS`）|
| `stage1_sampler` | COMBO | `euler` | stage1 采样器（`comfy.samplers.SAMPLER_NAMES` 全集）|
| `stage2_sampler` | COMBO | `euler` | stage2 采样器 |
| `stage3_sampler` | COMBO | `dpmpp_sde` | stage3 采样器 |

#### `stage_resolution_chain` 四档

| 档位 | (s1, s2, s3) | 行为 |
|---|---|---|
| `fast` | (0.25, 0.50, 1.00) | X21 默认速度档；stage1 缩到 1/4 尺寸 |
| `quality` | (0.50, 0.75, 1.00) | 精细档；stage1 1/2 起步 |
| `aggressive` | (0.25, 0.50, 0.75) | 三阶段逐步放大，stage3 缩到 0.75 再 resize 回输入 |
| `none` | (1, 1, 1) | 跳过尺寸调整，按 stage 配 sampler 自决 |

#### `creativity_mode` 四档差异

| 档位 | stage1 s1 起始 σ | scramble stage2 | preproc（1 步 euler）| 说明 |
|---|---|---|---|---|
| `off` | 0.991 | ❌ | ❌ | 完全关闭 X21 的 scramble+refine；stage2 静默直通 |
| `lite`（默认）| 0.960 | ❌ | ✅ | 降低 s1 起始 σ（低频填充）+ preproc 增稳 |
| `middle` | 0.991 | ✅ | ✅ | 原版 X21 行为：0.991 s1 + scramble + preproc |
| `high` | 0.960 | ✅ | ✅ | 全开：0.960 s1 + scramble + preproc |

> [!NOTE]
> `seed % 3 == 0` 时**跳过 preproc**（`high_as_a_kite` 短路），其余三档同理受此规则影响。

#### `stage_handoff_mode` 三档

| 档位 | 行为 |
|---|---|
| `off` | 完全跳过 `_noise_inverse`；每 stage 各采全新噪声，stage 之间信号不连续 |
| `legacy`（默认）| `_noise_inverse(model, x0, sigma_target=0, ...)`；sigma_target=0 时直接返回 `x0`。stage 入口由 `ModelSamplingDiscreteFlow` 的 `noise_scaling` 内部重新加噪，前一阶段信号可存活到下一阶段而不被双倍加噪 |
| `locked` | `_noise_inverse(model, x0, sigma_target=stage_{i+1} 第一 σ, ...)`；输出直接作为下一 stage 的 `epsilon` 喂入 `_stage_denoise(eps_external=...)`。**信号连续性最紧，但实验性** |

#### `stage3_chain_mode`

- **`off`**（batch）：stage3 跑 N 个**独立候选**，从同一 stage2 latent 出发，noise_seed = `696969 + i`，每个 slot 独立 noise。
- **`chain`**（默认，N 次串行 refine）：slot `i` 接力 slot `i-1` 的输出 latent，sigma 序列走 `_STAGE3_CHAIN_SIGMAS[min(i, 3)]`（4 个 sigma 三元组按 slot 索引选取）。

#### 输出（7 项）

| 名称 | 类型 | 说明 |
|---|---|---|
| `latent_stage1` | LATENT | Stage 1 干净 latent（强制 σ=0 终末），可下游 VAE Decode |
| `latent_stage2` | LATENT | Stage 2 干净 latent（强制 σ=0 终末）|
| `latent_stage3_0` | LATENT | Stage 3 slot 0（`noise_seed = 696969+0`）；`stage3_count<1` 时为 `None` |
| `latent_stage3_1` | LATENT | slot 1（`696969+1`）；`stage3_count<2` 时为 `None` |
| `latent_stage3_2` | LATENT | slot 2（`696969+2`）；`stage3_count<3` 时为 `None` |
| `latent_stage3_3` | LATENT | slot 3（`696969+3`）；`stage3_count<4` 时为 `None` |
| `debug_scrambled_latent` | LATENT | 调试用：creativity_mode 路径下 scramble 之后、stage2 preproc/denoise 之前取的 latent；无 creativity 路径下则是 noise_inversion 之后。无 stage2 时为 `None`。可直接 VAE Decode 看图 |

#### Sigma preset 速查

- `alpha_3` ~ `alpha_10`：硬编码 8 套（`_SIGMA_PRESETS_BY_NAME`）
- `steps=11` ~ `15`：按 `_ALPHA_INSERT_COUNTS = {(11,(1,1)), ..., (15,(5,5))}` 插入中间 σ
- `steps ∈ [16, 99]`：`extra = steps-9`；`n1 = int(0.4 + 0.6*extra)`，`n2 = extra - n1`，按插入规则生成
- 其它：回落 `alpha_8`
- `_REFINE_ENTER_SIGMA = 0.658`：stage3 σ 序列从 ≤ 0.658 处切片开始

---

## 🛠️ 添加新节点

本插件遵循"**单文件单节点**"的单一职责原则。

```bash
# 1. 创建节点文件
touch nodes/my_new_node.py

# 2. 在文件中实现类
# 参考 nodes/random_number_plus.py / nodes/save_image_plus.py

# 3. 在根 __init__.py 中注册
# from .nodes.my_new_node import MyNewNode
# NODE_CLASS_MAPPINGS["MyNewNode"] = MyNewNode

# 4. 重启 ComfyUI
```

---

## 📋 依赖

> [!NOTE]
> ComfyUI 内置依赖（`comfy_api`、`Pillow`、`numpy`）不需要在 `requirements.txt` 中声明。本插件仅在以下情况有外部依赖：

| 类型 | 包名 | 必需 | 说明 |
|---|---|---|---|
| 可选 | `pillow-jxl-plugin` | ❌ | 启用 `SaveImagePlus` 的 `format="jxl"` 时需 `pip install pillow-jxl-plugin` |

完整声明见 [`requirements.txt`](requirements.txt)（默认仅含注释示例）。

---

## 🧪 运行测试

```bash
python -m pytest tests/
```

目前仅有一个测试文件 `tests/test_zimage_turbo_progressive.py`。

---

## 📝 兼容性

- **ComfyUI**：V3 schema（`comfy_api.latest` / `io.ComfyNode`，推荐最新稳定版）
- **Python**：3.10+
- **操作系统**：Windows / macOS / Linux

---

## 📝 许可证

本项目以 [MIT 许可证](LICENSE) 开源。

---

## 🙏 致谢

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) —— 让节点工作流成为可能
- [ComfyUI-ZImagePowerNodes](https://github.com/martin-rizzo/ComfyUI-ZImagePowerNodes) —— `ZImageTurboProgressive` 节点的核心算法实现参考
- 所有提供建议、反馈、Issue 的用户

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star 支持开发！**

</div>