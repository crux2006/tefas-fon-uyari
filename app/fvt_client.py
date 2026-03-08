from __future__ import annotations

from dataclasses import dataclass
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
                "User-Agent": "Mozilla/5.0 (compatible; FVT-FundAlert/1.0)",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self.base_url}/bir-bakista-fonlar/",
            }
        )

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

    def fetch_summary(self, period: str, fund_type: str, katilim_only: bool = False) -> Dict[str, object]:
        payload = {
            "action": "summary",
            "period": period,
            "type": fund_type,
            "katilim_only": 1 if katilim_only else 0,
        }
        return self._post_form("/fon_metrikler_ajax.php", payload)

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

    def fetch_fund_series(
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

