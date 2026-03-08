from __future__ import annotations

import pandas as pd
import streamlit as st

from app.config import load_settings
from app.fvt_client import FvtClient
from app.scoring import z_to_100
from app.storage import Storage

st.set_page_config(page_title="Fon Alarm Dashboard", layout="wide")

settings = load_settings()
storage = Storage(settings.db_path)
client = FvtClient()

st.title("FVT Fon Alarm Dashboard")
st.caption("Günlük/Haftalık/Aylık sinyaller, ivmelenme ve karşılaştırmalı grafikler")

period = st.selectbox("Periyot", settings.periods, index=0)
fund_type = settings.fund_type

signals_q = """
SELECT *
FROM signals
WHERE period = ?
  AND fund_type = ?
ORDER BY snapshot_date DESC, signal_score DESC
"""
with storage._connect() as conn:
    all_signals = pd.read_sql_query(signals_q, conn, params=[period, fund_type])

if all_signals.empty:
    st.warning("Henüz sinyal verisi bulunamadı. Önce pipeline çalıştırın.")
    st.stop()

latest_date = all_signals["snapshot_date"].max()
latest = all_signals[all_signals["snapshot_date"] == latest_date].copy()
latest["score_100"] = latest["signal_score"].apply(z_to_100)
latest["interest_100"] = latest["interest_score"].apply(z_to_100)
latest["accel_100"] = latest["acceleration"].apply(z_to_100)

c1, c2, c3 = st.columns(3)
c1.metric("Tarih", latest_date)
c2.metric("Sinyal Sayısı", len(latest))
c3.metric("Ortalama Skor", f"{latest['signal_score'].mean():.2f}")

st.subheader("Güncel Sinyaller")
view_cols = [
    "kod",
    "fon_adi",
    "kategori_adi",
    "signal_score",
    "score_100",
    "interest_score",
    "interest_100",
    "acceleration",
    "accel_100",
    "reasons",
]
st.dataframe(latest[view_cols], use_container_width=True, height=420)

codes = latest["kod"].head(10).tolist()
selected_codes = st.multiselect("Karşılaştırma Fonları", options=codes, default=codes[:4])
metric = st.selectbox("Grafik Metriği", ["fiyat", "doluluk_orani", "pay_adet", "toplam_deger", "yatirimci"], index=0)
range_value = st.selectbox("Aralık", ["1W", "1M", "3M", "6M", "9M", "YBB", "1Y", "5Y"], index=6)

if selected_codes:
    data_frames = []
    for code in selected_codes:
        rows = client.fetch_fund_series(code, metric=metric, range_value=range_value)
        d = pd.DataFrame(rows)
        if not d.empty and "x" in d.columns and "y" in d.columns:
            d["x"] = pd.to_datetime(d["x"], errors="coerce")
            d["y"] = pd.to_numeric(d["y"], errors="coerce")
            d = d.dropna(subset=["x", "y"]).sort_values("x")
            if not d.empty:
                d["kod"] = code
                base = d["y"].iloc[0]
                if base != 0:
                    d["norm_100"] = (d["y"] / base) * 100
                else:
                    d["norm_100"] = d["y"]
                data_frames.append(d[["x", "kod", "y", "norm_100"]])
    if data_frames:
        comp = pd.concat(data_frames, ignore_index=True)
        st.subheader("Karşılaştırmalı Grafik (Başlangıç=100)")
        pivot = comp.pivot_table(index="x", columns="kod", values="norm_100")
        st.line_chart(pivot)
    else:
        st.info("Seçilen fonlar için grafik verisi bulunamadı.")

st.subheader("Sinyal Geçmişi")
sel_code = st.selectbox("Fon Kodu", options=sorted(latest["kod"].unique().tolist()))
hist = all_signals[all_signals["kod"] == sel_code].copy()
hist["snapshot_date"] = pd.to_datetime(hist["snapshot_date"], errors="coerce")
hist = hist.sort_values("snapshot_date")
if not hist.empty:
    chart_df = hist.set_index("snapshot_date")[["signal_score", "interest_score", "acceleration"]]
    st.line_chart(chart_df)
    st.dataframe(hist[["snapshot_date", "signal_score", "interest_score", "acceleration", "reasons"]], use_container_width=True)
