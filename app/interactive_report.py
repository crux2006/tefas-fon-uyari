from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

from app.benchmarks import YahooBenchmarkClient
from app.enrichment import analyze_price_series
from app.fvt_client import FvtClient
from app.scoring import z_band_label, z_to_100


def _serialize_signals(per_period_signals: Dict[str, pd.DataFrame]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for period, df in per_period_signals.items():
        if df is None or df.empty:
            out[period] = []
            continue
        part = []
        for _, row in df.iterrows():
            s = float(row.get("signal_score", 0))
            i = float(row.get("interest_score", 0))
            a = float(row.get("acceleration", 0))
            part.append(
                {
                    "kod": row.get("kod"),
                    "fon_adi": row.get("fon_adi"),
                    "kategori_adi": row.get("kategori_adi"),
                    "signal_z": round(s, 4),
                    "interest_z": round(i, 4),
                    "accel_z": round(a, 4),
                    "signal_100": z_to_100(s),
                    "interest_100": z_to_100(i),
                    "accel_100": z_to_100(a),
                    "signal_band": z_band_label(s),
                    "interest_band": z_band_label(i),
                    "accel_band": z_band_label(a),
                    "reasons": row.get("reasons"),
                    "getiri_gunluk_pct": row.get("getiri_gunluk_pct"),
                    "getiri_haftalik_pct": row.get("getiri_haftalik_pct"),
                    "getiri_aylik_pct": row.get("getiri_aylik_pct"),
                    "return_5d_avg_pct": row.get("return_5d_avg_pct"),
                    "return_hist_avg_pct": row.get("return_hist_avg_pct"),
                    "return_gap_pct": row.get("return_gap_pct"),
                    "max_drawdown_pct": row.get("max_drawdown_pct"),
                    "accel_breakout_date": row.get("accel_breakout_date"),
                    "accel_breakout_z": row.get("accel_breakout_z"),
                }
            )
        out[period] = part
    return out


def _build_fund_metrics(per_period_snapshot: Dict[str, pd.DataFrame]) -> tuple[dict, list]:
    maps = {}
    all_codes = set()
    for period, df in per_period_snapshot.items():
        if df is None or df.empty:
            maps[period] = {}
            continue
        d = {}
        for _, r in df.iterrows():
            code = str(r.get("kod") or "").upper()
            if not code:
                continue
            d[code] = r
            all_codes.add(code)
        maps[period] = d

    out = {}
    all_funds = []
    for code in sorted(all_codes):
        d = maps.get("gunluk", {}).get(code)
        w = maps.get("haftalik", {}).get(code)
        m = maps.get("aylik", {}).get(code)
        fon_adi = d.get("fon_adi") if d is not None else (w.get("fon_adi") if w is not None else None)
        kategori = d.get("kategori_adi") if d is not None else (w.get("kategori_adi") if w is not None else None)
        out[code] = {
            "fon_adi": fon_adi,
            "kategori_adi": kategori,
            "getiri_gunluk_pct": float(d.get("getiri_pct")) if d is not None and pd.notna(d.get("getiri_pct")) else None,
            "getiri_haftalik_pct": float(w.get("getiri_pct")) if w is not None and pd.notna(w.get("getiri_pct")) else None,
            "getiri_aylik_pct": float(m.get("getiri_pct")) if m is not None and pd.notna(m.get("getiri_pct")) else None,
            "yatirimci_delta": float(d.get("yatirimci_delta")) if d is not None and pd.notna(d.get("yatirimci_delta")) else None,
        }
        all_funds.append({"kod": code, "fon_adi": fon_adi, "kategori_adi": kategori})

    return out, all_funds


def _fetch_compare_series(
    client: FvtClient,
    codes: Iterable[str],
    metric: str,
    ranges: Iterable[str],
) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    benchmark_client = YahooBenchmarkClient(timeout=20)
    for r in ranges:
        out[r] = []
        for code in codes:
            rows = client.fetch_fund_series(code, metric=metric, range_value=r)
            if not rows:
                continue
            d = pd.DataFrame(rows)
            if "x" not in d.columns or "y" not in d.columns:
                continue
            d["x"] = pd.to_datetime(d["x"], errors="coerce")
            d["y"] = pd.to_numeric(d["y"], errors="coerce")
            d = d.dropna(subset=["x", "y"]).sort_values("x")
            if d.empty:
                continue
            start = d["y"].iloc[0]
            if start == 0:
                continue

            d["norm"] = (d["y"] / start) * 100.0
            d["ret_1d"] = d["y"].pct_change() * 100.0
            d["ret_5avg"] = d["ret_1d"].rolling(5, min_periods=1).mean()
            d["ret_21avg"] = d["ret_1d"].rolling(21, min_periods=1).mean()

            enrich = analyze_price_series(d[["x", "y"]].to_dict(orient="records"))
            accel_x = None
            accel_y = None
            accel_z = None
            if enrich.accel_breakout_date:
                dt = pd.to_datetime(enrich.accel_breakout_date, errors="coerce")
                m = d[d["x"].dt.date == dt.date()]
                if not m.empty:
                    accel_x = m["x"].iloc[-1].strftime("%Y-%m-%d")
                    accel_y = round(float(m["norm"].iloc[-1]), 6)
                    accel_z = enrich.accel_breakout_z

            out[r].append(
                {
                    "name": code,
                    "is_benchmark": False,
                    "x": [x.strftime("%Y-%m-%d") for x in d["x"]],
                    "y": [round(v, 6) for v in d["norm"]],
                    "raw": [round(v, 6) for v in d["y"]],
                    "ret_1d": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_1d"]],
                    "ret_5avg": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_5avg"]],
                    "ret_21avg": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_21avg"]],
                    "accel_x": accel_x,
                    "accel_y": accel_y,
                    "accel_z": accel_z,
                }
            )

        benchmarks = benchmark_client.fetch_all_norm(range_value=r)
        for name, bdf in benchmarks.items():
            if bdf is None or bdf.empty:
                continue
            d = bdf.copy().sort_values("x")
            d["ret_1d"] = pd.to_numeric(d["y"], errors="coerce").pct_change() * 100.0
            d["ret_5avg"] = d["ret_1d"].rolling(5, min_periods=1).mean()
            d["ret_21avg"] = d["ret_1d"].rolling(21, min_periods=1).mean()
            out[r].append(
                {
                    "name": name,
                    "is_benchmark": True,
                    "x": [x.strftime("%Y-%m-%d") for x in d["x"]],
                    "y": [round(v, 6) for v in d["norm"]],
                    "raw": [round(v, 6) for v in d["y"]],
                    "ret_1d": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_1d"]],
                    "ret_5avg": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_5avg"]],
                    "ret_21avg": [None if pd.isna(v) else round(float(v), 6) for v in d["ret_21avg"]],
                    "accel_x": None,
                    "accel_y": None,
                    "accel_z": None,
                }
            )
    return out


def _fetch_investor_series(client: FvtClient, codes: Iterable[str], range_value: str = "1Y") -> list[dict]:
    out: List[dict] = []
    for code in codes:
        rows = client.fetch_fund_series(code, metric="yatirimci", range_value=range_value)
        if not rows:
            continue
        d = pd.DataFrame(rows)
        if "x" not in d.columns or "y" not in d.columns:
            continue
        d["x"] = pd.to_datetime(d["x"], errors="coerce")
        d["y"] = pd.to_numeric(d["y"], errors="coerce")
        d = d.dropna(subset=["x", "y"]).sort_values("x")
        if len(d) < 2:
            continue
        d["delta"] = d["y"].diff()
        d["interest_5d"] = d["delta"].rolling(5, min_periods=1).mean()
        d = d.dropna(subset=["interest_5d"])
        if d.empty:
            continue
        out.append(
            {
                "name": code,
                "x": [x.strftime("%Y-%m-%d") for x in d["x"]],
                "y": [round(v, 6) for v in d["interest_5d"]],
            }
        )
    return out


def generate_interactive_report(
    output_path: Path,
    run_time: datetime,
    per_period_signals: Dict[str, pd.DataFrame],
    top_codes: Iterable[str],
    client: FvtClient,
    compare_metric: str = "fiyat",
    compare_ranges: Iterable[str] | None = None,
    per_period_snapshot: Dict[str, pd.DataFrame] | None = None,
    portfolio_df: pd.DataFrame | None = None,
    portfolio_suggestions_df: pd.DataFrame | None = None,
    portfolio_total_tl: float = 0.0,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    top_codes = list(top_codes)
    ranges = list(compare_ranges) if compare_ranges else ["1M", "3M", "6M", "9M", "1Y"]

    signals = _serialize_signals(per_period_signals)

    fund_metrics = {}
    all_funds = []
    if per_period_snapshot:
        fund_metrics, all_funds = _build_fund_metrics(per_period_snapshot)

    portfolio_codes = []
    portfolio_default_holdings = []
    if portfolio_df is not None and not portfolio_df.empty:
        for _, r in portfolio_df.iterrows():
            code = str(r.get("kod") or "").upper()
            if not code:
                continue
            portfolio_codes.append(code)
            portfolio_default_holdings.append({"kod": code, "weight_pct": float(r.get("weight_pct") or 0)})

    all_compare_codes = sorted(set(top_codes + portfolio_codes))
    compare = _fetch_compare_series(client, all_compare_codes, metric=compare_metric, ranges=ranges)
    investor = _fetch_investor_series(client, top_codes, range_value="1Y")

    suggestions = []
    if portfolio_suggestions_df is not None and not portfolio_suggestions_df.empty:
        for _, r in portfolio_suggestions_df.iterrows():
            suggestions.append(
                {
                    "kod": r.get("kod"),
                    "fon_adi": r.get("fon_adi"),
                    "kategori_adi": r.get("kategori_adi"),
                    "signal_score": r.get("signal_score"),
                    "interest_score": r.get("interest_score"),
                    "acceleration": r.get("acceleration"),
                    "reasons": r.get("reasons"),
                }
            )

    payload = {
        "generated_at": run_time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": signals,
        "compare_metric": compare_metric,
        "compare_ranges": ranges,
        "compare": compare,
        "investor": investor,
        "fund_metrics": fund_metrics,
        "all_funds": all_funds,
        "portfolio_default": {
            "total_tl": float(portfolio_total_tl),
            "holdings": portfolio_default_holdings,
        },
        "portfolio_suggestions": suggestions,
    }

    html = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Fon Alarm İnteraktif Rapor</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <script src="https://cdn.plot.ly/plotly-locale-tr-latest.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #f3f7ff; color: #102033; }}
    .wrap {{ max-width: 1380px; margin: 0 auto; padding: 14px; }}
    .head {{ background: linear-gradient(135deg,#0f5132,#0c2e5e); color:#fff; padding:14px; border-radius:12px; }}
    .controls {{ margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; }}
    button, select, input {{ border:1px solid #c7d5e7; background:#fff; border-radius:10px; padding:7px 10px; font-weight:600; }}
    .grid {{ margin-top:12px; display:grid; grid-template-columns: 1fr 1fr; gap:12px; }}
    .card {{ background:#fff; border:1px solid #e0e8f4; border-radius:12px; padding:10px; min-width:0; }}
    .compare-card {{ grid-column:1/-1; }}
    .portfolio-card {{ grid-column:1/-1; }}
    .card h3 {{ margin:0 0 8px 0; font-size:18px; }}
    .plot {{ width:100%; min-height:360px; }}
    #comparePlot {{ min-height:575px; }}
    #portfolioComparePlot {{ min-height:460px; }}
    .muted {{ color:#5d6d83; font-size:12px; }}
    .legend-note {{ margin-top:8px; font-size:12px; color:#5d6d83; background:#eef5ff; border:1px solid #dce7f6; border-radius:10px; padding:8px; overflow-wrap:anywhere; }}
    .period-tabs {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }}
    .period-tab.active {{ background:#0f5132; color:#fff; border-color:#0f5132; }}
    .table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
    .tbl {{ width:100%; border-collapse:collapse; font-size:12px; min-width:1080px; }}
    .tbl th,.tbl td {{ border-bottom:1px solid #ebeff5; padding:7px 6px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
    .pill {{ display:inline-block; border-radius:999px; padding:2px 8px; font-size:11px; font-weight:700; background:#e8f6ef; color:#11663d; }}
    .pill.m {{ background:#eef3ff; color:#2a4d8f; }}
    .cards {{ display:none; gap:8px; }}
    .signal-card {{ border:1px solid #e6ecf5; border-radius:10px; padding:8px; background:#fff; }}
    .signal-card .row {{ margin:4px 0; font-size:12px; line-height:1.4; overflow-wrap:anywhere; }}

    .portfolio-grid {{ display:grid; grid-template-columns: 1fr; gap:10px; }}
    .portfolio-actions {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }}
    .portfolio-actions input {{ min-width:120px; }}
    .status-iyi {{ color:#0f7b3b; font-weight:700; }}
    .status-orta {{ color:#936f08; font-weight:700; }}
    .status-zayif {{ color:#b52222; font-weight:700; }}

    body.mobile .grid {{ grid-template-columns:1fr; }}
    body.mobile .portfolio-grid {{ grid-template-columns:1fr; }}
    body.mobile .plot {{ min-height:320px; }}
    body.mobile #comparePlot {{ min-height:462px; }}
    body.mobile .cards {{ display:grid; }}
    body.mobile .table-wrap {{ display:none; }}

    @media (max-width:980px) {{
      .grid {{ grid-template-columns:1fr; }}
      .portfolio-grid {{ grid-template-columns:1fr; }}
      .plot {{ min-height:320px; }}
      #comparePlot {{ min-height:462px; }}
      .cards {{ display:grid; }}
      .table-wrap {{ display:none; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <h2 style="margin:0">Fon Alarm İnteraktif Rapor</h2>
      <div style="opacity:.9;margin-top:6px">Üretim zamanı: {payload['generated_at']}</div>
      <div class="controls">
        <button id="desktopBtn">Masaüstü Görünüm</button>
        <button id="mobileBtn">Mobil Görünüm</button>
        <select id="rangeSelect"></select>
      </div>
    </div>

    <div class="grid">
      <div class="card compare-card">
        <h3>Karşılaştırmalı Fon Grafiği <span class="muted">(Başlangıç=100)</span></h3>
        <div id="comparePlot" class="plot"></div>
        <div class="legend-note">Mouse üzerine gelince: Günlük getiri, 5 günlük ortalama getiri ve 1 aylık (21g) ortalama getiri görünür. Yıldız işareti ani ivme noktasını gösterir. Kesik çizgi seriler: BIST 100 ve Gram Altın benchmarkları.</div>
      </div>

      <div class="card">
        <h3>Yatırımcı İlgisi <span class="muted">(5 günlük ortalama değişim)</span></h3>
        <div id="investorPlot" class="plot"></div>
      </div>

      <div class="card">
        <h3>Top Sinyaller</h3>
        <div class="period-tabs" id="periodTabs"></div>
        <div id="signalTable"></div>
        <div class="legend-note">Skor/İlgi/İvme Z-skorudur. 0-100 puan normal dağılım yüzdelik karşılığıdır.</div>
      </div>

      <div class="card portfolio-card">
        <h3>Portföy Modülü (Maks 10 Fon)</h3>
        <div class="portfolio-grid">
          <div>
            <div class="portfolio-actions">
              <input id="pfTotalTl" type="text" placeholder="Toplam Portföy TL (örn 1.600.000)">
              <input id="pfCode" list="fundCodes" placeholder="Fon Kodu (örn TLY)">
              <input id="pfWeight" type="number" step="0.01" placeholder="Ağırlık %">
              <button id="pfAddBtn">Ekle/Güncelle</button>
              <button id="pfSaveBtn">Ağırlıkları Kaydet</button>
            </div>
            <div id="pfModeInfo" class="legend-note">Toplam portföy TL ve ağırlıkları buradan güncelleyebilirsin.</div>
            <datalist id="fundCodes"></datalist>
            <div id="portfolioHoldings"></div>
            <div id="portfolioAnalysis"></div>
          </div>
          <div>
            <h4 style="margin:4px 0">Portföy Karşılaştırma</h4>
            <div id="portfolioComparePlot" class="plot"></div>
            <div class="legend-note">Portföy eğrisi ağırlıklı ortalamadır. Fon adı üzerine tıklayıp gizleyebilirsin.</div>
            <div id="portfolioSuggestions"></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const PAYLOAD = {json.dumps(payload, ensure_ascii=False)};
    Plotly.setPlotConfig({{locale: 'tr'}});

    const rangeSelect = document.getElementById('rangeSelect');
    const periods = Object.keys(PAYLOAD.signals || {{}});
    let activePeriod = periods.includes('gunluk') ? 'gunluk' : (periods[0] || 'gunluk');

    function fmt(v, d=2) {{
      if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
      return Number(v).toLocaleString('tr-TR', {{minimumFractionDigits:d, maximumFractionDigits:d}});
    }}

    function clsStatus(s) {{
      const t = String(s || '').toLowerCase();
      if (t.includes('güçlü')) return 'status-iyi';
      if (t.includes('izle')) return 'status-orta';
      return 'status-zayif';
    }}

    const rangeLabels = {{'1M':'1 Ay','3M':'3 Ay','6M':'6 Ay','9M':'9 Ay','1Y':'1 Yıl'}};
    (PAYLOAD.compare_ranges || []).forEach(r => {{
      const o=document.createElement('option'); o.value=r; o.textContent=rangeLabels[r] || r; rangeSelect.appendChild(o);
    }});
    rangeSelect.value = (PAYLOAD.compare_ranges || []).includes('1Y') ? '1Y' : ((PAYLOAD.compare_ranges || [])[0] || '1Y');

    const allFunds = PAYLOAD.all_funds || [];
    const fundMetrics = PAYLOAD.fund_metrics || {{}};
    const suggestions = PAYLOAD.portfolio_suggestions || [];
    const API_BASE = 'http://127.0.0.1:8765';
    let hasApi = false;

    function parseTlInput(v) {{
      if (v === null || v === undefined) return 0;
      const s = String(v).trim();
      if (!s) return 0;
      const normalized = s.replace(/\\./g, '').replace(/,/g, '.').replace(/[^0-9.-]/g, '');
      const n = Number(normalized);
      return Number.isFinite(n) ? n : 0;
    }}

    function setPortfolioModeInfo() {{
      const el = document.getElementById('pfModeInfo');
      if (!el) return;
      if (hasApi) {{
        el.textContent = 'DB servisi aktif: Kaydet ile ana veritabanına yazılır.';
      }} else {{
        el.textContent = 'Bulut/Pages modunda DB yok: Kaydet ile tarayıcıda saklanır (bu cihazda).';
      }}
    }}

    function loadPortfolioStateLocal() {{
      const raw = localStorage.getItem('fvt_portfolio_state_v2');
      if (raw) {{
        try {{
          return JSON.parse(raw);
        }} catch(e) {{ }}
      }}
      return PAYLOAD.portfolio_default || {{ total_tl: 0, holdings: [] }};
    }}

    function savePortfolioStateLocal(st) {{
      localStorage.setItem('fvt_portfolio_state_v2', JSON.stringify(st));
    }}

    async function loadPortfolioState() {{
      const local = loadPortfolioStateLocal() || {{ total_tl: 0, holdings: [] }};
      try {{
        const res = await fetch(`${{API_BASE}}/portfolio`, {{method:'GET'}});
        if (res.ok) {{
          hasApi = true;
          const j = await res.json();
          if (j && j.ok && j.portfolio) {{
            const st = {{
              total_tl: Number(j.portfolio.total_tl || 0),
              holdings: j.portfolio.holdings || []
            }};
            savePortfolioStateLocal(st);
            return st;
          }}
        }}
      }} catch(e) {{ }}
      return local;
    }}

    async function savePortfolioState(st) {{
      const payload = {{
        total_tl: Number(st.total_tl || 0),
        holdings: normalizeHoldings(st.holdings || [])
      }};
      let ok = false;
      try {{
        const res = await fetch(`${{API_BASE}}/portfolio`, {{
          method: 'PUT',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        ok = res.ok;
        hasApi = res.ok;
      }} catch(e) {{
        ok = false;
        hasApi = false;
      }}
      savePortfolioStateLocal(payload);
      return ok;
    }}

    let pfState = {{ total_tl: Number(PAYLOAD.portfolio_default?.total_tl || 0), holdings: PAYLOAD.portfolio_default?.holdings || [] }};

    function normalizeHoldings(arr) {{
      const map = new Map();
      (arr || []).forEach(x => {{
        const c = String(x.kod || '').trim().toUpperCase();
        const w = Number(x.weight_pct || 0);
        if (!c || !(w > 0)) return;
        map.set(c, w);
      }});
      return Array.from(map.entries()).slice(0,10).map(([kod, weight_pct]) => ({{kod, weight_pct}}));
    }}

    function buildFundDatalist() {{
      const dl = document.getElementById('fundCodes');
      dl.innerHTML = '';
      allFunds.forEach(f => {{
        const o = document.createElement('option');
        o.value = f.kod;
        o.label = `${{f.kod}} - ${{f.fon_adi || ''}}`;
        dl.appendChild(o);
      }});
    }}

    function drawCompare(rangeVal) {{
      const list = PAYLOAD.compare[rangeVal] || [];
      const traces = [];
      list.forEach(s => {{
        const custom = (s.y || []).map((_,i)=>[s.ret_1d?.[i], s.ret_5avg?.[i], s.ret_21avg?.[i]]);
        const isBenchmark = Boolean(s.is_benchmark);
        traces.push({{
          x:s.x, y:s.y, customdata:custom,
          mode:'lines', type:'scatter', name:s.name, line:{{width:isBenchmark ? 2.2 : 2.4, dash: isBenchmark ? 'dash' : 'solid'}},
          hovertemplate:
            '%{{x|%d.%m.%Y}}<br><b>'+s.name+'</b><br>'+
            'Normalize: %{{y:.2f}}<br>'+
            'Günlük Getiri: %{{customdata[0]:.2f}}%<br>'+
            '5g Ort. Getiri: %{{customdata[1]:.2f}}%<br>'+
            '1A Ort. Getiri: %{{customdata[2]:.2f}}%<extra></extra>'
        }});
        if (s.accel_x && s.accel_y !== null) {{
          traces.push({{
            x:[s.accel_x], y:[s.accel_y], mode:'markers+text', type:'scatter',
            marker:{{size:10,symbol:'star',color:'#d9480f'}}, text:[`${{s.name}} ivme`], textposition:'top center',
            showlegend:false, name:`${{s.name}} ivme`,
            hovertemplate:`%{{x|%d.%m.%Y}}<br>${{s.name}} ani ivme (Z=${{fmt(s.accel_z)}})<extra></extra>`
          }});
        }}
      }});
      const compareHeight = document.body.classList.contains('mobile') ? 462 : 575;
      Plotly.newPlot('comparePlot', traces, {{
        height: compareHeight,
        margin:{{l:52,r:12,t:14,b:72}}, paper_bgcolor:'transparent', plot_bgcolor:'transparent',
        xaxis:{{title:'Tarih', tickformat:'%d.%m.%Y', hoverformat:'%d %B %Y'}},
        yaxis:{{title:'Normalize Değer (Başlangıç=100)'}},
        legend:{{orientation:'h', y:-0.30}}, hovermode:'x unified'
      }}, {{responsive:true, locale:'tr'}});
    }}

    function drawInvestor() {{
      const traces = (PAYLOAD.investor || []).map(s=>({{x:s.x,y:s.y,mode:'lines',type:'scatter',name:s.name,line:{{width:2.2}}}}));
      Plotly.newPlot('investorPlot', traces, {{
        margin:{{l:52,r:12,t:14,b:56}}, paper_bgcolor:'transparent', plot_bgcolor:'transparent',
        xaxis:{{title:'Tarih', tickformat:'%d.%m.%Y', hoverformat:'%d %B %Y'}},
        yaxis:{{title:'Yatırımcı Değişimi (5g ort.)'}}, legend:{{orientation:'h', y:-0.26}}, hovermode:'x unified'
      }}, {{responsive:true, locale:'tr'}});
    }}

    function drawSignals(period) {{
      const rows = PAYLOAD.signals?.[period] || [];
      const box = document.getElementById('signalTable');
      if (!rows.length) {{ box.innerHTML='<div class="muted">Bu periyot için sinyal yok.</div>'; return; }}

      let table = '<div class="table-wrap"><table class="tbl"><thead><tr>'+
      '<th>#</th><th>Fon</th><th>Kategori</th><th>Skor</th><th>İlgi</th><th>İvme</th><th>Getiri G/H/A</th><th>5g/Geçmiş/Fark</th><th>DD</th><th>Kalkış</th><th>Neden</th></tr></thead><tbody>';
      rows.forEach((r,i)=>{{
        table += '<tr>'+
          `<td>${{i+1}}</td>`+
          `<td><b>${{r.kod}}</b><div class="muted">${{r.fon_adi||'-'}}</div></td>`+
          `<td>${{r.kategori_adi||'-'}}</td>`+
          `<td><span class="pill">${{fmt(r.signal_z)}} / ${{r.signal_100}}</span></td>`+
          `<td><span class="pill m">${{fmt(r.interest_z)}} / ${{r.interest_100}}</span></td>`+
          `<td><span class="pill m">${{fmt(r.accel_z)}} / ${{r.accel_100}}</span></td>`+
          `<td>${{fmt(r.getiri_gunluk_pct)}} / ${{fmt(r.getiri_haftalik_pct)}} / ${{fmt(r.getiri_aylik_pct)}}</td>`+
          `<td>${{fmt(r.return_5d_avg_pct)}} / ${{fmt(r.return_hist_avg_pct)}} / ${{fmt(r.return_gap_pct)}}</td>`+
          `<td>${{fmt(r.max_drawdown_pct)}}</td>`+
          `<td>${{r.accel_breakout_date||'-'}}</td>`+
          `<td>${{r.reasons||'-'}}</td>`+
          '</tr>';
      }});
      table += '</tbody></table></div>';

      let cards = '<div class="cards">';
      rows.forEach((r,i)=>{{
        cards += '<div class="signal-card">'+
          `<div class="row"><b>#${{i+1}} ${{r.kod}}</b> - ${{r.kategori_adi||'-'}}</div>`+
          `<div class="row">Skor/İlgi/İvme: ${{fmt(r.signal_z)}} (${{r.signal_100}}) | ${{fmt(r.interest_z)}} (${{r.interest_100}}) | ${{fmt(r.accel_z)}} (${{r.accel_100}})</div>`+
          `<div class="row">Getiri G/H/A: ${{fmt(r.getiri_gunluk_pct)}} / ${{fmt(r.getiri_haftalik_pct)}} / ${{fmt(r.getiri_aylik_pct)}}</div>`+
          `<div class="row">5g/Geçmiş/Fark: ${{fmt(r.return_5d_avg_pct)}} / ${{fmt(r.return_hist_avg_pct)}} / ${{fmt(r.return_gap_pct)}}</div>`+
          `<div class="row">DD: ${{fmt(r.max_drawdown_pct)}} | Kalkış: ${{r.accel_breakout_date||'-'}}</div>`+
          `<div class="row"><b>Neden:</b> ${{r.reasons||'-'}}</div>`+
          '</div>';
      }});
      cards += '</div>';
      box.innerHTML = table + cards;
    }}

    function buildSignalTabs() {{
      const tabs = document.getElementById('periodTabs'); tabs.innerHTML='';
      periods.forEach(p=>{{
        const b = document.createElement('button');
        b.className='period-tab'+(p===activePeriod?' active':'');
        b.textContent=p.toUpperCase();
        b.onclick=()=>{{activePeriod=p; document.querySelectorAll('.period-tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); drawSignals(activePeriod);}};
        tabs.appendChild(b);
      }});
      drawSignals(activePeriod);
    }}

    function getPortfolioRows() {{
      const arr = normalizeHoldings(pfState.holdings || []);
      const total = Number(pfState.total_tl || 0);
      const sw = arr.reduce((a,b)=>a+Number(b.weight_pct||0),0) || 1;
      return arr.map(x=>{{
        const code = String(x.kod).toUpperCase();
        const m = fundMetrics[code] || {{}};
        const wn = Number(x.weight_pct)/sw;
        const amount = total * wn;
        const g = Number(m.getiri_gunluk_pct); const h = Number(m.getiri_haftalik_pct); const a = Number(m.getiri_aylik_pct);
        const yd = Number(m.yatirimci_delta);
        let score = 0;
        if (!Number.isNaN(g)) score += 0.5*g;
        if (!Number.isNaN(h)) score += 0.3*h;
        if (!Number.isNaN(yd)) score += 0.2*(yd/50);
        const status = score >= 1 ? 'Güçlü' : (score >= 0.25 ? 'İzle' : 'Zayıf');
        return {{
          kod: code,
          fon_adi: m.fon_adi || '-',
          kategori_adi: m.kategori_adi || '-',
          weight_pct: Number(x.weight_pct),
          weight_norm_pct: wn*100,
          amount_tl: amount,
          getiri_gunluk_pct: Number.isNaN(g)?null:g,
          getiri_haftalik_pct: Number.isNaN(h)?null:h,
          getiri_aylik_pct: Number.isNaN(a)?null:a,
          yatirimci_delta: Number.isNaN(yd)?null:yd,
          health_status: status
        }};
      }});
    }}

    function renderPortfolio() {{
      document.getElementById('pfTotalTl').value = fmt(pfState.total_tl || 0, 2);
      setPortfolioModeInfo();
      const rows = getPortfolioRows();
      savePortfolioStateLocal({{
        total_tl: Number(pfState.total_tl || 0),
        holdings: normalizeHoldings(pfState.holdings || [])
      }});

      let hhtml = '<div class="table-wrap"><table class="tbl"><thead><tr><th>Kod</th><th>Ağırlık%</th><th>Pay%</th><th>Tutar (TL)</th><th>Güncelle</th><th>Sil</th></tr></thead><tbody>';
      rows.forEach((r,idx)=>{{
        hhtml += '<tr>'+
          `<td>${{r.kod}}</td><td><input id="w_${{r.kod}}" type="number" step="0.01" value="${{Number(r.weight_pct).toFixed(2)}}" style="width:90px"></td><td>${{fmt(r.weight_norm_pct)}}</td><td>${{fmt(r.amount_tl,2)}}</td>`+
          `<td><button onclick="updateHolding('${{r.kod}}')">Güncelle</button></td>`+
          `<td><button onclick="removeHolding('${{r.kod}}')">Sil</button></td>`+
          '</tr>';
      }});
      hhtml += '</tbody></table></div>';
      document.getElementById('portfolioHoldings').innerHTML = '<h4 style="margin:6px 0">Portföy Dağılımı</h4>' + hhtml;

      let ahtml = '<div class="table-wrap"><table class="tbl"><thead><tr><th>Kod</th><th>Fon</th><th>Kategori</th><th>Getiri G/H/A</th><th>Yatırımcı Δ</th><th>Durum</th></tr></thead><tbody>';
      rows.forEach(r=>{{
        ahtml += '<tr>'+
          `<td>${{r.kod}}</td><td>${{r.fon_adi}}</td><td>${{r.kategori_adi}}</td>`+
          `<td>${{fmt(r.getiri_gunluk_pct)}} / ${{fmt(r.getiri_haftalik_pct)}} / ${{fmt(r.getiri_aylik_pct)}}</td>`+
          `<td>${{fmt(r.yatirimci_delta,0)}}</td>`+
          `<td class="${{clsStatus(r.health_status)}}">${{r.health_status}}</td>`+
          '</tr>';
      }});
      ahtml += '</tbody></table></div>';
      document.getElementById('portfolioAnalysis').innerHTML = '<h4 style="margin:8px 0">Portföy Sağlık Analizi</h4>' + ahtml;

      let shtml = '<h4 style="margin:8px 0">Portföyde Olmayan Öneriler</h4>';
      if (!suggestions.length) shtml += '<div class="muted">Öneri yok.</div>';
      suggestions.forEach(s=>{{
        shtml += `<div class="legend-note"><b>${{s.kod}}</b> - ${{s.kategori_adi||'-'}} | Skor:${{fmt(s.signal_score)}} İlgi:${{fmt(s.interest_score)}} İvme:${{fmt(s.acceleration)}} <button onclick="quickAdd('${{s.kod}}')">Portföye Ekle</button><br>${{s.reasons||''}}</div>`;
      }});
      document.getElementById('portfolioSuggestions').innerHTML = shtml;

      drawPortfolioCompare(rangeSelect.value);
    }}

    function drawPortfolioCompare(rangeVal) {{
      const all = PAYLOAD.compare?.[rangeVal] || [];
      const codes = new Set((normalizeHoldings(pfState.holdings || [])).map(x=>String(x.kod).toUpperCase()));
      const list = all.filter(s => codes.has(String(s.name).toUpperCase()));
      if (!list.length) {{
        Plotly.newPlot('portfolioComparePlot', [], {{annotations:[{{text:'Seçili fonlar bu raporun karşılaştırma setinde yok. Workflow’u portföy girdisi ile manuel tetikleyebilirsin.',showarrow:false}}], xaxis:{{visible:false}}, yaxis:{{visible:false}}}}, {{responsive:true, locale:'tr'}});
        return;
      }}

      const traces = [];
      const weightsArr = normalizeHoldings(pfState.holdings || []);
      const sw = weightsArr.reduce((a,b)=>a+Number(b.weight_pct||0),0) || 1;
      const wmap = {{}};
      weightsArr.forEach(x=>wmap[String(x.kod).toUpperCase()] = Number(x.weight_pct)/sw);

      list.forEach(s=>{{
        traces.push({{x:s.x,y:s.y,mode:'lines',type:'scatter',name:s.name,line:{{width:2}}}});
      }});

      const dateMap = new Map();
      list.forEach(s=>{{
        const w = wmap[String(s.name).toUpperCase()] || 0;
        s.x.forEach((dt,idx)=>{{
          const y = Number(s.y[idx]);
          if (!dateMap.has(dt)) dateMap.set(dt, {{sum:0, w:0}});
          const obj = dateMap.get(dt);
          if (!Number.isNaN(y)) {{ obj.sum += y*w; obj.w += w; }}
        }});
      }});
      const px = Array.from(dateMap.keys()).sort();
      const py = px.map(dt=>{{ const o=dateMap.get(dt); return o.w>0 ? o.sum/o.w : null; }});
      traces.push({{x:px,y:py,mode:'lines',type:'scatter',name:'PORTFÖY',line:{{width:3.2,color:'#111'}}}});

      Plotly.newPlot('portfolioComparePlot', traces, {{
        margin:{{l:52,r:12,t:14,b:56}}, paper_bgcolor:'transparent', plot_bgcolor:'transparent',
        xaxis:{{title:'Tarih', tickformat:'%d.%m.%Y', hoverformat:'%d %B %Y'}},
        yaxis:{{title:'Normalize Değer (Başlangıç=100)'}}, legend:{{orientation:'h', y:-0.26}}, hovermode:'x unified'
      }}, {{responsive:true, locale:'tr'}});
    }}

    function removeHolding(code) {{
      pfState.holdings = normalizeHoldings((pfState.holdings || []).filter(x => String(x.kod).toUpperCase() !== String(code).toUpperCase()));
      renderPortfolio();
    }}

    function updateHolding(code) {{
      const node = document.getElementById(`w_${{code}}`);
      if (!node) return;
      const w = Number(node.value || 0);
      if (!(w > 0)) {{ alert('Ağırlık 0dan büyük olmalı'); return; }}
      let arr = normalizeHoldings(pfState.holdings || []);
      const idx = arr.findIndex(x => String(x.kod).toUpperCase() === String(code).toUpperCase());
      if (idx < 0) return;
      arr[idx].weight_pct = w;
      pfState.holdings = normalizeHoldings(arr);
      renderPortfolio();
    }}

    function quickAdd(code) {{
      document.getElementById('pfCode').value = code;
      document.getElementById('pfWeight').value = 10;
    }}

    document.getElementById('pfAddBtn').onclick = () => {{
      const code = String(document.getElementById('pfCode').value || '').trim().toUpperCase();
      const w = Number(document.getElementById('pfWeight').value || 0);
      if (!code || !(w>0)) return;
      let arr = normalizeHoldings(pfState.holdings || []);
      const idx = arr.findIndex(x => String(x.kod).toUpperCase() === code);
      if (idx >= 0) arr[idx].weight_pct = w;
      else {{ if (arr.length >= 10) {{ alert('En fazla 10 fon eklenebilir'); return; }} arr.push({{kod: code, weight_pct: w}}); }}
      pfState.holdings = normalizeHoldings(arr);
      document.getElementById('pfCode').value = '';
      document.getElementById('pfWeight').value = '';
      renderPortfolio();
    }};

    document.getElementById('pfSaveBtn').onclick = async () => {{
      pfState.total_tl = parseTlInput(document.getElementById('pfTotalTl').value);
      pfState.holdings = normalizeHoldings(pfState.holdings || []);
      const ok = await savePortfolioState(pfState);
      alert(ok ? 'Portföy ana veritabanına kaydedildi.' : 'DB servisine ulaşılamadı. Geçici olarak tarayıcıda tutuldu.');
      renderPortfolio();
    }};

    document.getElementById('pfTotalTl').addEventListener('change', () => {{
      pfState.total_tl = parseTlInput(document.getElementById('pfTotalTl').value);
      renderPortfolio();
    }});

    rangeSelect.onchange = () => {{ drawCompare(rangeSelect.value); drawPortfolioCompare(rangeSelect.value); }};
    document.getElementById('desktopBtn').onclick = () => document.body.classList.remove('mobile');
    document.getElementById('mobileBtn').onclick = () => document.body.classList.add('mobile');

    if (window.innerWidth < 760) document.body.classList.add('mobile');

    async function bootstrap() {{
      buildFundDatalist();
      pfState = await loadPortfolioState();
      pfState.holdings = normalizeHoldings(pfState.holdings || []);
      drawCompare(rangeSelect.value);
      drawInvestor();
      buildSignalTabs();
      renderPortfolio();
    }}

    bootstrap();
  </script>
</body>
</html>
"""

    html = html.replace("{{", "{").replace("}}", "}")
    html = html.replace("{payload['generated_at']}", payload["generated_at"])
    html = html.replace("{json.dumps(payload, ensure_ascii=False)}", json.dumps(payload, ensure_ascii=False))
    output_path.write_text(html, encoding="utf-8")
    return output_path
