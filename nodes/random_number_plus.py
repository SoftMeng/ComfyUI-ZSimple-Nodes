from comfy_api.latest import io


class RandomNumberPlus(io.ComfyNode):
    """Outputs the current seed in four formats plus the next seed (seed + 1).

    `control_after_generate` is handled by the ComfyUI frontend widget:
    the backend only receives the already-processed current seed and computes +1.
    """

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
                io.Float.Output("float_out"),
                io.String.Output("string_out"),
                io.Number.Output("number_out"),
                io.Int.Output("next_int"),
                io.Float.Output("next_float"),
            ],
        )

    @classmethod
    def execute(cls, seed: int) -> io.NodeOutput:
        return io.NodeOutput(
            int(seed),
            float(seed),
            str(seed),
            seed,
            seed + 1,
            float(seed + 1),
        )