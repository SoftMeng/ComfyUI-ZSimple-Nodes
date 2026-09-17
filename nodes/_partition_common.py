# 共享 partition + locked-noise helper，ZImageTurboProgressive 与新 upscale 节点共用，避免两份实现漂移。

import torch


_PARTITION_CACHE: dict = {}


def _build_partition_map(low_n: int, high_n: int, device):
    key = (low_n, high_n, device.type)
    if key in _PARTITION_CACHE:
        return _PARTITION_CACHE[key]

    if high_n < low_n:
        raise ValueError(f"Partition requires high_n >= low_n, got {high_n} < {low_n}")

    base = high_n // low_n
    rem = high_n % low_n

    counts = torch.full((low_n,), base, dtype=torch.long, device=device)
    if rem > 0:
        counts[:rem] += 1

    map_hi_to_lo = torch.repeat_interleave(torch.arange(low_n, device=device), counts)
    inv_sqrt = (counts.float().rsqrt())[map_hi_to_lo]

    _PARTITION_CACHE[key] = (map_hi_to_lo, inv_sqrt, counts)
    return map_hi_to_lo, inv_sqrt, counts


def _reduce_height(x, map_h, inv_sqrt_h, low_h):
    B, C, Hh, W = x.shape
    out = torch.zeros((B, C, low_h, W), device=x.device, dtype=x.dtype)
    weighted = x * inv_sqrt_h.view(1, 1, Hh, 1)
    out.index_add_(2, map_h, weighted)
    return out


def _expand_height(coeff, map_h, inv_sqrt_h):
    Hh = map_h.shape[0]
    out = coeff.index_select(2, map_h) * inv_sqrt_h.view(1, 1, Hh, 1)
    return out


def _reduce_width(x, map_w, inv_sqrt_w, low_w):
    B, C, H, Ww = x.shape
    out = torch.zeros((B, C, H, low_w), device=x.device, dtype=x.dtype)
    weighted = x * inv_sqrt_w.view(1, 1, 1, Ww)
    out.index_add_(3, map_w, weighted)
    return out


def _expand_width(coeff, map_w, inv_sqrt_w):
    Ww = map_w.shape[0]
    out = coeff.index_select(3, map_w) * inv_sqrt_w.view(1, 1, 1, Ww)
    return out


def _project_to_coarse_subspace(x, low_h, low_w, high_h, high_w, device):
    map_h, inv_h, _ = _build_partition_map(low_h, high_h, device)
    map_w, inv_w, _ = _build_partition_map(low_w, high_w, device)

    tmp = _reduce_width(x, map_w, inv_w, low_w)
    coeff = _reduce_height(tmp, map_h, inv_h, low_h)
    recon = _expand_height(coeff, map_h, inv_h)
    recon = _expand_width(recon, map_w, inv_w)
    return recon


def _lift_noise(eps_prev, high_h, high_w):
    device = eps_prev.device
    low_h, low_w = eps_prev.shape[-2], eps_prev.shape[-1]
    map_h, inv_h, _ = _build_partition_map(low_h, high_h, device)
    map_w, inv_w, _ = _build_partition_map(low_w, high_w, device)

    out = _expand_height(eps_prev, map_h, inv_h)
    out = _expand_width(out, map_w, inv_w)
    return out


def _locked_noise_from_prev(eps_prev, target_shape, seed_new):
    device = eps_prev.device
    dtype = eps_prev.dtype
    B, C, H1, W1 = target_shape
    H0, W0 = eps_prev.shape[-2], eps_prev.shape[-1]

    g = torch.Generator(device=device)
    g.manual_seed(seed_new)
    eta = torch.randn((B, C, H1, W1), generator=g, device=device, dtype=dtype)

    proj = _project_to_coarse_subspace(eta, H0, W0, H1, W1, device)
    eta_perp = eta - proj

    lifted = _lift_noise(eps_prev, H1, W1)

    eps_new = lifted + eta_perp
    return eps_new