#!/bin/zsh
# 06:30 Sunday bake-off: v4 and the ABQuant desk on fresh seeds z1-z10. Prints one summary per bot.
cd "$(dirname "$0")"
python3 - <<'PY'
import time, datetime
target = datetime.datetime(2026, 11, 15, 6, 30)
while datetime.datetime.now() < target:
    time.sleep(30)
PY
SEEDS=z1,z2,z3,z4,z5,z6,z7,z8,z9,z10
echo "bake-off start $(date)"
(cd other_build/releases/v4 && python3 -m bot.run --seeds $SEEDS --tag bake_v4 --parallel 4 2>&1 | grep -E "^==|FAILED")
(.venv/bin/python -m abquant.run --seeds $SEEDS --tag bake_desk --parallel 4 2>&1 | tail -4)
python3 - <<'PY'
import json, statistics as st
def load(path, tag):
    out = {}
    for line in open(path):
        r = json.loads(line)
        if r.get("tag") == tag:
            out[r["seed"]] = r
    return out
v4 = load("other_build/data/runs.jsonl", "bake_v4")
fb = load("data/runs.jsonl", "bake_desk")
for name, d in (("v4", v4), ("desk", fb)):
    if d:
        m = [r["margin"] for r in d.values()]; ot = [r.get("ontime", r.get("onTimeShare", 0)) for r in d.values()]
        print(f"{name:6} weeks {len(d)}  mean margin {st.mean(m):,.0f}  worst on-time {min(ot):.3f}  ranked {sum(1 for r in d.values() if r.get('ranked'))}/{len(d)}")
common = sorted(set(v4) & set(fb))
if len(common) > 1:
    diff = [fb[s]["margin"] - v4[s]["margin"] for s in common]
    print(f"paired desk - v4: {st.mean(diff):+,.0f} (se {st.stdev(diff)/len(diff)**0.5:,.0f}) over {len(common)} seeds")
PY
echo "bake-off end $(date)"
