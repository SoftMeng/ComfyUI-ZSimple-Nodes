# Karras-EDM 风格 noise inversion；用于 stage 间桥接（把上一 stage 的 clean latent 加噪到下一 stage 入口 sigma）

import torch


def _noise_inverse(model, x0: torch.Tensor, sigma_target: float, noise_seed: int) -> torch.Tensor:
    noise = torch.randn(x0.shape, dtype=x0.dtype, device=x0.device,
                        generator=torch.Generator(device=x0.device).manual_seed(noise_seed))
    return (1.0 - sigma_target) * x0 + sigma_target * noise