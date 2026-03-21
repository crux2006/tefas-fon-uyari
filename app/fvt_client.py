from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class FvtClient:
    base_url: str = "https://fvt.com.tr"
    timeout: int = 25

    def __post_init__(self) -> None:
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; FVT-FundAlert/2.0)",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self.base_url}/fonlar/yatirim-fonlari",
            }
        )

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _norm_type(fund_type: str) -> str:
        val = (fund_type or "").strip().lower()
        if val in {"bes", "bireysel"}:
            return "bes"
        if val in {"tum", "all", "hepsi"}:
            return "tum"
        return "yatirim"

    @staticmethod
    def _norm_period(period: str) -> str:
        val = (period or "").strip().lower()
        mapping = {
            "daily": "gunluk",
            "weekly": "haftalik",
            "monthly": "aylik",
            "3m": "3ay",
            "6m": "6ay",
            "1y": "1y",
        }
        return mapping.get(val, val if val else "gunluk")

    @staticmethod
    def _parse_date(value) -> date | None:
        if value is None or value == "":
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            try:
                return datetime.strptime(text[:10], "%Y-%m-%d").date()
            except ValueError:
                return None

    def _post_form(self, path: str, data: Dict[str, object]) -> Dict[str, object]:
        url = f"{self.base_url}{path}"
        res = self.session.post(url, data=data, timeout=self.timeout)
        res.raise_for_status()
        payload = res.json()
        if isinstance(payload, dict):
            return payload
        raise ValueError(f"Unexpected response shape for {url}")

    def _get_json(self, path: str, params: Optional[Dict[str, object]] = None):
        url = f"{self.base_url}{path}"
        res = self.session.get(url, params=params, timeout=self.timeout)
        res.raise_for_status()
        return res.json()

    def _get_overview_payload(self, period: str, fund_type: str, katilim_only: bool) -> Dict[str, object]:
        params: Dict[str, object] = {
            "period": self._norm_period(period),
            "type": self._norm_type(fund_type),
        }
        if katilim_only:
            params["katilim"] = 1
        payload = self._get_json("/api/funds/overview", params=params)
        if not isinstance(payload, dict) or not payload.get("success"):
            raise RuntimeError(f"FVT overview response not ok: {payload}")
        return payload

    @staticmethod
    def _normalize_fund_row(row: Dict[str, object]) -> Dict[str, object]:
        return {
            "kod": row.get("kod"),
            "fon_adi": row.get("fonAdi"),
            "kategori_id": row.get("kategoriId"),
            "kategori_adi": row.get("kategoriAdi"),
            "sirket_adi": row.get("sirketAdi") or row.get("sirketKod"),
            "getiri_pct": row.get("getiriPct"),
            "yatirimci_delta": row.get("yatirimciDelta"),
            "yatirimci_pct": row.get("yatirimciPct"),
            "toplam_deger_delta": row.get("toplamDegerDelta", row.get("nakitDelta")),
            "toplam_deger_pct": row.get("toplamDegerPct"),
            "pay_adet_delta": row.get("payAdetDelta"),
            "pay_adet_pct": row.get("payAdetPct"),
            "doluluk_delta": row.get("dolulukDelta"),
            "doluluk_pct": row.get("dolulukPct"),
            "akim_skor": row.get("akimSkor"),
            "uyum_skor": row.get("uyumSkor"),
            "risk_skor": row.get("riskSkor", row.get("risk")),
            "sharpe": row.get("sharpe"),
            "sortino": row.get("sortino"),
            "katilim": row.get("katilim"),
            "raw": row,
        }

    def fetch_summary(self, period: str, fund_type: str, katilim_only: bool = False) -> Dict[str, object]:
        try:
            payload = self._get_overview_payload(period, fund_type, katilim_only)
            data = payload.get("data") or {}
            end_date = self._parse_date(payload.get("timestamp")) or date.today()
            if isinstance(data, dict):
                data = {**data, "end_date": end_date.isoformat()}
            return {"ok": True, "data": data}
        except Exception:
            legacy = {
                "action": "summary",
                "period": period,
                "type": fund_type,
                "katilim_only": 1 if katilim_only else 0,
            }
            return self._post_form("/fon_metrikler_ajax.php", legacy)

    def _fetch_all_funds_legacy(
        self,
        period: str,
        fund_type: str,
        katilim_only: bool = False,
        sort: str = "akim_skor_desc",
        page_size: int = 200,
        kategori_id: str = "",
        q: str = "",
    ) -> List[Dict[str, object]]:
        all_items: List[Dict[str, object]] = []
        offset = 0
        done = False
        while not done:
            payload = {
                "action": "list",
                "period": period,
                "type": fund_type,
                "katilim_only": 1 if katilim_only else 0,
                "q": q,
                "sort": sort,
                "kategori_id": kategori_id,
                "offset": offset,
                "limit": page_size,
            }
            resp = self._post_form("/fon_metrikler_ajax.php", payload)
            if not resp.get("ok"):
                raise RuntimeError(f"FVT list response not ok: {resp}")
            data = resp.get("data") or {}
            items = data.get("items") or []
            if not isinstance(items, list):
                raise RuntimeError("FVT list payload missing items list")
            all_items.extend(items)
            done = bool(data.get("done"))
            offset = int(data.get("offset", offset)) + len(items)
            if len(items) == 0:
                done = True
        return all_items

    def fetch_all_funds(
        self,
        period: str,
        fund_type: str,
        katilim_only: bool = False,
        sort: str = "akim_skor_desc",
        page_size: int = 200,
        kategori_id: str = "",
        q: str = "",
    ) -> List[Dict[str, object]]:
        try:
            payload = self._get_overview_payload(period, fund_type, katilim_only)
            data = payload.get("data") or {}
            funds = data.get("funds") or []
            if not isinstance(funds, list):
                raise RuntimeError("FVT overview payload missing funds list")

            normalized = [self._normalize_fund_row(row) for row in funds]
            if kategori_id:
                kid = self._to_int(kategori_id)
                if kid is not None:
                    normalized = [r for r in normalized if self._to_int(r.get("kategori_id")) == kid]
            if q:
                ql = q.strip().lower()
                if ql:
                    normalized = [
                        r
                        for r in normalized
                        if ql in str(r.get("kod") or "").lower() or ql in str(r.get("fon_adi") or "").lower()
                    ]
            if sort.strip().lower() == "akim_skor_desc":
                normalized.sort(key=lambda r: self._to_float(r.get("akim_skor")) or float("-inf"), reverse=True)
            return normalized
        except Exception:
            return self._fetch_all_funds_legacy(
                period=period,
                fund_type=fund_type,
                katilim_only=katilim_only,
                sort=sort,
                page_size=page_size,
                kategori_id=kategori_id,
                q=q,
            )

    @staticmethod
    def _shift_months(base: date, month_delta: int) -> date:
        month_idx = base.month - 1 + month_delta
        year = base.year + month_idx // 12
        month = month_idx % 12 + 1
        return date(year, month, 1)

    def _range_to_dates(self, range_value: str) -> Dict[str, str]:
        if not range_value:
            return {}
        text = str(range_value).strip().upper()
        if ":" in text:
            parts = text.split(":", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return {"baslangic": parts[0], "bitis": parts[1]}
        end_dt = date.today()
        if text == "1W":
            start_dt = end_dt - timedelta(days=7)
        elif text == "1M":
            start_dt = self._shift_months(end_dt, -1)
        elif text == "3M":
            start_dt = self._shift_months(end_dt, -3)
        elif text == "6M":
            start_dt = self._shift_months(end_dt, -6)
        elif text == "9M":
            start_dt = self._shift_months(end_dt, -9)
        elif text == "YBB":
            start_dt = date(end_dt.year, 1, 1)
        elif text == "1Y":
            start_dt = self._shift_months(end_dt, -12)
        elif text == "5Y":
            start_dt = self._shift_months(end_dt, -60)
        else:
            return {}
        return {"baslangic": start_dt.isoformat(), "bitis": end_dt.isoformat()}

    @staticmethod
    def _metric_field(metric: str) -> str:
        key = (metric or "").strip().lower()
        mapping = {
            "fiyat": "fiyat",
            "price": "fiyat",
            "yatirimci": "yatirimci",
            "investor": "yatirimci",
            "getiri": "getiri",
            "toplam_deger": "toplamDeger",
            "pay_adet": "payAdet",
            "doluluk": "dolulukOrani",
        }
        return mapping.get(key, "fiyat")

    def _fetch_fund_series_legacy(
        self,
        kod: str,
        metric: str = "fiyat",
        range_value: str = "1Y",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        params: Dict[str, object] = {"kod": kod, "metric": metric}
        if start and end:
            params["start"] = start
            params["end"] = end
        else:
            params["range"] = range_value
        data = self._get_json("/datafon.php", params=params)
        return data if isinstance(data, list) else []

    def fetch_fund_series(
        self,
        kod: str,
        metric: str = "fiyat",
        range_value: str = "1Y",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        try:
            params: Dict[str, object] = {}
            if start and end:
                params["baslangic"] = start
                params["bitis"] = end
            else:
                params.update(self._range_to_dates(range_value))

            payload = self._get_json(f"/api/funds/{str(kod).upper()}/prices", params=params)
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return []

            field = self._metric_field(metric)
            out: List[Dict[str, object]] = []
            for row in rows:
                x = row.get("tarih") if isinstance(row, dict) else None
                y = row.get(field) if isinstance(row, dict) else None
                y_num = self._to_float(y)
                if x and y_num is not None:
                    out.append({"x": x, "y": y_num})
            out.sort(key=lambda r: str(r.get("x")))
            return out
        except Exception:
            return self._fetch_fund_series_legacy(
                kod=kod,
                metric=metric,
                range_value=range_value,
                start=start,
                end=end,
            )
