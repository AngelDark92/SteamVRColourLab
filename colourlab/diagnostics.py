"""Read back the same render target used by the application, not a CPU mock."""
from __future__ import annotations

from .core import Settings, linear_to_srgb, quantise


def check_source_precision(renderer) -> dict:
    target = renderer.create_target(4096, 8)
    counts, maximum_errors = {}, {}
    for mode in ("8bit", "10bit", "reference"):
        s = Settings(mode=mode, labels=False, start_rgb=(0, 0, 0), end_rgb=(1, 1, 1))
        renderer.draw(target, s)
        data = renderer.read_pixels(target)
        row = data[0:4096 * 4:4]
        counts[mode] = len(set(row))
        bits = 8 if mode == "8bit" else 10
        errors = []
        for x, value in enumerate(row):
            source = (x + 0.5) / 4096
            expected = source if mode == "reference" else quantise(source, bits)
            errors.append(abs(linear_to_srgb(value) - expected))
        maximum_errors[mode] = max(errors)
        if max(errors) > 0.0006:
            raise RuntimeError(f"GPU source precision check failed for {mode}: error {max(errors):.8f}.")
    if counts["8bit"] != 256 or counts["10bit"] != 1024 or counts["reference"] <= 1024:
        raise RuntimeError(f"GPU source level counts failed: {counts}. No precision fallback is allowed.")
    return {
        "status": "passed",
        "scope": "Application source buffer only, before SteamVR/compression/display",
        "target": "GL_RGBA16F, linear-light RGB, opaque alpha",
        "size": [4096, 8],
        "unique_red_levels": counts,
        "maximum_srgb_roundtrip_error": maximum_errors,
        "channel_bits": target.channel_bits,
    }
