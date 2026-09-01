"""Save Image Plus — modern image saver with format, quality, and metadata controls.

Improvements over the native SaveImage:
- Multi-format: png / jpeg / webp / jxl (user-controlled)
- Quality slider (1-100) for lossy formats
- PNG compression level (0-9, default 9 for archival)
- JPEG subsampling control (4:4:4 / 4:2:0)
- WebP lossless mode + quality/method trade-off
- Metadata embedding policy: none / prompt_only / all (JPEG EXIF size guarded)
- Filename template supporting both ComfyUI native `%date:yyyy-MM-dd%` syntax and `{var}` syntax
- Returns saved paths and first filename as STRING outputs (chainable)

JPEG XL support requires `pillow-jxl-plugin` to be installed:
    pip install pillow-jxl-plugin
If the plugin is missing and format=jxl is selected, the node raises a clear error.
"""

import json
import os
from datetime import datetime

import numpy as np
from PIL import ExifTags, Image
from PIL.PngImagePlugin import PngInfo

from comfy_api.latest import io

import folder_paths

_JPEG_EXIF_SAFETY_BYTES = 60000

try:
    import pillow_jxl  # registers JPEG XL support in Pillow  # noqa: F401

    JXL_AVAILABLE = True
except ImportError:
    JXL_AVAILABLE = False


