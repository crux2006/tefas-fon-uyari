from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def find_latest_report_dir(reports_dir: Path) -> Path:
    if not reports_dir.exists():
        raise FileNotFoundError(f"Rapor dizini bulunamadi: {reports_dir}")
    dirs = [p for p in reports_dir.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"Rapor klasoru yok: {reports_dir}")
    dirs.sort(key=lambda p: p.name)
    return dirs[-1]


def build_index_html(latest_dir_name: str) -> str:
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FVT Fon Alarm Raporu</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f4f8ff;
      color: #0f1f35;
    }}
    .card {{
      max-width: 860px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #dfe8f7;
      border-radius: 12px;
      padding: 18px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 24px; }}
    p {{ margin: 8px 0; line-height: 1.5; }}
    a {{
      display: inline-block;
      margin: 6px 10px 0 0;
      padding: 8px 12px;
      border: 1px solid #b7cae7;
      border-radius: 9px;
      text-decoration: none;
      color: #0a417a;
      background: #f3f8ff;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>FVT Fon Alarm</h1>
    <p>En son rapor klasoru: <strong>{latest_dir_name}</strong></p>
    <p>
      <a href="./latest/interactive_report.html">Interaktif Raporu Ac</a>
      <a href="./latest/report.txt">Metin Raporu (TXT)</a>
    </p>
    <p style="font-size:13px;color:#51627c;">
      Grafik dosyalari ve diger ciktilar <code>latest/</code> altindadir.
    </p>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Pages icin son raporu hazirlar.")
    parser.add_argument("--reports-dir", default="reports", help="Rapor kok dizini")
    parser.add_argument("--site-dir", default="site", help="Site cikti dizini")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir).resolve()
    site_dir = Path(args.site_dir).resolve()
    latest = find_latest_report_dir(reports_dir)

    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    latest_target = site_dir / "latest"
    shutil.copytree(latest, latest_target)

    files = []
    for p in latest_target.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(latest_target)).replace("\\", "/"))
    files.sort()

    (site_dir / "latest_report.txt").write_text(latest.name, encoding="utf-8")
    (site_dir / "manifest.json").write_text(
        json.dumps({"latest_report": latest.name, "files": files}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (site_dir / "index.html").write_text(build_index_html(latest.name), encoding="utf-8")
    print(f"Hazirlandi: {site_dir}")
    print(f"Kaynak rapor: {latest}")


if __name__ == "__main__":
    main()
