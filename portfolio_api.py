from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from app.config import load_settings
from app.storage import Storage


HOST = "127.0.0.1"
PORT = 8765


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    storage: Storage = Storage(load_settings().db_path)

    def do_OPTIONS(self):
        _json_response(self, 200, {"ok": True})

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            _json_response(self, 200, {"ok": True, "service": "portfolio_api"})
            return
        if p == "/portfolio":
            pf = self.storage.get_portfolio()
            holdings = []
            h = pf.get("holdings")
            if h is not None and not h.empty:
                for _, r in h.iterrows():
                    holdings.append({"kod": str(r["kod"]).upper(), "weight_pct": float(r["weight_pct"])})
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "portfolio": {
                        "total_tl": float(pf.get("total_tl") or 0),
                        "holdings": holdings,
                        "updated_at": pf.get("updated_at"),
                    },
                },
            )
            return
        _json_response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        self._save_portfolio()

    def do_PUT(self):
        self._save_portfolio()

    def _save_portfolio(self):
        p = urlparse(self.path).path
        if p != "/portfolio":
            _json_response(self, 404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw.decode("utf-8"))
            total_tl = float(data.get("total_tl") or 0)
            holdings = data.get("holdings") or []
            self.storage.set_portfolio(total_tl, holdings)
            _json_response(self, 200, {"ok": True})
        except Exception as e:
            _json_response(self, 400, {"ok": False, "error": str(e)})

    def log_message(self, format, *args):  # noqa: A003
        return


def main():
    httpd = HTTPServer((HOST, PORT), Handler)
    print(f"Portfolio API running on http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

