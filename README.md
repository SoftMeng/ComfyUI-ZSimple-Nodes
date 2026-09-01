<div align="center">

# ⚡ ComfyUI-ZSimple-Nodes

### 简洁、实用的 ComfyUI 自定义节点合集

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-V3%20Schema-blue?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge)](https://www.python.org/)
[![Nodes](https://img.shields.io/badge/Nodes-2-orange?style=for-the-badge)](#-节点列表)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](../../pulls)

**为 ComfyUI 工作流添砖加瓦 · 单文件单节点 · 现代压缩与质量参数**

</div>

---

## ✨ 为什么用它？

ComfyUI 自带的 `SaveImage` 节点已足够基础，但当你需要更精细的控制时——比如**JPEG q 值、PNG 压缩级别、WebP 无损模式、metadata 嵌入策略**——你会发现原生节点要么不支持，要么写死。

`ComfyUI-ZSimple-Nodes` 是一个**渐进生长**的个人插件，每个节点都解决一个具体痛点，单文件单职责。**当前已上线的两个节点都经过 2026 图像压缩最佳实践审查**。

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

**用途**：随机种子生成器，输出当前 seed 的多种格式 + 下一值。

| 特性 | 说明 |
|---|---|
| 多格式输出 | INT / FLOAT / STRING / NUMBER（复合类型） |
| 当前 + 下一值 | 同时输出 `seed` 和 `seed + 1` |
| 生成后控制 | `randomize` / `increment` / `decrement` / `fixed` —— 由 ComfyUI 前端 widget 处理 |
| 零依赖 | 仅依赖 ComfyUI V3 API |

**典型用法**：从 `seed_out` 拉取字符串种子注入 `CLIPTextEncode`，从 `next_int` 注入下一节点的 KSampler。

---

### 🖼️ SaveImagePlus（菜单：ZSimple-Nodes/image）

**用途**：替代原生 SaveImage，支持多格式 + 精细压缩控制 + 智能 metadata 保护。

| 能力 | 原生 SaveImage | SaveImagePlus |
|---|---|---|
| PNG / JPEG / WebP / **JXL** 输出 | 仅 PNG | ✅ |
| 用户控制质量 | ❌（固定 `compress_level=4`） | ✅（按格式分别控制） |
| WebP 无损模式 | ❌ | ✅（`webp_lossless=on`） |
| JPEG chroma 控制 | ❌ | ✅（`4:4:4` / `4:2:0`） |
| Metadata 细粒度策略 | 全局开关 | ✅（`none` / `prompt_only` / `all`） |
| **JPEG EXIF 64KB 保护** | 静默截断 | ✅（自动降级） |
| 返回保存路径 | ❌ | ✅（STRING 输出，可链式） |
| 双语法文件名模板 | 仅 `%date%` | ✅（同时支持 `%date%` 与 `{var}`） |

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

> [!NOTE]
> **JPEG XL** (`jxl`) 需要可选依赖 `pillow-jxl-plugin`：
> ```bash
> pip install pillow-jxl-plugin
> ```
> 安装后在 `requirements.txt` 中取消对应行的注释。JXL 提供**比 PNG 小很多的数学无损压缩**，非常适合 AI 绘画存档。

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

| 类型 | 包名 | 必需 | 说明 |
|---|---|---|---|
| 必需 | `comfy_api` | ✅ | V3 节点接口 |
| 必需 | `Pillow` | ✅ | 图像处理 |
| 必需 | `numpy` | ✅ | 张量转换 |
| 可选 | `pillow-jxl-plugin` | ❌ | 启用 `format="jxl"` |

完整声明见 [`requirements.txt`](requirements.txt)。

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
- 所有提供建议、反馈、Issue 的用户

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star 支持开发！**

</div>