from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
import requests


_YAHOO_RANGE_MAP: Dict[str, str] = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "9M": "9mo",
    "1Y": "1y",
}

_GRAM_DIVISOR = 31.1034768  # 1 troy ounce = 31.1034768 gram


@dataclass
class BenchmarkSeries:
    name: str
    df: pd.DataFrame


class YahooBenchmarkClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        self._warmed = False

    def _warmup(self) -> None:
        if self._warmed:
            return
        self.session.get(
            "https://finance.yahoo.com/",
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        self._warmed = True

    def _map_range(self, range_value: str) -> str:
        return _YAHOO_RANGE_MAP.get((range_value or "").upper(), "1y")

    def _fetch_symbol_close(self, symbol: str, range_value: str) -> pd.DataFrame:
        self._warmup()
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"range": self._map_range(range_value), "interval": "1d"}
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://finance.yahoo.com/",
            "Accept": "application/json, text/plain, */*",
        }
        res = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        res.raise_for_status()
        payload = res.json()
        result = ((payload or {}).get("chart") or {}).get("result") or []
        if not result:
            return pd.DataFrame()
        first = result[0] or {}
        ts = first.get("timestamp") or []
        quote = (((first.get("indicators") or {}).get("quote") or [{}])[0] or {})
        close = quote.get("close") or []
        if not ts or not close:
            return pd.DataFrame()

        n = min(len(ts), len(close))
        d = pd.DataFrame(
            {
                "x": pd.to_datetime(ts[:n], unit="s", errors="coerce"),
                "y": pd.to_numeric(close[:n], errors="coerce"),
            }
        )
        d = d.dropna(subset=["x", "y"]).sort_values("x")
        if d.empty:
            return pd.DataFrame()
        d["date"] = d["x"].dt.date
        return d

    @staticmethod
    def _normalize(df: pd.DataFrame, name: str) -> pd.DataFrame:
        if df.empty or "y" not in df.columns:
            return pd.DataFrame()
        d = df.copy().sort_values("x")
        first = float(d["y"].iloc[0])
        if first == 0:
            return pd.DataFrame()
        d["norm"] = (d["y"] / first) * 100.0
        d["kod"] = name
        return d

    def fetch_bist100_norm(self, range_value: str) -> pd.DataFrame:
        d = self._fetch_symbol_close("XU100.IS", range_value=range_value)
        return self._normalize(d, "BIST 100")

    def fetch_gram_altin_norm(self, range_value: str) -> pd.DataFrame:
        # Gram Altin TRY ~= (COMEX Gold USD/ons * USDTRY) / 31.1034768
        gold = self._fetch_symbol_close("GC=F", range_value=range_value)
        usdtry = self._fetch_symbol_close("TRY=X", range_value=range_value)
        if gold.empty or usdtry.empty:
            return pd.DataFrame()

        g = gold[["date", "x", "y"]].rename(columns={"y": "gold_usd_oz"})
        f = usdtry[["date", "y"]].rename(columns={"y": "usdtry"})
        m = pd.merge(g, f, on="date", how="inner")
        if m.empty:
            return pd.DataFrame()
        m["y"] = (pd.to_numeric(m["gold_usd_oz"], errors="coerce") * pd.to_numeric(m["usdtry"], errors="coerce")) / _GRAM_DIVISOR
        m = m.dropna(subset=["x", "y"]).sort_values("x")
        if m.empty:
            return pd.DataFrame()
        return self._normalize(m[["x", "y"]], "Gram Altın")

    def fetch_all_norm(self, range_value: str) -> Dict[str, pd.DataFrame]:
        out: Dict[str, pd.DataFrame] = {}
        try:
            b = self.fetch_bist100_norm(range_value)
            if not b.empty:
                out["BIST 100"] = b
        except Exception:
            pass
        try:
            g = self.fetch_gram_altin_norm(range_value)
            if not g.empty:
                out["Gram Altın"] = g
        except Exception:
            pass
        return out

