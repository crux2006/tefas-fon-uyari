from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from app.charts import (
    plot_category_strength,
    plot_fund_comparison,
    plot_investor_interest_trend,
    plot_portfolio_comparison,
    plot_top_signals,
)
from app.config import Settings
from app.enrichment import analyze_price_series
from app.fvt_client import FvtClient
from app.interactive_report import generate_interactive_report
from app.portfolio import analyze_portfolio
from app.reporting import TelegramReporter, build_report_text
from app.signals import compute_signals
from app.storage import Storage


@dataclass
class PipelineResult:
    report_text: str
    report_dir: Path
    chart_paths: List[Path]
    interactive_html_path: Path
    per_period_signals: Dict[str, pd.DataFrame]


class FundAlertPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = FvtClient()
        self.storage = Storage(settings.db_path)
        self.reporter = TelegramReporter(settings.telegram_bot_token, settings.telegram_chat_id)
        self._excluded = {x.strip().lower() for x in settings.excluded_categories if x.strip()}

    def _snapshot_date_from_summary(self, summary_payload: dict) -> str:
        data = summary_payload.get("data") if isinstance(summary_payload, dict) else None
        if isinstance(data, dict):
            end_date = data.get("end_date")
            if end_date:
                return str(end_date)
        return datetime.utcnow().date().isoformat()

    def _filter_excluded_categories(self, items: List[dict]) -> List[dict]:
        if not self._excluded:
            return items
        out = []
        for item in items:
            cat = str(item.get("kategori_adi") or "").strip().lower()
            if any(ex in cat for ex in self._excluded):
                continue
            out.append(item)
        return out

    def _enrich_signals_with_period_returns(
        self,
        per_period_signals: Dict[str, pd.DataFrame],
        per_period_snapshot: Dict[str, pd.DataFrame],
    ) -> None:
        ret_maps: Dict[str, Dict[str, float]] = {}
        for p, sdf in per_period_snapshot.items():
            if sdf is None or sdf.empty:
                ret_maps[p] = {}
            else:
                tmp = sdf[["kod", "getiri_pct"]].copy()
                tmp["getiri_pct"] = pd.to_numeric(tmp["getiri_pct"], errors="coerce")
                ret_maps[p] = dict(zip(tmp["kod"], tmp["getiri_pct"]))

        for _, sig in per_period_signals.items():
            if sig is None or sig.empty:
                continue
            sig["getiri_gunluk_pct"] = sig["kod"].map(ret_maps.get("gunluk", {}))
            sig["getiri_haftalik_pct"] = sig["kod"].map(ret_maps.get("haftalik", {}))
            sig["getiri_aylik_pct"] = sig["kod"].map(ret_maps.get("aylik", {}))

    def _enrich_signals_with_price_stats(self, per_period_signals: Dict[str, pd.DataFrame]) -> None:
        all_codes = sorted(
            {
                code
                for df in per_period_signals.values()
                if df is not None and not df.empty
                for code in df["kod"].tolist()
            }
        )
        cache = {}
        for code in all_codes:
            rows = self.client.fetch_fund_series(code, metric="fiyat", range_value="1Y")
            cache[code] = analyze_price_series(rows)

        for _, sig in per_period_signals.items():
            if sig is None or sig.empty:
                continue
            sig["return_5d_avg_pct"] = sig["kod"].map(lambda k: cache[k].return_5d_avg_pct if k in cache else None)
            sig["return_hist_avg_pct"] = sig["kod"].map(lambda k: cache[k].return_hist_avg_pct if k in cache else None)
            sig["return_gap_pct"] = sig["kod"].map(lambda k: cache[k].return_gap_pct if k in cache else None)
            sig["max_drawdown_pct"] = sig["kod"].map(lambda k: cache[k].max_drawdown_pct if k in cache else None)
            sig["accel_breakout_date"] = sig["kod"].map(lambda k: cache[k].accel_breakout_date if k in cache else None)
            sig["accel_breakout_z"] = sig["kod"].map(lambda k: cache[k].accel_breakout_z if k in cache else None)

            def enrich_reason(row):
                r = str(row.get("reasons") or "")
                if pd.notna(row.get("accel_breakout_z")) and float(row.get("accel_breakout_z")) >= 1.5:
                    tag = "ani_kalkis_tespit"
                    if tag not in r:
                        r = (r + ", " + tag).strip(", ")
                if pd.notna(row.get("return_gap_pct")) and float(row.get("return_gap_pct")) >= 0.35:
                    tag2 = "getiri_gecmis_ortalama_ustu"
                    if tag2 not in r:
                        r = (r + ", " + tag2).strip(", ")
                return r

            sig["reasons"] = sig.apply(enrich_reason, axis=1)

    def _apply_trend_quality_filter(self, per_period_signals: Dict[str, pd.DataFrame]) -> None:
        if not self.settings.enable_trend_quality_filter:
            return

        ret_col_by_period = {
            "gunluk": "getiri_gunluk_pct",
            "haftalik": "getiri_haftalik_pct",
            "aylik": "getiri_aylik_pct",
        }

        for period, sig in list(per_period_signals.items()):
            if sig is None or sig.empty:
                continue

            ret_col = ret_col_by_period.get(period, "getiri_gunluk_pct")
            working = sig.copy()
            for col in [ret_col, "return_5d_avg_pct", "return_gap_pct", "signal_score"]:
                working[col] = pd.to_numeric(working[col], errors="coerce").fillna(0.0)

            weak_trend = (
                (working[ret_col] <= 0.0)
                & (working["return_5d_avg_pct"] <= 0.0)
                & (working["return_gap_pct"] <= 0.0)
                & (working["signal_score"] < float(self.settings.trend_quality_override_score))
            )
            filtered = working.loc[~weak_trend].copy()
            filtered = filtered.sort_values(
                ["signal_score", "interest_score", "acceleration"],
                ascending=[False, False, False],
            ).head(self.settings.top_n_alerts)
            per_period_signals[period] = filtered.reset_index(drop=True)

    def run(self, send_telegram_override: bool | None = None) -> PipelineResult:
        run_time = datetime.now()
        report_dir = self.settings.reports_dir / run_time.strftime("%Y%m%d_%H%M%S")
        report_dir.mkdir(parents=True, exist_ok=True)

        per_period_signals: Dict[str, pd.DataFrame] = {}
        per_period_snapshot: Dict[str, pd.DataFrame] = {}
        snapshot_dates: Dict[str, str] = {}
        category_df = pd.DataFrame()
        category_period_label = "Günlük"

        for period in self.settings.periods:
            summary = self.client.fetch_summary(
                period=period,
                fund_type=self.settings.fund_type,
                katilim_only=self.settings.katilim_only,
            )
            snapshot_date = self._snapshot_date_from_summary(summary)
            snapshot_dates[period] = snapshot_date

            items = self.client.fetch_all_funds(
                period=period,
                fund_type=self.settings.fund_type,
                katilim_only=self.settings.katilim_only,
                page_size=250,
            )
            items = self._filter_excluded_categories(items)

            current_df = self.storage.upsert_fund_snapshots(
                snapshot_date=snapshot_date,
                period=period,
                fund_type=self.settings.fund_type,
                items=items,
            )
            per_period_snapshot[period] = current_df

            category_current = self.storage.upsert_category_snapshots(
                snapshot_date=snapshot_date,
                period=period,
                fund_type=self.settings.fund_type,
                fund_df=current_df,
            )
            if period == "gunluk":
                category_df = category_current.copy()
                category_period_label = "Günlük"

            history_df = self.storage.get_fund_history(
                period=period,
                fund_type=self.settings.fund_type,
                lookback_days=self.settings.lookback_days,
            )
            signal_df = compute_signals(
                latest_df=current_df,
                history_df=history_df,
                lookback_days=self.settings.lookback_days,
                min_history_points=self.settings.min_history_points,
                min_signal_score=self.settings.min_signal_score,
                min_interest_score=self.settings.min_interest_score,
                min_acceleration=self.settings.min_acceleration,
                top_n=max(self.settings.top_n_alerts * 3, self.settings.top_n_alerts),
            )
            per_period_signals[period] = signal_df

        self._enrich_signals_with_period_returns(per_period_signals, per_period_snapshot)
        self._enrich_signals_with_price_stats(per_period_signals)
        self._apply_trend_quality_filter(per_period_signals)

        for period, sig in per_period_signals.items():
            snap = snapshot_dates.get(period)
            if snap:
                self.storage.clear_signals_for_snapshot(snap, period, self.settings.fund_type)
            self.storage.save_signals(sig)

        portfolio_state = self.storage.get_portfolio()
        portfolio_result = analyze_portfolio(
            client=self.client,
            holdings_df=portfolio_state.get("holdings"),
            total_tl=float(portfolio_state.get("total_tl") or 0),
            per_period_snapshot=per_period_snapshot,
            daily_signals=per_period_signals.get("gunluk", pd.DataFrame()),
        )

        chart_paths: List[Path] = []
        for period, signals_df in per_period_signals.items():
            p = report_dir / f"top_signals_{period}.png"
            chart_paths.append(plot_top_signals(signals_df, p, f"Top Sinyaller - {period.upper()}"))

        category_chart = report_dir / "category_strength_gunluk.png"
        chart_paths.append(plot_category_strength(category_df, category_chart, "Kategori Güç Sıralaması - GÜNLÜK"))

        top_codes: List[str] = []
        if "gunluk" in per_period_signals and not per_period_signals["gunluk"].empty:
            top_codes = per_period_signals["gunluk"]["kod"].head(6).tolist()
        elif per_period_signals:
            for df in per_period_signals.values():
                if not df.empty:
                    top_codes = df["kod"].head(6).tolist()
                    break

        for range_value in self.settings.chart_compare_ranges:
            compare_chart = report_dir / f"fund_compare_{range_value}.png"
            chart_paths.append(
                plot_fund_comparison(
                    client=self.client,
                    fund_codes=top_codes,
                    output_path=compare_chart,
                    metric=self.settings.chart_compare_metric,
                    range_value=range_value,
                )
            )

        interest_chart = report_dir / "investor_interest_trend.png"
        chart_paths.append(
            plot_investor_interest_trend(
                client=self.client,
                fund_codes=top_codes,
                output_path=interest_chart,
                range_value="1Y",
            )
        )

        portfolio_chart = report_dir / "portfolio_compare_1Y.png"
        chart_paths.append(
            plot_portfolio_comparison(
                client=self.client,
                holdings_df=portfolio_result.portfolio_df,
                output_path=portfolio_chart,
                range_value="1Y",
            )
        )

        report_text = build_report_text(
            run_time=run_time,
            per_period_signals=per_period_signals,
            category_df=category_df,
            category_period_label=category_period_label,
            portfolio_df=portfolio_result.portfolio_df,
            portfolio_suggestions_df=portfolio_result.suggestions_df,
            portfolio_summary=portfolio_result.summary,
        )
        report_txt_path = report_dir / "report.txt"
        report_txt_path.write_text(report_text, encoding="utf-8")

        interactive_html_path = report_dir / "interactive_report.html"
        generate_interactive_report(
            output_path=interactive_html_path,
            run_time=run_time,
            per_period_signals=per_period_signals,
            top_codes=top_codes,
            client=self.client,
            compare_metric=self.settings.chart_compare_metric,
            compare_ranges=self.settings.chart_compare_ranges,
            per_period_snapshot=per_period_snapshot,
            portfolio_df=portfolio_result.portfolio_df,
            portfolio_suggestions_df=portfolio_result.suggestions_df,
            portfolio_total_tl=float(portfolio_state.get("total_tl") or 0),
        )

        should_send = self.settings.send_telegram if send_telegram_override is None else send_telegram_override
        if should_send and self.reporter.enabled:
            self.reporter.send_text(report_text)
            for idx, chart in enumerate(chart_paths):
                caption = f"Grafik {idx + 1}/{len(chart_paths)} - {chart.name}"
                self.reporter.send_photo(chart, caption=caption)
            self.reporter.send_document(interactive_html_path, caption="İnteraktif HTML rapor")
            self.reporter.send_document(report_txt_path, caption="Metin raporu")

        return PipelineResult(
            report_text=report_text,
            report_dir=report_dir,
            chart_paths=chart_paths,
            interactive_html_path=interactive_html_path,
            per_period_signals=per_period_signals,
        )
