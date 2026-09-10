<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### 简洁、实用的 ComfyUI 自定义节点合集

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-7-orange?style=for-the-badge)](#-节点列表)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**为 ComfyUI 工作流添砖加瓦 · 单文件单节点 · 现代压缩与质量参数**

🌐 **[English Version](./README.en.md)**

</div>

---

## ✨ 七个节点，各自解决一个具体痛点

| 节点 | 痛点 | 关键特性 |
|---|---|---|
| **RandomNumberPlus** | 节点间 seed 传递格式不统一 | 每次给你一个新种子，同时输出数字版和文字版两种格式，下游节点不用再转类型 |
| **SaveImagePlus** | 同一节点只能写死 PNG / 固定压缩 | 一个节点搞定 PNG/JPG/WebP/JXL 四种格式，每种格式独立调画质；自动编号，再也不覆盖旧图 |
| **SaveTextPlus** | prompt / workflow 文本需要临时存档 | 把提示词和工作流 JSON 存到本地，再也不怕改坏了找不回上一版 |
| **SaveVideoPlus** | 视频帧序列需要保存为 mp4/webm/gif | mp4(libx264) / webm(libvpx-vp9 恒定质量) / gif(PIL) 三格式；frame_rate / quality / loop_count / pingpong / metadata embed；STRING 输出文件名+帧数；客户端进程 try/finally 清理 |
| **ZImageTurboProgressive** | Z-Image Turbo 单节点缺少统一的 3 阶段 progressive sampling 编排 | Z-Image Turbo 的三段式采样器：先粗画、再细化、最后出大图，全在一个节点里完成 |
| **ZSimpleAnthropicAgent** | 短 prompt 扩写 / 文案润色需要写规则、调 API | 通过本地 Anthropic 代理调用 Claude Messages API；system prompt 从 markdown 文件下拉选择；STRING → STRING；API 失败直接 raise |
| **ZSimpleOpenAIAgent** | 短 prompt 需要调用 OpenAI 兼容 API（默认 Qwen）扩写 | 节点参数全自包含（model/api_key/base_url/temperature/max_tokens）；默认指向阿里云 DashScope Qwen；STRING → STRING；空 api_key 或 API 失败直接 raise |

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
git clone https://github.com/SoftMeng/ComfyUI-ZSimple-Nodes.git
cd ComfyUI-ZSimple-Nodes
pip install -r requirements.txt
```

> [!TIP]
> 重启 ComfyUI 后，新节点会出现在菜单的 **ZSimple-Nodes** 类目下，子目录：`image` / `text` / `sampling`。

---

## 📦 节点列表

### 🎲 RandomNumberPlus（菜单：`ZSimple-Nodes`）

随机生成种子。每跑一次自动给你一个新的种子值，同时给你**数字版和文字版**两种格式（直接接到任何节点都行，不用手动转类型），外加**下一颗种子**方便连续抽卡。

**典型用法**：把数字版种子喂给 KSampler 复现同一张图；把文字版种子接到 SaveImagePlus 的"文件名前缀"，文件名里就自动带上种子号。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `seed` | 种子值；前端自带"随机换一颗/加一/减一/锁定"按钮，不用你手动改 |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

**输入**

| 名称 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| `seed` | INT | 0 | 0 ~ 2⁶⁴-1 | 种子值；前端控制按钮由 `control_after_generate` 启用 |

**输出**

| 名称 | 类型 | 值 |
|---|---|---|
| `int_out` | INT | `int(seed)` |
| `string_out` | STRING | `str(seed)` |
| `number_out` | INT | `seed` |
| `next_int` | INT | `seed + 1` |

**搜索别名**：`random` / `seed` / `rng`

</details>

---

### 🖼️ SaveImagePlus（菜单：`ZSimple-Nodes/image`）

一个节点搞定所有图片保存格式：PNG（无损）/ JPG（带压缩）/ WebP（更小）/ JXL（最新最强）。画质、是否压缩、是否把提示词一起存进图片，都可以在节点上调。文件自动按日期分子文件夹、自动编号，永远不会覆盖你之前的出图。

**典型用法**：批量跑图时直接接在出图节点后面，挑格式和画质就行。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `format` | 保存格式：PNG / JPG / WebP / JXL（默认 PNG 无损） |
| `quality` | JPG/WebP 的画质（默认 92 已经很高，肉眼几乎看不出差别） |
| `filename_prefix` | 文件名前缀；自动按日期（`%date:yyyy-MM-dd%`）分子文件夹 |
| `embed_metadata` | 是否把提示词和工作流一起存进图片（默认存全部；JPG 工作流很大时会自动改成只存 prompt） |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

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

</details>

---

### 📝 SaveTextPlus（菜单：`ZSimple-Nodes/text`）

把提示词、工作流 JSON、或者任意多行文本存到本地 .txt / .md / .json / .csv 文件。JSON 格式会自动美化（带缩进），方便阅读。

**典型用法**：在调试工作流时随时存档当前 prompt 和 workflow；想保留多份历史版本时改一下文件名前缀即可。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `text` | 要保存的内容（必填，多行） |
| `format` | 保存格式：txt / md / json / csv（默认 txt） |
| `filename_prefix` | 文件名前缀；自动按日期分子文件夹 |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

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

</details>

---

### 🎬 SaveVideoPlus（菜单：`ZSimple-Nodes/video`）

把 ComfyUI IMAGE 帧序列编码为 mp4 / webm / gif 视频保存到 output/。mp4(libx264) 兼容性最广、webm(libvpx-vp9) 开源高压缩、gif 走 PIL 无 ffmpeg 依赖。三格式统一参数 + 自动续接编号 + 客户端进程 try/finally 清理。

**典型用法**：把 KSampler/VHS 视频工作流末尾的 IMAGE 张量接进来，配置 fps 与 quality 出 mp4；或做 gif 表情包接 `loop_count`；webm 适合上传开源视频平台。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `format` | mp4 / webm / gif 三选一；默认 mp4 |
| `frame_rate` | 输出视频帧率（fps）；默认 24 |
| `quality` | mp4=webm 的 CRF 反向参数（1=低质大文件，100=高质小文件）；gif 忽略此字段 |
| `loop_count` | 仅 gif 生效；0=无限循环（与 PIL 语义一致），1=播放 1 遍停 |
| `pingpong` | on 时追加反向帧（去首尾）制造无缝循环播放 |
| `embed_metadata` | 仅 mp4 生效；写 prompt / workflow 到容器 metadata；workflow 超 60KB 自动截断只留 prompt |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `images` | IMAGE (force_input) | — | ComfyUI IMAGE tensor 批；支持 3 通道(RGB) / 4 通道(RGBA) / 2 维灰度 |
| `format` | COMBO | `mp4` | `mp4` / `webm` / `gif` |
| `frame_rate` | FLOAT (1.0–120.0) | 24.0 | 输出视频帧率（fps） |
| `filename_prefix` | STRING | `ZSimple` | — |
| `subfolder_template` | STRING | `%date:yyyy-MM-dd%` | output/ 下子目录模板，支持 `%date%`/`%width%`/`%height%` |
| `filename_number_padding` | INT (1–9) | 5 | 文件计数器零填充宽度（5 → 00001） |
| `quality` | INT (1–100) | 90 | mp4=webm 的 CRF 反向参数 |
| `loop_count` | INT (0–100) | 0 | 仅 gif；0=无限循环 |
| `pingpong` | COMBO (`off`/`on`) | `off` | on 时追加反向帧制造无缝循环 |
| `embed_metadata` | COMBO (`none` /`prompt_only`/`all`) | `all` | 仅 mp4；workflow 超 60KB 自动截断 |

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `images` | IMAGE | 原图透传 |
| `paths` | STRING | 保存文件的相对路径 |
| `filename_first` | STRING | 保存的文件名 |
| `frame_count` | INT | 实际编码的帧数（含 pingpong 附加帧） |
| `workflow_json` | STRING | extra_pnginfo workflow JSON；不可用时为空字符串 |

#### ⚠️ 重要约束

- **API 失败 / 包缺失 / 空 images / 编码异常** 全部 raise（workflow 红条失败，不静默降级）
- **mp4 metadata 写入 prompt + workflow**：与 SaveImagePlus 同等风险面，分享 workflow 等于分享提示词内容（开源插件通用行为，与 VHS 一致）
- **编码中途若遇磁盘满 / ffmpeg 崩溃**：try/finally 保证 ffmpeg 子进程被 close，不会泄漏
- **frame_count 含 pingpong 帧**：若 pingpong=on 启用，frame_count = 原始帧数 × 2 − 2

#### 三种格式的取舍

| 格式 | 编码器 | 体积 | 兼容性 | 适用场景 |
|---|---|---|---|---|
| mp4 | libx264（h264） | 中 | 极广（几乎所有播放器 / 平台） | 通用默认 |
| webm | libvpx-vp9（CRF 恒定质量） | 较小 | 较好（YouTube / Web 主流） | 开源平台、追求体积 |
| gif | PIL（256 色 palette） | 较大 | 极广 | 短小动图、表情包 |

#### 搜索别名

`save` / `save video` / `export` / `mp4` / `webm` / `gif`

</details>

---

### 🎯 ZImageTurboProgressive（菜单：`ZSimple-Nodes/sampling`）

Z-Image Turbo 的**一键三段采样**：先生成草图（低分辨率快速铺结构）→ 再放大细化 → 最后到目标分辨率出大图。一个节点完成，不用手动串三个 KSampler。

**典型用法**：想要"先快后精"就用 `quality` 档；想要创意多一些就把 `creativity_mode` 调到 `middle` 或 `high`；想要一次出多张候选就选 `stage3_count=4`。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `steps` | 画几步（默认 8 步，质量与速度的平衡点） |
| `creativity_mode` | 让模型多想还是少想：`off`=纯模板不走样 / `lite`=轻微变化（默认）/ `middle`=原版 X21（带点发挥）/ `high`=大胆发挥 |
| `stage_resolution_chain` | 跑多快 vs 跑多细：`fast`=快速草稿（首段 1/4 尺寸）/ `quality`=质量优先（默认，首段 1/2）/ `aggressive`=激进三段渐进 / `none`=不缩放 |
| `stage_handoff_mode` | 阶段之间怎么衔接：`off`=完全独立 / `legacy`=标准接力（默认）/ `locked`=紧咬上一步（实验性） |
| `stage3_count` | 最后阶段出几张候选图（1-4 张，可链式细化） |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 全部输入（18 项）

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

> [!WARNING]
> **不线程安全**：模块级 `_PARTITION_CACHE`（与 `ComfyUI-ZImageTurboProgressiveLockedUpscale` 共享）会在并发实例间竞争。**同时只跑一个 `ZImageTurboProgressive` 实例**。

#### 全部输出（7 项）

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

</details>

---

### 🤖 ZSimpleOpenAIAgent（菜单：`ZSimple-Nodes/agent`）

通过 OpenAI 兼容 Chat Completions API（默认指向阿里云 DashScope Qwen）把一段简短 prompt 扩展成更完整、更结构化的输出。**STRING → STRING**：输入文本 → 输出扩展后的文本。所有连接信息都在节点 UI 上，零环境变量配置 — 跨平台复制 workflow 即可直接跑。

**典型用法**：用国内 API（DashScope / DeepSeek / 月之暗面 等 OpenAI 兼容端点）做 prompt 扩写；切换 base_url 也能直连 OpenAI 官方。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `model` | OpenAI 兼容模型名，默认 `qwen3.5-flash` |
| `api_key` | API key（必填，空字符串时节点会拒绝执行） |
| `base_url` | OpenAI 兼容 base url，默认指向阿里云 DashScope |
| `system_prompt` | 从 `system_prompt/` 目录下的 markdown 文件下拉选择；选 `none` 时改用下面的 `prompt_enhancement_text` |
| `temperature` | 采样温度，默认 0.7 |
| `max_tokens` | 最大生成 token，默认 4096 |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | STRING (multiline, force_input) | — | 用户输入文本（user message content） |
| `system_prompt` | COMBO | `none` | `system_prompt/` 下所有 `.md` 文件名（不含扩展名），首项固定 `none` |
| `prompt_enhancement_text` | STRING (multiline) | `""` | 仅 `system_prompt=none` 时生效：作为 system 字段发送；空时省略 system 字段 |
| `model` | COMBO | `qwen3.5-flash` | `qwen3.5-flash` / `qwen-plus` / `qwen-max` / `qwen-turbo` |
| `api_key` | STRING | `""` | API key；**空字符串 → RuntimeError** |
| `base_url` | STRING | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容 base url |
| `temperature` | FLOAT (0.0–2.0) | 0.7 | 采样温度；0=确定性，1=默认，2=最大多样性 |
| `max_tokens` | INT (1–8192) | 4096 | 最大生成 token 数 |

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `output_text` | STRING | 模型返回的文本内容 |
| `model_used` | STRING | SDK 响应中读取的实际模型名（调试用） |

#### 三种 system 模式

| `system_prompt` 取值 | `prompt_enhancement_text` | 实际请求中的 `system` 消息 |
|---|---|---|
| `foo`（任一 md 文件名） | 任意 | 读取 `system_prompt/foo.md` 文件内容 |
| `none` | 非空 | `prompt_enhancement_text` 原样 |
| `none` | 空（仅空白） | **完全省略** system 消息 |

#### 客户端缓存

按 `(api_key, base_url)` 缓存 SDK client：

- 同一组 key + url → 复用 client（省去每次新建 HTTP 连接）
- 改了 key 或 url → 自动重建
- `model` 不影响 client 身份，所以切换模型不会触发重建

> [!WARNING]
> **API key 会写入 workflow JSON**。ComfyUI 把所有节点参数原样序列化到 `.json` workflow 文件里，分享 workflow 等于分享你的 API key。**分享前请先清空 `api_key` 字段**（或用文本编辑器手动替换）。
>
> 隐私优先的用户：考虑自建一个 wrapper 节点（不在本仓库）来从本地文件读 key，再传给本节点的 `api_key` 输入。

> [!WARNING]
> **未安装 `openai` SDK** 时，节点首次执行会抛出 `RuntimeError("请运行 pip install openai")`，**不**会让 ComfyUI 启动崩溃。
>
> **API key 空字符串** 时立即 `RuntimeError("api_key 为空...")`，不静默调用。
>
> **API 调用失败**（网络、token、超时）一律直接 `raise`，让 ComfyUI workflow 红条失败；不静默降级。

#### 切换到 OpenAI 官方 / 其他兼容端点

只需改 `base_url`：

| 端点 | base_url |
|---|---|
| 阿里云 DashScope（默认） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| OpenAI 官方 | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 自建 / 第三方代理 | 你的 URL |

model 字段填对应端点支持的模型名即可。

#### 搜索别名

`openai` / `qwen` / `dashscope` / `llm` / `prompt enhancer` / `prompt expander`

</details>

---

### 🤖 ZSimpleAnthropicAgent（菜单：`ZSimple-Nodes/agent`）

通过本地 Anthropic 代理调用 Claude Messages API，把一段简短 prompt 扩展成更完整、更结构化的输出。**STRING → STRING**：输入文本 → 输出扩展后的文本。API 失败直接 raise，workflow 红条失败（不静默）。

**典型用法**：在写图 prompt / 写工作流注释时，先让 Claude 帮你把一段口语化描述扩写成正式 prompt；也可以用作"文案润色""指令改写"等通用 LLM 节点。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `system_prompt` | 从 `system_prompt/` 目录下的 markdown 文件下拉选择，作为 Claude 的 system 指令；选 `none` 时改用下面的 `prompt_enhancement_text` |
| `prompt_enhancement_text` | 仅当 `system_prompt=none` 时生效：作为 system 字段发送；留空 → 完全省略 system |
| `model` | Claude 模型名，默认 `claude-sonnet-4-6` |
| `max_tokens` | 最大生成 token，默认 1024 |
| `temperature` | 采样温度，默认 1.0 |

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | STRING (multiline, force_input) | — | 用户输入文本（user message content） |
| `system_prompt` | COMBO | `none` | `system_prompt/` 下所有 `.md` 文件名（不含扩展名），首项固定 `none` |
| `prompt_enhancement_text` | STRING (multiline) | `""` | 仅 `system_prompt=none` 时生效：作为 system 字段发送；空时省略 system 字段 |
| `model` | COMBO | `claude-sonnet-4-6` | `claude-sonnet-4-6` / `claude-3-5-sonnet-latest` / `claude-opus-4-6` |
| `max_tokens` | INT (1–8192) | 1024 | 最大生成 token 数 |
| `temperature` | FLOAT (0.0–2.0) | 1.0 | 采样温度；0=确定性，1=默认，2=最大多样性 |

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `output_text` | STRING | 模型返回的文本内容 |
| `model_used` | STRING | SDK 响应中读取的实际模型名（调试用） |

#### `system_prompt/` 目录

- 节点扫描 `<plugin>/system_prompt/*.md`，把文件名（不含 `.md`）作为下拉选项。
- 首项固定为 `none`，代表"不使用 system prompt"。
- 插件自带两个示例：
  - `prompt_enhancer.md` — 通用 prompt 扩写（中文风格）
  - `image_prompt_expander.md` — 图像生成 prompt 扩写（输出英文、可直接喂 SD/Flux）
- **新增 / 修改 markdown 文件后重启 ComfyUI** 才会刷新下拉（COMBO 选项在节点注册时静态确定）。

#### 三种 system 模式

| `system_prompt` 取值 | `prompt_enhancement_text` | 实际请求中的 `system` 字段 |
|---|---|---|
| `foo`（任一 md 文件名） | 任意 | 读取 `system_prompt/foo.md` 文件内容 |
| `none` | 非空 | `prompt_enhancement_text` 原样 |
| `none` | 空（仅空白） | **完全省略** system 字段（让 Claude 自由发挥） |

#### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `http://127.0.0.1:5000` | Claude API base url（指向本地代理） |
| `ANTHROPIC_AUTH_TOKEN` | `PROXY_MANAGED` | API key；`PROXY_MANAGED` 表示由本地代理管理真实 token |

> [!WARNING]
> **未安装 `anthropic` SDK** 时，节点首次执行会抛出 `RuntimeError("请运行 pip install anthropic")`，**不**会让 ComfyUI 启动崩溃。

> [!WARNING]
> **API 调用失败**（代理 5000 端口不通、token 无效、超时、模型返回错误）一律直接 `raise`，让 ComfyUI workflow 红条失败；不静默降级。

#### 搜索别名

`anthropic` / `claude` / `llm` / `prompt enhancer` / `prompt expander`

</details>

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
> ComfyUI 内置依赖（`comfy_api`、`Pillow`、`numpy`）不需要在 `requirements.txt` 中声明。本插件的外部依赖：

| 类型 | 包名 | 必需 | 说明 |
|---|---|---|---|
| 必需 | `anthropic` | ✅ | `ZSimpleAnthropicAgent` 节点需要；安装：`pip install anthropic>=0.40.0` |
| 必需 | `openai` | ✅ | `ZSimpleOpenAIAgent` 节点需要；安装：`pip install openai>=1.0.0` |
| 必需 | `imageio-ffmpeg` | ✅ | `SaveVideoPlus` 节点需要（mp4/webm 编码；gif 不需要）；安装：`pip install imageio-ffmpeg>=0.5.0` |
| 可选 | `pillow-jxl-plugin` | ❌ | 启用 `SaveImagePlus` 的 `format="jxl"` 时需 `pip install pillow-jxl-plugin` |

完整声明见 [`requirements.txt`](requirements.txt)（默认仅含注释示例）。

---

## 🧪 运行测试

```bash
python -m pytest tests/
```

> [!NOTE]
> 由于本插件的 `__init__.py` 一次性 import 全部 5 个节点（其中部分依赖 ComfyUI runtime 的 `comfy.*` 模块），**独立 pytest 环境**（无 ComfyUI 安装）下 `pytest` 会因 `ModuleNotFoundError: No module named 'comfy.*'` 失败。
>
> 推荐两种运行方式：
>
> - **各节点单测（推荐）**：在 plugin 根目录直接执行 `python tests/test_z_simple_anthropic_agent.py` / `python tests/test_z_simple_openai_agent.py` / `python tests/test_save_video_plus.py`（自带 comfy_api stub，无需 ComfyUI 安装）。
> - **完整 pytest 套件**：在 **ComfyUI 实际 runtime**（`comfy` 已装）下 `python -m pytest tests/` 可跑通。

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
- 所有提供建议、反馈、Issue 的用户

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star 支持开发！**

</div>