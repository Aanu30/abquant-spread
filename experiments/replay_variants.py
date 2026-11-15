import collections, glob, json, sys
EXP = sys.argv[1]
sys.path.insert(0, EXP)
import importlib.util
spec = importlib.util.spec_from_file_location("replay_triples", __file__.replace("replay_variants", "replay_triples"))
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
from abquant.geo import Geo
from abquant.desk import load_model
geo = Geo(json.load(open(EXP + "/data/map.json")))
model = load_model()
paths = sorted(glob.glob(EXP + "/../data/worlds/*.json"))
if not paths:
    sys.exit("No saved weeks found. Play a practice week with --reveal first: its file goes to data/worlds/ of the desk, where these tools look.")
variants = [("f3 (hop 45)", {}), ("long hauls up to 400 min may wait", {"pool_long": 400}),
            ("long hauls up to 400: a partner now, or alone now", {"pool_long": 400, "pool_long_now": True})]
print(f"{'variant':<44}{'alone':>7}{'pairs':>7}{'threes':>7}{'cars alone %':>14}")
for name, settings in variants:
    tot = collections.Counter()
    for path in paths:
        tot += rt.replay(path, geo, model, **settings)
    n = len(paths)
    one, two, three = tot["gigs of 1"] / n, tot["gigs of 2"] / n, tot["gigs of 3"] / n
    print(f"{name:<44}{one:>7.1f}{two:>7.1f}{three:>7.1f}{one / (one + 2 * two + 3 * three):>14.1%}" + ("  NOT DRIVABLE: %d" % tot["THREES NOT DRIVABLE"] if tot["THREES NOT DRIVABLE"] else ""))
print("pair_stops vs chain_stops:", dict(rt.CHECK))
