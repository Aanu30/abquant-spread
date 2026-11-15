"""Read-only sizing: in the desk's revealed weeks, how many cars went out ALONE that one driver could have chained
with another lone car (A's delivery near B's pickup, B picked up after A's drop-off plus the drive), and what that
is worth if the chained cars cost what the desk's pairs cost (0.76 x typical fee). No API calls."""
import glob, json, os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repository root (the ABQuant desk)
sys.path.insert(0, os.path.join(BASE, "other_build"))
from bot.geo import Geo

ROOT = os.path.join(BASE, "data")  # needs downloaded practice weeks in data/worlds (not in the repository)
geo = Geo()
PAIR_COST = 0.76
runs = {}
with open(os.path.join(ROOT, "runs.jsonl")) as f:
    for line in f:
        r = json.loads(line)
        runs[r["world"]] = r
tot = {"weeks": 0, "lone": 0, "chainable": 0, "save": 0.0, "lone_fee": 0.0, "lone_ref": 0.0}
for path in sorted(glob.glob(os.path.join(ROOT, "worlds", "*.json"))):
    wid = os.path.basename(path)[:-5]
    d = json.load(open(path))
    ref = {x["request"]["id"]: x["request"]["referenceFeeCents"] / 100 / len(x["request"]["legs"]) for x in d["reveal"]["requests"]}
    fee = {}
    for e in d["events"]:
        if e["kind"] == "ledger" and e["line"]["kind"] == "driver_fee" and e["line"]["gigId"]:
            fee[e["line"]["gigId"]] = fee.get(e["line"]["gigId"], 0) - e["line"]["cents"] / 100
    pick, drop = {}, {}
    for e in d["events"]:
        if e["kind"] == "picked_up":
            pick[(e["orderId"], e["leg"])] = (e["at"], e["placeId"], e["gigId"])
        elif e["kind"] == "delivered":
            drop[(e["orderId"], e["leg"])] = (e["at"], e["placeId"], e["gigId"])
    lone = []
    for g in d["snapshot"]["gigs"]:
        pk = [s for s in g["stops"] if s["kind"] == "pickup"]
        if len(pk) != 1 or g["id"] not in fee:
            continue
        key = (pk[0]["orderId"], pk[0]["leg"])
        if key in pick and key in drop and key[0] in ref:
            lone.append({"key": key, "gig": g["id"], "fee": fee[g["id"]], "ref": ref[key[0]], "p": pick[key], "d": drop[key]})
    # greedy: earliest drop-offs first, each car used once as the first or second of a chain
    lone.sort(key=lambda c: c["d"][0])
    used, pairs, save = set(), 0, 0.0
    for a in lone:
        if a["key"] in used:
            continue
        best = None
        for b in lone:
            if b["key"] in used or b["key"] == a["key"]:
                continue
            m = geo.minutes(a["d"][1], b["p"][1])
            if m > 45:
                continue
            slack = b["p"][0] - (a["d"][0] + m)
            if 0 <= slack <= 180:  # B was collected after A's drop-off plus the drive, within three hours
                gain = a["fee"] + b["fee"] - PAIR_COST * (a["ref"] + b["ref"])
                if gain > 0 and (best is None or gain > best[0]):
                    best = (gain, b)
        if best:
            used.add(a["key"]); used.add(best[1]["key"])
            pairs += 1; save += best[0]
    r = runs.get(wid, {})
    tot["weeks"] += 1; tot["lone"] += len(lone); tot["chainable"] += 2 * pairs; tot["save"] += save
    tot["lone_fee"] += sum(c["fee"] for c in lone); tot["lone_ref"] += sum(c["ref"] for c in lone)
    print(f"{wid[:10]} {r.get('tag','?'):<12} {r.get('seed','?'):<5} lone cars {len(lone):>3}  chainable {2*pairs:>3}  "
          f"saving if chained EUR {save:>6,.0f}  (week margin {r.get('margin', 0):,.0f})")
w = tot["weeks"] or 1
print(f"\nper week: lone cars {tot['lone']/w:.0f} at {tot['lone_fee']/max(1,tot['lone_ref']):.2f}x typical fee; "
      f"chainable {tot['chainable']/w:.0f}; saving about EUR {tot['save']/w:,.0f} a week")
