<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### 简洁、实用的 ComfyUI 自定义节点合集

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-8-orange?style=for-the-badge)](#-节点列表)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**为 ComfyUI 工作流添砖加瓦 · 单文件单节点 · 现代压缩与质量参数**

🌐 **[English Version](./README.en.md)**

</div>

---

## ✨ 九个节点，各自解决一个具体痛点

| 节点 | 痛点 | 关键特性 |
|---|---|---|
| **RandomNumberPlus** | 节点间 seed 传递格式不统一 | 每次给你一个新种子，同时输出数字版和文字版两种格式，下游节点不用再转类型 |
| **SaveImagePlus** | 同一节点只能写死 PNG / 固定压缩 | 一个节点搞定 PNG/JPG/WebP/JXL 四种格式，每种格式独立调画质；自动编号，再也不覆盖旧图 |
| **SaveTextPlus** | prompt / workflow 文本需要临时存档 | 把提示词和工作流 JSON 存到本地，再也不怕改坏了找不回上一版 |
| **SaveVideoPlus** | 视频帧序列需要保存为 mp4/webm/gif | mp4(libx264) / webm(libvpx-vp9 恒定质量) / gif(PIL) 三格式；frame_rate / quality / loop_count / pingpong / metadata embed；STRING 输出文件名+帧数；客户端进程 try/finally 清理 |
| **ZImageTurboProgressive** | Z-Image Turbo 单节点缺少统一的 3 阶段 progressive sampling 编排 | Z-Image Turbo 的三段式采样器：先粗画、再细化、最后出大图，全在一个节点里完成 |
| **ZLTXVideoTurboProgressive** | LTX2.5 多模态视频工作流需要 14+ LTXV 算子节点堆叠 | LTX2.5 视频两阶段渐进式采样（Stage1 低分辨率 + ×2 升频 + Stage2 高分辨率）；多模态文本/参考图/音频单节点配置 |
| **ZSimpleAnthropicAgent** | 短 prompt 扩写 / 文案润色需要写规则、调 API | 通过本地 Anthropic 代理调用 Claude Messages API；system prompt 从 markdown 文件下拉选择；STRING → STRING；API 失败直接 raise |
| **ZSimpleOpenAIAgent** | 短 prompt 需要调用 OpenAI 兼容 API（默认 Qwen）扩写 | 节点参数全自包含（model/api_key/base_url/temperature/max_tokens）；默认指向阿里云 DashScope Qwen；STRING → STRING；空 api_key 或 API 失败直接 raise |
| **PromptEnhancePlus** | 短 prompt 喂给 LTX/H3/Z-Image/Krea-2 经常效果差，需要按目标模型训练 caption 风格扩写 | 内置 5 个目标模型 system prompt（LTX2.5/H3/Z-Image/Krea-2/Krea-2-Edit），自动适配 Gemma 3/4 + Qwen chat 模板，支持 image/video/audio 多模态输入，支持外接自定义模板覆盖内置 |

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

### 🎞️ ZLTXVideoTurboProgressive（菜单：`ZSimple-Nodes/sampling`）

LTX2.5 视频单阶段采样节点。接收一个预构建的 `Guider` 和 AV latent，按预设 sigma 调度跑采样。

#### 设计原则

- **专注于采样**：节点不做 AV 生命周期（concat/separate）、CFG 构建、mask 路由——这些由上游节点负责
- **Guider 作为参数**：用上游 `CFGGuider` 或 `DualCFGGuider` 节点预构建好，传进来
- **可链式**：2 阶段渐进由"两次单阶段调用 + 中间 native upscale"实现

#### 2 阶段工作流示例

```
LoadImage
  → LTXVAddGuide (注入 frame N 参考图)
  → CLIPTextEncode × 2 (positive / negative)
  → CFGGuider / DualCFGGuider (model + cond + cfg)
  → EmptyLTXVLatent (起始视频 latent)
  → LTXVAudioVAEEncode (audio → audio_latent)
  → LTXVConcatAVLatent (视频 latent + 音频 latent)
  → ZLTXVideoTurboProgressive(stage="stage1")
  → LTXVLatentUpscaler (官方 ×2 latent 上采样)
  → ZLTXVideoTurboProgressive(stage="stage2")
  → LTXVSeparateAVLatent (拆 video + audio)
  → VAEDecodeTiled + LTXVAudioVAEDecode
  → CreateVideo
```

#### 输入（14 项）

| 名称 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `model` | MODEL | — | 用于 latent preview callback |
| `guider` | GUIDER | — | 上游 CFGGuider / DualCFGGuider 节点预构建 |
| `av_latent` | LATENT | — | 已 concat 的 AV latent（NestedTensor） |
| `sampler_obj` | SAMPLER | — | 采样算法（如 `euler_ancestral_cfg_pp`） |
| `sigmas_pipe` | STRING (multiline) | (2 行 distilled_default) | 每行一个 stage 的 σ 调度；前一阶段输出 re-noise 后作为下一阶段输入；每行必须以 1.0 开头、0.0 结尾（首 stage 必须 1.0；后续 stage 可任意 ≤1.0）；单调不增 |
| `upscale_modes` | STRING | `external` | 每阶段间 upscale 模式；逗号分隔；1 个值广播到所有 stage；stage 0 之后不能用 `external` |
| `vae_video` | VAE | — | `interpolate` / `vae_roundtrip` 模式必填 |
| `upscale_model` | LATENT_UPSCALE_MODEL | — | 预留字段（external 模式实际 upscale 由上游节点处理） |
| `guidance_rescale` | FLOAT | 0.7 | SD3 CFG rescale；每阶段都应用 |
| `enforce_per_frame_path` | BOOL | false | 强制 noise_mask 纯时间，触发 model 内部 per_frame_path 优化 |
| `enable_stg` | BOOL | false | 每阶段自动 bundle Spatio-Temporal Guidance（σ-bounded 至 [0.0, 0.5]） |
| `enable_modality_guidance` | BOOL | false | 每阶段自动 bundle Modality Guidance |
| `stg_blocks` | STRING | `29` | STG 自注意力 block 索引（逗号分隔） |
| `modality_scale` | FLOAT | 3.0 | Modality guidance scale；1.0 关闭 |
| `seed` | INT | 0 | 噪声种子；每个 stage 自动加 i 偏移 |

#### 输出（1 项）

| 名称 | 类型 | 说明 |
|---|---|---|
| `latent` | LATENT | 采样后的 AV latent（NestedTensor），下游用 `LTXVSeparateAVLatent` 拆分 |

#### sigmas_pipe 多阶段

每行一个 stage 的 σ schedule，前一阶段输出 re-noise 后传给下一阶段。这是 Karras EDM stochastic churn / SD3 resample / SDXL refiner 在一个节点里的直接表达。

**每行首 σ 规则**：必须 ∈ (0, 1]。
- `1.0` = 从全噪声开始（纯 T2V / 多阶段细化）
- `<1.0` = V2V 去噪强度：源视频 latent 按 `x = latent × (1-σ₀) + noise × σ₀` 混合，σ₀ 越小越贴近源视频（0.3~0.4 轻度重绘；0.5~0.6 中度变换；0.7~0.8 大幅重绘）

**每行末 σ 规则**：仅**最后一行**必须以 `0.0` 结尾（VAE 解码需要完全去噪）；中间行可停在 σ > 0 做**轨迹分段**（见下）。所有行内部单调不增。

#### 轨迹分段（Z-Image 风格）

中间行停在 σ_end > 0 时，下一行的交接语义：

| 下一行首 σ 与上一行末 σ 的关系 | 交接行为 |
|---|---|
| **相等**（容差 1e-6） | **精确续接**：带噪 latent 原样传递（`noise = latent` 使 `x_init = latent×(1-σ₀)+latent×σ₀ = latent` 恒等），轨迹无缝拼接 |
| **存在跳变** | 重加噪近似（把上一段输出按 clean latent 混合新噪声，即 Z-Image `_noise_inverse` 手法）；跳变越小近似越好，建议 \|Δσ\| ≤ 0.05 |

相比"每段都去噪到 0 再重加噪"，轨迹分段不做破坏性的噪声往返，**细节保留显著更好**，尤其适合"低分辨率粗去噪 → upscale → 高分辨率续去噪"：

```
sigmas_pipe:
  [1.0, 0.98, 0.94, 0.86, 0.80]           ← stage 0 @ 半分辨率，停在 σ=0.80
  [0.80, 0.72, 0.60, 0.42, 0.20, 0.0]     ← stage 1 @ 全分辨率，精确续接到 0

upscale_modes: "external,interpolate"      ← 段间 interpolate ×2（对带噪 latent 同样有效）
```

Z-Image Turbo 的 `alpha_8` 预设就是这种形态：stage1 `(0.991→0.920)` 停在高 σ，stage2 以 `(0.935→0)` 近似续接（+0.015 微小跳变）。

示例（distilled_default 2 阶段）：
```
[1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]
[0.909375, 0.725, 0.4219, 0.0]
```

示例（3 阶段迭代细化）：
```
[1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]
[0.5, 0.25, 0.0]
[0.357, 0.125, 0.0]
```

示例（V2V 中度变换，源视频经 VAEEncode 后接入 av_latent）：
```
[0.6, 0.5, 0.4, 0.0]
```

#### upscale_modes 与 sigmas_pipe 配合

`upscale_modes` 长度 = `sigmas_pipe` 行数（除了 1 个值会广播）。**Stage 0 之前不做 upscale**（没有前一阶段）；Stage i > 0 才执行。

| 模式 | 要求 | 行为 |
|---|---|---|
| `external` | 仅 stage 0 | 不在节点内 upscale（由用户在两个节点调用之间接 LTXVLatentUpscaler） |
| `interpolate` | stage > 0 + `vae_video` | 纯 `F.interpolate(scale=(1,2,2))` 在 latent 域 |
| `vae_roundtrip` | stage > 0 + `vae_video` | VAE decode → bilinear 像素插值 → VAE encode |

**示例**：3 阶段渐进 + 第 1→2 stage 用 interpolate：
```
sigmas_pipe:
  [1.0, ..., 0.725, 0.0]      # stage 0: 全分辨率生成
  [0.42, 0.21, 0.0]          # stage 1: re-noise 后 upscale 再细化
  [0.357, 0.125, 0.0]        # stage 2: 进一步细化（无 upscale）

upscale_modes: "external,interpolate,external"
```

#### 每阶段优化（A / B / C / D）

| 优化 | 触发条件 | 效果 |
|---|---|---|
| A. SD3 CFG rescale | `guidance_rescale>0` | 每阶段都应用；高 σ 半段自动 rescale |
| B. per_frame_path 校验 | `enforce_per_frame_path=True` | 拒绝 noise_mask 有空间维度的 latent |
| C. STG bundle | `enable_stg=True` | 每阶段自动 bundle Spatio-Temporal Guidance |
| D. Modality Guidance | `enable_modality_guidance=True` | 每阶段自动 bundle Modality Guidance |

#### Quick Start（最少节点数）

1. **加载模型**：UNETLoader + VAELoader × 2 + CLIPLoader
2. **构 Guider**：`CLIPTextEncode × 2` → `CFGGuider`（cfg=1.0）
3. **构 AV latent**：`EmptyLTXVLatentVideo` → `LTXVConcatAVLatent`
4. **单次采样**（2-stage + external upscaler）：
   `ZLTXVideoTurboProgressive(sigmas_pipe="<2 行 distilled_default>")`
5. **解码 + 保存**：`LTXVSeparateAVLatent` → `VAEDecodeTiled` + `LTXVAudioVAEDecode` → `CreateVideo`

参考工作流见 `examples/use_new_node.json`。

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

### ✨ PromptEnhancePlus（菜单：`ZSimple-Nodes/text`）

用本地轻量 LLM（Gemma 3/4、Qwen 3.5 等）把短 prompt 扩写成目标模型的训练 caption 风格。内置 7 个目标（5 个模型 + 2 个 `Phrase` 风格：中/英）的 system prompt，可外接自定义模板覆盖，支持 image / video / audio 多模态输入。

**典型用法**：短句"A cat walks" → 自动扩写成 LTX 2.5 训练风格的完整描述（含镜头、声音、动作时序），直接喂给 `LTXAddVideoICLoRAGuide` 或 `KSampler` 出片。

#### 关键旋钮

| 旋钮 | 它是干嘛的 |
|---|---|
| `target_model` | 目标模型（LTX2.5 / H3 / Z-Image / Krea-2 / Krea-2-Edit / **Phrase** / **PhraseEN**）—— 决定走哪套内置 system prompt；`Phrase` 输出中文逗号分隔短语串，`PhraseEN` 输出英文逗号分隔短语串（30-80 词），适配 SD / FLUX / Z-Image 等 T2I 模型 |
| `mode` | `auto` = 按 image/video/audio 是否连接自动选 T2V/T2I/I2V；或强制指定 |
| `custom_template` | 非空时优先于内置模板；用户粘贴自己的 system prompt |
| `image` / `video` / `audio` | 可选多模态参考；连接 image/video 自动切 I2V，Krea-2-Edit 必须连接图 |
| `max_length` / `temperature` / `top_k` / `top_p` / `seed` | 标准 LLM 采样参数 |

> [!NOTE]
> **输入/输出语言**：Z-Image 是 **Tongyi-MAI（阿里达摩院）** 发布的双语模型，HF 官方 model card 一再强调 *"bilingual text rendering (English & Chinese)"*。`PromptEnhancePlus` 内置 Z-Image 模板默认输出**中文 caption**（保留"汉服/大雁塔/龙"等中文专属实体）；用户输入可以是中文或英文。要英文 caption，用 `custom_template` 粘贴英文版 Krea-2 官方 expansion prompt 覆盖。

> [!IMPORTANT]
> **Image 多模态需要视觉语言 CLIP**：`image` 输入端口接受首帧参考图，但只有加载视觉语言 CLIP（`Qwen2.5-VL-7B-Instruct` / `Qwen-Image-Edit` / `Gemma4-12B+` 等）时图片才会真正影响扩写内容。普通文本编码器（`qwen3_4b.safetensors` 即 Z-Image TE、`Lumina2` 等）会**静默丢弃** `image` 输入——本节点在检测到这种不匹配时会主动 raise 提示，避免"看似跑通但实际零效果"的误判。每轮 execute 都会在控制台打印诊断日志（family / formatted_text_len / image tensor / tokenize output 含 vision token 计数），用于确认 image 是否被真正注入。

> [!TIP]
> 内置 system prompt 以可编辑的 markdown 文件存放在 `model_system_prompt/` 文件夹下（如 `zimage_t2i.md`、`h3_t2v.md`），可直接修改文件内容自定义内置模板，无需改代码。

<details>
<summary>📋 完整参数与输出参考（点击展开）</summary>

#### 输入

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `clip` | CLIP | — | 本地 LLM（通过 ComfyUI `LoadCLIP` 加载 Gemma / Qwen 等） |
| `prompt` | STRING | `""` | 用户短 prompt（multiline + dynamic_prompts） |
| `target_model` | COMBO | `LTX2.5` | `LTX2.5` / `H3` / `Z-Image` / `Krea-2` / `Krea-2-Edit` / `Phrase` / `PhraseEN` |
| `mode` | COMBO | `auto` | `auto` / `T2V` / `T2I` / `I2V` |
| `image` | IMAGE | opt | 首帧参考（I2V 模式自动启用） |
| `video` | IMAGE | opt | 视频帧序列（24 FPS，1 FPS 内部采样） |
| `audio` | AUDIO | opt | 音频上下文（仅 qwen 支持） |
| `custom_template` | STRING | `""` | 外接 system prompt，覆盖内置 |
| `max_length` | INT | 512 | LLM 最大输出 token |
| `temperature` | FLOAT | 0.7 | 采样温度 |
| `top_k` | INT | 64 | top-k 采样 |
| `top_p` | FLOAT | 0.95 | nucleus 采样 |
| `seed` | INT | 0 | 随机种子 |

#### 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `enhanced_prompt` | STRING | 扩写后的 prompt，已剥离 `<think>` 推理块；空输出回退到原始 prompt |

#### Chat 模板自动适配

节点根据 `clip.tokenizer.clip_name` 自动选择 chat 模板：

| 加载的 LLM | chat 模板 |
|---|---|
| 含 `gemma4` | `<\|turn\|>system...<\|turn\|>` |
| 含 `gemma` / 默认 | `<start_of_turn>system...<start_of_turn>` |
| 含 `qwen` | `<\|im_start\|>system...<\|im_end\|>` |
| 未知 | 兜底 gemma3 格式 + 警告 |

#### 7 个内置模板来源

| 模型 | 模板风格 | 来源 |
|---|---|---|
| LTX 2.5 | 客观、镜头三要素（shot type + camera motion + viewpoint）、电影级 | 与 ComfyUI `TextGenerateLTX2Prompt` LTX24 系列同源 |
| H3 | 三段式结构（integrated_multimodal_description / overall_soundscape / non_diegetic_music）+ Shot-based + 时间锚点 | `MiniMax-H3/skills/h3-prompt-writing/references/base-en.txt` |
| Z-Image | 自然语言 + 风格前缀 + 摄影术语 | 与 `ComfyUI-ZImagePowerNodes` style encoder 风格对齐 |
| Krea-2 | 自然语言、详细、含具体细节（颜色/构图/灯光/视角） | 直接复用 `krea-2/docs/expansion.txt` 官方模板 |
| Krea-2-Edit | 指令式 + 参考图描述 | 与 `Comfyui-QwenEditUtils` llama_template 风格一致 |
| **Phrase** | 中文逗号分隔短语串 | 通用 T2I 风格；见 `model_system_prompt/phrase_t2i.md` |
| **PhraseEN** | 英文逗号分隔短语串（无完整句子、无主谓结构） | 通用 T2I 风格（SD / FLUX / Z-Image）；见 `model_system_prompt/phrase_en.md` |

#### 与 ZSimpleAgent 系列的区别

| 节点 | LLM 来源 | 用途 |
|---|---|---|
| `ZSimpleAnthropicAgent` | 云端 Claude API | 通用 prompt 润色 |
| `ZSimpleOpenAIAgent` | OpenAI 兼容 API（默认 Qwen DashScope） | 通用 prompt 扩写 |
| `PromptEnhancePlus` | **本地 LLM**（Gemma/Qwen 通过 CLIP loader 加载） | **按目标模型训练 caption 风格**扩写 |

#### 搜索别名

`prompt enhance` / `LLM` / `prompt expander` / `gemma` / `qwen`

</details>

---

## 🧩 Gemma → Qwen Adapter (Z-Image bridge)

把 LTX2.5 配套的 Gemma4 (`gemma4_e2b_it_int8_convrot.safetensors`, hidden=1536, 35 层) 当作 Z-Image 的 Qwen3-4B 替代文本编码器使用,通过训练一个 Perceiver-Resampler + MLP adapter 做跨模型特征空间对齐。

> **路线 B 蒸馏对齐** —— 当前是 MSE-only warmup,对齐精度有限;production 前应做 denoising-loss 精调(节点 metadata `denoising_done=False` 会打 WARNING)。详见 [CLIP 替换方案参考](docs/principle/04-vl-models.md) 与节点源码。

### 🏋️ TrainGemmaToQwenAdapter(菜单:`ZSimple-Nodes/training`)

训练节点。两阶段流水线:

1. **Stage 1 特征抽取**:遍历 `texts_dir/*.txt`,分别用 `clip_gemma` 与 `clip_qwen` 编码,缓存到 `model-trainer/cached_features/{idx:05d}.pt`
2. **Stage 2 训练**:Perceiver-Resampler (4 层, 8 头, 77 latents) + MLP proj (1536→2560),MSE 蒸馏对齐 Gemma4 → Qwen3 隐藏态

#### 关键旋钮

| 旋钮 | 默认 | 说明 |
|---|---|---|
| `texts_dir` | `~/ComfyUI/output/2026-09-16` | .txt prompt 文件目录,文件名 `NNNN.txt` |
| `layer_idx` | `-2` | 双 CLIP 提取层索引;`-2` 匹配 ZImageTE 默认 |
| `chat_template` | `user\n{}\nassistant\n` | 推理时也要用同一 chat 模板 |
| `batch_size` | `4` | bf16 + 124M adapter, RTX 4090 推荐 4~8 |
| `epochs` | `20` | val_loss patience=3 早停 |
| `lr` | `5e-5` | AdamW + cosine annealing + clip_grad_norm=1.0 |
| `run_train` | `True` | `False` 时只抽特征不训练 |

#### 输出

- `adapter_path` STRING — 产物 `model-trainer/gemma_to_zimage_adapter.safetensors`(含 metadata `phase`、`denoising_done`)

#### 已知约束

- **ComfyUI execution.py:751 用 `torch.inference_mode()` 包裹节点**——训练节点内部用 `torch.inference_mode(False)` 局部开启 autograd(否则 adapter 参数被 inference 标记,`loss.backward()` 抛 `element 0 of tensors does not require grad`)。
- `_pad_stack` 阶段会丢弃无效样本但 cache 落盘循环按 `len(prompts)` 索引,collate 阶段再过滤 `gemma_mask.sum()==0` 行(防止 adapter 收到全零 noise)。
- 训练/推理的 pooled_output 都是 **token-mean**(与训练 loss 对齐);Qwen3-4B 原生 cls-like pool 暂未实现,denoising 阶段会重做。

#### 关键诊断

首 batch 第一 epoch 打印:
```
[TrainGemmaToQwenAdapter]   adapter params: 124.0M  grad_enabled=True  inf_mode=False  req_grad=61 frozen=0
[TrainGemmaToQwenAdapter]   diag: pool.requires_grad=True grad_fn=True
[TrainGemmaToQwenAdapter]   diag: loss.requires_grad=True grad_fn=True
```

若 `inf_mode=True` 持续输出 → ComfyUI 版本升级后可能改了上下文,检查 `execution.py:751` 上下文并适配。

### 🔌 GemmaToQwenAdapterApply(菜单:`ZSimple-Nodes/adapter`)

推理节点。在 ComfyUI workflow 把 Gemma4 CLIPTextEncode 的 CONDITIONING 经训练好的 adapter 投射成 Z-Image 可消费的 Qwen-like 特征,直接喂 Z-Image UNet。

#### 关键旋钮

| 旋钮 | 默认 | 说明 |
|---|---|---|
| `conditioning` | (上游 Gemma4 CLIPTextEncode 输出) | 接受 `[B,N,1536]` bf16 张量;也容错 4D `[B,layer,N,H]` 与 2D `[N,H]`(自动 collapse) |
| `adapter_path` | `model-trainer/gemma_to_zimage_adapter.safetensors` | 训练节点输出路径 |

#### 输出

- `conditioning` CONDITIONING — `[proj_tokens[B,77,2560], proj_pooled[B,2560]]`,dtype 与输入一致;其他 key 透传(pooled_dict 中的 `clip_start_percent` / hooks 等)

#### 全局单例缓存

`load_adapter_singleton(path, dtype, device)` 线程安全(lock + dict)。cache key = `(resolve(path), dtype_str, device_str)`,避免:
- 同 path 不同 dtype 误用
- 同 path 不同 device 误用(cuda / cpu 切换会得到新 instance)

#### denoising WARNING

若 `.safetensors` metadata `denoising_done != "True"`(当前训练阶段都是 warmup),节点 print WARNING + 继续执行不阻断。例:

```
[GemmaToQwenAdapterApply] WARNING: phase=text-align-mse-warmup, denoising_done=False; outputs may be off — run denoising-loss stage before production use.
```

#### 端到端示例

加载 [`examples/gemma4_to_zimage_inference.json`](examples/gemma4_to_zimage_inference.json),把模型路径改成你本地 `gemma4_e2b_it_int8_convrot.safetensors` / `qwen_3_4b.safetensors` / `z_image_turbo_bf16.safetensors` / `z_image_vae.safetensors`,运行出图。

---

## ❓ FAQ

### 为什么 CFG 默认是 1.0？

LTX2.5-distilled 模型训练时**不使用** classifier-free guidance（CFG=1.0 不是 typo）。把上游 `CFGGuider` 的 cfg 设为 1.0；改成 1.5 或 2.0 会显著降低视频质量。

> 上游 `LTXVDualCFGGuider`（若使用）默认 video_cfg=3.0、audio_cfg=7.0；distilled workflow 把两者都覆盖为 1.0。dev / SFT 模型可参考 [HuggingFace Lightricks/LTX-2.5-Diffusers](https://huggingface.co/Lightricks/LTX-2.5-Diffusers) 的 `modality_scale` / `guidance_rescale`。

### 为什么我的视频全黑/全噪？

最常见原因：

1. **CFG 没有锁在 1.0** —— 上游 Guider 节点 cfg 改回 1.0
2. **sigma preset 被覆盖** —— schedule 输入必须是默认 `distilled_default`
3. **帧数不满足 (length-1) % 8 == 0** —— 实际合法值：9, 17, 25, 33, ..., 97, 121, 241, 361
4. **空 latent 尺寸不能被 32 整除** —— 例如 800×800 应改为 768×768 或 832×832

### 怎么注入参考图？

本节点不做图像注入——用上游 `LTXVAddGuide(frame_idx=N, strength=...)` 在 conditioning 和 latent 进入 `LTXVConcatAVLatent` 之前注入参考。patch 过的 conditioning 和 noise_mask 会自然流入 Guider。

### 为什么升频后 frame 48（或任一引导帧）参考丢失？

因为 `LTXVLatentUpscaler` 在空间 ×2 升频时会丢弃 noise_mask。要保留参考：在 upscaler 与 `ZLTXVideoTurboProgressive(stage="stage2")` 之间再跑一次 `LTXVAddGuide`，或确保 noise_mask 在模型 patch 中被保留。

### 音频怎么保存？

节点输出单个 `latent`（NestedTensor AV latent）。下游需用 `LTXVSeparateAVLatent` 拆分为 `video_latent` + `audio_latent`，然后：
- 视频 → `VAEDecodeTiled` → `CreateVideo`
- 音频 → `LTXVAudioVAEDecode` → `CreateVideo`（audio 槽）

### 能自定义 sigma 吗？

当前 schedule 锁 `distilled_default` 以保证 distilled 正确性。**自定义 sigma 输入暂未暴露**——如需自定义，可改用原生 `KSampler` + `comfy.sample.sample_custom` 自行连线。

### 361 帧能用吗？

能用，但属于"长视频"用法（>121 帧单段默认）。建议：

- 在上游用更低分辨率的 latent + 升频策略控制显存
- 或分段拼接：拆成 2 段 181 帧（约 7.5 秒），用相同 seed 续接

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