"""Agent 节点共享辅助：system_prompt/ 目录扫描 + 三分支 system 解析。"""

from __future__ import annotations

import os
from typing import Optional

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SYSTEM_PROMPT_DIR = os.path.join(_PLUGIN_ROOT, "system_prompt")


def _scan_system_prompts() -> list[str]:
    """扫描 system_prompt/ 目录，返回 ["none", ...文件名(无扩展名)]。"""
    os.makedirs(_SYSTEM_PROMPT_DIR, exist_ok=True)
    names = sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(_SYSTEM_PROMPT_DIR)
        if name.endswith(".md")
    )
    return ["none", *names]


def _resolve_system(choice: str, enhancement_text: str) -> Optional[str]:
    """根据下拉选择 + 增强文本，返回最终 system 字段（None 表示省略）。"""
    if choice != "none":
        path = os.path.join(_SYSTEM_PROMPT_DIR, f"{choice}.md")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    if enhancement_text and enhancement_text.strip():
        return enhancement_text
    return None