"""ZAdvancedProgressiveSampler — generic 3-stage progressive sampling.

User supplies three σ schedules (one per stage) via sigmas_pipe; per-stage latent
size and sampler are configurable. Designed for flow-matching / distillation
schedules where the total step count is given by the σ list length (no `steps`
input required).
"""

from typing import Any

import torch

import comfy.model_management
import comfy.samplers

from comfy_api.latest import io

from ._noise_inverse import _noise_inverse
from ._sample_common import (
    _parse_multiline_sigmas,
    _stage_sample_with_sigmas,
    _stage_seed,
    _validate_multiline_sigmas,
)
from .zimage_turbo_progressive import _generate_noise, adjust_latent_size


_SAMPLER_NAMES = comfy.samplers.SAMPLER_NAMES

_DEFAULT_SIGMAS_PIPE = "[1.0, 0.96, 0.88, 0.78, 0.66, 0.54, 0.42, 0.30, 0.18, 0.08, 0.0]\n[0.08, 0.04, 0.0]\n[0.04, 0.0]"


def _next_latent_shape(target_h: int, target_w: int, scale: float) -> tuple[int, int]:
    return (
        max(8, round(target_h * scale / 8) * 8),
        max(8, round(target_w * scale / 8) * 8),
    )


def _expected_channels(model) -> int | None:
    for candidate in (getattr(model, "model", None), model):
        if candidate is None:
            continue
        lf = getattr(candidate, "latent_format", None)
        if lf is not None:
            ch = getattr(lf, "latent_channels", None)
            if ch is not None:
                return ch
    return None


