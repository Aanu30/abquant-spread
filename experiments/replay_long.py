"""Offline: which pairs form when long hauls may wait for a partner (pool_long). No server.

  python replay_long.py EXP_DIR [pool_long=400]
"""
import collections
import glob
import json
import statistics as st
import sys

EXP = sys.argv[1]
sys.path.insert(0, EXP)
import importlib.util
spec = importlib.util.spec_from_file_location("replay_triples", EXP + "/replay_triples.py")
sys.argv = [sys.argv[0], EXP] + sys.argv[2:]
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
from abquant.desk import Desk, load_model
from abquant.geo import DAY, Geo

limit = int(sys.argv[2]) if len(sys.argv) > 2 else 400
geo = Geo(json.load(open(EXP + "/data/map.json")))
model = load_model()
rows = []
orig = Desk.post_pair
def post_pair(self, a, b, plan):
    da = self.geo.minutes(a["legs"][0]["pickup"]["placeId"], a["legs"][0]["delivery"]["placeId"])
    db = self.geo.minutes(b["legs"][0]["pickup"]["placeId"], b["legs"][0]["delivery"]["placeId"])
    lo = plan[0][0]["window"]["from"]
    wait = lo - self.now
    rows.append({"da": da, "db": db, "total": plan[1], "loop": plan[2], "start": lo % DAY, "posted": self.now % DAY, "lead": wait,
                 "width": plan[0][0]["window"]["to"] - lo})
    return orig(self, a, b, plan)
Desk.post_pair = post_pair
paths = sorted(glob.glob(EXP + "/../data/worlds/*.json"))
if not paths:
    sys.exit("No saved weeks found. Play a practice week with --reveal first: its file goes to data/worlds/ of the desk, where these tools look.")
for path in paths:
    rt.replay(path, geo, model, pool_long=limit)
n = len(paths)
longs = [r for r in rows if max(r["da"], r["db"]) >= 240]
print(f"pairs a week: {len(rows) / n:.1f}; with a long haul: {len(longs) / n:.1f}; both long: {sum(1 for r in longs if min(r['da'], r['db']) >= 240) / n:.1f}; loops among them: {sum(r['loop'] for r in longs) / n:.1f}")
print("long haul first:", f"{sum(1 for r in longs if r['da'] >= 240) / max(1, len(longs)):.0%}")
tot = sorted(r["total"] for r in longs)
print("planned minutes: median", st.median(tot), "quartiles", tot[len(tot) // 4], tot[3 * len(tot) // 4], "max", tot[-1])
b = collections.Counter("under 360" if t < 360 else "360-450" if t < 450 else "450-540" if t < 540 else "540-690" for t in tot)
print("by planned minutes:", {k: f"{v / len(tot):.0%}" for k, v in b.items()})
print("first pickup window opens at (median):", "%02d:%02d" % divmod(int(st.median(r["start"] for r in longs)), 60), "| window width median", st.median(r["width"] for r in longs), "min")
print("posted at (clock):", collections.Counter("17:30 batch" if 1045 <= r["posted"] <= 1060 else "other" for r in longs))
print("minutes from posting to the first pickup window (median):", st.median(r["lead"] for r in longs))
other = sorted(min(r["da"], r["db"]) for r in longs)
print("the other car's drive: median", st.median(other), "quartiles", other[len(other) // 4], other[3 * len(other) // 4])
