"""Shared Gemma4→Z-Image adapter: network definition + inference helpers.

Train and Apply nodes both use GemmaToZImageAdapter. This module owns the
class plus a thread-safe singleton loader and an inference runner so the
two nodes don't redeclare the architecture or reload weights per call.
"""

import threading
from pathlib import Path

import torch
import torch.nn as nn
from safetensors import safe_open


GEMMA_HIDDEN = 1536
QWEN_HIDDEN = 2560
NUM_LATENTS = 77
DEFAULT_DTYPE = torch.bfloat16


class PerceiverResamplerBlock(nn.Module):
    def __init__(self, dim: int, num_heads: int):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.cross_attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(dim)
        self.ff = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.GELU(),
            nn.Linear(dim * 4, dim),
        )

    def forward(self, queries, keys_values, key_padding_mask):
        q = self.norm1(queries)
        ca, _ = self.cross_attn(q, keys_values, keys_values, key_padding_mask=key_padding_mask, need_weights=False)
        x = queries + ca
        x = x + self.ff(self.norm2(x))
        return x


class GemmaToZImageAdapter(nn.Module):
    def __init__(
        self,
        gemma_hidden: int = GEMMA_HIDDEN,
        qwen_hidden: int = QWEN_HIDDEN,
        num_latents: int = NUM_LATENTS,
        resampler_layers: int = 4,
        num_heads: int = 8,
    ):
        super().__init__()
        self.gemma_hidden = gemma_hidden
        self.qwen_hidden = qwen_hidden
        self.num_latents = num_latents

        self.input_norm = nn.LayerNorm(gemma_hidden)
        self.latents = nn.Parameter(torch.randn(num_latents, gemma_hidden) * 0.02)
        self.resampler = nn.ModuleList(
            [PerceiverResamplerBlock(gemma_hidden, num_heads) for _ in range(resampler_layers)]
        )
        self.resampler_norm = nn.LayerNorm(gemma_hidden)

        self.proj = nn.Sequential(
            nn.Linear(gemma_hidden, qwen_hidden),
            nn.LayerNorm(qwen_hidden),
            nn.GELU(),
            nn.Linear(qwen_hidden, qwen_hidden),
            nn.LayerNorm(qwen_hidden),
        )
        nn.init.normal_(self.proj[3].weight, std=0.02)
        nn.init.zeros_(self.proj[3].bias)

    def forward(self, gemma_embeds, gemma_mask):
        B = gemma_embeds.shape[0]
        h = self.input_norm(gemma_embeds)
        queries = self.latents.unsqueeze(0).expand(B, -1, -1)
        key_padding = gemma_mask == 0
        for blk in self.resampler:
            queries = blk(queries, h, key_padding)
        queries = self.resampler_norm(queries)
        tokens = self.proj(queries)
        pooled = tokens.mean(dim=1)
        return tokens, pooled


_ADAPTER_LOCK = threading.Lock()
_ADAPTER_CACHE: dict = {}


def _cache_key(path: str, dtype: torch.dtype, device: str) -> tuple:
    return (str(Path(path).resolve()), str(dtype).split(".")[-1], str(device))


def load_adapter_singleton(path: str, dtype: torch.dtype = DEFAULT_DTYPE, device: str = None):
    """Load a GemmaToZImageAdapter from .safetensors with thread-safe singleton cache.

    On miss: load weights, move to device, switch to eval mode, return (module, metadata).
    On hit: return the cached instance — caller's device-migration responsibility.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    key = _cache_key(path, dtype, device)
    if key in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[key]
    with _ADAPTER_LOCK:
        if key in _ADAPTER_CACHE:
            return _ADAPTER_CACHE[key]
        with safe_open(path, framework="pt") as f:
            meta = dict(f.metadata() or {})
            state = {k: f.get_tensor(k) for k in f.keys()}
        adapter = GemmaToZImageAdapter().to(device, dtype=dtype)
        adapter.load_state_dict(state)
        adapter.eval()
        result = (adapter, meta)
        _ADAPTER_CACHE[key] = result
        return result


def apply_adapter_to_gemma_embeds(adapter, gemma_embeds: torch.Tensor, gemma_mask: torch.Tensor):
    """Run adapter on Gemma per-token hidden states; returns (tokens [B,77,2560], pooled [B,2560]).

    Wrapped in inference_mode so no autograd state is created on the projector path.
    """
    with torch.inference_mode():
        tokens, pooled = adapter(gemma_embeds, gemma_mask)
    return tokens, pooled