class SaveImagePlus(io.ComfyNode):
    OUTPUT_NODE = True

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SaveImagePlus",
            display_name="Save Image Plus",
            category="ZSimple-Nodes/image",
            search_aliases=["save", "save image", "save plus", "export", "webp"],
            inputs=[
                io.Image.Input("images"),
                io.String.Input("filename_prefix", default="ZSimple"),
                io.Combo.Input(
                    "format",
                    options=["png", "jpeg", "webp", "jxl"],
                    default="png",
                ),
                io.Int.Input("quality", default=92, min=1, max=100),
                io.Int.Input(
                    "png_compress_level", default=9, min=0, max=9
                ),
                io.Combo.Input(
                    "webp_lossless",
                    options=["off", "on"],
                    default="off",
                ),
                io.Int.Input("webp_method", default=4, min=0, max=6),
                io.Combo.Input(
                    "jpeg_subsampling",
                    options=["4:4:4", "4:2:0"],
                    default="4:4:4",
                ),
                io.Combo.Input(
                    "embed_metadata",
                    options=["none", "prompt_only", "all"],
                    default="all",
                ),
                io.String.Input(
                    "filename_template", default="{prefix}_{counter:05}_"
                ),
                io.Int.Input(
                    "seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                ),
            ],
            hidden=[
                io.Hidden.prompt,
                io.Hidden.extra_pnginfo,
            ],
            outputs=[
                io.Image.Output("images"),
                io.String.Output("paths"),
                io.String.Output("filename_first"),
            ],
        )

    @classmethod
    def _resolve_template(
        cls, template: str, prefix: str, seed: int, width: int, height: int
    ) -> str:
        """Resolve both native `%date:yyyy-MM-dd%` and `{var}` placeholders."""
        now = datetime.now()
        result = template
        result = result.replace("%date:yyyy-MM-dd%", now.strftime("%Y-%m-%d"))
        result = result.replace("%date", now.strftime("%Y-%m-%d"))
        result = result.replace("%seed%", str(seed))
        result = result.replace("%width%", str(width))
        result = result.replace("%height%", str(height))
        result = result.replace("{prefix}", prefix)
        result = result.replace("{seed}", str(seed))
        result = result.replace("{date}", now.strftime("%Y-%m-%d"))
        return result

    @classmethod
    def _build_png_metadata(
        cls, embed_mode: str, prompt, extra_pnginfo
    ) -> PngInfo | None:
        if embed_mode == "none":
            return None
        metadata = PngInfo()
        if prompt is not None:
            metadata.add_text("prompt", json.dumps(prompt))
        if embed_mode == "all" and extra_pnginfo is not None:
            for key in extra_pnginfo:
                metadata.add_text(key, json.dumps(extra_pnginfo[key]))
        return metadata

    @classmethod
    def _build_jpeg_exif(
        cls, embed_mode: str, prompt, extra_pnginfo
    ) -> bytes | None:
        """Build EXIF bytes for JPEG; auto-downgrade to prompt_only if too large.

        JPEG EXIF segment hard cap is ~64KB. If total exceeds
        _JPEG_EXIF_SAFETY_BYTES, drop extra_pnginfo to avoid silent truncation.
        """
        if embed_mode == "none" or prompt is None:
            return None
        prompt_bytes = json.dumps(prompt).encode("utf-8")
        exif = Image.Exif()
        # UserComment is ASCII per EXIF spec; embed UTF-8 bytes directly is
        # the pragmatic choice ComfyUI's native SaveImage also makes.
        # Pillow handles encoding via UserComment tag bytes.
        if embed_mode == "all" and extra_pnginfo is not None:
            extra_bytes = b""
            for key in extra_pnginfo:
                extra_bytes += json.dumps(extra_pnginfo[key]).encode("utf-8")
                extra_bytes += b"\x00"
            if len(prompt_bytes) + len(extra_bytes) <= _JPEG_EXIF_SAFETY_BYTES:
                for key in extra_pnginfo:
                    exif[ExifTags.Base.UserComment] = json.dumps(
                        extra_pnginfo[key]
                    ).encode("utf-8")
        exif[ExifTags.Base.UserComment] = prompt_bytes
        return exif.tobytes()

    @classmethod
    def execute(
        cls,
        images,
        filename_prefix,
        format,
        quality,
        png_compress_level,
        webp_lossless,
        webp_method,
        jpeg_subsampling,
        embed_metadata,
        filename_template,
        seed,
        prompt=None,
        extra_pnginfo=None,
    ):
        output_dir = folder_paths.get_output_directory()
        height, width = images[0].shape[1], images[0].shape[0]

        # Step 1: Resolve %date% / %seed% / {prefix} in user-supplied prefix.
        # Must run BEFORE get_save_image_path because folder_paths only
        # supports a narrow placeholder grammar (%date, %time, %seed, %width,
        # %height) — our richer {var} syntax and full %date:yyyy-MM-dd% need
        # to be replaced first.
        resolved_prefix = cls._resolve_template(
            filename_prefix, filename_prefix, seed, width, height
        )
        # Strip placeholder counters that get_save_image_path itself manages,
        # so we don't accidentally double-replace them.
        resolved_prefix = resolved_prefix.replace("%batch_num%", "0")

        # Step 2: Let ComfyUI derive subfolder + counter from the cleaned prefix.
        _, _, counter, subfolder, _ = folder_paths.get_save_image_path(
            resolved_prefix, output_dir, width, height
        )

        # Step 3: Apply filename_template to build the actual file_name.
        # We feed `prefix` from the resolved name (basename of prefix) so
        # {prefix} resolves to "ZSimple" rather than the full subfolder path.
        # Strip the subfolder part from resolved_prefix to avoid duplication
        # in the filename (e.g. resolved_prefix="screenshots/ZSimple",
        # subfolder="screenshots", so we want name_base="ZSimple").
        if subfolder and resolved_prefix.startswith(subfolder + os.sep):
            name_root = resolved_prefix[len(subfolder) + 1:]
        elif subfolder and resolved_prefix == subfolder:
            name_root = ""
        else:
            name_root = os.path.basename(resolved_prefix)

        paths: list[str] = []
        results: list[dict] = []
        first_filename: str = ""

        for batch_number, image_tensor in enumerate(images):
            array = np.clip(255.0 * image_tensor.cpu().numpy(), 0, 255).astype(
                np.uint8
            )
            pil_image = Image.fromarray(array)

            # Apply filename_template to name_root (not full prefix).
            name_base = cls._resolve_template(
                filename_template, name_root, seed, width, height
            )
            name_base = name_base.replace("%batch_num%", str(batch_number))
            file_name = f"{name_base}{counter:05}_.{format}"

            full_output_folder = (
                os.path.join(output_dir, subfolder) if subfolder else output_dir
            )
            os.makedirs(full_output_folder, exist_ok=True)
            full_save_path = os.path.join(full_output_folder, file_name)

            if format == "png":
                pil_image.save(
                    full_save_path,
                    "PNG",
                    pnginfo=cls._build_png_metadata(
                        embed_metadata, prompt, extra_pnginfo
                    ),
                    compress_level=png_compress_level,
                )
            elif format == "jpeg":
                jpeg_kwargs: dict = {
                    "quality": quality,
                    "subsampling": jpeg_subsampling,
                }
                exif_bytes = cls._build_jpeg_exif(
                    embed_metadata, prompt, extra_pnginfo
                )
                if exif_bytes:
                    jpeg_kwargs["exif"] = exif_bytes
                pil_image.save(full_save_path, "JPEG", **jpeg_kwargs)
            elif format == "webp":
                webp_kwargs: dict = {"method": webp_method}
                if webp_lossless == "on":
                    webp_kwargs["lossless"] = True
                else:
                    webp_kwargs["quality"] = quality
                pil_image.save(full_save_path, "WEBP", **webp_kwargs)
            elif format == "jxl":
                if not JXL_AVAILABLE:
                    raise RuntimeError(
                        "JPEG XL save requires pillow-jxl-plugin. "
                        "Install with: pip install pillow-jxl-plugin"
                    )
                # JXL uses distance parameter (lower = higher quality),
                # not quality 0-100. Approximate quality -> distance.
                distance = max(0.0, (100 - quality) / 20.0)
                pil_image.save(full_save_path, "JXL", distance=distance)

            paths.append(
                f"{subfolder}/{file_name}" if subfolder else file_name
            )
            results.append(
                {"filename": file_name, "subfolder": subfolder, "type": "output"}
            )
            if batch_number == 0:
                first_filename = file_name
            counter += 1

        return io.NodeOutput(
            images,
            ",".join(paths),
            first_filename,
            ui={"images": results},
        )