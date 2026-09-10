"""ZSimple Anthropic Agent 单元测试。

测试策略
--------
本插件的 `__init__.py` 一次性 import 全部节点类，其中部分节点依赖
ComfyUI runtime（comfy.* 等），独立测试环境（无 ComfyUI 安装）下
pytest 触发 ImportError。本文件采用 standalone runner 模式，自带
comfy_api stub，可直接执行：`python tests/test_z_simple_anthropic_agent.py`。
真实 ComfyUI runtime 下亦可作为 pytest 用例运行。
"""

from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock


_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


try:
    from comfy_api.latest import io as _io_real  # noqa: F401
    _HAVE_REAL_COMFY = True
except ImportError:
    _HAVE_REAL_COMFY = False

if not _HAVE_REAL_COMFY:
    import types

    _comfy_api = types.ModuleType("comfy_api")
    _latest = types.ModuleType("comfy_api.latest")

    class _StubSchema:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _StubNodeOutput:
        def __init__(self, *args, **kwargs):
            self._values = args
            self._kwargs = kwargs
            if len(args) == 1:
                self.output_text = args[0]
            for i, key in enumerate(("output_text", "model_used"), start=0):
                if i < len(args):
                    setattr(self, key, args[i])
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _InputBase:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _OutputBase:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs

    class _String:
        Input = _InputBase
        Output = _OutputBase

    class _Combo:
        Input = _InputBase
        Output = _OutputBase

    class _Int:
        Input = _InputBase
        Output = _OutputBase

    class _Float:
        Input = _InputBase
        Output = _OutputBase

    class _Hidden:
        prompt = _InputBase()
        extra_pnginfo = _InputBase()

    class _ComfyNode:
        pass

    class _IO:
        Schema = _StubSchema
        NodeOutput = _StubNodeOutput
        String = _String
        Combo = _Combo
        Int = _Int
        Float = _Float
        Hidden = _Hidden
        ComfyNode = _ComfyNode

    _io = _IO()
    _latest.io = _io
    _latest.ComfyNode = _ComfyNode
    _comfy_api.latest = _latest
    sys.modules["comfy_api"] = _comfy_api
    sys.modules["comfy_api.latest"] = _latest


_FAILED: list[str] = []


def _check(name: str, fn) -> None:
    """Run a test fn; record failures without raising."""
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001
        _FAILED.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")


def _fixture_system_prompt_dir():
    """Create a temp system_prompt dir; returns path. Cleans up via temp.TemporaryDirectory."""
    tmp = tempfile.TemporaryDirectory()
    with open(os.path.join(tmp.name, "foo.md"), "w", encoding="utf-8") as f:
        f.write("# Foo system prompt")
    with open(os.path.join(tmp.name, "bar.md"), "w", encoding="utf-8") as f:
        f.write("# Bar system prompt")
    return tmp


def _set_system_prompt_dir(path: str) -> None:
    """把 _agent_common 的 _SYSTEM_PROMPT_DIR 临时改成 path。"""
    from nodes import _agent_common
    _agent_common._SYSTEM_PROMPT_DIR = path


def test_scan_system_prompts_includes_none_and_files():
    from nodes import _agent_common
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    try:
        result = _agent_common._scan_system_prompts()
        assert result[0] == "none"
        assert set(result) >= {"none", "foo", "bar"}
    finally:
        tmp.cleanup()


def test_scan_system_prompts_creates_dir_if_missing():
    from nodes import _agent_common

    missing = tempfile.mkdtemp()
    target = os.path.join(missing, "does_not_exist")
    _set_system_prompt_dir(target)
    try:
        result = _agent_common._scan_system_prompts()
        assert result == ["none"]
        assert os.path.isdir(target)
    finally:
        import shutil
        shutil.rmtree(missing)


def test_resolve_system_reads_md_file():
    from nodes import _agent_common

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    try:
        result = _agent_common._resolve_system("foo", "ignored when file chosen")
        assert result == "# Foo system prompt"
    finally:
        tmp.cleanup()


def test_resolve_system_uses_enhancement_when_none():
    from nodes import _agent_common

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    try:
        result = _agent_common._resolve_system("none", "inline enhancement text")
        assert result == "inline enhancement text"
    finally:
        tmp.cleanup()


def test_resolve_system_returns_none_when_empty():
    from nodes import _agent_common

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    try:
        assert _agent_common._resolve_system("none", "") is None
        assert _agent_common._resolve_system("none", "   \n  ") is None
    finally:
        tmp.cleanup()


def _mock_client(response):
    client = mock.MagicMock()
    client.messages.create.return_value = response
    return client


def test_execute_with_md_system_passes_kwargs_to_sdk():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        content=[SimpleNamespace(text="expanded prompt here")],
        model="claude-sonnet-4-6",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            result = mod.ZSimpleAnthropicAgent.execute(
                text="hello",
                system_prompt="bar",
                prompt_enhancement_text="ignored",
                model="claude-sonnet-4-6",
                max_tokens=512,
                temperature=0.7,
            )
        client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-6",
            max_tokens=512,
            temperature=0.7,
            system="# Bar system prompt",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert result.output_text == "expanded prompt here"
        assert result.model_used == "claude-sonnet-4-6"
    finally:
        tmp.cleanup()


