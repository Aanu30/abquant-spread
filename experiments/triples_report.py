"""How did three-car gigs book in the practice weeks of a tag played with triple=1? Logs only.

  python triples_report.py ytri
"""
import collections
import glob
import json
import statistics as st
import sys

tag = "fb_" + sys.argv[1]
c = collections.Counter(); ratios = []; ages = []; late = [0, 0]; alone = [0, 0]; base_alone = [0, 0]
r2 = []; b2 = []
for path in sorted(glob.glob(f"logs/{tag}__y*.jsonl")):
    seed = path.split("__")[1]
    rows = [json.loads(l) for l in open(path)]
    posted = [r for r in rows if r.get("kind") == "triple"]
    members = {o for r in posted for o in r["oids"]}
    c["posted"] += len(posted); c["loops"] += sum(1 for r in posted if r["round_trip"]); c["weeks"] += 1
    c["planned minutes"] += sum(r["drive"] for r in posted)
    for r in rows:
        if r.get("kind") == "booked" and len(r.get("oids", [])) == 3:
            c["booked"] += 1; ratios.append(r["ratio"]); ages.append(r["age"])
        if r.get("kind") == "booked" and len(r.get("oids", [])) == 2:
            r2.append(r["ratio"])
        if r.get("kind") == "result":
            alone[0] += 1; alone[1] += not r["pair"]
            if r["oid"] in members:
                late[0] += 1; late[1] += bool(r["late"])
    base = glob.glob(f"logs/fb_yf3__{seed}__*.jsonl")
    if base:
        for r in (json.loads(l) for l in open(base[0])):
            if r.get("kind") == "result":
                base_alone[0] += 1; base_alone[1] += not r["pair"]
            if r.get("kind") == "booked" and len(r.get("oids", [])) == 2:
                b2.append(r["ratio"])
n = c["weeks"]
print(f"weeks {n} | three-car gigs a week {c['posted'] / n:.1f} (ending where they began: {c['loops'] / n:.1f}) | booked as three {c['booked'] / max(1, c['posted']):.0%} | fee x typical {st.mean(ratios):.2f} | median minutes to book {st.median(ages)} | planned minutes {c['planned minutes'] / max(1, c['posted']):.0f}")
print(f"late among their cars {late[1]}/{late[0]} = {late[1] / max(1, late[0]):.1%} | pairs' fee x typical: {st.mean(r2):.2f} with the setting, {st.mean(b2):.2f} as played")
print(f"cars never in a pair or a three: {alone[1] / n:.0f} a week ({alone[1] / max(1, alone[0]):.0%}), as played {base_alone[1] / n:.0f} ({base_alone[1] / max(1, base_alone[0]):.0%})")
