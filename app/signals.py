from __future__ import annotations

import json
from typing import Dict, List

import numpy as np
import pandas as pd


def _safe_z(value: float, mean: float, std: float) -> float:
    if value is None or mean is None or std is None:
        return 0.0
    if not np.isfinite(std) or std == 0:
        return 0.0
    return float((value - mean) / std)


def _cross_section_z(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    mu = s.mean()
    sigma = s.std(ddof=0)
    if sigma is None or sigma == 0 or not np.isfinite(sigma):
        return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
    return (s - mu) / sigma


def _build_category_strength(latest_df: pd.DataFrame) -> Dict[int, float]:
    if latest_df.empty:
        return {}
    grp = (
        latest_df.groupby(["kategori_id", "kategori_adi"], dropna=False)
        .agg(
            getiri_pct_mean=("getiri_pct", "mean"),
            toplam_deger_delta_sum=("toplam_deger_delta", "sum"),
            yatirimci_delta_sum=("yatirimci_delta", "sum"),
            akim_skor_mean=("akim_skor", "mean"),
        )
        .reset_index()
    )
    for col in ["getiri_pct_mean", "toplam_deger_delta_sum", "yatirimci_delta_sum", "akim_skor_mean"]:
        grp[f"{col}_z"] = _cross_section_z(grp[col])
    grp["category_strength"] = (
        0.35 * grp["getiri_pct_mean_z"]
        + 0.30 * grp["toplam_deger_delta_sum_z"]
        + 0.20 * grp["yatirimci_delta_sum_z"]
        + 0.15 * grp["akim_skor_mean_z"]
    )
    return {
        int(row["kategori_id"]) if pd.notna(row["kategori_id"]) else -1: float(row["category_strength"])
        for _, row in grp.iterrows()
    }


def compute_signals(
    latest_df: pd.DataFrame,
    history_df: pd.DataFrame,
    lookback_days: int,
    min_history_points: int,
    min_signal_score: float,
    min_interest_score: float,
    min_acceleration: float,
    top_n: int,
) -> pd.DataFrame:
    if latest_df.empty:
        return pd.DataFrame()

    df = latest_df.copy()
    for col in [
        "getiri_pct",
        "akim_skor",
        "yatirimci_delta",
        "toplam_deger_delta",
    ]:
        df[f"{col}_z_cs"] = _cross_section_z(df[col])

    history = history_df.copy()
    history["snapshot_date"] = pd.to_datetime(history["snapshot_date"], errors="coerce")
    latest_date = pd.to_datetime(df["snapshot_date"].iloc[0], errors="coerce")
    history = history[history["snapshot_date"] < latest_date]

    category_strength_map = _build_category_strength(df)
    rows: List[dict] = []

    metrics = ["getiri_pct", "akim_skor", "yatirimci_delta", "toplam_deger_delta"]

    for _, row in df.iterrows():
        kod = row["kod"]
        hist_fund = history[history["kod"] == kod].sort_values("snapshot_date")
        metric_scores = {}
        accel_scores = {}

        for metric in metrics:
            current_value = row.get(metric)
            cs_z = row.get(f"{metric}_z_cs", 0.0)

            ts_z = 0.0
            accel_z = 0.40 * cs_z
            if len(hist_fund) >= min_history_points:
                hist_vals = pd.to_numeric(hist_fund[metric], errors="coerce").dropna()
                if len(hist_vals) >= min_history_points:
                    ts_z = _safe_z(float(current_value), float(hist_vals.mean()), float(hist_vals.std(ddof=0)))
                    last_k = hist_vals.tail(min(7, len(hist_vals)))
                    accel_base = float(last_k.mean()) if len(last_k) else float(hist_vals.mean())
                    accel_raw = float(current_value) - accel_base if pd.notna(current_value) else 0.0
                    accel_z = _safe_z(accel_raw, 0.0, float(hist_vals.std(ddof=0)))

            metric_scores[metric] = 0.65 * ts_z + 0.35 * cs_z
            accel_scores[metric] = accel_z

        perf = metric_scores["getiri_pct"]
        flow = metric_scores["toplam_deger_delta"]
        investor = metric_scores["yatirimci_delta"]
        quality = metric_scores["akim_skor"]
        acceleration = (
            0.35 * accel_scores["getiri_pct"]
            + 0.30 * accel_scores["toplam_deger_delta"]
            + 0.25 * accel_scores["yatirimci_delta"]
            + 0.10 * accel_scores["akim_skor"]
        )
        signal_score = 0.35 * perf + 0.30 * flow + 0.25 * investor + 0.10 * quality
        interest_score = 0.65 * flow + 0.35 * investor
        kategori_id = int(row["kategori_id"]) if pd.notna(row["kategori_id"]) else -1
        category_strength = float(category_strength_map.get(kategori_id, 0.0))

        reasons: List[str] = []
        if perf > 0.8:
            reasons.append("getiri_ortalama_ustu")
        if flow > 0.8:
            reasons.append("nakit_girisi_guclu")
        if investor > 0.8:
            reasons.append("yatirimci_ilgisi_artiyor")
        if acceleration > min_acceleration:
            reasons.append("ivmelenme_var")
        if category_strength > 0.7:
            reasons.append("kategori_ayrisiyor")

        if (
            signal_score >= min_signal_score
            and (interest_score >= min_interest_score or acceleration >= min_acceleration)
        ):
            rows.append(
                {
                    "snapshot_date": row["snapshot_date"],
                    "period": row["period"],
                    "fund_type": row["fund_type"],
                    "kod": kod,
                    "fon_adi": row.get("fon_adi"),
                    "kategori_id": kategori_id,
                    "kategori_adi": row.get("kategori_adi"),
                    "signal_score": float(signal_score),
                    "interest_score": float(interest_score),
                    "acceleration": float(acceleration),
                    "category_strength": float(category_strength),
                    "reasons": ", ".join(reasons) if reasons else "istatistiksel_ayrisma",
                    "details_json": json.dumps(
                        {
                            "perf_score": perf,
                            "flow_score": flow,
                            "investor_score": investor,
                            "quality_score": quality,
                            "metric_scores": metric_scores,
                            "accel_scores": accel_scores,
                            "raw": {
                                "getiri_pct": row.get("getiri_pct"),
                                "toplam_deger_delta": row.get("toplam_deger_delta"),
                                "yatirimci_delta": row.get("yatirimci_delta"),
                                "akim_skor": row.get("akim_skor"),
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out = out.sort_values(
        ["signal_score", "interest_score", "acceleration"],
        ascending=[False, False, False],
    ).head(top_n)
    return out.reset_index(drop=True)
