from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PriceEnrichment:
    return_5d_avg_pct: float | None
    return_hist_avg_pct: float | None
    return_gap_pct: float | None
    max_drawdown_pct: float | None
    accel_breakout_date: str | None
    accel_breakout_z: float | None


def analyze_price_series(rows: list[dict]) -> PriceEnrichment:
    if not rows:
        return PriceEnrichment(None, None, None, None, None, None)

    d = pd.DataFrame(rows)
    if "x" not in d.columns or "y" not in d.columns:
        return PriceEnrichment(None, None, None, None, None, None)
    d["x"] = pd.to_datetime(d["x"], errors="coerce")
    d["y"] = pd.to_numeric(d["y"], errors="coerce")
    d = d.dropna(subset=["x", "y"]).sort_values("x")
    if len(d) < 15:
        return PriceEnrichment(None, None, None, None, None, None)

    d["ret"] = d["y"].pct_change() * 100.0
    d["ret_5d"] = d["ret"].rolling(5, min_periods=3).mean()
    ret5 = d["ret_5d"].dropna()

    if ret5.empty:
        return PriceEnrichment(None, None, None, None, None, None)

    hist_avg = float(ret5.mean())
    latest = float(ret5.iloc[-1])
    gap = latest - hist_avg
    std = float(ret5.std(ddof=0))
    z = (gap / std) if std > 0 else 0.0

    roll_mean_30 = ret5.rolling(30, min_periods=10).mean()
    roll_std_30 = ret5.rolling(30, min_periods=10).std(ddof=0).fillna(0.0)
    denom = roll_std_30.mask(roll_std_30 == 0, np.nan)
    accel_z = ((ret5 - roll_mean_30) / denom).astype(float).fillna(0.0)
    trigger = accel_z > 1.5
    cross = trigger & (~trigger.shift(1, fill_value=False))
    breakout_date: Optional[str] = None
    breakout_z: Optional[float] = None
    if cross.any():
        idx = cross[cross].index[-1]
        breakout_date = pd.to_datetime(d.loc[idx, "x"]).strftime("%Y-%m-%d")
        breakout_z = float(accel_z.loc[idx])
    elif len(accel_z):
        idx = accel_z.idxmax()
        if float(accel_z.loc[idx]) > 1.2:
            breakout_date = pd.to_datetime(d.loc[idx, "x"]).strftime("%Y-%m-%d")
            breakout_z = float(accel_z.loc[idx])

    running_max = d["y"].cummax()
    dd = (d["y"] / running_max - 1.0) * 100.0
    max_dd = float(dd.min()) if not dd.empty else None

    return PriceEnrichment(
        return_5d_avg_pct=latest,
        return_hist_avg_pct=hist_avg,
        return_gap_pct=gap,
        max_drawdown_pct=max_dd,
        accel_breakout_date=breakout_date,
        accel_breakout_z=breakout_z,
    )
