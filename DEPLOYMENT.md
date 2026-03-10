# Deployment Rehberi

Bu proje icin oncelikli yol: `GitHub Actions + GitHub Pages`.

## 1) GitHub Yolu (Oncelikli)

### 1.1 Repoyu olustur
- GitHub hesabinda yeni repo ac (ornek: `tefas-fon-uyari`).
- Baslangicta bos olsun.

### 1.2 Secrets tanimla
Repo > `Settings` > `Secrets and variables` > `Actions` > `New repository secret`

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 1.3 Pipeline
- Workflow dosyasi: `.github/workflows/fund-alert-daily.yml`
- Otomatik calisma: her gun `08:00 UTC` (Istanbul saati ile `11:00`)
- Manuel calisma: `Actions` sekmesinden `Run workflow`
  - `send_telegram`: true/false
  - `portfolio_total_tl`: opsiyonel
  - `portfolio_holdings`: opsiyonel (ornek `TLY:40,PBR:35,TKZ:25`)

### 1.4 Pages yayin
- Repo > `Settings` > `Pages`
- Source: `GitHub Actions` sec
- Ilk workflow kosusundan sonra URL acilir.

### 1.5 Neler yayinlanir
- Son calisan rapor `site/latest/` altina kopyalanir.
- `site/index.html` son rapora link verir.
- `site/manifest.json` son rapordaki dosya listesini verir (yerel sync icin).
- `reports`, `data/fund_alerts.sqlite`, `site` workflow artifact olarak saklanir.

### 1.6 Bilgisayara otomatik indirme
- Script: `python scripts/sync_latest_report.py`
- Varsayilan klasor: `Desktop/FonRaporlari`
- Her rapor `Desktop/FonRaporlari/YYYYMMDD_HHMMSS/` klasorune iner.
- Acilista otomatik calisma (startup):
  - `powershell -ExecutionPolicy Bypass -File scripts/install_startup_sync.ps1`
  - VBS olusturur, hatasiz quote kacisi ile calisir.
  - 11:00'dan once bekler, 11:00'dan sonra bugunun raporu gelene kadar periyodik kontrol eder.

### 1.7 Tek tik manuel tetikleme (Masaustu)
- Kurulum:
  - `powershell -ExecutionPolicy Bypass -File scripts/install_desktop_workflow_shortcuts.ps1`
- Masaustunde olusan `Fon Workflow Tetikle.cmd`:
  - workflow_dispatch tetikler,
  - opsiyonel portfoy toplam/dagilim girisi alir,
  - run ve pages linklerini otomatik acar.

## 2) Oracle Yolu (Fallback)

GitHub istenen sekilde stabil olmazsa:
- Oracle Ubuntu VM acilir
- Proje clone edilir
- Python ortam + `requirements.txt` kurulur
- `.env` olusturulur
- `cron` ile gunde 1 calisma + manuel tetik komutu eklenir
- `portfolio_api.py` systemd service olarak acilir

Bu adimlar istenirse ayrica `oracle_setup.sh` ve `systemd` unit dosyalariyla otomatiklestirilebilir.
