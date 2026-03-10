from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.benchmarks import YahooBenchmarkClient
from app.enrichment import analyze_price_series
from app.fvt_client import FvtClient
from app.scoring import z_to_100

sns.set_theme(style="whitegrid", context="talk")


_DATE_FMT = mdates.DateFormatter("%d.%m.%Y")


def plot_top_signals(signal_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if signal_df.empty:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Sinyal bulunamadı", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    data = signal_df.copy().sort_values("signal_score", ascending=True)
    labels = data["kod"] + " - " + data["kategori_adi"].fillna("-")
    fig, ax = plt.subplots(figsize=(15, max(6, len(data) * 0.9)))
    bars = ax.barh(labels, data["signal_score"], color="#0E7A0D")
    ax.set_title(title)
    ax.set_xlabel("Sinyal Skoru (Z)")
    ax.set_ylabel("Fon")
    ax.axvline(0, color="#777", linewidth=1, alpha=0.7)

    for i, bar in enumerate(bars):
        accel = float(data["acceleration"].iloc[i])
        interest = float(data["interest_score"].iloc[i])
        txt = (
            f"İvme: {accel:.2f} ({z_to_100(accel)}/100) | "
            f"İlgi: {interest:.2f} ({z_to_100(interest)}/100)"
        )
        ax.text(bar.get_width() + 0.03, bar.get_y() + bar.get_height() / 2, txt, va="center", fontsize=10)

    note = "Not: Skorlar Z-temellidir; +1 güçlü, +2 çok güçlü. Teorik üst sınır yoktur."
    fig.text(0.01, 0.01, note, fontsize=10, color="#444")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_category_strength(category_df: pd.DataFrame, output_path: Path, title: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if category_df.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "Kategori verisi bulunamadı", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    data = category_df.copy()
    for col in ["getiri_pct_mean", "toplam_deger_delta_sum", "yatirimci_delta_sum", "akim_skor_mean"]:
        s = pd.to_numeric(data[col], errors="coerce")
        std = s.std(ddof=0)
        data[f"{col}_z"] = 0 if std == 0 or pd.isna(std) else (s - s.mean()) / std
    data["strength"] = (
        0.35 * data["getiri_pct_mean_z"]
        + 0.30 * data["toplam_deger_delta_sum_z"]
        + 0.20 * data["yatirimci_delta_sum_z"]
        + 0.15 * data["akim_skor_mean_z"]
    )
    data = data.sort_values("strength", ascending=False).head(12).iloc[::-1]

    fig, ax = plt.subplots(figsize=(13, max(5, len(data) * 0.7)))
    ax.barh(data["kategori_adi"].fillna("-"), data["strength"], color="#0B4F9E")
    ax.set_title(title)
    ax.set_xlabel("Kategori Güç Skoru (Z birleşik)")
    ax.set_ylabel("Kategori")
    fig.tight_layout()
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _fetch_price_norm_series(client: FvtClient, code: str, metric: str, range_value: str) -> pd.DataFrame:
    rows = client.fetch_fund_series(code, metric=metric, range_value=range_value)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    if "x" not in d.columns or "y" not in d.columns:
        return pd.DataFrame()
    d["x"] = pd.to_datetime(d["x"], errors="coerce")
    d["y"] = pd.to_numeric(d["y"], errors="coerce")
    d = d.dropna(subset=["x", "y"]).sort_values("x")
    if d.empty:
        return pd.DataFrame()
    first_val = d["y"].iloc[0]
    if first_val == 0:
        return pd.DataFrame()
    d["norm"] = (d["y"] / first_val) * 100.0
    d["kod"] = code
    return d


def plot_fund_comparison(
    client: FvtClient,
    fund_codes: Iterable[str],
    output_path: Path,
    metric: str = "fiyat",
    range_value: str = "1Y",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    series_rows: List[pd.DataFrame] = []
    accel_markers: List[tuple] = []

    for code in fund_codes:
        d = _fetch_price_norm_series(client, code, metric=metric, range_value=range_value)
        if d.empty:
            continue
        series_rows.append(d)
        e = analyze_price_series(d[["x", "y"]].rename(columns={"x": "x", "y": "y"}).to_dict(orient="records"))
        if e.accel_breakout_date:
            dt = pd.to_datetime(e.accel_breakout_date, errors="coerce")
            m = d[d["x"].dt.date == dt.date()]
            if not m.empty:
                accel_markers.append((code, m["x"].iloc[-1], m["norm"].iloc[-1], e.accel_breakout_z))

    benchmark_client = YahooBenchmarkClient(timeout=20)
    benchmark_series = benchmark_client.fetch_all_norm(range_value=range_value)
    for _, bdf in benchmark_series.items():
        if bdf is not None and not bdf.empty:
            series_rows.append(bdf.copy())

    if not series_rows:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Karşılaştırma verisi bulunamadı", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    fig, ax = plt.subplots(figsize=(14, 7))
    for d in series_rows:
        code = d["kod"].iloc[0]
        is_benchmark = str(code) in {"BIST 100", "Gram Altın"}
        if is_benchmark:
            ax.plot(d["x"], d["norm"], linewidth=2.2, linestyle="--", label=code)
        else:
            ax.plot(d["x"], d["norm"], linewidth=2.1, label=code)

    for code, x, y, z in accel_markers:
        ax.scatter([x], [y], s=80, marker="*", zorder=6)
        ax.annotate(f"{code} ivme", (x, y), textcoords="offset points", xytext=(6, 6), fontsize=9)

    ax.set_title(f"Fon Karşılaştırma ({metric}, {range_value}) - Başlangıç=100")
    ax.set_xlabel("Tarih")
    ax.set_ylabel("Normalize Değer")
    ax.xaxis.set_major_formatter(_DATE_FMT)
    ax.tick_params(axis="x", rotation=35)
    ax.legend(title="Fon", loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    ax.grid(alpha=0.2)

    note = "* Yıldız: Ani ivmelenme/kalkış tespit noktası"
    fig.text(0.01, 0.01, note, fontsize=10, color="#444")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_investor_interest_trend(
    client: FvtClient,
    fund_codes: Iterable[str],
    output_path: Path,
    range_value: str = "1Y",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    interest_chunks: List[pd.DataFrame] = []

    for code in fund_codes:
        rows_inv = client.fetch_fund_series(code, metric="yatirimci", range_value=range_value)
        if not rows_inv:
            continue

        inv = pd.DataFrame(rows_inv)
        if {"x", "y"}.issubset(inv.columns):
            inv["x"] = pd.to_datetime(inv["x"], errors="coerce")
            inv["y"] = pd.to_numeric(inv["y"], errors="coerce")
            inv = inv.dropna(subset=["x", "y"]).sort_values("x")
            if len(inv) >= 3:
                inv["delta"] = inv["y"].diff()
                inv["interest_5d"] = inv["delta"].rolling(5, min_periods=1).mean()
                inv["kod"] = code
                interest_chunks.append(inv[["x", "kod", "interest_5d"]])

    if not interest_chunks:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Yatırımcı ilgisi trend verisi yok", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    fig, ax = plt.subplots(figsize=(14, 7))
    interest = pd.concat(interest_chunks, ignore_index=True)
    for code, g in interest.groupby("kod"):
        ax.plot(g["x"], g["interest_5d"], label=code, linewidth=2)
    ax.set_title("Yatırımcı İlgisi (5 günlük ortalama değişim)")
    ax.set_ylabel("Yatırımcı Değişimi (5g ort.)")
    ax.set_xlabel("Tarih")
    ax.grid(alpha=0.2)
    ax.xaxis.set_major_formatter(_DATE_FMT)
    ax.tick_params(axis="x", rotation=35)
    ax.legend(title="Fon", loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    fig.subplots_adjust(left=0.08, right=0.82, top=0.92, bottom=0.12)
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_portfolio_comparison(
    client: FvtClient,
    holdings_df: pd.DataFrame,
    output_path: Path,
    range_value: str = "1Y",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if holdings_df is None or holdings_df.empty:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Portföy karşılaştırma verisi yok", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    h = holdings_df.copy()
    h["kod"] = h["kod"].astype(str).str.upper()
    if "weight_norm" not in h.columns:
        if "weight_norm_pct" in h.columns:
            h["weight_norm"] = pd.to_numeric(h["weight_norm_pct"], errors="coerce").fillna(0.0) / 100.0
        elif "weight_pct" in h.columns:
            w = pd.to_numeric(h["weight_pct"], errors="coerce").fillna(0.0)
            s = float(w.sum()) if float(w.sum()) > 0 else 1.0
            h["weight_norm"] = w / s
        else:
            h["weight_norm"] = 0.0
    h = h[h["weight_norm"] > 0]
    if h.empty:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Portföy karşılaştırma verisi yok", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    series: List[pd.DataFrame] = []
    for _, row in h.iterrows():
        code = row["kod"]
        d = _fetch_price_norm_series(client, code, metric="fiyat", range_value=range_value)
        if d.empty:
            continue
        d["weight_norm"] = float(row["weight_norm"])
        series.append(d)

    if not series:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, "Portföy karşılaştırma verisi yok", ha="center", va="center")
        ax.axis("off")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    fig, ax = plt.subplots(figsize=(14, 7))
    all_df = pd.concat(series, ignore_index=True)
    for code, g in all_df.groupby("kod"):
        ax.plot(g["x"], g["norm"], linewidth=1.8, alpha=0.85, label=code)

    pivot = all_df.pivot_table(index="x", columns="kod", values="norm", aggfunc="last")
    weights = {str(r["kod"]).upper(): float(r["weight_norm"]) for _, r in h.iterrows()}
    common_cols = [c for c in pivot.columns if c in weights]
    if common_cols:
        w = pd.Series({c: weights[c] for c in common_cols})
        w = w / w.sum()
        port_curve = (pivot[common_cols] * w).sum(axis=1)
        ax.plot(port_curve.index, port_curve.values, color="#111", linewidth=3.1, label="PORTFÖY")

    ax.set_title(f"Portföy Fon Karşılaştırması ({range_value}) - Başlangıç=100")
    ax.set_xlabel("Tarih")
    ax.set_ylabel("Normalize Değer")
    ax.xaxis.set_major_formatter(_DATE_FMT)
    ax.tick_params(axis="x", rotation=35)
    ax.legend(title="Fon", loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return output_path
