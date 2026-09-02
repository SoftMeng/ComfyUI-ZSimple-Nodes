<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### 简洁、实用的 ComfyUI 自定义节点合集

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-4-orange?style=for-the-badge)](#-节点列表)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**为 ComfyUI 工作流添砖加瓦 · 单文件单节点 · 现代压缩与质量参数**

</div>

---

## ✨ 四个节点，各自解决一个具体痛点

| 节点 | 痛点 | 关键特性 |
|---|---|---|
| **RandomNumberPlus** | 节点间 seed 传递格式不统一 | INT 当前值 + `next_int`（seed + 1）给下游节点预热 |
| **SaveImagePlus** | 同一节点只能写死 PNG / 固定压缩 | PNG / JPEG / WebP / JXL 四格式；每格式独立质量参数；metadata 策略可控；自动续接 counter 防覆盖；4 个 STRING 输出可链式 |
| **SaveTextPlus** | prompt / workflow 文本需要临时存档 | `txt` / `md` / `json` / `csv` 四格式；JSON 自动 pretty-print；返回完整路径与字节数 |
| **ZImageTurboProgressive** | Z-Image Turbo 单节点缺少统一的 3 阶段 progressive upscale 编排 | 3 阶段（构图 / 协调 / 细化）；CFG / shift / 创意 / Spectral-Tilt / Detailed-Refiner 一站式开关 |

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
> 重启 ComfyUI 后，新节点会出现在菜单的 **ZSimple-Nodes** 类目下。

---

## 📦 节点列表

### 🎲 RandomNumberPlus（菜单：ZSimple-Nodes）

**用途**：随机种子生成器，输出当前 seed + 下一值（seed + 1）。

| 特性 | 说明 |
|---|---|
| 多输出 | `int_out`（当前 seed）+ `number_out`（同 int_out，便于不同连接节点命名）+ `next_int`（seed + 1）|
| 生成后控制 | `randomize` / `increment` / `decrement` / `fixed` —— 由 ComfyUI 前端 widget 处理 |
| 零依赖 | 仅依赖 ComfyUI V3 API |

**典型用法**：从 `int_out` / `next_int` 注入下一节点的 KSampler。

---

### 🖼️ SaveImagePlus（菜单：ZSimple-Nodes/image）

**用途**：单节点保存图像到多种格式，精细控制压缩参数与 metadata 嵌入策略。

#### 压缩参数（2026 最佳实践默认值）

| 参数 | 默认 | 适用格式 | 理由 |
|---|---|---|---|
| `quality` | 92 | JPEG / WebP | 4:4:4 + 视觉无损，印刷级 |
| `png_compress_level` | 9 | PNG | 存档优先，最大压缩 |
| `jpeg_subsampling` | `4:4:4` | JPEG | Q≥90 时自动 4:4:4，避免色彩丢失 |
| `webp_lossless` | `off` | WebP | 开启时忽略 quality，走 PIL 默认无损编码 |
| `webp_method` | 4 | WebP | 速度 vs 大小平衡 |

> [!WARNING]
> **JPEG EXIF 段硬硬限 64KB**。大 workflow + prompt JSON 经常超量，导致 metadata 静默截断。SaveImagePlus 检测到超量时会**自动降级到 `prompt_only`**，但仍建议**存档优先用 PNG 或 lossless WebP**。

#### Counter 续接（避免覆盖）

每次 `execute()` 启动时扫描目标子目录，按 `<filename_prefix> + ext` 过滤已有文件，取最大 `_NNNNN + 1` 作为起始 counter；目录为空时仍从 `_00001` 起算。四种格式（png / jpeg / webp / jxl）各自独立计数，同 prefix 切换格式互不串扰。

#### 输出

- `images`：IMAGE（原图透传，可继续接到下游节点）
- `paths`：STRING（所有保存文件的相对路径，逗号分隔）
- `filename_first`：STRING（本批第一张的文件名）
- `workflow_json`：STRING（自动从 `extra_pnginfo` 导出 API workflow JSON；空字符串表示不可用）

### 📝 SaveTextPlus（菜单：ZSimple-Nodes/text）

**用途**：保存任意文本到 `.txt` / `.md` / `.json` / `.csv`，字段单一职责（filename_prefix / subfolder_template / padding），并暴露 `workflow_json` 输出。

**输入**（7 个）：
- `text`：STRING（必填，多行）
- `extra_texts`：STRING（可选，多行，追加在 text 之后）
- `filename_prefix`：默认 `"ComfyUI"`
- `subfolder_template`：默认 `"%date:yyyy-MM-dd%"`，独立子目录
- `filename_number_padding`：INT 1-9，默认 5
- `format`：`txt` / `md` / `json` / `csv`，默认 `txt`
- `embed_json_keys`：`none` / `pretty`，默认 `pretty`（仅 format=json 时生效）

**输出**（3 个）：
- `path`：STRING（保存的文件完整路径）
- `byte_count`：INT（写入字节数）
- `workflow_json`：STRING（自动从 `extra_pnginfo` 导出 API workflow JSON）

> [!WARNING]
> **当前文件名固定为 `<prefix>_00001.<ext>`，不会续接 counter**（与 SaveImagePlus 行为不同）。重复保存会覆盖同名文件——若需保留多份，请先切换 `filename_prefix`。

---

### 🎯 ZImageTurboProgressive（菜单：ZSimple-Nodes/sampling）

**用途**：Z-Image Turbo 专用 3 阶段 progressive upscale（步数比例 2:4:2），按阶段差异化能力：

- Stage 1：构图（`creativity_mode` 可选）
- Stage 2：协调（per-stage 采样器 / 调度器独立）
- Stage 3：细化（`detailed_refiner` + `spectral_tilt` 可选）

实现参考 `ComfyUI-ZImagePowerNodes` 的核心编排模式（sigma preset + scramble + spectral tilt），对外暴露单一节点。

#### 核心输入

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `latent_input` | LATENT | — | Empty Latent 节点输出 |
| `model` | MODEL | — | Z-Image Turbo loader 输出 |
| `positive` | CONDITIONING | — | 主条件 |
| `positive_stg2` | CONDITIONING (可选) | — | Stage 2 单独条件 |
| `positive_stg3` | CONDITIONING (可选) | — | Stage 3 单独条件 |
| `cfg` | FLOAT | 1.0 (min=0, max=15) | Z-Image Turbo 推荐 1.0（CFG-distilled） |
| `seed` | INT | 0 | `control_after_generate=True` |
| `shift` | FLOAT | 3.5 (min=0, max=100, 0=关闭) | logit-normal 时间分布重映射；Z-Image Turbo ≈ 3.5 |
| `steps` | INT | 8 (min=2, max=64) | 总步数按 2:4:2 分配为 2/4/2 |
| `start_step` / `end_step` | INT | 0 / 8 | 仅 Stage 1 有效 |

#### 多阶段独立参数

| 参数 | stage1 | stage2 | stage3 |
|---|---|---|---|
| `sampler` | euler | euler | dpmpp_sde |
| `scheduler` | normal | normal | normal |

可选 8 个 sampler：`euler` / `euler_ancestral` / `dpmpp_2m` / `dpmpp_sde` / `dpmpp_2m_sde` / `dpmpp_3m_sde` / `uni_pc` / `ddim`
可选 6 个 scheduler：`normal` / `karras` / `exponential` / `sgm_uniform` / `ddim_uniform` / `beta`

#### 能力开关

| 参数 | 默认 | 说明 |
|---|---|---|
| `creativity_mode` | `off` | `off` / `scrambled`（构图变体） / `refined_1/2/3`（N 步 coherence 恢复） |
| `detailed_refiner` | True | Stage 3 切 dpmpp_sde 增强高频细节 |
| `spectral_tilt` | `none` | Colored Noise Sampling 频域塑形；5 档预设：`none` / `stage3_H` / `stages12x_H` / `stages12x_l` / `stages123_H` |
| `upscale_factor` | 2.0 (min=1, max=4) | 单 stage 倍率；3 stage 总放大 = `factor²` |
| `add_noise` | `enable` | Stage 1 是否加噪（inpainting 设为 `disable`） |
| `return_leftover_noise` | `disable` | Stage 3 是否保留残留噪波（链式下游节点用） |

#### 输出

- `latent_output`：LATENT（denoise 完成后的最终 latent）

> [!WARNING]
> - **shift 默认 3.5 与 Z-Image Turbo 官方推荐一致**；改为其它值（特别是 ≥4）会导致生成图"melted/smeared"（社区实测）。
> - **upscale_factor > 1.0** 会让 latent 输出尺寸 = 输入 × `factor²`（例：factor=2 → 4× 放大）。如需保持输入尺寸，factor=1.0。
> - **return_leftover_noise=enable** 会让 Stage 3 保留残留 σ 噪波，可能让下游节点处理异常——确认下游需要时再启用。

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
| 可选 | `pillow-jxl-plugin` | ❌ | 启用 `format="jxl"` 时需 `pip install pillow-jxl-plugin` |

完整声明见 [`requirements.txt`](requirements.txt)（默认仅含注释示例）。

---

## 🧪 兼容性

- **ComfyUI**：V3 schema（推荐最新稳定版）
- **Python**：3.10+
- **操作系统**：Windows / macOS / Linux

---

## 📝 许可证

本项目以 [MIT 许可证](LICENSE) 开源。

---

## 🙏 致谢

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) —— 让节点工作流成为可能
- [ComfyUI-ZImagePowerNodes](https://github.com/martin-rizzo/ComfyUI-ZImagePowerNodes) —— ZImageTurboProgressive 节点的核心算法实现参考
- 所有提供建议、反馈、Issue 的用户

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star 支持开发！**

</div>