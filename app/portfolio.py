from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from app.enrichment import analyze_price_series
from app.fvt_client import FvtClient


@dataclass
class PortfolioAnalysisResult:
    portfolio_df: pd.DataFrame
    suggestions_df: pd.DataFrame
    summary: dict


def _status_label(score: float) -> str:
    if score >= 1.0:
        return "Güçlü"
    if score >= 0.25:
        return "İzle"
    return "Zayıf"


def analyze_portfolio(
    client: FvtClient,
    holdings_df: pd.DataFrame,
    total_tl: float,
    per_period_snapshot: Dict[str, pd.DataFrame],
    daily_signals: pd.DataFrame,
) -> PortfolioAnalysisResult:
    if holdings_df is None or holdings_df.empty:
        return PortfolioAnalysisResult(pd.DataFrame(), pd.DataFrame(), {"total_tl": float(total_tl), "count": 0})

    h = holdings_df.copy()
    h["kod"] = h["kod"].astype(str).str.upper()
    h["weight_pct"] = pd.to_numeric(h["weight_pct"], errors="coerce").fillna(0.0)
    h = h[h["weight_pct"] > 0].copy()
    if h.empty:
        return PortfolioAnalysisResult(pd.DataFrame(), pd.DataFrame(), {"total_tl": float(total_tl), "count": 0})

    if len(h) > 10:
        h = h.head(10).copy()

    weight_sum = float(h["weight_pct"].sum())
    if weight_sum <= 0:
        weight_sum = 1.0
    h["weight_norm"] = h["weight_pct"] / weight_sum
    h["amount_tl"] = float(total_tl) * h["weight_norm"]

    period_maps: Dict[str, Dict[str, dict]] = {}
    for period, sdf in per_period_snapshot.items():
        if sdf is None or sdf.empty:
            period_maps[period] = {}
            continue
        period_maps[period] = {
            str(r["kod"]).upper(): r
            for _, r in sdf.iterrows()
        }

    rows: List[dict] = []
    for _, row in h.iterrows():
        kod = row["kod"]
        d = period_maps.get("gunluk", {}).get(kod)
        w = period_maps.get("haftalik", {}).get(kod)
        m = period_maps.get("aylik", {}).get(kod)

        fon_adi = d.get("fon_adi") if d is not None else (w.get("fon_adi") if w is not None else None)
        kategori = d.get("kategori_adi") if d is not None else (w.get("kategori_adi") if w is not None else None)
        getiri_g = float(d.get("getiri_pct")) if d is not None and pd.notna(d.get("getiri_pct")) else None
        getiri_h = float(w.get("getiri_pct")) if w is not None and pd.notna(w.get("getiri_pct")) else None
        getiri_a = float(m.get("getiri_pct")) if m is not None and pd.notna(m.get("getiri_pct")) else None
        yat_delta = float(d.get("yatirimci_delta")) if d is not None and pd.notna(d.get("yatirimci_delta")) else None

        price_rows = client.fetch_fund_series(kod, metric="fiyat", range_value="1Y")
        enrich = analyze_price_series(price_rows)

        score = 0.0
        score += 0.45 * (getiri_g if getiri_g is not None else 0)
        score += 0.35 * (enrich.return_gap_pct if enrich.return_gap_pct is not None else 0)
        score += 0.20 * ((yat_delta or 0) / 50.0)

        reasons = []
        if getiri_g is not None and getiri_g < 0:
            reasons.append("günlük_getiri_negatif")
        if enrich.return_gap_pct is not None and enrich.return_gap_pct < 0:
            reasons.append("5g_getiri_geçmiş_ortalama_altı")
        if yat_delta is not None and yat_delta < 0:
            reasons.append("yatırımcı_azalıyor")
        if enrich.accel_breakout_date:
            reasons.append("yakın_dönem_ivme_tespit")
        if not reasons:
            reasons.append("stabil")

        rows.append(
            {
                "kod": kod,
                "fon_adi": fon_adi,
                "kategori_adi": kategori,
                "weight_pct": float(row["weight_pct"]),
                "weight_norm_pct": float(row["weight_norm"] * 100),
                "amount_tl": float(row["amount_tl"]),
                "getiri_gunluk_pct": getiri_g,
                "getiri_haftalik_pct": getiri_h,
                "getiri_aylik_pct": getiri_a,
                "return_5d_avg_pct": enrich.return_5d_avg_pct,
                "return_hist_avg_pct": enrich.return_hist_avg_pct,
                "return_gap_pct": enrich.return_gap_pct,
                "max_drawdown_pct": enrich.max_drawdown_pct,
                "yatirimci_delta": yat_delta,
                "accel_breakout_date": enrich.accel_breakout_date,
                "accel_breakout_z": enrich.accel_breakout_z,
                "health_score": float(score),
                "health_status": _status_label(float(score)),
                "reasons": ", ".join(reasons),
            }
        )

    portfolio_df = pd.DataFrame(rows).sort_values("health_score", ascending=False).reset_index(drop=True)

    owned_codes = {str(x).strip().upper() for x in portfolio_df["kod"].astype(str).tolist()}
    if daily_signals is None or daily_signals.empty:
        suggestions_df = pd.DataFrame()
    else:
        sig = daily_signals.copy()
        sig["kod_norm"] = sig["kod"].astype(str).str.strip().str.upper()
        sig = sig[sig["kod_norm"] != ""].drop_duplicates(subset=["kod_norm"], keep="first")
        suggestions_df = sig[~sig["kod_norm"].isin(owned_codes)].copy()
        if not suggestions_df.empty:
            keep_cols = [
                "kod",
                "fon_adi",
                "kategori_adi",
                "signal_score",
                "interest_score",
                "acceleration",
                "reasons",
            ]
            suggestions_df = suggestions_df[keep_cols].head(5).reset_index(drop=True)

    summary = {
        "total_tl": float(total_tl),
        "count": int(len(portfolio_df)),
        "avg_daily_return": float(pd.to_numeric(portfolio_df["getiri_gunluk_pct"], errors="coerce").mean())
        if not portfolio_df.empty
        else None,
        "avg_weekly_return": float(pd.to_numeric(portfolio_df["getiri_haftalik_pct"], errors="coerce").mean())
        if not portfolio_df.empty
        else None,
        "avg_monthly_return": float(pd.to_numeric(portfolio_df["getiri_aylik_pct"], errors="coerce").mean())
        if not portfolio_df.empty
        else None,
    }

    return PortfolioAnalysisResult(portfolio_df=portfolio_df, suggestions_df=suggestions_df, summary=summary)