def test_execute_with_enhancement_text_when_none():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        content=[SimpleNamespace(text="x")], model="claude-sonnet-4-6"
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            mod.ZSimpleAnthropicAgent.execute(
                text="hi",
                system_prompt="none",
                prompt_enhancement_text="be brief",
                model="claude-sonnet-4-6",
                max_tokens=256,
                temperature=1.0,
            )
        _, kwargs = client.messages.create.call_args
        assert kwargs["system"] == "be brief"
    finally:
        tmp.cleanup()


def test_execute_omits_system_when_both_unset():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        content=[SimpleNamespace(text="x")], model="claude-sonnet-4-6"
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            mod.ZSimpleAnthropicAgent.execute(
                text="hi",
                system_prompt="none",
                prompt_enhancement_text="",
                model="claude-sonnet-4-6",
                max_tokens=256,
                temperature=1.0,
            )
        _, kwargs = client.messages.create.call_args
        assert "system" not in kwargs
    finally:
        tmp.cleanup()


def test_execute_raises_on_api_error():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    client = mock.MagicMock()
    client.messages.create.side_effect = RuntimeError("api down")
    try:
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleAnthropicAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="claude-sonnet-4-6",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "api down" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_get_client_raises_when_anthropic_missing():
    """模拟 anthropic 未安装时，_get_client 给出明确错误。"""
    import builtins
    from nodes import z_simple_anthropic_agent as mod

    mod._client = None
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        try:
            mod._get_client()
        except RuntimeError as exc:
            assert "pip install anthropic" in str(exc)
            return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        builtins.__import__ = real_import
        mod._client = None


def test_get_client_uses_env_vars():
    from nodes import z_simple_anthropic_agent as mod

    old_url = os.environ.get("ANTHROPIC_BASE_URL")
    old_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")

    mod._client = None
    os.environ["ANTHROPIC_BASE_URL"] = "http://example.test:9999"
    os.environ["ANTHROPIC_AUTH_TOKEN"] = "secret-token"

    fake_module = mock.MagicMock()
    fake_anthropic_cls = mock.MagicMock()
    fake_module.Anthropic = fake_anthropic_cls
    sys.modules["anthropic"] = fake_module

    try:
        mod._get_client()
        fake_anthropic_cls.assert_called_once_with(
            base_url="http://example.test:9999",
            auth_token="secret-token",
        )
    finally:
        if old_url is None:
            os.environ.pop("ANTHROPIC_BASE_URL", None)
        else:
            os.environ["ANTHROPIC_BASE_URL"] = old_url
        if old_token is None:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        else:
            os.environ["ANTHROPIC_AUTH_TOKEN"] = old_token
        sys.modules.pop("anthropic", None)
        mod._client = None


def test_execute_raises_when_content_empty():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(content=[], model="claude-sonnet-4-6")
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleAnthropicAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="claude-sonnet-4-6",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "content 为空" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_when_content_block_not_text():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"foo": "bar"})],
        model="claude-sonnet-4-6",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleAnthropicAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="claude-sonnet-4-6",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "类型不受支持" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_when_stop_reason_max_tokens():
    from nodes import z_simple_anthropic_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        content=[SimpleNamespace(text="truncated...")],
        model="claude-sonnet-4-6",
        stop_reason="max_tokens",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleAnthropicAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="claude-sonnet-4-6",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "截断" in str(exc) and "max_tokens" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def main() -> int:
    """Run all checks; return 0 on success, 1 on failure."""
    print("ZSimple Anthropic Agent — unit tests")
    print("-" * 50)
    _check("scan_system_prompts_includes_none_and_files",
           test_scan_system_prompts_includes_none_and_files)
    _check("scan_system_prompts_creates_dir_if_missing",
           test_scan_system_prompts_creates_dir_if_missing)
    _check("resolve_system_reads_md_file", test_resolve_system_reads_md_file)
    _check("resolve_system_uses_enhancement_when_none",
           test_resolve_system_uses_enhancement_when_none)
    _check("resolve_system_returns_none_when_empty",
           test_resolve_system_returns_none_when_empty)
    _check("execute_with_md_system_passes_kwargs_to_sdk",
           test_execute_with_md_system_passes_kwargs_to_sdk)
    _check("execute_with_enhancement_text_when_none",
           test_execute_with_enhancement_text_when_none)
    _check("execute_omits_system_when_both_unset",
           test_execute_omits_system_when_both_unset)
    _check("execute_raises_on_api_error",
           test_execute_raises_on_api_error)
    _check("get_client_raises_when_anthropic_missing",
           test_get_client_raises_when_anthropic_missing)
    _check("get_client_uses_env_vars", test_get_client_uses_env_vars)
    _check("execute_raises_when_content_empty",
           test_execute_raises_when_content_empty)
    _check("execute_raises_when_content_block_not_text",
           test_execute_raises_when_content_block_not_text)
    _check("execute_raises_when_stop_reason_max_tokens",
           test_execute_raises_when_stop_reason_max_tokens)
    print("-" * 50)
    if _FAILED:
        print(f"FAILED: {len(_FAILED)} test(s)")
        return 1
    print(f"PASSED: all 14 tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())