"""Outputs the current seed plus the next seed (seed + 1).

`control_after_generate` is handled by the ComfyUI frontend widget:
the backend only receives the already-processed current seed and computes +1.
"""
from comfy_api.latest import io


class RandomNumberPlus(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="RandomNumberPlus",
            display_name="Random Number Plus",
            category="ZSimple-Nodes",
            search_aliases=["random", "seed", "rng"],
            inputs=[
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                ),
            ],
            outputs=[
                io.Int.Output("int_out"),
                io.Int.Output("number_out"),
                io.Int.Output("next_int"),
            ],
        )

    @classmethod
    def execute(cls, seed: int) -> io.NodeOutput:
        return io.NodeOutput(int(seed), seed, seed + 1)