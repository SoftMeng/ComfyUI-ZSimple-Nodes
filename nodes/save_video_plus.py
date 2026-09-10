"""Save Video Plus — encode IMAGE frames to mp4 / webm / gif."""

import json
import os

import numpy as np
from PIL import Image

from comfy_api.latest import io

import folder_paths

from ._save_common import resolve_subfolder, resume_counter, workflow_json_from_extra

try:
    from comfy.utils import ProgressBar as _ProgressBar
except ImportError:
    _ProgressBar = None

_WORKFLOW_SAFETY_BYTES = 60000


def _crf_h264(quality: int) -> int:
    return max(0, min(51, 51 - round(quality * 0.32)))


def _crf_vp9(quality: int) -> int:
    return max(0, min(63, 63 - round(quality * 0.44)))


def _pingpong_frames(frames: list) -> list:
    if len(frames) < 3:
        return frames
    return frames + frames[-2:0:-1]


def _build_mp4_metadata_params(embed_mode: str, prompt, extra_pnginfo) -> list[str]:
    if embed_mode == "none" or prompt is None:
        return []
    params = ["-movflags", "use_metadata_tags"]
    params += ["-metadata", f"prompt={json.dumps(prompt, ensure_ascii=False)}"]
    if embed_mode == "all" and extra_pnginfo is not None:
        workflow_json = workflow_json_from_extra(extra_pnginfo)
        if workflow_json and len(workflow_json.encode("utf-8")) <= _WORKFLOW_SAFETY_BYTES:
            params += ["-metadata", f"workflow={workflow_json}"]
    return params


def _input_pix_fmt(frames) -> str:
    arr = frames[0]
    channels = arr.shape[2] if arr.ndim == 3 else 1
    if channels == 4:
        return "rgba"
    if channels == 1:
        return "gray"
    return "rgb24"


def _get_ffmpeg_writer(path, size, fps, codec, crf, pix_fmt="rgb24", extra_output_params=None):
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "imageio-ffmpeg package is required for mp4/webm encoding. "
            "Install with: pip install imageio-ffmpeg>=0.5.0"
        ) from exc
    output_params = ["-crf", str(crf), "-b:v", "0"] if codec == "libvpx-vp9" else ["-crf", str(crf)]
    if extra_output_params:
        output_params += extra_output_params
    return imageio_ffmpeg.write_frames(
        path,
        size=size,
        fps=fps,
        codec=codec,
        pix_fmt_in=pix_fmt,
        macro_block_size=1,
        output_params=output_params,
    )


def _encode_mp4(frames, path, fps, quality, metadata_params=None):
    h, w = frames[0].shape[0], frames[0].shape[1]
    writer = _get_ffmpeg_writer(
        path, (w, h), fps, "libx264", _crf_h264(quality),
        pix_fmt=_input_pix_fmt(frames),
        extra_output_params=metadata_params,
    )
    try:
        writer.send(None)
        pbar = _ProgressBar(len(frames)) if _ProgressBar else None
        for frame in frames:
            writer.send(frame.tobytes())
            if pbar:
                pbar.update(1)
    finally:
        writer.close()


def _encode_webm(frames, path, fps, quality):
    h, w = frames[0].shape[0], frames[0].shape[1]
    writer = _get_ffmpeg_writer(
        path, (w, h), fps, "libvpx-vp9", _crf_vp9(quality),
        pix_fmt=_input_pix_fmt(frames),
    )
    try:
        writer.send(None)
        pbar = _ProgressBar(len(frames)) if _ProgressBar else None
        for frame in frames:
            writer.send(frame.tobytes())
            if pbar:
                pbar.update(1)
    finally:
        writer.close()


def _encode_gif(frames, path, fps, loop_count):
    images = [Image.fromarray(frame) for frame in frames]
    duration = int(round(1000 / fps))
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        loop=loop_count,
        duration=duration,
    )


