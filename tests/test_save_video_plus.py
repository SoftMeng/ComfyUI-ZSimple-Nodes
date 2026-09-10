"""SaveVideoPlus 单元测试。

standalone runner 模式：自带 comfy_api / folder_paths stub，
可直接执行 `python tests/test_save_video_plus.py`。
真实 ComfyUI runtime 下亦可作为 pytest 用例运行。
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

import numpy as np


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
            self.ui = kwargs.get("ui")
            names = ("images", "paths", "filename_first", "frame_count", "workflow_json")
            for i, key in enumerate(names):
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

    class _TypeT:
        Input = _InputBase
        Output = _OutputBase

    class _IO:
        Schema = _StubSchema
        NodeOutput = _StubNodeOutput
        String = _TypeT
        Combo = _TypeT
        Int = _TypeT
        Float = _TypeT
        Image = _TypeT
        Hidden = types.SimpleNamespace(prompt=_InputBase(), extra_pnginfo=_InputBase())
        ComfyNode = type("ComfyNode", (), {})

    _io = _IO()
    _latest.io = _io
    _latest.ComfyNode = type("ComfyNode", (), {})
    _comfy_api.latest = _latest
    sys.modules["comfy_api"] = _comfy_api
    sys.modules["comfy_api.latest"] = _latest

    _fp = types.ModuleType("folder_paths")
    _fp.get_output_directory = lambda: "/tmp"
    _fp.get_input_directory = lambda: "/tmp"
    _fp.get_temp_directory = lambda: "/tmp"
    sys.modules["folder_paths"] = _fp


_FAILED: list[str] = []


def _check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001
        _FAILED.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")


def _fake_frames(n, h=8, w=8):
    return [np.full((h, w, 3), i * 10 % 255, dtype=np.uint8) for i in range(n)]


class _FakeTensor:
    def __init__(self, array):
        self._array = array

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class _FakeImages:
    def __init__(self, frames):
        self._tensors = [_FakeTensor(f) for f in frames]

    def __len__(self):
        return len(self._tensors)

    def __getitem__(self, i):
        return self._tensors[i]


# ---------------------------------------------------------------------------
# 纯函数层
# ---------------------------------------------------------------------------

def test_crf_h264_mapping():
    from nodes.save_video_plus import _crf_h264

    assert _crf_h264(100) == 19
    assert _crf_h264(50) == 35
    assert _crf_h264(0) == 51
    assert 0 <= _crf_h264(1) <= 51
    assert 0 <= _crf_h264(100) <= 51


def test_crf_vp9_mapping():
    from nodes.save_video_plus import _crf_vp9

    assert _crf_vp9(100) == 19
    assert 0 <= _crf_vp9(90) <= 63
    assert _crf_vp9(0) == 63
    assert 0 <= _crf_vp9(1) <= 63


def test_pingpong_expansion():
    from nodes.save_video_plus import _pingpong_frames

    frames = _fake_frames(5)
    out = _pingpong_frames(frames)
    assert len(out) == 8
    assert out[0] is frames[0]
    assert out[-1] is frames[1]

    single = _pingpong_frames(_fake_frames(1))
    assert len(single) == 1

    three = _pingpong_frames(_fake_frames(3))
    assert len(three) == 4


def test_resume_counter_continuation():
    from nodes._save_common import resume_counter

    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "ZSimple_00002.mp4"), "w").close()
        assert resume_counter(tmp, "ZSimple", "mp4") == 3
        assert resume_counter(tmp, "ZSimple", "webm") == 1


def test_filename_generation():
    pad = 5
    name = f"{'ZSimple'}_{3:0{pad}d}.{'mp4'}"
    assert name == "ZSimple_00003.mp4"


def test_metadata_params_modes():
    from nodes.save_video_plus import _build_mp4_metadata_params

    prompt = {"node1": {"class_type": "X"}}
    extra = {"workflow": {"nodes": []}}

    assert _build_mp4_metadata_params("none", prompt, extra) == []

    p_only = _build_mp4_metadata_params("prompt_only", prompt, extra)
    assert any("prompt" in p for p in p_only)
    assert not any("workflow" in p for p in p_only)

    p_all = _build_mp4_metadata_params("all", prompt, extra)
    assert any("prompt" in p for p in p_all)
    assert any("workflow" in p for p in p_all)


def test_metadata_workflow_truncation():
    from nodes.save_video_plus import _build_mp4_metadata_params

    prompt = {"k": "v"}
    big_workflow = {"data": "x" * 70000}
    extra = {"workflow": big_workflow}
    params = _build_mp4_metadata_params("all", prompt, extra)
    assert any("prompt" in p for p in params)
    assert not any("workflow" in p for p in params)


def test_get_ffmpeg_writer_raises_when_missing():
    import builtins
    from nodes import save_video_plus as mod

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "imageio_ffmpeg":
            raise ImportError("No module named 'imageio_ffmpeg'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        try:
            mod._get_ffmpeg_writer("/tmp/x.mp4", (8, 8), 24, "libx264", 19)
        except RuntimeError as exc:
            assert "pip install imageio-ffmpeg" in str(exc)
            return
        raise AssertionError("expected RuntimeError not raised")
    finally:
        builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# encoder dispatch 层
# ---------------------------------------------------------------------------

def test_execute_dispatches_to_mp4_encoder():
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(mod.folder_paths, "get_output_directory", return_value=tmp), \
             mock.patch.object(mod, "_encode_mp4") as enc:
            mod.SaveVideoPlus.execute(
                images=_FakeImages(_fake_frames(3)),
                format="mp4",
                frame_rate=24.0,
                filename_prefix="ZSimple",
                subfolder_template="",
                filename_number_padding=5,
                quality=90,
                loop_count=0,
                pingpong="off",
                embed_metadata="none",
            )
        enc.assert_called_once()
        frames_arg = enc.call_args[0][0]
        assert len(frames_arg) == 3


def test_execute_dispatches_to_webm_encoder():
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(mod.folder_paths, "get_output_directory", return_value=tmp), \
             mock.patch.object(mod, "_encode_webm") as enc:
            mod.SaveVideoPlus.execute(
                images=_FakeImages(_fake_frames(2)),
                format="webm",
                frame_rate=24.0,
                filename_prefix="ZSimple",
                subfolder_template="",
                filename_number_padding=5,
                quality=90,
                loop_count=0,
                pingpong="off",
                embed_metadata="none",
            )
        enc.assert_called_once()


def test_execute_dispatches_to_gif_encoder():
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(mod.folder_paths, "get_output_directory", return_value=tmp), \
             mock.patch.object(mod, "_encode_gif") as enc:
            mod.SaveVideoPlus.execute(
                images=_FakeImages(_fake_frames(2)),
                format="gif",
                frame_rate=12.0,
                filename_prefix="ZSimple",
                subfolder_template="",
                filename_number_padding=5,
                quality=90,
                loop_count=0,
                pingpong="off",
                embed_metadata="none",
            )
        enc.assert_called_once()


# ---------------------------------------------------------------------------
# execute 集成层
# ---------------------------------------------------------------------------

def test_execute_raises_on_empty_images():
    from nodes import save_video_plus as mod

    try:
        mod.SaveVideoPlus.execute(
            images=_FakeImages([]),
            format="mp4",
            frame_rate=24.0,
            filename_prefix="ZSimple",
            subfolder_template="",
            filename_number_padding=5,
            quality=90,
            loop_count=0,
            pingpong="off",
            embed_metadata="none",
        )
    except RuntimeError as exc:
        assert "images 为空" in str(exc)
        return
    raise AssertionError("expected RuntimeError not raised")


def test_execute_returns_five_outputs_and_ui():
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(mod.folder_paths, "get_output_directory", return_value=tmp), \
             mock.patch.object(mod, "_encode_mp4") as enc:
            result = mod.SaveVideoPlus.execute(
                images=_FakeImages(_fake_frames(4)),
                format="mp4",
                frame_rate=24.0,
                filename_prefix="ZSimple",
                subfolder_template="",
                filename_number_padding=5,
                quality=90,
                loop_count=0,
                pingpong="off",
                embed_metadata="none",
                prompt={"k": "v"},
                extra_pnginfo={"workflow": {"nodes": []}},
            )
        assert result.filename_first == "ZSimple_00001.mp4"
        assert result.paths == "ZSimple_00001.mp4"
        assert result.frame_count == 4
        assert result.workflow_json != ""
        assert result.ui["gifs"][0]["filename"] == "ZSimple_00001.mp4"
        assert result.ui["gifs"][0]["type"] == "output"
        assert result.ui["gifs"][0]["frame_rate"] == 24.0


def test_execute_pingpong_expands_frames():
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(mod.folder_paths, "get_output_directory", return_value=tmp), \
             mock.patch.object(mod, "_encode_mp4") as enc:
            mod.SaveVideoPlus.execute(
                images=_FakeImages(_fake_frames(5)),
                format="mp4",
                frame_rate=24.0,
                filename_prefix="ZSimple",
                subfolder_template="",
                filename_number_padding=5,
                quality=90,
                loop_count=0,
                pingpong="on",
                embed_metadata="none",
            )
        frames_arg = enc.call_args[0][0]
        assert len(frames_arg) == 8


def test_execute_gif_real_encoding_smoke():
    """真实 PIL 编码小 gif，验证 _encode_gif 可用（不走 ffmpeg）。"""
    from nodes import save_video_plus as mod

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "smoke.gif")
        mod._encode_gif(_fake_frames(3, h=16, w=16), path, 12.0, 0)
        assert os.path.getsize(path) > 0


# ---------------------------------------------------------------------------
# 修复新增测试（审查 I-1 / I-2 / S-1）
# ---------------------------------------------------------------------------

def test_encode_mp4_closes_writer_on_send_error():
    from nodes import save_video_plus as mod

    call_count = {"n": 0}

    def _failing_send(_):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("模拟 ffmpeg 写帧失败")
        return None

    writer = mock.MagicMock()
    writer.send.side_effect = _failing_send

    with mock.patch.object(mod, "_get_ffmpeg_writer", return_value=writer):
        try:
            mod._encode_mp4(_fake_frames(3), "/tmp/x.mp4", 24.0, 90)
        except RuntimeError as exc:
            assert "模拟 ffmpeg 写帧失败" in str(exc)
            writer.close.assert_called_once()
            return
    raise AssertionError("expected RuntimeError not raised")


def test_input_pix_fmt_dispatch():
    from nodes.save_video_plus import _input_pix_fmt

    rgb_frames = _fake_frames(2, h=8, w=8)
    assert _input_pix_fmt(rgb_frames) == "rgb24"

    rgba_frames = [np.zeros((4, 4, 4), dtype=np.uint8) for _ in range(2)]
    assert _input_pix_fmt(rgba_frames) == "rgba"

    gray_frames = [np.zeros((4, 4), dtype=np.uint8) for _ in range(2)]
    assert _input_pix_fmt(gray_frames) == "gray"


def test_get_ffmpeg_writer_codec_specific_args():
    from nodes import save_video_plus as mod

    fake_module = mock.MagicMock()
    fake_write_frames = mock.MagicMock()
    fake_module.write_frames = fake_write_frames
    sys.modules["imageio_ffmpeg"] = fake_module
    try:
        mod._get_ffmpeg_writer("/tmp/v.mp4", (8, 8), 24, "libvpx-vp9", 30)
        _, kw = fake_write_frames.call_args
        assert kw["output_params"] == ["-crf", "30", "-b:v", "0"]

        fake_write_frames.reset_mock()
        mod._get_ffmpeg_writer("/tmp/x.mp4", (8, 8), 24, "libx264", 19)
        _, kw = fake_write_frames.call_args
        assert kw["output_params"] == ["-crf", "19"]
    finally:
        sys.modules.pop("imageio_ffmpeg", None)


def main() -> int:
    print("SaveVideoPlus — unit tests")
    print("-" * 50)
    _check("crf_h264_mapping", test_crf_h264_mapping)
    _check("crf_vp9_mapping", test_crf_vp9_mapping)
    _check("pingpong_expansion", test_pingpong_expansion)
    _check("resume_counter_continuation", test_resume_counter_continuation)
    _check("filename_generation", test_filename_generation)
    _check("metadata_params_modes", test_metadata_params_modes)
    _check("metadata_workflow_truncation", test_metadata_workflow_truncation)
    _check("get_ffmpeg_writer_raises_when_missing", test_get_ffmpeg_writer_raises_when_missing)
    _check("execute_dispatches_to_mp4_encoder", test_execute_dispatches_to_mp4_encoder)
    _check("execute_dispatches_to_webm_encoder", test_execute_dispatches_to_webm_encoder)
    _check("execute_dispatches_to_gif_encoder", test_execute_dispatches_to_gif_encoder)
    _check("execute_raises_on_empty_images", test_execute_raises_on_empty_images)
    _check("execute_returns_five_outputs_and_ui", test_execute_returns_five_outputs_and_ui)
    _check("execute_pingpong_expands_frames", test_execute_pingpong_expands_frames)
    _check("execute_gif_real_encoding_smoke", test_execute_gif_real_encoding_smoke)
    _check("encode_mp4_closes_writer_on_send_error", test_encode_mp4_closes_writer_on_send_error)
    _check("input_pix_fmt_dispatch", test_input_pix_fmt_dispatch)
    _check("get_ffmpeg_writer_codec_specific_args", test_get_ffmpeg_writer_codec_specific_args)
    print("-" * 50)
    if _FAILED:
        print(f"FAILED: {len(_FAILED)} test(s)")
        return 1
    print("PASSED: all 18 tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())