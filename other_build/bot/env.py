"""Paths, the vendored kit, and the team key from spread_bot/.env (never printed)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "vendor", "spread_pkg")
if KIT not in sys.path:
    sys.path.insert(0, KIT)


def load_env() -> None:
    os.environ.setdefault("SPREAD_URL", "https://spread.bahnexpress.com")
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