class SaveVideoPlus(io.ComfyNode):
    OUTPUT_NODE = True

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SaveVideoPlus",
            display_name="Save Video Plus",
            category="ZSimple-Nodes/video",
            search_aliases=["save", "save video", "export", "mp4", "webm", "gif"],
            inputs=[
                io.Image.Input("images"),
                io.Combo.Input("format", options=["mp4", "webm", "gif"], default="mp4"),
                io.Float.Input(
                    "frame_rate",
                    default=24.0,
                    min=1.0,
                    max=120.0,
                    step=1.0,
                    tooltip="输出视频帧率（fps）。",
                ),
                io.String.Input("filename_prefix", default="ZSimple"),
                io.String.Input(
                    "subfolder_template",
                    default="%date:yyyy-MM-dd%",
                    tooltip="output/ 下的子目录模板，支持 %date%/%width%/%height%。",
                ),
                io.Int.Input(
                    "filename_number_padding",
                    default=5,
                    min=1,
                    max=9,
                    tooltip="文件计数器零填充宽度（5 -> 00001）。",
                ),
                io.Int.Input("quality", default=90, min=1, max=100),
                io.Int.Input(
                    "loop_count",
                    default=0,
                    min=0,
                    max=100,
                    tooltip="仅 gif 生效；0=无限循环。",
                ),
                io.Combo.Input("pingpong", options=["off", "on"], default="off",
                               tooltip="on 时追加反向帧（去首尾）制造无缝循环。"),
                io.Combo.Input(
                    "embed_metadata",
                    options=["none", "prompt_only", "all"],
                    default="all",
                    tooltip="仅 mp4 生效；写入 prompt / workflow 到容器 metadata。",
                ),
            ],
            hidden=[
                io.Hidden.prompt,
                io.Hidden.extra_pnginfo,
            ],
            outputs=[
                io.Image.Output("images", tooltip="原图透传。"),
                io.String.Output("paths", tooltip="保存文件的相对路径。"),
                io.String.Output("filename_first", tooltip="保存的文件名。"),
                io.Int.Output("frame_count", tooltip="实际编码的帧数。"),
                io.String.Output("workflow_json", tooltip="API workflow JSON；不可用时为空字符串。"),
            ],
        )

    @classmethod
    def execute(
        cls,
        images,
        format,
        frame_rate,
        filename_prefix,
        subfolder_template,
        filename_number_padding,
        quality,
        loop_count,
        pingpong,
        embed_metadata,
        prompt=None,
        extra_pnginfo=None,
    ):
        if len(images) == 0:
            raise RuntimeError("images 为空，无法编码视频")

        frames = [
            np.clip(255.0 * t.cpu().numpy(), 0, 255).astype(np.uint8)
            for t in images
        ]
        if pingpong == "on":
            frames = _pingpong_frames(frames)

        height, width = frames[0].shape[0], frames[0].shape[1]
        output_dir = folder_paths.get_output_directory()
        subfolder = resolve_subfolder(subfolder_template, width=width, height=height)
        full_output_folder = os.path.join(output_dir, subfolder) if subfolder else output_dir
        os.makedirs(full_output_folder, exist_ok=True)

        pad = max(1, int(filename_number_padding))
        counter = resume_counter(full_output_folder, filename_prefix, format)
        file_name = f"{filename_prefix}_{counter:0{pad}d}.{format}"
        full_save_path = os.path.join(full_output_folder, file_name)

        if format == "mp4":
            metadata_params = _build_mp4_metadata_params(embed_metadata, prompt, extra_pnginfo)
            _encode_mp4(frames, full_save_path, frame_rate, quality, metadata_params)
        elif format == "webm":
            _encode_webm(frames, full_save_path, frame_rate, quality)
        elif format == "gif":
            _encode_gif(frames, full_save_path, frame_rate, loop_count)
        else:
            raise RuntimeError(f"不支持的视频格式: {format}")

        relative_path = f"{subfolder}/{file_name}" if subfolder else file_name
        preview = {
            "filename": file_name,
            "subfolder": subfolder,
            "type": "output",
            "frame_rate": frame_rate,
        }
        return io.NodeOutput(
            images,
            relative_path,
            file_name,
            len(frames),
            workflow_json_from_extra(extra_pnginfo),
            ui={"gifs": [preview]},
        )