"""How did pairs with a long haul book, in the practice weeks of a tag played with pool_long? Logs only.

  python long_pairs_report.py ylong
"""
import collections
import glob
import json
import statistics as st
import sys

tag = "fb_" + sys.argv[1]
c = collections.Counter(); ratios = []; ages = []; late = [0, 0]; late_long = [0, 0]; base_long = [0, 0]
alone = [0, 0]; base_alone = [0, 0]
for path in sorted(glob.glob(f"logs/{tag}__y*.jsonl")):
    seed = path.split("__")[1]
    rows = [json.loads(l) for l in open(path)]
    q = {r["rid"]: r for r in rows if r.get("kind") == "quote"}
    lp = [r for r in rows if r.get("kind") == "pair" and (q.get(r["a"], {}).get("drive", 0) >= 240 or q.get(r["b"], {}).get("drive", 0) >= 240)]
    keys = {frozenset((r["a"], r["b"])) for r in lp}
    members = {o for k in keys for o in k}
    c["pairs"] += len(lp); c["weeks"] += 1
    for r in rows:
        if r.get("kind") == "booked" and len(r.get("oids", [])) == 2 and frozenset(r["oids"]) in keys:
            c["booked"] += 1; ratios.append(r["ratio"]); ages.append(r["age"])
        if r.get("kind") == "result":
            alone[0] += 1; alone[1] += not r["pair"]
            if r["oid"] in members:
                late[0] += 1; late[1] += bool(r["late"])
            if q.get(r["oid"], {}).get("drive", 0) >= 240:
                late_long[0] += 1; late_long[1] += bool(r["late"])
    base = glob.glob(f"logs/fb_yf3__{seed}__*.jsonl")
    if base:
        rows = [json.loads(l) for l in open(base[0])]
        q = {r["rid"]: r for r in rows if r.get("kind") == "quote"}
        for r in rows:
            if r.get("kind") == "result":
                base_alone[0] += 1; base_alone[1] += not r["pair"]
                if q.get(r["oid"], {}).get("drive", 0) >= 240:
                    base_long[0] += 1; base_long[1] += bool(r["late"])
n = c["weeks"]
print(f"weeks {n} | pairs with a long haul a week {c['pairs'] / n:.1f} | booked as a pair {c['booked'] / max(1, c['pairs']):.0%} | fee x typical {st.mean(ratios):.2f} | median minutes to book {st.median(ages)}")
print(f"late among their cars {late[1]}/{late[0]} = {late[1] / max(1, late[0]):.1%} | long hauls late: with the setting {late_long[1]}/{late_long[0]} = {late_long[1] / max(1, late_long[0]):.1%}, as played {base_long[1]}/{base_long[0]} = {base_long[1] / max(1, base_long[0]):.1%}")
print(f"cars never in a pair: with the setting {alone[1] / n:.0f} a week ({alone[1] / max(1, alone[0]):.0%}), as played {base_alone[1] / n:.0f} ({base_alone[1] / max(1, base_alone[0]):.0%})")
