from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fund_snapshots (
                    snapshot_date TEXT NOT NULL,
                    period TEXT NOT NULL,
                    fund_type TEXT NOT NULL,
                    kod TEXT NOT NULL,
                    fon_adi TEXT,
                    kategori_id INTEGER,
                    kategori_adi TEXT,
                    sirket_adi TEXT,
                    getiri_pct REAL,
                    yatirimci_delta REAL,
                    yatirimci_pct REAL,
                    toplam_deger_delta REAL,
                    toplam_deger_pct REAL,
                    pay_adet_delta REAL,
                    pay_adet_pct REAL,
                    doluluk_delta REAL,
                    doluluk_pct REAL,
                    akim_skor REAL,
                    uyum_skor REAL,
                    risk_skor REAL,
                    sharpe REAL,
                    sortino REAL,
                    katilim INTEGER,
                    raw_json TEXT,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (snapshot_date, period, fund_type, kod)
                );

                CREATE TABLE IF NOT EXISTS category_snapshots (
                    snapshot_date TEXT NOT NULL,
                    period TEXT NOT NULL,
                    fund_type TEXT NOT NULL,
                    kategori_id INTEGER NOT NULL,
                    kategori_adi TEXT,
                    fund_count INTEGER,
                    getiri_pct_mean REAL,
                    yatirimci_delta_sum REAL,
                    toplam_deger_delta_sum REAL,
                    akim_skor_mean REAL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (snapshot_date, period, fund_type, kategori_id)
                );

                CREATE TABLE IF NOT EXISTS signals (
                    snapshot_date TEXT NOT NULL,
                    period TEXT NOT NULL,
                    fund_type TEXT NOT NULL,
                    kod TEXT NOT NULL,
                    fon_adi TEXT,
                    kategori_id INTEGER,
                    kategori_adi TEXT,
                    signal_score REAL,
                    interest_score REAL,
                    acceleration REAL,
                    category_strength REAL,
                    reasons TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (snapshot_date, period, fund_type, kod)
                );

                CREATE TABLE IF NOT EXISTS portfolio_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_tl REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS portfolio_holdings (
                    kod TEXT PRIMARY KEY,
                    weight_pct REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _to_float(value):
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def upsert_fund_snapshots(
        self,
        snapshot_date: str,
        period: str,
        fund_type: str,
        items: List[dict],
    ) -> pd.DataFrame:
        fetched_at = datetime.utcnow().isoformat(timespec="seconds")
        rows = []
        for item in items:
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "period": period,
                    "fund_type": fund_type,
                    "kod": item.get("kod"),
                    "fon_adi": item.get("fon_adi"),
                    "kategori_id": self._to_int(item.get("kategori_id")),
                    "kategori_adi": item.get("kategori_adi"),
                    "sirket_adi": item.get("sirket_adi"),
                    "getiri_pct": self._to_float(item.get("getiri_pct")),
                    "yatirimci_delta": self._to_float(item.get("yatirimci_delta")),
                    "yatirimci_pct": self._to_float(item.get("yatirimci_pct")),
                    "toplam_deger_delta": self._to_float(item.get("toplam_deger_delta")),
                    "toplam_deger_pct": self._to_float(item.get("toplam_deger_pct")),
                    "pay_adet_delta": self._to_float(item.get("pay_adet_delta")),
                    "pay_adet_pct": self._to_float(item.get("pay_adet_pct")),
                    "doluluk_delta": self._to_float(item.get("doluluk_delta")),
                    "doluluk_pct": self._to_float(item.get("doluluk_pct")),
                    "akim_skor": self._to_float(item.get("akim_skor")),
                    "uyum_skor": self._to_float(item.get("uyum_skor")),
                    "risk_skor": self._to_float(item.get("risk_skor")),
                    "sharpe": self._to_float(item.get("sharpe")),
                    "sortino": self._to_float(item.get("sortino")),
                    "katilim": self._to_int(item.get("katilim")),
                    "raw_json": json.dumps(item, ensure_ascii=False),
                    "fetched_at": fetched_at,
                }
            )

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        sql = """
            INSERT OR REPLACE INTO fund_snapshots (
                snapshot_date, period, fund_type, kod, fon_adi, kategori_id, kategori_adi, sirket_adi,
                getiri_pct, yatirimci_delta, yatirimci_pct, toplam_deger_delta, toplam_deger_pct,
                pay_adet_delta, pay_adet_pct, doluluk_delta, doluluk_pct, akim_skor, uyum_skor, risk_skor,
                sharpe, sortino, katilim, raw_json, fetched_at
            ) VALUES (
                :snapshot_date, :period, :fund_type, :kod, :fon_adi, :kategori_id, :kategori_adi, :sirket_adi,
                :getiri_pct, :yatirimci_delta, :yatirimci_pct, :toplam_deger_delta, :toplam_deger_pct,
                :pay_adet_delta, :pay_adet_pct, :doluluk_delta, :doluluk_pct, :akim_skor, :uyum_skor, :risk_skor,
                :sharpe, :sortino, :katilim, :raw_json, :fetched_at
            );
        """
        with self._connect() as conn:
            conn.executemany(sql, df.to_dict(orient="records"))
        return df

    def upsert_category_snapshots(
        self,
        snapshot_date: str,
        period: str,
        fund_type: str,
        fund_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if fund_df.empty:
            return pd.DataFrame()
        fetched_at = datetime.utcnow().isoformat(timespec="seconds")
        agg = (
            fund_df.groupby(["kategori_id", "kategori_adi"], dropna=False)
            .agg(
                fund_count=("kod", "count"),
                getiri_pct_mean=("getiri_pct", "mean"),
                yatirimci_delta_sum=("yatirimci_delta", "sum"),
                toplam_deger_delta_sum=("toplam_deger_delta", "sum"),
                akim_skor_mean=("akim_skor", "mean"),
            )
            .reset_index()
        )
        agg["snapshot_date"] = snapshot_date
        agg["period"] = period
        agg["fund_type"] = fund_type
        agg["fetched_at"] = fetched_at
        agg["kategori_id"] = agg["kategori_id"].fillna(-1).astype(int)
        cols = [
            "snapshot_date",
            "period",
            "fund_type",
            "kategori_id",
            "kategori_adi",
            "fund_count",
            "getiri_pct_mean",
            "yatirimci_delta_sum",
            "toplam_deger_delta_sum",
            "akim_skor_mean",
            "fetched_at",
        ]
        agg = agg[cols]
        sql = """
            INSERT OR REPLACE INTO category_snapshots (
                snapshot_date, period, fund_type, kategori_id, kategori_adi, fund_count,
                getiri_pct_mean, yatirimci_delta_sum, toplam_deger_delta_sum, akim_skor_mean, fetched_at
            ) VALUES (
                :snapshot_date, :period, :fund_type, :kategori_id, :kategori_adi, :fund_count,
                :getiri_pct_mean, :yatirimci_delta_sum, :toplam_deger_delta_sum, :akim_skor_mean, :fetched_at
            );
        """
        with self._connect() as conn:
            conn.executemany(sql, agg.to_dict(orient="records"))
        return agg

    def get_fund_history(self, period: str, fund_type: str, lookback_days: int) -> pd.DataFrame:
        start_date = (datetime.utcnow().date() - timedelta(days=lookback_days)).isoformat()
        query = """
            SELECT *
            FROM fund_snapshots
            WHERE period = ?
              AND fund_type = ?
              AND snapshot_date >= ?
            ORDER BY snapshot_date, kod;
        """
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=[period, fund_type, start_date])

    def get_category_latest(self, snapshot_date: str, period: str, fund_type: str) -> pd.DataFrame:
        query = """
            SELECT *
            FROM category_snapshots
            WHERE snapshot_date = ?
              AND period = ?
              AND fund_type = ?
            ORDER BY toplam_deger_delta_sum DESC;
        """
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=[snapshot_date, period, fund_type])

    def save_signals(self, signal_df: pd.DataFrame) -> None:
        if signal_df.empty:
            return
        created_at = datetime.utcnow().isoformat(timespec="seconds")
        df = signal_df.copy()
        df["created_at"] = created_at
        sql = """
            INSERT OR REPLACE INTO signals (
                snapshot_date, period, fund_type, kod, fon_adi, kategori_id, kategori_adi,
                signal_score, interest_score, acceleration, category_strength, reasons, details_json, created_at
            ) VALUES (
                :snapshot_date, :period, :fund_type, :kod, :fon_adi, :kategori_id, :kategori_adi,
                :signal_score, :interest_score, :acceleration, :category_strength, :reasons, :details_json, :created_at
            );
        """
        with self._connect() as conn:
            conn.executemany(sql, df.to_dict(orient="records"))

    def clear_signals_for_snapshot(self, snapshot_date: str, period: str, fund_type: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM signals
                WHERE snapshot_date = ?
                  AND period = ?
                  AND fund_type = ?;
                """,
                (snapshot_date, period, fund_type),
            )

    def get_latest_signals(self, snapshot_date: str, fund_type: str) -> pd.DataFrame:
        query = """
            SELECT *
            FROM signals
            WHERE snapshot_date = ?
              AND fund_type = ?
            ORDER BY period, signal_score DESC;
        """
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=[snapshot_date, fund_type])

    def get_recent_metric_history(
        self,
        period: str,
        fund_type: str,
        codes: Iterable[str],
        metric: str,
        days: int = 45,
    ) -> pd.DataFrame:
        codes = list(codes)
        if not codes:
            return pd.DataFrame()
        start_date = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
        placeholders = ",".join("?" * len(codes))
        query = f"""
            SELECT snapshot_date, kod, fon_adi, {metric} AS metric_value
            FROM fund_snapshots
            WHERE period = ?
              AND fund_type = ?
              AND snapshot_date >= ?
              AND kod IN ({placeholders})
            ORDER BY snapshot_date, kod;
        """
        params = [period, fund_type, start_date, *codes]
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_portfolio(self) -> dict:
        with self._connect() as conn:
            settings = conn.execute("SELECT total_tl, updated_at FROM portfolio_settings WHERE id = 1").fetchone()
            holdings = pd.read_sql_query(
                "SELECT kod, weight_pct, updated_at FROM portfolio_holdings ORDER BY weight_pct DESC, kod ASC",
                conn,
            )
        total_tl = float(settings[0]) if settings else 0.0
        updated_at = settings[1] if settings else None
        return {"total_tl": total_tl, "updated_at": updated_at, "holdings": holdings}

    def set_portfolio(self, total_tl: float, holdings: List[dict]) -> None:
        rows = []
        now = datetime.utcnow().isoformat(timespec="seconds")
        for h in holdings:
            kod = str(h.get("kod", "")).strip().upper()
            if not kod:
                continue
            try:
                weight = float(h.get("weight_pct", 0))
            except (TypeError, ValueError):
                continue
            if weight <= 0:
                continue
            rows.append({"kod": kod, "weight_pct": weight, "updated_at": now})

        if len(rows) > 10:
            raise ValueError("Portföyde en fazla 10 fon olabilir.")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_settings (id, total_tl, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    total_tl=excluded.total_tl,
                    updated_at=excluded.updated_at;
                """,
                (float(total_tl), now),
            )
            conn.execute("DELETE FROM portfolio_holdings;")
            if rows:
                conn.executemany(
                    """
                    INSERT INTO portfolio_holdings (kod, weight_pct, updated_at)
                    VALUES (:kod, :weight_pct, :updated_at)
                    """,
                    rows,
                )

    def upsert_portfolio_holding(self, kod: str, weight_pct: float) -> None:
        kod = str(kod).strip().upper()
        if not kod:
            raise ValueError("Fon kodu boş olamaz.")
        if weight_pct <= 0:
            raise ValueError("Ağırlık 0'dan büyük olmalı.")
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM portfolio_holdings").fetchone()[0]
            exists = conn.execute("SELECT 1 FROM portfolio_holdings WHERE kod = ?", (kod,)).fetchone() is not None
            if (not exists) and count >= 10:
                raise ValueError("Portföyde en fazla 10 fon olabilir.")
            conn.execute(
                """
                INSERT INTO portfolio_holdings (kod, weight_pct, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(kod) DO UPDATE SET
                    weight_pct=excluded.weight_pct,
                    updated_at=excluded.updated_at;
                """,
                (kod, float(weight_pct), now),
            )

    def delete_portfolio_holding(self, kod: str) -> None:
        kod = str(kod).strip().upper()
        with self._connect() as conn:
            conn.execute("DELETE FROM portfolio_holdings WHERE kod = ?", (kod,))

    def set_portfolio_total_tl(self, total_tl: float) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_settings (id, total_tl, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    total_tl=excluded.total_tl,
                    updated_at=excluded.updated_at;
                """,
                (float(total_tl), now),
            )
