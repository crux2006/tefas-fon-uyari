from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests


def str_to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "evet"}


def read_token(token: str, token_file: str) -> str:
    if token and token.strip():
        return token.strip()
    if token_file:
        p = Path(token_file).expanduser().resolve()
        if p.exists():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                return txt
    raise RuntimeError("GitHub token bulunamadi. --token veya --token-file verin.")


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub workflow_dispatch tetikler.")
    parser.add_argument("--owner", default="crux2006")
    parser.add_argument("--repo", default="tefas-fon-uyari")
    parser.add_argument("--workflow", default="fund-alert-daily.yml")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--send-telegram", default="true")
    parser.add_argument("--portfolio-total-tl", default="")
    parser.add_argument("--portfolio-holdings", default="")
    parser.add_argument("--wait-seconds", type=int, default=6)
    args = parser.parse_args()

    token = read_token(args.token, args.token_file)
    base = f"https://api.github.com/repos/{args.owner}/{args.repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    inputs = {"send_telegram": "true" if str_to_bool(args.send_telegram) else "false"}
    if str(args.portfolio_total_tl).strip():
        inputs["portfolio_total_tl"] = str(args.portfolio_total_tl).strip()
    if str(args.portfolio_holdings).strip():
        inputs["portfolio_holdings"] = str(args.portfolio_holdings).strip()

    payload = {"ref": args.ref, "inputs": inputs}
    r = requests.post(
        f"{base}/actions/workflows/{args.workflow}/dispatches",
        headers=headers,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    time.sleep(max(args.wait_seconds, 0))
    rr = requests.get(f"{base}/actions/runs?per_page=1", headers=headers, timeout=30)
    rr.raise_for_status()
    run = (rr.json().get("workflow_runs") or [{}])[0]
    run_url = run.get("html_url", f"https://github.com/{args.owner}/{args.repo}/actions")
    pages_url = f"https://{args.owner}.github.io/{args.repo}/"

    print("DISPATCH_OK=1")
    print(f"RUN_URL={run_url}")
    print(f"PAGES_URL={pages_url}")


if __name__ == "__main__":
    main()
