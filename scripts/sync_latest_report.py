from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin

import requests


def default_output_dir() -> Path:
    return Path.home() / "Desktop" / "FonRaporlari"


def read_manifest(base_url: str, timeout: int) -> dict:
    manifest_url = urljoin(base_url.rstrip("/") + "/", "manifest.json")
    res = requests.get(manifest_url, timeout=timeout)
    res.raise_for_status()
    return res.json()


def download_file(base_url: str, relative_path: str, output_dir: Path, timeout: int) -> None:
    url = urljoin(base_url.rstrip("/") + "/", f"latest/{relative_path}")
    out_path = output_dir / relative_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    res = requests.get(url, timeout=timeout)
    res.raise_for_status()
    out_path.write_bytes(res.content)


def safe_report_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "unknown_report"
    allowed = []
    for ch in raw:
        if ch.isalnum() or ch in {"_", "-"}:
            allowed.append(ch)
    name = "".join(allowed).strip("_-")
    return name or "unknown_report"


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Pages'teki son raporu yerel klasore indirir.")
    parser.add_argument(
        "--base-url",
        default="https://crux2006.github.io/tefas-fon-uyari/",
        help="GitHub Pages ana URL",
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help="Raporlarin kaydedilecegi klasor",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Hedef rapor klasoru varsa yeniden indirir (silip tekrar olusturur).",
    )
    parser.add_argument("--timeout", type=int, default=25, help="HTTP timeout saniye")
    args = parser.parse_args()

    root_dir = Path(args.output_dir).expanduser().resolve()
    root_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(args.base_url, args.timeout)
    files = manifest.get("files") or []
    if not isinstance(files, list) or not files:
        raise RuntimeError("manifest.json icinde indirilecek dosya listesi bulunamadi.")

    latest_name = safe_report_name(str(manifest.get("latest_report", "")))
    report_dir = root_dir / latest_name
    if report_dir.exists() and not args.force:
        print(f"Rapor zaten var, indirme atlandi: {report_dir}")
        (root_dir / "latest_report.txt").write_text(str(latest_name), encoding="utf-8")
        return

    if report_dir.exists() and args.force:
        for p in sorted(report_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                p.rmdir()
        report_dir.rmdir()
    report_dir.mkdir(parents=True, exist_ok=True)

    for rel in files:
        if not rel or not isinstance(rel, str):
            continue
        download_file(args.base_url, rel, report_dir, args.timeout)

    (root_dir / "latest_report.txt").write_text(str(latest_name), encoding="utf-8")
    print(f"Indirme tamamlandi: {report_dir}")
    print(f"Rapor: {latest_name}")


if __name__ == "__main__":
    main()
