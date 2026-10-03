# Questrade Portfolio Tracker

A single read-only script, `portfolio.py`, that prints your Questrade portfolio to the terminal. For each account it shows a table of symbol, quantity, market value and open P&L, followed by cash and total value. It only makes GET requests (plus the token exchange) and never prints your tokens. It supports several people at once, so you can see your own accounts and someone else's in one run.

## How it works

Questrade uses OAuth refresh tokens, and each one is **single-use**. You generate the first one (token A) in the Questrade API Centre and put it in `.env`. After that, every run follows this pipeline, once per token in `.env`:

1. **Exchange**: the script sends A to Questrade. Questrade replies with a short-lived access pass, the address to use for data requests, and a new refresh token (B). This is the only request that returns a token.
2. **Save**: A is now dead, so the script writes B back to `.env` immediately, before fetching any data. If a later step fails, the new token is already safe.
3. **List accounts**: using the access pass, the script asks Questrade for the list of accounts.
4. **Per account**: for each account, it asks for the holdings and the cash balances.
5. **Print**: a table of positions, then cash and total value. These data requests return account data only, never tokens.

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