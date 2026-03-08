from __future__ import annotations

import math


def z_to_100(z_value: float | None) -> int:
    """Maps z-score to 0-100 percentile-like scale using normal CDF."""
    if z_value is None:
        return 50
    try:
        z = float(z_value)
    except (TypeError, ValueError):
        return 50
    pct = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return int(round(max(0.0, min(1.0, pct)) * 100))


def z_band_label(z_value: float | None) -> str:
    if z_value is None:
        return "Nötr"
    try:
        z = float(z_value)
    except (TypeError, ValueError):
        return "Nötr"
    if z >= 2.0:
        return "Çok Güçlü"
    if z >= 1.0:
        return "Güçlü"
    if z >= 0.3:
        return "Pozitif"
    if z <= -2.0:
        return "Çok Zayıf"
    if z <= -1.0:
        return "Zayıf"
    if z <= -0.3:
        return "Negatif"
    return "Nötr"

