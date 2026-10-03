#!/usr/bin/env python3
"""Print a read-only summary of your Questrade portfolio."""
import os
import sys

import requests
from dotenv import dotenv_values, set_key

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
TOKEN_URL = "https://login.questrade.com/oauth2/token"
TOKEN_VAR = "QUESTRADE_REFRESH_TOKEN"
HIDE_EMPTY_ACCOUNTS = True  # skip accounts with no positions and no cash


def token_vars():
    """Every .env variable named QUESTRADE_REFRESH_TOKEN or QUESTRADE_REFRESH_TOKEN_<NAME>."""
    return [k for k, v in dotenv_values(ENV_PATH).items() if k.startswith(TOKEN_VAR) and v]


def refresh_session(var):
    """Exchange the refresh token in `var` for an access token and persist the new refresh token."""
    refresh_token = dotenv_values(ENV_PATH)[var]

    resp = requests.post(
        TOKEN_URL,
        params={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=30,
    )
    if not resp.ok:
        print(
            f"Token exchange failed for {var} (HTTP {resp.status_code}). The refresh token "
            "may be expired or already used; generate a new one in the Questrade API Centre.",
            file=sys.stderr,
        )
        return None
    data = resp.json()

    # Refresh tokens are single-use: save the new one immediately.
    set_key(ENV_PATH, var, data["refresh_token"], quote_mode="never")

    session = requests.Session()
    session.headers["Authorization"] = f"{data['token_type']} {data['access_token']}"
    return session, data["api_server"].rstrip("/")


def get(session, base, path):
    resp = session.get(f"{base}/{path}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def money(value):
    return f"{value:,.2f}"


def qty(value):
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def print_account(session, base, account):
    num = account["number"]
    positions = get(session, base, f"v1/accounts/{num}/positions")["positions"]
    balances = get(session, base, f"v1/accounts/{num}/balances")

    if HIDE_EMPTY_ACCOUNTS and not positions and not any(
        b["totalEquity"] for b in balances["combinedBalances"]
    ):
        return

    print(f"\n=== {account['type']} account {num} ===")
    rows = [
        (p["symbol"], qty(p["openQuantity"]), money(p["currentMarketValue"]), money(p["openPnl"]))
        for p in positions
    ]
    headers = ("Symbol", "Quantity", "Market Value", "Open P&L")
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(4)]

    def fmt(row):
        return "  ".join(
            str(c).ljust(w) if i == 0 else str(c).rjust(w)
            for i, (c, w) in enumerate(zip(row, widths))
        )

    print(fmt(headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))
    if not rows:
        print("(no positions)")

    print()
    for b in balances["perCurrencyBalances"]:
        print(f"Cash ({b['currency']}):        {money(b['cash'])}")
    for b in balances["combinedBalances"]:
        print(f"Total cash ({b['currency']}):  {money(b['cash'])}")
        print(f"Total value ({b['currency']}): {money(b['totalEquity'])}")


def main():
    names = token_vars()
    if not names:
        sys.exit(f"{TOKEN_VAR} not found in {ENV_PATH}")
    for var in names:
        owner = var[len(TOKEN_VAR):].lstrip("_") or "default"
        print(f"\n##### {owner} #####")
        try:
            result = refresh_session(var)
            if result is None:
                continue
            session, base = result
            for account in get(session, base, "v1/accounts")["accounts"]:
                print_account(session, base, account)
        except requests.RequestException as e:
            # Don't print the exception itself: URLs in it could include the token.
            print(f"Request failed for {var}: {type(e).__name__}", file=sys.stderr)


if __name__ == "__main__":
    main()
