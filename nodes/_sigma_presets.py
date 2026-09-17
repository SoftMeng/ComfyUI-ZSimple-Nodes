# Z-Image Turbo 蒸馏 sigma preset 集合；zimage_turbo_progressive 和 z_image_upscale_plus 共用 v2 选择面


_SIGMA_PRESETS_BY_NAME = {
    "alpha_3" : [(0.991, 0.920), (0.942, 0.000), (0.710, 0.000)],
    "alpha_4" : [(0.991, 0.920), (0.935, 0.789, 0.000), (0.710, 0.000)],
    "alpha_5" : [(0.991, 0.920), (0.935, 0.789, 0.000), (0.658, 0.302, 0.000)],
    "alpha_6" : [(0.991, 0.920), (0.935, 0.770, 0.690, 0.000), (0.658, 0.302, 0.000)],
    "alpha_7" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.800, 0.000), (0.658, 0.302, 0.000)],
    "alpha_8" : [(0.991, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.000), (0.658, 0.302, 0.000)],
    "alpha_9" : [(0.991, 0.960, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.000), (0.658, 0.302, 0.000)],
    "alpha_10" : [(0.991, 0.960, 0.920), (0.935, 0.900, 0.875, 0.820, 0.750, 0.000), (0.658, 0.4556, 0.200, 0.000)],
}

_BASE_S1_LOW = (0.960, 0.920)
_BASE_S1_HIGH = (0.991, 0.920)
_BASE_S2 = (0.935, 0.900, 0.875, 0.820, 0.750, 0.000)
_BASE_S3 = (0.658, 0.4556, 0.200, 0.000)

_BASE_S1_BY_MODE = {
    "off": _BASE_S1_HIGH,
    "lite": _BASE_S1_LOW,
    "middle": _BASE_S1_HIGH,
    "high": _BASE_S1_LOW,
}

_MODE_DOES_SCRAMBLE = {"middle", "high"}
_MODE_DOES_PREPROC = {"lite", "middle", "high"}

_ALPHA_INSERT_COUNTS: dict[int, tuple[int, int]] = {
    11: (1, 1),
    12: (2, 2),
    13: (3, 3),
    14: (4, 4),
    15: (5, 5),
}


def _refine_sigma_sequence(sigmas, insert_count: int):
    if not sigmas or len(sigmas) < 2:
        sigmas = [1.0, 0.0]
    sigmas = list(sigmas)
    while insert_count > 0:
        new_sequence = [sigmas[0]]
        for i in range(len(sigmas) - 1):
            if insert_count > 0:
                new_sequence.append((sigmas[i] + sigmas[i + 1]) / 2)
                insert_count -= 1
            new_sequence.append(sigmas[i + 1])
        sigmas = new_sequence
    return sigmas


def _get_sigma_preset(steps: int, mode: str = "middle"):
    s1 = _BASE_S1_BY_MODE.get(mode, _BASE_S1_HIGH)
    if f"alpha_{steps}" in _SIGMA_PRESETS_BY_NAME:
        return _SIGMA_PRESETS_BY_NAME[f"alpha_{steps}"]
    if steps in _ALPHA_INSERT_COUNTS:
        s2_inserts, s3_inserts = _ALPHA_INSERT_COUNTS[steps]
        return (
            s1,
            tuple(_refine_sigma_sequence(_BASE_S2, s2_inserts)),
            tuple(_refine_sigma_sequence(_BASE_S3, s3_inserts)),
        )
    if 10 <= steps <= 99:
        extra = steps - 9
        n1 = int(0.4 + 0.6 * extra)
        n2 = extra - n1
        return (
            s1,
            tuple(_refine_sigma_sequence(_BASE_S2, n2)),
            tuple(_refine_sigma_sequence(_BASE_S3, n1)),
        )
    return _SIGMA_PRESETS_BY_NAME["alpha_8"]