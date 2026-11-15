"""Paths and the team key. The key is read from spread_bot/.env at run time and is never printed or logged."""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../the desk's folder
PROJECT = os.path.dirname(ROOT)                                             # .../HackJunction26'
DATA = os.path.join(ROOT, "data")
LOGS = os.path.join(ROOT, "logs")
REVEALED = os.path.join(PROJECT, "spread_bot", "data", "worlds")            # weeks revealed by the other build: read as data only
KEYFILE = os.path.join(PROJECT, "spread_bot", ".env")


def load_key() -> None:
    """Puts SPREAD_KEY and SPREAD_URL in the environment for spread.client.Client."""
    os.environ.setdefault("SPREAD_URL", "https://spread.bahnexpress.com")
    if os.environ.get("SPREAD_KEY"):
        return
    with open(KEYFILE, encoding="utf-8") as f:
        for line in f:
            name, _, value = line.strip().partition("=")
            if name == "SPREAD_KEY" and value:
                os.environ["SPREAD_KEY"] = value.strip().strip('"').strip("'")
                return
    raise SystemExit("No SPREAD_KEY found in spread_bot/.env")


for folder in (DATA, LOGS):
    os.makedirs(folder, exist_ok=True)
