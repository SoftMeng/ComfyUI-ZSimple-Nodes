"""ZSimple OpenAI Agent 单元测试。

测试策略
--------
本插件的 `__init__.py` 一次性 import 全部节点类，其中部分节点依赖
ComfyUI runtime（comfy.* 等），独立测试环境（无 ComfyUI 安装）下
pytest 触发 ImportError。本文件采用 standalone runner 模式，自带
comfy_api stub，可直接执行：`python tests/test_z_simple_openai_agent.py`。
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
    tmp = tempfile.TemporaryDirectory()
    with open(os.path.join(tmp.name, "foo.md"), "w", encoding="utf-8") as f:
        f.write("# Foo system prompt")
    with open(os.path.join(tmp.name, "bar.md"), "w", encoding="utf-8") as f:
        f.write("# Bar system prompt")
    return tmp


def _mock_client(response):
    client = mock.MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _set_system_prompt_dir(path: str) -> None:
    """把 _agent_common 的 _SYSTEM_PROMPT_DIR 临时改成 path。"""
    from nodes import _agent_common
    _agent_common._SYSTEM_PROMPT_DIR = path


def test_scan_system_prompts_includes_none_and_files():
    from nodes import _agent_common

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


def test_get_client_caches_by_api_key_and_base_url():
    """按 (api_key, base_url) 缓存 client；key 变化则重建。"""
    from nodes import z_simple_openai_agent as mod

    instances = iter([mock.MagicMock(name=f"client-{i}") for i in range(8)])
    fake_openai_cls = mock.MagicMock(side_effect=lambda **_: next(instances))
    fake_module = mock.MagicMock()
    fake_module.OpenAI = fake_openai_cls
    sys.modules["openai"] = fake_module

    try:
        mod._client = None
        mod._client_key = None
        client1 = mod._get_client("key-a", "https://a.test/v1")
        client2 = mod._get_client("key-a", "https://a.test/v1")
        client3 = mod._get_client("key-b", "https://a.test/v1")
        client4 = mod._get_client("key-a", "https://b.test/v1")

        assert client1 is client2, "相同 key 应复用 client"
        assert client1 is not client3, "api_key 不同应重建"
        assert client1 is not client4, "base_url 不同应重建"
        assert client3 is not client4, "两组不同 key 各自独立"
        assert fake_openai_cls.call_count == 3, "应只创建 3 次 OpenAI()"
    finally:
        sys.modules.pop("openai", None)
        mod._client = None
        mod._client_key = None


def test_execute_with_md_system_passes_messages_to_sdk():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="expanded prompt here"))],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            result = mod.ZSimpleOpenAIAgent.execute(
                text="hello",
                system_prompt="bar",
                prompt_enhancement_text="ignored",
                model="qwen3.5-flash",
                api_key="sk-test",
                base_url="https://example.test/v1",
                max_tokens=512,
                temperature=0.7,
            )
        client.chat.completions.create.assert_called_once_with(
            model="qwen3.5-flash",
            max_tokens=512,
            temperature=0.7,
            messages=[
                {"role": "system", "content": "# Bar system prompt"},
                {"role": "user", "content": "hello"},
            ],
        )
        assert result.output_text == "expanded prompt here"
        assert result.model_used == "qwen3.5-flash"
    finally:
        tmp.cleanup()


def test_execute_with_enhancement_text_when_none():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            mod.ZSimpleOpenAIAgent.execute(
                text="hi",
                system_prompt="none",
                prompt_enhancement_text="be brief",
                model="qwen3.5-flash",
                api_key="sk-test",
                base_url="https://example.test/v1",
                max_tokens=256,
                temperature=1.0,
            )
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["messages"] == [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
    finally:
        tmp.cleanup()


def test_execute_omits_system_when_both_unset():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            mod.ZSimpleOpenAIAgent.execute(
                text="hi",
                system_prompt="none",
                prompt_enhancement_text="",
                model="qwen3.5-flash",
                api_key="sk-test",
                base_url="https://example.test/v1",
                max_tokens=256,
                temperature=1.0,
            )
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    finally:
        tmp.cleanup()


def test_execute_raises_when_api_key_empty():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    try:
        try:
            mod.ZSimpleOpenAIAgent.execute(
                text="hi",
                system_prompt="none",
                prompt_enhancement_text="",
                model="qwen3.5-flash",
                api_key="",
                base_url="https://example.test/v1",
                max_tokens=256,
                temperature=1.0,
            )
        except RuntimeError as exc:
            assert "api_key 为空" in str(exc)
            return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_on_api_error():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    client = mock.MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("api down")
    try:
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleOpenAIAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="qwen3.5-flash",
                    api_key="sk-test",
                    base_url="https://example.test/v1",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "api down" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_get_client_raises_when_openai_missing():
    """模拟 openai 未安装时，_get_client 给出明确错误。"""
    import builtins
    from nodes import z_simple_openai_agent as mod

    mod._client = None
    mod._client_key = None
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        try:
            mod._get_client("sk-test", "https://example.test/v1")
        except RuntimeError as exc:
            assert "pip install openai" in str(exc)
            return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        builtins.__import__ = real_import
        mod._client = None
        mod._client_key = None


def test_execute_raises_when_choices_empty():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(choices=[], model="qwen3.5-flash")
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleOpenAIAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="qwen3.5-flash",
                    api_key="sk-test",
                    base_url="https://example.test/v1",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "choices 为空" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_when_content_none():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=None),
            finish_reason="length",
        )],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleOpenAIAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="qwen3.5-flash",
                    api_key="sk-test",
                    base_url="https://example.test/v1",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "content 为 None" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_when_finish_reason_length():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="truncated..."),
            finish_reason="length",
        )],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleOpenAIAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="qwen3.5-flash",
                    api_key="sk-test",
                    base_url="https://example.test/v1",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "截断" in str(exc) and "max_tokens" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def test_execute_raises_when_finish_reason_content_filter():
    from nodes import z_simple_openai_agent as mod

    tmp = _fixture_system_prompt_dir()
    _set_system_prompt_dir(tmp.name)
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=""),
            finish_reason="content_filter",
        )],
        model="qwen3.5-flash",
    )
    try:
        client = _mock_client(response)
        with mock.patch.object(mod, "_get_client", return_value=client):
            try:
                mod.ZSimpleOpenAIAgent.execute(
                    text="hi",
                    system_prompt="none",
                    prompt_enhancement_text="",
                    model="qwen3.5-flash",
                    api_key="sk-test",
                    base_url="https://example.test/v1",
                    max_tokens=256,
                    temperature=1.0,
                )
            except RuntimeError as exc:
                assert "content_filter" in str(exc) or "审核" in str(exc)
                return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        tmp.cleanup()


def main() -> int:
    """Run all checks; return 0 on success, 1 on failure."""
    print("ZSimple OpenAI Agent — unit tests")
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
    _check("get_client_caches_by_api_key_and_base_url",
           test_get_client_caches_by_api_key_and_base_url)
    _check("execute_with_md_system_passes_messages_to_sdk",
           test_execute_with_md_system_passes_messages_to_sdk)
    _check("execute_with_enhancement_text_when_none",
           test_execute_with_enhancement_text_when_none)
    _check("execute_omits_system_when_both_unset",
           test_execute_omits_system_when_both_unset)
    _check("execute_raises_when_api_key_empty",
           test_execute_raises_when_api_key_empty)
    _check("execute_raises_on_api_error",
           test_execute_raises_on_api_error)
    _check("get_client_raises_when_openai_missing",
           test_get_client_raises_when_openai_missing)
    _check("execute_raises_when_choices_empty",
           test_execute_raises_when_choices_empty)
    _check("execute_raises_when_content_none",
           test_execute_raises_when_content_none)
    _check("execute_raises_when_finish_reason_length",
           test_execute_raises_when_finish_reason_length)
    _check("execute_raises_when_finish_reason_content_filter",
           test_execute_raises_when_finish_reason_content_filter)
    print("-" * 50)
    if _FAILED:
        print(f"FAILED: {len(_FAILED)} test(s)")
        return 1
    print(f"PASSED: all 16 tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())