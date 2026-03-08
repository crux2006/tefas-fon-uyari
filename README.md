# FVT Fon Alarm Sistemi (MVP)

Bu proje FVT verilerini kullanarak:
- Günlük / haftalık / aylık tarama yapar
- Fon bazlı sinyal skorları üretir
- İvmelenme ve yatırımcı ilgisi değişimini ölçer
- D/H/A getiri, 5 günlük ortalama getiri, geçmiş ortalama ve drawdown metrikleri üretir
- Grafik üretir
- Telegram'a açıklayıcı rapor gönderir
- Mobil/masaüstü uyumlu interaktif HTML raporu üretir

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env` içinde Telegram bilgilerini doldurun:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

`TELEGRAM_CHAT_ID` bilmiyorsanız:

```bash
python find_telegram_chat_id.py
```

Önce botunuza Telegram'dan `/start` gönderin, sonra komutu çalıştırın.

## Çalıştırma

Telegram dahil:

```bash
python run_pipeline.py
```

Sadece yerel rapor (Telegram kapalı):

```bash
python run_pipeline.py --no-telegram
```

Raporlar:
- `reports/YYYYMMDD_HHMMSS/report.txt`
- aynı klasörde PNG grafikler
- `reports/YYYYMMDD_HHMMSS/interactive_report.html`
  Not: Fon karşılaştırma grafikleri varsayılan olarak `1M,3M,6M,9M,1Y` için ayrı ayrı üretilir.

Veritabanı:
- `data/fund_alerts.sqlite`

## Dashboard

```bash
streamlit run dashboard.py
```

Dashboard özellikleri:
- Son sinyaller tablosu
- Karşılaştırmalı fon grafikleri (normalize)
- Fon bazlı sinyal geçmişi (skor / ilgi / ivme)
- 0-100 yorum ölçeği (Z-skorundan türetilir)

Varsayılan olarak `Para Piyasası Fonları` analiz dışıdır. İstersen `.env` içindeki `EXCLUDED_CATEGORIES` alanından değiştirebilirsin.

## Portföy Modülü

Portföyünü kalıcı olarak veritabanına kaydetmek için:

```bash
python manage_portfolio.py replace 1000000 --holdings "TLY:40,PBR:35,PHE:25"
```

Yardımcı komutlar:

```bash
python manage_portfolio.py list
python manage_portfolio.py add TLY 30
python manage_portfolio.py remove TLY
python manage_portfolio.py set-total 1500000
python manage_portfolio.py clear
```

Pipeline çalıştığında:
- Portföy fon analizi rapora eklenir
- Portföy karşılaştırma grafiği üretilir
- İnteraktif HTML içinde portföy ekle/sil/düzenle paneli açılır (yerel tarayıcı kaydı)

Portföy değişikliklerini doğrudan ana veritabanına yazmak için API:

```bash
python portfolio_api.py
```

API çalışırken HTML içindeki `Ağırlıkları Kaydet` butonu DB'ye kaydeder.

## Sinyal Mantığı (özet)

Skor bileşenleri:
- Getiri sapması
- Nakit akımı sapması
- Yatırımcı değişim sapması
- Akım skoru sapması

Her metrik için:
- Zaman serisine göre sapma (`time-series z-score`)
- Aynı gün fonlar arası sapma (`cross-sectional z-score`)

Ek ölçüler:
- İvme: son birkaç güne göre artış hızı
- Kategori gücü: kategori ortalama getiri + net akım + yatırımcı + akım skoru birleşik etkisi

## Otomasyon

Windows Görev Zamanlayıcı ile günlük çalıştırma önerisi:
- Program: `python`
- Argüman: `run_pipeline.py`
- Çalışma dizini: proje kök klasörü

## GitHub Cloud Calisma (PC Kapaliyken)

- Workflow: `.github/workflows/fund-alert-daily.yml`
- Gunluk otomatik saat: `11:00` (Istanbul), cron: `0 8 * * *`
- Manuel tetikleme: GitHub > `Actions` > `FVT Fon Alarm Daily` > `Run workflow`
- Pages yayininda son rapor:
  - `https://crux2006.github.io/tefas-fon-uyari/`
  - `interactive_report.html` buradan acilir.

Yerel bilgisayara rapor indirme:

```bash
python scripts/sync_latest_report.py
```

Varsayilan hedef klasor: `Desktop/FonRaporlari`

Windows acilista otomatik indirme task'i:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_report_sync_task.ps1
```

## Not

Bu sistem yatırım tavsiyesi vermez; veri temelli alarm üretir.
