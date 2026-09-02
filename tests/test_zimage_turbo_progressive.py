"""Tests for ZImageTurboProgressive (run from ComfyUI-ZSimple-Nodes/ root)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ComfyUI"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes.zimage_turbo_progressive import (
    _stage_split, ZImageTurboProgressive, _apply_shift, _resolve_sampler,
)


def test_stage_split_default():
    s1, s2, s3 = _stage_split(8)
    assert s1 == 2
    assert s2 == 4
    assert s3 == 2


def test_stage_split_min_steps():
    s1, s2, s3 = _stage_split(3)
    assert s1 >= 1 and s2 >= 1 and s3 >= 1


def test_resolve_sampler_known():
    assert _resolve_sampler("euler") is not None


def test_resolve_sampler_unknown_returns_none():
    assert _resolve_sampler("nonexistent_xyz_42") is None


def test_apply_shift_zero_is_noop():
    class FakeMS:
        pass
    fake = FakeMS()
    fake.shift = 1.0

    class FakeModel:
        def get_model_object(self, key):
            return fake
    gen = _apply_shift(FakeModel(), 0.0)
    next(gen, None)
    try:
        assert fake.shift == 1.0
    finally:
        gen.close()


def test_define_schema_has_21_inputs():
    schema = ZImageTurboProgressive.define_schema()
    assert len(schema.input) == 21


def test_define_schema_io_names():
    schema = ZImageTurboProgressive.define_schema()
    names = {getattr(inp, "name", None) or inp[0] for inp in schema.input}
    expected = {
        "latent_input", "model", "positive", "positive_stg2", "positive_stg3",
        "cfg", "seed", "shift", "add_noise", "return_leftover_noise",
        "steps", "start_step", "end_step", "creativity_mode", "upscale_factor",
        "detailed_refiner",
        "stage1_sampler", "stage1_scheduler",
        "stage2_sampler", "stage2_scheduler",
        "stage3_sampler", "stage3_scheduler",
    }
    missing = expected - names
    assert not missing, f"Missing IO: {missing}"