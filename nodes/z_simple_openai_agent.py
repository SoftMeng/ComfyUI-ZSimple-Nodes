"""ZSimple OpenAI Agent — 通过 OpenAI 兼容 Chat Completions API 扩展用户提示词。"""

from __future__ import annotations

import os
from typing import Optional

from comfy_api.latest import io

from nodes._agent_common import (
    _SYSTEM_PROMPT_DIR,
    _resolve_system,
    _scan_system_prompts,
)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_MODEL_OPTIONS = [
    "qwen3.5-flash",
    "qwen-plus",
    "qwen-max",
    "qwen-turbo",
]

_client: Optional["object"] = None
_client_key: Optional[tuple[str, str]] = None


def _get_client(api_key: str, base_url: str):
    """懒加载 OpenAI SDK 客户端；按 (api_key, base_url) 缓存，model 不影响 client 身份。"""
    global _client, _client_key
    key = (api_key, base_url)
    if _client is None or _client_key != key:
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for ZSimple OpenAI Agent. "
                "Install with: pip install openai>=1.0.0"
            ) from exc
        _client = openai.OpenAI(api_key=api_key, base_url=base_url)
        _client_key = key
    return _client


def _extract_openai_text(response) -> str:
    """从 OpenAI ChatCompletion 响应提取文本；遇空 choices/None content raise。"""
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("OpenAI 响应 choices 为空")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message else None
    if content is None:
        finish_reason = getattr(choices[0], "finish_reason", "?")
        raise RuntimeError(
            f"OpenAI 响应 content 为 None（finish_reason={finish_reason}）"
        )
    return content


class ZSimpleOpenAIAgent(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ZSimpleOpenAIAgent",
            display_name="ZSimple OpenAI Agent",
            category="ZSimple-Nodes/agent",
            search_aliases=[
                "openai", "qwen", "dashscope", "llm",
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
                    default="qwen3.5-flash",
                    tooltip="OpenAI 兼容模型名；默认 qwen3.5-flash（阿里云 DashScope）。",
                ),
                io.String.Input(
                    "api_key",
                    default="",
                    tooltip="API key；空字符串时节点会拒绝执行。⚠ 会随 workflow 文件一起保存，请勿分享含 api_key 的 workflow。",
                ),
                io.String.Input(
                    "base_url",
                    default=_DEFAULT_BASE_URL,
                    tooltip="OpenAI 兼容 base url；默认指向阿里云 DashScope。",
                ),
                io.Float.Input(
                    "temperature",
                    default=0.7,
                    min=0.0,
                    max=2.0,
                    step=0.05,
                    tooltip="采样温度；0=确定性，1=默认，2=最大多样性。",
                ),
                io.Int.Input(
                    "max_tokens",
                    default=4096,
                    min=1,
                    max=8192,
                    tooltip="最大生成 token 数。",
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
        api_key: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
    ) -> io.NodeOutput:
        if not api_key or not api_key.strip():
            raise RuntimeError(
                "api_key 为空，请在节点上填写 OpenAI / DashScope 的 API key"
            )

        client = _get_client(api_key, base_url)
        system_content = _resolve_system(system_prompt, prompt_enhancement_text)

        messages: list[dict[str, str]] = []
        if system_content is not None:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": text})

        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        text = _extract_openai_text(response)
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            raise RuntimeError(
                "OpenAI 响应被 max_tokens 截断（建议调大 max_tokens 参数）"
            )
        if finish_reason == "content_filter":
            raise RuntimeError(
                "OpenAI 响应被内容审核过滤（finish_reason=content_filter）"
            )
        actual_model = getattr(response, "model", model)
        return io.NodeOutput(output_text=text, model_used=actual_model)