class ZAdvancedProgressiveSampler(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ZAdvancedProgressiveSampler",
            display_name="Z-Image Advanced Progressive Sampler",
            category="ZSimple-Nodes/sampling",
            description=(
                "Generic 3-stage progressive sampling. Each stage reads its own σ "
                "schedule from one sigmas_pipe line; per-stage latent scale and "
                "sampler are independent. Total step count comes from the σ list "
                "length (no `steps` parameter)."
            ),
            inputs=[
                io.Latent.Input("latent_input"),
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.String.Input(
                    "sigmas_pipe",
                    default=_DEFAULT_SIGMAS_PIPE,
                    multiline=True,
                    tooltip=(
                        "Three lines = three stage σ schedules. Each line = comma-separated "
                        "floats. First σ of each line ∈ (0, 1]; last line must end at 0.0 "
                        "(intermediate lines may stop at σ>0 for trajectory segmentation). "
                        "Lines must be monotonically non-increasing."
                    ),
                ),
                io.Float.Input("stage1_scale", default=0.5, min=0.1, max=2.0, step=0.05,
                               tooltip="Stage 1 latent size (relative to input H/W). 0.5 = half size, 1.0 = input size."),
                io.Float.Input("stage2_scale", default=0.75, min=0.1, max=2.0, step=0.05,
                               tooltip="Stage 2 latent size (relative to input H/W). 0.5 = half size, 1.0 = input size."),
                io.Float.Input("stage3_scale", default=1.0, min=0.1, max=2.0, step=0.05,
                               tooltip="Stage 3 latent size (relative to input H/W). 0.5 = half size, 1.0 = input size."),
                io.Combo.Input("stage1_sampler", options=_SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage2_sampler", options=_SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage3_sampler", options=_SAMPLER_NAMES, default="euler"),
                io.Combo.Input("stage_handoff", options=["off", "legacy"], default="legacy",
                               tooltip="off = pass previous stage output as-is; legacy = Karras-EDM noise_inverse bridge before resize."),
                io.Float.Input("cfg", default=1.0, min=1.0, max=20.0, step=0.1,
                               tooltip="Classifier-free guidance. Distilled models: 1.0. Higher values need a connected CONDITIONING."),
                io.Int.Input("seed", default=0, min=0, max=2**63 - 1),
            ],
            outputs=[
                io.Latent.Output("latent",
                                  tooltip="Stage 3 clean latent (force_full_denoise=True). Final output."),
                io.Latent.Output("debug_stage1_latent",
                                  tooltip="Stage 1 clean latent (after stage1 sample). Connect to VAE Decode + Save Image to inspect."),
                io.Latent.Output("debug_stage2_latent",
                                  tooltip="Stage 2 clean latent (after stage2 sample). Connect to VAE Decode + Save Image to inspect."),
            ],
        )

    @classmethod
    def execute(
        cls,
        latent_input: dict,
        model: Any,
        positive: list | None = None,
        sigmas_pipe: str = _DEFAULT_SIGMAS_PIPE,
        stage1_scale: float = 0.5,
        stage2_scale: float = 0.75,
        stage3_scale: float = 1.0,
        stage1_sampler: str = "euler",
        stage2_sampler: str = "euler",
        stage3_sampler: str = "euler",
        stage_handoff: str = "legacy",
        cfg: float = 1.0,
        seed: int = 0,
    ) -> io.NodeOutput:
        stages = _parse_multiline_sigmas(sigmas_pipe)
        if len(stages) != 3:
            raise ValueError(f"sigmas_pipe must have exactly 3 stage lines, got {len(stages)}")
        _validate_multiline_sigmas(stages, require_last_end_zero=True)

        cond = positive or []
        negative = cond if cfg > 1.0 else []

        expected = _expected_channels(model)
        if expected is not None and latent_input["samples"].shape[1] != expected:
            raise RuntimeError(
                f"ZAdvancedProgressiveSampler: latent has {latent_input['samples'].shape[1]} channels "
                f"but model expects {expected}. Use a matching Empty latent node "
                f"(Qwen-Image 2.1 → TextEncodeQwenImage21.latent 64-ch 4D; "
                f"SDXL/Flux → Empty Latent Image 4-ch 4D). "
                f"EmptyQwenImageLayeredLatentImage (16-ch 5D) is for Qwen-Image-Layered only."
            )

        scales = [stage1_scale, stage2_scale, stage3_scale]
        sampler_names = [stage1_sampler, stage2_sampler, stage3_sampler]
        target_h, target_w = latent_input["samples"].shape[-2:]
        prev_end_sigma = None
        debug_stage1 = None
        debug_stage2 = None

        for i in range(3):
            if i < 2 and stage_handoff == "legacy":
                next_h, next_w = _next_latent_shape(target_h, target_w, scales[i + 1])
                cur_h, cur_w = current["samples"].shape[-2:]
                if (cur_h, cur_w) != (next_h, next_w):
                    # Karras-EDM noise bridge: re-noise prev to stage i+1's start σ
                    bridge_sigma = stages[i + 1][0]
                    skip = _noise_inverse(model, current["samples"], sigma_target=bridge_sigma, noise_seed=seed + (i + 1) * 16)
                    current = {"samples": skip}

            target_h_i = max(8, round(target_h * scales[i] / 8) * 8)
            target_w_i = max(8, round(target_w * scales[i] / 8) * 8)
            current = adjust_latent_size(current, target_size=(target_h_i, target_w_i))

            stage_sigmas_list = list(stages[i])
            if i > 0 and prev_end_sigma is not None and stage_sigmas_list[0] < prev_end_sigma - 1e-6:
                stage_sigmas_list = [prev_end_sigma] + stage_sigmas_list

            device = comfy.model_management.get_torch_device()
            samples_i = current["samples"].to(device)
            shape = samples_i.shape
            stage_seed = _stage_seed(seed, i)
            eps = _generate_noise(stage_seed, shape, noise_scale=1.0, noise_bias=0.0,
                                  dtype=samples_i.dtype, device=device)
            sigmas_i = torch.tensor(stage_sigmas_list, dtype=samples_i.dtype, device=device)
            sampler_obj = comfy.samplers.sampler_object(sampler_names[i])

            out = _stage_sample_with_sigmas(
                model=model,
                latent_image=samples_i,
                noise=eps,
                cfg=cfg,
                sampler_obj=sampler_obj,
                sigmas=sigmas_i,
                callback=None,
                seed=stage_seed,
                force_full_denoise=True,
                conditioning=cond,
                negative=negative,
                sampler_name=sampler_names[i],
            )
            current = {"samples": out}
            prev_end_sigma = stage_sigmas_list[-1]
            if i == 0:
                debug_stage1 = current
            elif i == 1:
                debug_stage2 = current

        return io.NodeOutput(current, debug_stage1, debug_stage2)