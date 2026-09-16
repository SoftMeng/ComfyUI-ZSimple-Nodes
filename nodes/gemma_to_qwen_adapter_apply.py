"""Project Gemma4-encoded CONDITIONING into the Qwen-like space Z-Image expects.

Train and inference share the adapter definition in _gemma_adapter_common.
This node consumes a CONDITIONING list emitted by a Gemma4 CLIPTextEncode
and rewrites each pair so Z-Image's UNet reads the projected tokens as
native Qwen3-4B features.
"""

from pathlib import Path

import torch

from comfy_api.latest import io

from ._gemma_adapter_common import (
    DEFAULT_DTYPE,
    GEMMA_HIDDEN,
    apply_adapter_to_gemma_embeds,
    load_adapter_singleton,
)


def _log(msg: str):
    print(f"[GemmaToQwenAdapterApply] {msg}", flush=True)


class GemmaToQwenAdapterApply(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="GemmaToQwenAdapterApply",
            display_name="Apply Gemma→Qwen Adapter (Z-Image)",
            category="ZSimple-Nodes/adapter",
            search_aliases=["adapter", "Gemma", "Qwen", "Z-Image", "text encoder"],
            description=(
                "Take a Gemma4-encoded CONDITIONING and project it through the trained "
                "Perceiver-Resampler adapter so Z-Image UNet reads it as native Qwen3-4B "
                "features. Output token count is fixed at 77 to match Z-Image's cross-attention. "
                "pooled_output = projected token-mean (warmup alignment; production should redo with denoising-loss for cls-like pool)."
            ),
            inputs=[
                io.Conditioning.Input(
                    "conditioning",
                    tooltip="CONDITIONING encoded by Gemma4 CLIPTextEncode (LTX2.5 gemma4_e2b_it_int8_convrot).",
                ),
                io.String.Input(
                    "adapter_path",
                    default="model-trainer/gemma_to_zimage_adapter.safetensors",
                    tooltip="Path to gemma_to_zimage_adapter.safetensors produced by TrainGemmaToQwenAdapter.",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="conditioning"),
            ],
        )

    @classmethod
    def execute(cls, conditioning: list | tuple, adapter_path: str) -> io.NodeOutput:
        if not Path(adapter_path).is_file():
            raise FileNotFoundError(
                f"adapter file not found: {adapter_path}; run TrainGemmaToQwenAdapter first"
            )

        adapter, meta = load_adapter_singleton(adapter_path, dtype=DEFAULT_DTYPE)
        denoising_done = str(meta.get("denoising_done", "True"))
        if denoising_done != "True":
            _log(
                f"WARNING: phase={meta.get('phase')}, denoising_done={denoising_done}; "
                f"outputs may be off — run denoising-loss stage before production use."
            )

        out = []
        for cond_pair in conditioning:
            if not isinstance(cond_pair, (list, tuple)) or len(cond_pair) < 1:
                raise RuntimeError(f"malformed conditioning element: {cond_pair!r}")

            cond_tensor = cond_pair[0]
            pooled_dict = cond_pair[1] if len(cond_pair) > 1 and isinstance(cond_pair[1], dict) else {}

            if not hasattr(cond_tensor, "dim"):
                raise RuntimeError(
                    f"conditioning[0] must be a tensor, got {type(cond_tensor).__name__}"
                )
            while cond_tensor.dim() > 3:
                cond_tensor = cond_tensor.select(1, -1)
            if cond_tensor.dim() == 2:
                cond_tensor = cond_tensor.unsqueeze(0)
            if cond_tensor.dim() != 3:
                raise RuntimeError(
                    f"conditioning tensor must collapse to [B,N,H], got shape {tuple(cond_tensor.shape)}"
                )

            if cond_tensor.shape[-1] != GEMMA_HIDDEN:
                raise RuntimeError(
                    f"expected hidden_size={GEMMA_HIDDEN}, got {cond_tensor.shape[-1]}; "
                    f"adapter was trained for Gemma4-E2B (LTX2.5 gemma4_e2b_it_int8_convrot); wrong CLIP?"
                )

            B, N, _ = cond_tensor.shape
            # Standard CONDITIONING list omits attention_mask (it lives only in encode_from_tokens return_dict output); treat all tokens as valid.
            mask = torch.ones(B, N, dtype=torch.long, device=cond_tensor.device)

            proj_tokens, proj_pooled = apply_adapter_to_gemma_embeds(
                adapter, cond_tensor.to(DEFAULT_DTYPE), mask
            )

            in_dtype = cond_tensor.dtype
            proj_tokens = proj_tokens.to(in_dtype)
            proj_pooled = proj_pooled.to(in_dtype)

            new_pooled = dict(pooled_dict)
            new_pooled["pooled_output"] = proj_pooled

            out.append([proj_tokens, new_pooled])

        return io.NodeOutput(out)