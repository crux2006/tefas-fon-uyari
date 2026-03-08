from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN .env içinde bulunamadı.")
        return
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    payload = res.json()
    items = payload.get("result", [])
    if not items:
        print("Henüz update yok. Botunuza Telegram'dan /start yazın ve tekrar çalıştırın.")
        return
    print("Bulunan olası chat_id değerleri:")
    seen = set()
    for item in items:
        msg = item.get("message") or item.get("edited_message") or {}
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid in seen:
            continue
        seen.add(cid)
        print(
            f"- chat_id={cid} | type={chat.get('type')} | username={chat.get('username')} | "
            f"title={chat.get('title')}"
        )


if __name__ == "__main__":
    main()

