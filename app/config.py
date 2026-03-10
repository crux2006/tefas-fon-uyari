from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv


def _split_csv(value: str) -> List[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    reports_dir: Path
    db_path: Path
    fund_type: str
    periods: List[str]
    lookback_days: int
    min_history_points: int
    top_n_alerts: int
    min_signal_score: float
    min_interest_score: float
    min_acceleration: float
    katilim_only: bool
    telegram_bot_token: str
    telegram_chat_id: str
    send_telegram: bool
    chart_compare_range: str
    chart_compare_ranges: List[str]
    chart_compare_metric: str
    excluded_categories: List[str]
    enable_trend_quality_filter: bool
    trend_quality_override_score: float


def load_settings() -> Settings:
    load_dotenv()
    base_dir = Path(os.getenv("BASE_DIR", ".")).resolve()
    data_dir = Path(os.getenv("DATA_DIR", base_dir / "data")).resolve()
    reports_dir = Path(os.getenv("REPORTS_DIR", base_dir / "reports")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    periods = _split_csv(os.getenv("PERIODS", "gunluk,haftalik,aylik"))
    if not periods:
        periods = ["gunluk", "haftalik", "aylik"]
    compare_ranges = _split_csv(os.getenv("CHART_COMPARE_RANGES", "1M,3M,6M,9M,1Y"))
    if not compare_ranges:
        compare_ranges = ["1M", "3M", "6M", "9M", "1Y"]
    excluded_categories = _split_csv(os.getenv("EXCLUDED_CATEGORIES", "Para Piyasası Fonları"))

    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        reports_dir=reports_dir,
        db_path=Path(os.getenv("DB_PATH", data_dir / "fund_alerts.sqlite")).resolve(),
        fund_type=os.getenv("FUND_TYPE", "yatirim").strip(),
        periods=periods,
        lookback_days=_to_int(os.getenv("LOOKBACK_DAYS"), 60),
        min_history_points=_to_int(os.getenv("MIN_HISTORY_POINTS"), 10),
        top_n_alerts=_to_int(os.getenv("TOP_N_ALERTS"), 10),
        min_signal_score=_to_float(os.getenv("MIN_SIGNAL_SCORE"), 0.9),
        min_interest_score=_to_float(os.getenv("MIN_INTEREST_SCORE"), 0.6),
        min_acceleration=_to_float(os.getenv("MIN_ACCELERATION"), 0.15),
        katilim_only=_to_bool(os.getenv("KATILIM_ONLY"), False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        send_telegram=_to_bool(os.getenv("SEND_TELEGRAM"), True),
        chart_compare_range=os.getenv("CHART_COMPARE_RANGE", "1Y").strip(),
        chart_compare_ranges=compare_ranges,
        chart_compare_metric=os.getenv("CHART_COMPARE_METRIC", "fiyat").strip(),
        excluded_categories=excluded_categories,
        enable_trend_quality_filter=_to_bool(os.getenv("ENABLE_TREND_QUALITY_FILTER"), True),
        trend_quality_override_score=_to_float(os.getenv("TREND_QUALITY_OVERRIDE_SCORE"), 2.0),
    )
