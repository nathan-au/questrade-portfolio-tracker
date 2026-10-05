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
USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
RED, GREEN, DIM, RESET = "\033[31m", "\033[32m", "\033[2m", "\033[0m"


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


def money(value, suffix=""):
    return "-" if value is None else f"{value:,.2f}{suffix}"


def signed(value, suffix=""):
    """Like money(), but with an explicit + for gains."""
    if value is None:
        return "-"
    value = round(value, 2)
    return f"{value:+,.2f}{suffix}" if value else f"0.00{suffix}"


def pct(numerator, denominator):
    return "-" if numerator is None or not denominator else signed(numerator / denominator * 100, "%")


def paint(text, color):
    return f"{color}{text}{RESET}" if USE_COLOR and color else text


def qty(value):
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def usd_to_cad(combined):
    """CAD per USD, or None. Combined balances show the same equity in both currencies."""
    equity = {b["currency"]: b["totalEquity"] for b in combined}
    return equity["CAD"] / equity["USD"] if equity.get("CAD") and equity.get("USD") else None


def totals_row(positions, code, rate):
    """Totals row in CAD, converting USD positions at `rate`; None if no rate is available."""
    def cad(value, symbol_id):
        return (value or 0) * (rate if code[symbol_id] == "USD" else 1)

    if rate is None and any(code[p["symbolId"]] == "USD" for p in positions):
        return None
    value, day, openpnl, cost = (
        sum(cad(p[key], p["symbolId"]) for p in positions)
        for key in ("currentMarketValue", "dayPnl", "openPnl", "totalCost")
    )
    return (
        "Total (CAD)", "", "", "",
        money(value, " CAD"),
        signed(day, " CAD"),
        pct(day, value - day),
        signed(openpnl, " CAD"),
        pct(openpnl, cost),
    )


def print_table(headers, rows, signed_cols=(), footer=None):
    """Print a boxed table; first column left-aligned, the rest right-aligned.

    signed_cols: indexes of columns to colour red/green by sign.
    footer: optional totals row, set off by a rule.
    """
    widths = [max(len(r[i]) for r in [headers, *rows, *([footer] if footer else [])]) for i in range(len(headers))]

    bar = paint("│", DIM)

    def fmt(row):
        cells = []
        for i, (c, w) in enumerate(zip(row, widths)):
            text = c.ljust(w) if i == 0 else c.rjust(w)  # pad before colouring
            if i in signed_cols and len(c) > 1:  # a lone "-" means no value
                text = paint(text, {"+": GREEN, "-": RED}.get(c[0]))
            cells.append(text)
        return bar + " " + f" {bar} ".join(cells) + " " + bar

    def rule(left, mid, right):
        return paint(left + mid.join("─" * (w + 2) for w in widths) + right, DIM)

    print(rule("┌", "┬", "┐"))
    print(fmt(headers))
    print(rule("├", "┼", "┤"))
    for r in rows:
        print(fmt(r))
    if footer:
        print(rule("├", "┼", "┤"))
        print(fmt(footer))
    print(rule("└", "┴", "┘"))


def print_account(session, base, account):
    num = account["number"]
    positions = get(session, base, f"v1/accounts/{num}/positions")["positions"]
    balances = get(session, base, f"v1/accounts/{num}/balances")

    if HIDE_EMPTY_ACCOUNTS and not positions and not any(
        b["totalEquity"] for b in balances["combinedBalances"]
    ):
        return

    print(f"\n--- {account['type']} ({num}) ---")
    # Position data has no currency, so look each symbol up in one batched request.
    ids = ",".join(str(p["symbolId"]) for p in positions)
    symbols = get(session, base, f"v1/symbols?ids={ids}")["symbols"] if ids else []
    code = {s["symbolId"]: s["currency"] for s in symbols}
    currency = {i: f" {c}" for i, c in code.items()}
    positions = sorted(positions, key=lambda p: p["openPnl"] or 0, reverse=True)
    rows = [
        (
            p["symbol"],
            qty(p["openQuantity"]),
            money(p["averageEntryPrice"], currency[p["symbolId"]]),
            money(p["currentPrice"], currency[p["symbolId"]]),
            money(p["currentMarketValue"], currency[p["symbolId"]]),
            signed(p["dayPnl"], currency[p["symbolId"]]),
            # Day % is relative to the value at yesterday's close.
            pct(p["dayPnl"], (p["currentMarketValue"] or 0) - (p["dayPnl"] or 0)),
            signed(p["openPnl"], currency[p["symbolId"]]),
            pct(p["openPnl"], p["totalCost"]),
        )
        for p in positions
    ]
    if rows:
        print_table(
            (
                "Symbol", "Shares", "Average", "Last", "Value",
                "Day P&L", "Day %", "Open P&L", "Open %",
            ),
            rows,
            signed_cols=(5, 6, 7, 8),
            footer=totals_row(positions, code, usd_to_cad(balances["combinedBalances"])),
        )
    else:
        print("(no positions)")

    print()
    combined = balances["combinedBalances"]
    lines = [(f"Total cash ({b['currency']}):", money(b["cash"])) for b in combined]
    for b in combined:
        if b["currency"] != "USD":
            lines.append((f"Total market value ({b['currency']}):", money(b["marketValue"])))
            lines.append((f"Total portfolio value ({b['currency']}):", money(b["totalEquity"])))
    label_w = max((len(label) for label, _ in lines), default=0)
    value_w = max((len(value) for _, value in lines), default=0)
    for label, value in lines:
        print(f"{label.ljust(label_w)}  {value.rjust(value_w)}")
    cash = {b["currency"]: b["cash"] for b in combined}
    return cash.get("CAD"), cash.get("USD")


def main():
    names = token_vars()
    if not names:
        sys.exit(f"{TOKEN_VAR} not found in {ENV_PATH}")
    cash_pairs = []  # (CAD cash, USD cash) from each printed account
    for var in names:
        owner = var[len(TOKEN_VAR):].lstrip("_") or "default"
        print(f"\n=== {owner} ===")
        try:
            result = refresh_session(var)
            if result is None:
                continue
            session, base = result
            for account in get(session, base, "v1/accounts")["accounts"]:
                cash_pairs.append(print_account(session, base, account))
        except requests.RequestException as e:
            # Don't print the exception itself: URLs in it could include the token.
            print(f"Request failed for {var}: {type(e).__name__}", file=sys.stderr)

    # Combined balances show the same cash in both currencies, so CAD / USD is the rate.
    # Use the account with the most USD cash, where rounding matters least.
    pairs = [pair for pair in cash_pairs if pair and all(pair)]
    if pairs:
        cad, usd = max(pairs, key=lambda pair: pair[1])
        print(f"\n1 USD = {cad / usd:.4f} CAD (total cash in CAD divided by total cash in USD)")


if __name__ == "__main__":
    main()
