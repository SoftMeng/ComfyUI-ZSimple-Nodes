"""Save Text Plus — write arbitrary text to .txt / .md / .json / .csv."""

import json
import os

from comfy_api.latest import io

import folder_paths

from ._save_common import resolve_subfolder, workflow_json_from_extra


class SaveTextPlus(io.ComfyNode):
    OUTPUT_NODE = True

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SaveTextPlus",
            display_name="Save Text Plus",
            category="ZSimple-Nodes/text",
            search_aliases=[
                "save text", "write text", "export text",
                "save txt", "write file",
            ],
            inputs=[
                io.String.Input("text", force_input=True, multiline=True),
                io.String.Input(
                    "extra_texts",
                    default="",
                    multiline=True,
                    tooltip="Optional extra content appended after a newline.",
                ),
                io.String.Input("filename_prefix", default="ComfyUI"),
                io.String.Input(
                    "subfolder_template",
                    default="%date:yyyy-MM-dd%",
                    tooltip=(
                        "Subfolder under output/. Supports %date%, %seed%, "
                        "%width%, %height%. Empty string = save to output_dir root."
                    ),
                ),
                io.Int.Input(
                    "filename_number_padding",
                    default=5,
                    min=1,
                    max=9,
                    tooltip="Zero-padding width for the file counter (e.g. 5 -> 00001).",
                ),
                io.Combo.Input(
                    "format",
                    options=["txt", "md", "json", "csv"],
                    default="txt",
                ),
                io.Combo.Input(
                    "embed_json_keys",
                    options=["none", "pretty"],
                    default="pretty",
                    tooltip="When format=json: 'pretty' pretty-prints valid JSON; 'none' writes text verbatim.",
                ),
            ],
            hidden=[
                io.Hidden.prompt,
                io.Hidden.extra_pnginfo,
            ],
            outputs=[
                io.String.Output(
                    "path",
                    tooltip="Full file path of the saved text file.",
                ),
                io.Int.Output(
                    "byte_count",
                    tooltip="Bytes written to disk.",
                ),
                io.String.Output(
                    "workflow_json",
                    tooltip="JSON dump of extra_pnginfo['workflow']. Empty string if unavailable.",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        text,
        extra_texts,
        filename_prefix,
        subfolder_template,
        filename_number_padding,
        format,
        embed_json_keys,
        prompt=None,
        extra_pnginfo=None,
    ):
        output_dir = folder_paths.get_output_directory()
        subfolder = resolve_subfolder(subfolder_template)
        full_output_folder = (
            os.path.join(output_dir, subfolder) if subfolder else output_dir
        )
        os.makedirs(full_output_folder, exist_ok=True)

        pad = max(1, int(filename_number_padding))
        file_name = f"{filename_prefix}_00001.{format}"
        full_save_path = os.path.join(full_output_folder, file_name)

        body = text + ("\n" + extra_texts if extra_texts else "")

        if format == "json" and embed_json_keys == "pretty":
            try:
                parsed = json.loads(body)
                body_to_write = json.dumps(
                    parsed, indent=2, ensure_ascii=False
                )
            except (json.JSONDecodeError, ValueError):
                body_to_write = body
        else:
            body_to_write = body

        with open(full_save_path, "w", encoding="utf-8") as f:
            f.write(body_to_write)
            byte_count = f.tell()

        return io.NodeOutput(
            full_save_path,
            byte_count,
            workflow_json_from_extra(extra_pnginfo),
        )
