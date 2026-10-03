# Questrade Portfolio Tracker

A single read-only script, `portfolio.py`, that prints your Questrade portfolio to the terminal. For each account it shows a table of positions, followed by cash and total value. Each row has the symbol, shares, average cost, last price, market value, and day and open P&L in dollars and percent. Rows are sorted by market value (the raw numbers, with no CAD/USD conversion), and every dollar amount is labelled with the currency its ticker trades in (CAD or USD). P&L is green with a `+` for gains and red for losses, and the table borders are dimmed. Colour is turned off when the output is piped or `NO_COLOR` is set. It only makes GET requests (plus the token exchange) and never prints your tokens. It supports several people at once, so you can see your own accounts and someone else's in one run.

## How it works

Questrade uses OAuth refresh tokens, and each one is **single-use**. You generate the first one (token A) in the Questrade API Centre and put it in `.env`. After that, every run follows this pipeline, once per token in `.env`:

1. **Exchange**: the script sends A to Questrade. Questrade replies with a short-lived access pass, the address to use for data requests, and a new refresh token (B). This is the only request that returns a token.
2. **Save**: A is now dead, so the script writes B back to `.env` immediately, before fetching any data. If a later step fails, the new token is already safe.
3. **List accounts**: using the access pass, the script asks Questrade for the list of accounts.
4. **Per account**: for each account, it asks for the holdings and the cash balances.
5. **Currencies**: positions don't say what currency they trade in, so the script asks Questrade's symbol lookup for all of the account's tickers in one request.
6. **Print**: a table of positions, then cash and total value. These data requests return account data only, never tokens.

The next run sends B and gets C, and so on.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project folder:

```
QUESTRADE_REFRESH_TOKEN=your_token_here
```

To add another person, add a line with any suffix. Every variable starting with `QUESTRADE_REFRESH_TOKEN` is picked up, and the suffix is used as the heading in the output:

```
QUESTRADE_REFRESH_TOKEN_STEVE=their_token_here
```

## Run

```
source .venv/bin/activate
python portfolio.py
```

## Next steps

- **Cache symbol currencies.** Each account with positions makes one extra request to look up which currency its tickers trade in. A symbol's currency never changes, so store a `symbolId` to currency map in a local JSON file (for example `.currency_cache.json`, added to `.gitignore`) and only look up IDs that aren't in it yet. In the usual case this removes the lookup call entirely.
