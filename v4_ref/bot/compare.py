"""Paired comparison of two tags on the same seeds (ST202 8.4): mean difference and its standard error.
  python3 -m bot.compare NEW BASE [NEW2 BASE2 ...]"""
import json
import os
import statistics as st
import sys

from .env import ROOT


def runs(tag):
    out = {}
    with open(os.path.join(ROOT, "data", "runs.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tag"] == tag:
                out[r["seed"]] = r
    return out


def main():
    a = sys.argv[1:]
    for new, base in zip(a[::2], a[1::2]):
        n, b = runs(new), runs(base)
        common = sorted(set(n) & set(b))
        d = [n[s]["margin"] - b[s]["margin"] for s in common]
        se = max(1e-9, st.stdev(d) / len(d) ** 0.5) if len(d) > 1 else float("nan")
        print(f"{new:>6} vs {base:<6} n={len(d)}  mean {st.mean(n[s]['margin'] for s in common):>8,.0f} vs {st.mean(b[s]['margin'] for s in common):>8,.0f}"
              f"  diff {st.mean(d):+7,.0f} (se {se:,.0f}, t={st.mean(d)/se:+.1f})  won {[n[s]['won'] for s in common]}"
              f"  worst on-time {min(n[s]['ontime'] for s in common):.3f}")


if __name__ == "__main__":
    main()
