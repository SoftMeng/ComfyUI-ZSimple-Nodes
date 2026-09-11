"""ZSimple Anthropic Agent — 调用 Claude Messages API 扩展用户提示词。"""

from __future__ import annotations

import os
from typing import Optional

from comfy_api.latest import io

from ._agent_common import (
    _SYSTEM_PROMPT_DIR,
    _resolve_system,
    _scan_system_prompts,
)

_DEFAULT_BASE_URL = "http://127.0.0.1:5000"
_DEFAULT_AUTH_TOKEN = "PROXY_MANAGED"

_MODEL_OPTIONS = [
    "claude-sonnet-4-6",
    "claude-3-5-sonnet-latest",
    "claude-opus-4-6",
]

_client: Optional["object"] = None


def _get_client():
    """懒加载 Anthropic SDK 客户端，从环境变量读取 base_url/auth_token。"""
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is required for ZSimple Anthropic Agent. "
                "Install with: pip install anthropic>=0.40.0"
            ) from exc
        base_url = os.environ.get("ANTHROPIC_BASE_URL", _DEFAULT_BASE_URL)
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", _DEFAULT_AUTH_TOKEN)
        _client = anthropic.Anthropic(base_url=base_url, auth_token=auth_token)
    return _client


def _extract_anthropic_text(msg) -> str:
    """从 Anthropic Message 响应提取文本；遇空/非 TextBlock raise。"""
    content = getattr(msg, "content", None)
    if not content:
        raise RuntimeError("Anthropic 响应 content 为空")
    block = content[0]
    text = getattr(block, "text", None)
    if not isinstance(text, str):
        raise RuntimeError(
            f"Anthropic 响应 content block 类型不受支持（type={getattr(block, 'type', '?')}）；本节点只取文本 block"
        )
    return text


class ZSimpleAnthropicAgent(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ZSimpleAnthropicAgent",
            display_name="ZSimple Anthropic Agent",
            category="ZSimple-Nodes/agent",
            search_aliases=[
                "anthropic", "claude", "llm",
                "prompt enhancer", "prompt expander",
            ],
            inputs=[
                io.String.Input(
                    "text",
                    force_input=True,
                    multiline=True,
                    tooltip="用户输入文本（user message content）。",
                ),
                io.Combo.Input(
                    "system_prompt",
                    options=_scan_system_prompts(),
                    default="none",
                    tooltip="下拉选择 system_prompt/ 下的 markdown 文件名；选 none 时使用 prompt_enhancement_text。",
                ),
                io.String.Input(
                    "prompt_enhancement_text",
                    multiline=True,
                    default="",
                    tooltip="仅当 system_prompt=none 时生效：作为 system 字段发送给 API。",
                ),
                io.Combo.Input(
                    "model",
                    options=_MODEL_OPTIONS,
                    default="claude-sonnet-4-6",
                    tooltip="Anthropic 模型名。",
                ),
                io.Int.Input(
                    "max_tokens",
                    default=1024,
                    min=1,
                    max=8192,
                    tooltip="最大生成 token 数。",
                ),
                io.Float.Input(
                    "temperature",
                    default=1.0,
                    min=0.0,
                    max=2.0,
                    step=0.05,
                    tooltip="采样温度；0=确定性，1=默认，2=最大多样性。",
                ),
            ],
            outputs=[
                io.String.Output(
                    "output_text",
                    tooltip="模型返回的文本内容。",
                ),
                io.String.Output(
                    "model_used",
                    tooltip="实际调用模型名（SDK 响应中读取）。",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        text: str,
        system_prompt: str,
        prompt_enhancement_text: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> io.NodeOutput:
        client = _get_client()
        system_content = _resolve_system(system_prompt, prompt_enhancement_text)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": text}],
        }
        if system_content is not None:
            kwargs["system"] = system_content

        msg = client.messages.create(**kwargs)
        text = _extract_anthropic_text(msg)
        stop_reason = getattr(msg, "stop_reason", None)
        if stop_reason == "max_tokens":
            raise RuntimeError(
                f"Anthropic 响应被 max_tokens 截断（建议调大 max_tokens 参数）；当前 stop_reason={stop_reason}"
            )
        actual_model = getattr(msg, "model", model)
        return io.NodeOutput(output_text=text, model_used=actual_model)
