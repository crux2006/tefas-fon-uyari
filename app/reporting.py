from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

from app.scoring import z_band_label, z_to_100


def _fmt_num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_report_text(
    run_time: datetime,
    per_period_signals: Dict[str, pd.DataFrame],
    category_df: pd.DataFrame,
    category_period_label: str = "Günlük",
    portfolio_df: pd.DataFrame | None = None,
    portfolio_suggestions_df: pd.DataFrame | None = None,
    portfolio_summary: dict | None = None,
) -> str:
    lines: List[str] = []
    lines.append("FVT Fon Alarm Raporu")
    lines.append(f"Tarih: {run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Skor/İlgi/İvme: Z-skoru tabanlıdır (teorik üst sınır yok).")
    lines.append("Yorum kolaylığı için 0-100 ölçeği de verilir (normal dağılım yüzdelik karşılığı).")
    lines.append("")

    if category_df is not None and not category_df.empty:
        top_cat = category_df.sort_values("toplam_deger_delta_sum", ascending=False).head(5)
        lines.append(f"Kategori Özeti ({category_period_label} Nakit Akımı):")
        for _, row in top_cat.iterrows():
            lines.append(
                f"- {row.get('kategori_adi','-')}: "
                f"Nakit={_fmt_num(row.get('toplam_deger_delta_sum'),0)}, "
                f"Yatırımcı={_fmt_num(row.get('yatirimci_delta_sum'),0)}, "
                f"GetiriOrt={_fmt_num(row.get('getiri_pct_mean'),2)}%"
            )
        lines.append("")

    for period, df in per_period_signals.items():
        lines.append(f"Top Sinyaller - {period.upper()}")
        if df is None or df.empty:
            lines.append("- Sinyal bulunamadı.")
            lines.append("")
            continue

        lines.append("Ölçek Notu: +1 güçlü, +2 çok güçlü sinyal kabul edilir.")
        for idx, row in df.iterrows():
            lines.append("-" * 62)
            s = float(row.get("signal_score", 0))
            i = float(row.get("interest_score", 0))
            a = float(row.get("acceleration", 0))
            lines.append(
                f"{idx + 1}. {row.get('kod')} | {row.get('kategori_adi','-')} | "
                f"Skor(Z)={_fmt_num(s)} ({z_to_100(s)}/100, {z_band_label(s)}) | "
                f"İlgi(Z)={_fmt_num(i)} ({z_to_100(i)}/100, {z_band_label(i)}) | "
                f"İvme(Z)={_fmt_num(a)} ({z_to_100(a)}/100, {z_band_label(a)})"
            )

            lines.append(
                "   "
                f"Getiri G/H/A: {_fmt_num(row.get('getiri_gunluk_pct'))}% / "
                f"{_fmt_num(row.get('getiri_haftalik_pct'))}% / "
                f"{_fmt_num(row.get('getiri_aylik_pct'))}%"
            )
            lines.append(
                "   "
                f"5g Getiri Ort: {_fmt_num(row.get('return_5d_avg_pct'))}% | "
                f"Geçmiş Ort: {_fmt_num(row.get('return_hist_avg_pct'))}% | "
                f"Fark: {_fmt_num(row.get('return_gap_pct'))}% | "
                f"Max Drawdown(1Y): {_fmt_num(row.get('max_drawdown_pct'))}%"
            )
            if pd.notna(row.get("accel_breakout_date")):
                lines.append(
                    "   "
                    f"Ani kalkış tarihi: {row.get('accel_breakout_date')} "
                    f"(Z={_fmt_num(row.get('accel_breakout_z'))})"
                )
            lines.append(f"   Neden: {row.get('reasons','-')}")
            lines.append("")
        lines.append("")

    if portfolio_df is not None and not portfolio_df.empty:
        lines.append("Portföy Analizi")
        lines.append("-" * 62)
        if portfolio_summary:
            lines.append(
                f"Toplam Portföy (TL): {_fmt_num(portfolio_summary.get('total_tl'),2)} | "
                f"Fon Sayısı: {portfolio_summary.get('count')}"
            )
            lines.append(
                f"Portföy Ortalama Getiri G/H/A: "
                f"{_fmt_num(portfolio_summary.get('avg_daily_return'))}% / "
                f"{_fmt_num(portfolio_summary.get('avg_weekly_return'))}% / "
                f"{_fmt_num(portfolio_summary.get('avg_monthly_return'))}%"
            )
            lines.append("")

        for idx, row in portfolio_df.iterrows():
            lines.append("-" * 62)
            lines.append(
                f"{idx + 1}. {row.get('kod')} | Ağırlık: {_fmt_num(row.get('weight_norm_pct'),2)}% | "
                f"Tutar: {_fmt_num(row.get('amount_tl'),2)} TL | Durum: {row.get('health_status')}"
            )
            lines.append(
                f"   Getiri G/H/A: {_fmt_num(row.get('getiri_gunluk_pct'))}% / "
                f"{_fmt_num(row.get('getiri_haftalik_pct'))}% / "
                f"{_fmt_num(row.get('getiri_aylik_pct'))}%"
            )
            lines.append(
                f"   5g Ort / Geçmiş Ort / Fark: {_fmt_num(row.get('return_5d_avg_pct'))}% / "
                f"{_fmt_num(row.get('return_hist_avg_pct'))}% / {_fmt_num(row.get('return_gap_pct'))}%"
            )
            lines.append(
                f"   Max Drawdown(1Y): {_fmt_num(row.get('max_drawdown_pct'))}% | "
                f"Yatırımcı Delta: {_fmt_num(row.get('yatirimci_delta'),0)}"
            )
            if pd.notna(row.get("accel_breakout_date")):
                lines.append(
                    f"   Ani kalkış: {row.get('accel_breakout_date')} (Z={_fmt_num(row.get('accel_breakout_z'))})"
                )
            lines.append(f"   Not: {row.get('reasons','-')}")
            lines.append("")
        lines.append("")

        if portfolio_suggestions_df is not None and not portfolio_suggestions_df.empty:
            lines.append("Portföyde Olmayan Öneri Fonlar")
            for idx, row in portfolio_suggestions_df.iterrows():
                lines.append(
                    f"- {idx + 1}) {row.get('kod')} | {row.get('kategori_adi','-')} | "
                    f"Skor={_fmt_num(row.get('signal_score'))} | İlgi={_fmt_num(row.get('interest_score'))} | "
                    f"İvme={_fmt_num(row.get('acceleration'))}"
                )
            lines.append("")

    lines.append("Not: Bu rapor yatırım tavsiyesi değildir; sinyal amaçlıdır.")
    return "\n".join(lines)


class TelegramReporter:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 20):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def send_text(self, text: str) -> None:
        if not self.enabled:
            return
        max_len = 3900
        chunks = [text[i : i + max_len] for i in range(0, len(text), max_len)]
        for chunk in chunks:
            res = requests.post(
                self._url("sendMessage"),
                data={"chat_id": self.chat_id, "text": chunk},
                timeout=self.timeout,
            )
            res.raise_for_status()

    def send_photo(self, photo_path: Path, caption: str = "") -> None:
        if not self.enabled:
            return
        with photo_path.open("rb") as f:
            res = requests.post(
                self._url("sendPhoto"),
                data={"chat_id": self.chat_id, "caption": caption[:1000]},
                files={"photo": f},
                timeout=self.timeout,
            )
        res.raise_for_status()

    def send_document(self, doc_path: Path, caption: str = "") -> None:
        if not self.enabled:
            return
        with doc_path.open("rb") as f:
            res = requests.post(
                self._url("sendDocument"),
                data={"chat_id": self.chat_id, "caption": caption[:1000]},
                files={"document": f},
                timeout=self.timeout,
            )
        res.raise_for_status()
