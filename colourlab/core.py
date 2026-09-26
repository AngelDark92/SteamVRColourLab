"""Configuration, colour math and transforms. No third-party dependencies."""
from __future__ import annotations

import colorsys
import json
import math
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

MODES = {
    "compare": "Compare: top 8-bit / bottom 10-bit",
    "three": "Compare: top 8-bit / middle 10-bit / bottom reference",
    "8bit": "8-bit source",
    "10bit": "10-bit source",
    "reference": "Float reference (no intentional quantisation)",
    "dither8": "8-bit source with deterministic dithering",
}
PATTERNS = {
    "horizontal": "Horizontal gradient",
    "vertical": "Vertical gradient",
    "radial": "Radial gradient",
    "solid": "Solid colour (start RGB)",
    "hue": "Continuous hue sweep",
    "atlas": "12-colour gradient atlas",
}


@dataclass
class Settings:
    mode: str = "compare"
    pattern: str = "horizontal"
    start_rgb: tuple[float, float, float] = (0.02, 0.02, 0.02)
    end_rgb: tuple[float, float, float] = (0.20, 0.20, 0.20)
    hue: float = 210.0
    saturation: float = 0.65
    value_min: float = 0.02
    value_max: float = 0.20
    labels: bool = True
    swap: bool = False
    animate: bool = False
    panel_width: float = 3.6
    panel_height: float = 2.1
    panel_distance: float = 2.5
    stream_depth_requested: str = "unknown"
    streaming_app: str = ""
    codec: str = ""
    bitrate_mbps: str = ""
    notes: str = ""

    def validate(self) -> Settings:
        if not isinstance(self.mode, str) or not isinstance(self.pattern, str) or self.mode not in MODES or self.pattern not in PATTERNS:
            raise ValueError("Unrecognised source mode or pattern.")
        for name in ("start_rgb", "end_rgb"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or len(value) != 3:
                raise ValueError(f"{name} must contain exactly three numbers.")
            if not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in value):
                raise ValueError(f"{name} components must be finite numbers between 0 and 1.")
            setattr(self, name, tuple(float(x) for x in value))
        ranges = {
            "hue": (0, 360), "saturation": (0, 1), "value_min": (0, 1), "value_max": (0, 1),
            "panel_width": (0.2, 10), "panel_height": (0.2, 10), "panel_distance": (0.5, 10),
        }
        for name, (low, high) in ranges.items():
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be a finite number between {low} and {high}.")
        for name in ("labels", "swap", "animate"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false.")
        if self.stream_depth_requested not in ("unknown", "8", "10"):
            raise ValueError("Requested streaming depth must be unknown, 8 or 10.")
        for name in ("streaming_app", "codec", "bitrate_mbps", "notes"):
            if not isinstance(getattr(self, name), str) or len(getattr(self, name)) > 4000:
                raise ValueError(f"{name} must be a string of at most 4000 characters.")
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        if not isinstance(data, dict):
            raise ValueError("Settings must be a JSON object.")
        unknown = set(data) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
        return cls(**data).validate()

    @classmethod
    def load(cls, path: Path) -> Settings:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        self.validate()
        path.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n", encoding="utf-8")


def srgb_to_linear(x: float) -> float:
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def linear_to_srgb(x: float) -> float:
    return x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def quantise(x: float, bits: int) -> float:
    if bits not in (8, 10):
        raise ValueError("bits must be 8 or 10")
    levels = (1 << bits) - 1
    return math.floor(max(0.0, min(1.0, x)) * levels + 0.5) / levels


def hue_endpoints(hue: float, saturation: float, low: float, high: float):
    return (colorsys.hsv_to_rgb((hue % 360) / 360, saturation, low),
            colorsys.hsv_to_rgb((hue % 360) / 360, saturation, high))


PRESETS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "Dark neutral (recommended)": ((0.02, 0.02, 0.02), (0.20, 0.20, 0.20)),
    "Very dark neutral": ((0.0, 0.0, 0.0), (0.06, 0.06, 0.06)),
    "Full-range neutral": ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
    "Mid-grey narrow": ((0.40, 0.40, 0.40), (0.55, 0.55, 0.55)),
    "Bright neutral": ((0.80, 0.80, 0.80), (1.0, 1.0, 1.0)),
    "Dark blue-grey": ((0.012, 0.018, 0.032), (0.10, 0.15, 0.24)),
    "Dark warm-grey": ((0.025, 0.018, 0.012), (0.22, 0.16, 0.11)),
    "Blue sky": ((0.25, 0.42, 0.65), (0.55, 0.70, 0.85)),
    "Deep purple": ((0.018, 0.006, 0.028), (0.18, 0.06, 0.28)),
    "Teal": ((0.005, 0.025, 0.022), (0.04, 0.25, 0.22)),
    "Red to green": ((0.20, 0.02, 0.02), (0.02, 0.20, 0.02)),
    "Blue to yellow": ((0.02, 0.02, 0.20), (0.20, 0.20, 0.02)),
}
for _name, _rgb in (("Red", (1, 0, 0)), ("Green", (0, 1, 0)), ("Blue", (0, 0, 1)),
                   ("Cyan", (0, 1, 1)), ("Magenta", (1, 0, 1)), ("Yellow", (1, 1, 0))):
    PRESETS[_name + " dark"] = (tuple(0.01 * v for v in _rgb), tuple(0.25 * v for v in _rgb))
    PRESETS[_name + " full range"] = ((0, 0, 0), _rgb)
for _hue in range(0, 360, 15):
    PRESETS[f"Hue {_hue:03d} / dark"] = hue_endpoints(_hue, 0.8, 0.015, 0.22)


def apply_preset(settings: Settings, name: str) -> Settings:
    a, b = PRESETS[name]
    # A named endpoint preset always selects an endpoint-based pattern.
    return replace(settings, start_rgb=a, end_rgb=b, pattern="horizontal").validate()


def identity() -> list[list[float]]:
    return [[float(i == j) for j in range(4)] for i in range(4)]


def matmul(a, b) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def rigid_inverse(m) -> list[list[float]]:
    """Invert a rotation/translation transform; never apply to a scaled matrix."""
    out = identity()
    for i in range(3):
        for j in range(3):
            out[i][j] = m[j][i]
        out[i][3] = -sum(out[i][j] * m[j][3] for j in range(3))
    return out


def from_openvr(m) -> list[list[float]]:
    out = identity()
    for i in range(len(m.m)):
        for j in range(4):
            out[i][j] = float(m.m[i][j])
    return out


def panel_model(anchor, settings: Settings):
    local = identity()
    local[0][0] = settings.panel_width / 2
    local[1][1] = settings.panel_height / 2
    local[2][3] = -settings.panel_distance
    return matmul(anchor, local)


def gl_matrix(m) -> list[float]:
    """OpenGL expects column-major storage, while our math uses row-major lists."""
    return [m[row][col] for col in range(4) for row in range(4)]
