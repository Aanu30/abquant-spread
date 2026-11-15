"""Averages the lane and dealer price levels learned in practice weeks, as priors for the next week.

The competitor's price on a lane has a part that is the same in every world (HANDBOOK.md). Each practice week ends
with the desk's estimate of every pickup place, delivery place and dealer, relative to that week's world level.
Their mean over weeks, shrunk toward zero when few weeks saw the place, is what a new week starts from.

  python -m abquant.priors TAG [TAG ...]      # writes data/priors.json from the runs with these tags
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

from .env import DATA


def main() -> None:
    tags = {"fb_" + t for t in sys.argv[1:]}
    values = defaultdict(list)
    weeks = 0
    with open(os.path.join(DATA, "runs.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tag"] in tags and "level_parts" in r:
                weeks += 1
                for key, v in r["level_parts"].items():
                    if not key.startswith("world"):
                        values[key].append(v)
    priors = {k: round(sum(v) / (len(v) + 2), 4) for k, v in values.items() if len(v) >= 3}
    with open(os.path.join(DATA, "priors.json"), "w", encoding="utf-8") as f:
        json.dump(priors, f, indent=0)
    big = sorted(priors.items(), key=lambda kv: -abs(kv[1]))[:12]
    print(f"{weeks} weeks, {len(priors)} priors; largest: {big}")


if __name__ == "__main__":
    main()
