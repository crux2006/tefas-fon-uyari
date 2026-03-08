from __future__ import annotations

import argparse

from app.config import load_settings
from app.storage import Storage


def parse_args():
    p = argparse.ArgumentParser(description="Portföy yönetimi (maks 10 fon)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("list", help="Portföyü listeler")

    s2 = sub.add_parser("set-total", help="Toplam portföy TL tutarını ayarlar")
    s2.add_argument("total_tl", type=float)

    s3 = sub.add_parser("add", help="Fon ekler/günceller")
    s3.add_argument("kod")
    s3.add_argument("weight_pct", type=float)

    s4 = sub.add_parser("remove", help="Fon siler")
    s4.add_argument("kod")

    s5 = sub.add_parser("replace", help="Portföyü komple değiştirir")
    s5.add_argument("total_tl", type=float)
    s5.add_argument(
        "--holdings",
        required=True,
        help="Örn: TLY:35,PBR:25,PHE:40",
    )

    sub.add_parser("clear", help="Portföyü temizler")
    return p.parse_args()


def parse_holdings(text: str):
    rows = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Geçersiz format: {item}")
        kod, w = item.split(":", 1)
        rows.append({"kod": kod.strip().upper(), "weight_pct": float(w)})
    return rows


def print_portfolio(storage: Storage):
    pf = storage.get_portfolio()
    print(f"Toplam TL: {pf['total_tl']:.2f}")
    h = pf["holdings"]
    if h.empty:
        print("Fon yok.")
        return
    print("Fonlar:")
    for _, r in h.iterrows():
        print(f"- {r['kod']}: %{float(r['weight_pct']):.2f}")


def main():
    args = parse_args()
    settings = load_settings()
    storage = Storage(settings.db_path)

    if args.cmd == "list":
        print_portfolio(storage)
        return
    if args.cmd == "set-total":
        storage.set_portfolio_total_tl(args.total_tl)
        print("Toplam TL güncellendi.")
        print_portfolio(storage)
        return
    if args.cmd == "add":
        storage.upsert_portfolio_holding(args.kod, args.weight_pct)
        print("Fon eklendi/güncellendi.")
        print_portfolio(storage)
        return
    if args.cmd == "remove":
        storage.delete_portfolio_holding(args.kod)
        print("Fon silindi.")
        print_portfolio(storage)
        return
    if args.cmd == "replace":
        holdings = parse_holdings(args.holdings)
        storage.set_portfolio(args.total_tl, holdings)
        print("Portföy tamamen güncellendi.")
        print_portfolio(storage)
        return
    if args.cmd == "clear":
        storage.set_portfolio(0, [])
        print("Portföy temizlendi.")
        print_portfolio(storage)
        return


if __name__ == "__main__":
    main()

