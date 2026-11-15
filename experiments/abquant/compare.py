"""Paired comparison of two tags on the same seeds: mean difference and its standard error, by seed set.

  python -m abquant.compare NEW BASE [NEW2 BASE2 ...]      # tags as recorded in data/runs.jsonl (with or without fb_)
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

from .env import DATA


def runs(tag: str) -> dict:
    out = {}
    with open(os.path.join(DATA, "runs.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tag"] in (tag, "fb_" + tag):
                out[r["seed"]] = r                      # the latest run of a seed under the tag
    return out


def line(label: str, new: dict, base: dict, seeds: list) -> str:
    d = [new[s]["margin"] - base[s]["margin"] for s in seeds]
    se = st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else float("nan")
    return (f"  {label:<5} n={len(d):2d}  {st.mean(new[s]['margin'] for s in seeds):>7,.0f} vs {st.mean(base[s]['margin'] for s in seeds):>7,.0f}"
            f"  diff {st.mean(d):+7,.0f} (se {se:,.0f})  won {st.mean(new[s]['won'] for s in seeds):.0f} vs {st.mean(base[s]['won'] for s in seeds):.0f}"
            f"  worst on-time {min(new[s]['ontime'] for s in seeds):.1%} vs {min(base[s]['ontime'] for s in seeds):.1%}"
            f"  better in {sum(1 for x in d if x > 0)}/{len(d)}")


def main() -> None:
    a = sys.argv[1:]
    for new_tag, base_tag in zip(a[::2], a[1::2]):
        new, base = runs(new_tag), runs(base_tag)
        common = sorted(set(new) & set(base))
        print(f"{new_tag} vs {base_tag}")
        for label, seeds in (("t", [s for s in common if s.startswith("t")]), ("v", [s for s in common if s.startswith("v")]),
                             ("s", [s for s in common if s.startswith("s")]), ("all", common)):
            if seeds:
                print(line(label, new, base, seeds))


if __name__ == "__main__":
    main()
