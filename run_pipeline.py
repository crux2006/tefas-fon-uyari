from __future__ import annotations

import argparse

from app.config import load_settings
from app.pipeline import FundAlertPipeline


def parse_args():
    parser = argparse.ArgumentParser(description="FVT fon alarm pipeline")
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Telegram gönderimini kapatır",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    pipeline = FundAlertPipeline(settings)
    override = False if args.no_telegram else None
    result = pipeline.run(send_telegram_override=override)
    print(f"Rapor klasörü: {result.report_dir}")
    print("Grafikler:")
    for p in result.chart_paths:
        print(f"- {p}")
    print(f"İnteraktif HTML: {result.interactive_html_path}")


if __name__ == "__main__":
    main()
