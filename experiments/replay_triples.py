"""Offline check of the three-car code: no server. Replays the requests and the wins of a saved week through the desk
of experiments, with a stand-in for the world that accepts every post. No gig is ever booked, so this tests the
pool, the matching and the stops only: what would be posted alone, in pairs and in threes.

  python replay_triples.py EXP_DIR WORLD.json [WORLD.json ...]
"""
import collections
import glob
import json
import sys

EXP = sys.argv[1]
sys.path.insert(0, EXP)

import abquant.desk as deskmod                      # noqa: E402
from abquant.desk import Desk, Params, load_model   # noqa: E402
from abquant.geo import DAY, Geo                    # noqa: E402
from abquant.pairs import chain_stops, pair_stops   # noqa: E402


class NoWorld:
    def act(self, actions):
        raise RuntimeError("the offline replay has no server")


CHECK = collections.Counter()


def checked_pair_stops(desk, a, b, now, transfer_max=30, slack=20):
    one = pair_stops(desk, a, b, now, transfer_max, slack)
    two = chain_stops(desk, [a, b], now, transfer_max, slack)
    CHECK["pair calls"] += 1
    if one != two:
        CHECK["MISMATCH"] += 1
        if CHECK["MISMATCH"] <= 3:
            print("MISMATCH", a["id"], b["id"], now, one, two)
    return one


deskmod.pair_stops = checked_pair_stops


def drivable(geo, stops, orders, t0):
    """A driver who leaves the first pickup at t0: are all stops reached inside their windows, by the road minutes?"""
    t, place = t0, None
    for stop in stops:
        leg = orders[stop["orderId"]]["legs"][0]
        here = leg[stop["kind"]]["placeId"]
        if place is not None:
            t += geo.minutes(place, here)
        w = stop["window"]
        t = max(t, w["from"])
        if t > w["to"]:
            return False
        place = here
    return True


def replay(path, geo, model, **settings):
    w = json.load(open(path, encoding="utf-8"))
    desk = Desk(NoWorld(), 8, 0, Params(**settings), geo, w["roster"], model, name="offline")
    events = [e for e in w["events"] if e["kind"] in ("price_request", "order_lost")
              or (e["kind"] == "order_won" and len(e["order"]["legs"]) == 1)]
    end = w["snapshot"]["endsAt"]
    driver = w["roster"][0]["id"]
    i, n, gid = 0, len(events), 0
    count = collections.Counter()
    bookings = []                                  # (minute, gig id, fee): a crude stand-in for the drivers
    wait = {1: 60, 2: 10, 3: 10}                   # minutes until a gig of 1, 2, 3 cars is taken
    while True:
        t_event = events[i]["at"] if i < n else None
        timer = desk.next_timer()
        t_book = min(bookings)[0] if bookings else None
        times = [t for t in (t_event, timer if timer is not None and timer > desk.now else None, t_book) if t is not None]
        if not times or min(times) >= end:
            break
        desk.now = max(desk.now, min(times))
        for item in sorted(b for b in bookings if b[0] <= desk.now):
            bookings.remove(item)
            _, g, fee = item
            post = desk.posts.get(g)
            if post is not None and any(desk.leg_gigs.get(st["orderId"], {}).get(st["leg"]) == g for st in post["stops"]):
                desk.handle({"kind": "gig_booked", "gigId": g, "driverId": driver, "feeCents": fee, "at": desk.now})
                count[f"booked gigs of {len(set(st['orderId'] for st in post['stops']))}"] += 1
        while i < n and events[i]["at"] <= desk.now:
            desk.handle(events[i])
            i += 1
        desk.tick()
        actions, desk.outbox = desk.outbox, []
        results = []
        for a in actions:
            if a["type"] == "post":
                gid += 1
                results.append({"ok": True, "id": f"x{gid}"})
                ids = list(dict.fromkeys(st["orderId"] for st in a["stops"]))
                count[f"gigs of {len(ids)}"] += 1
                bookings.append((desk.now + wait[len(ids)], f"x{gid}", a["schedule"][0]["feeCents"]))
                if len(ids) == 3:
                    stops = a["stops"]
                    lo, hi = stops[0]["window"]["from"], stops[0]["window"]["to"]
                    ok = drivable(geo, stops, desk.orders, lo) and drivable(geo, stops, desk.orders, hi)
                    count["threes drivable" if ok else "THREES NOT DRIVABLE"] += 1
                    if a["schedule"][0]["feeCents"] <= 0 or any(x["feeCents"] > y["feeCents"] for x, y in zip(a["schedule"], a["schedule"][1:])):
                        count["BAD SCHEDULE"] += 1
            else:
                if a["type"] == "withdraw":
                    count["withdrawn"] += 1
                results.append({"ok": True})
        desk.read_results(actions, results)
    for row in desk.log:
        if row["kind"] == "triple":
            count["threes that end where they began"] += bool(row["round_trip"])
            count["threes: planned minutes"] += row["drive"]
        if row["kind"] == "joined":
            count["cars taken down to join"] += 1
    return count


def main():
    geo = Geo(json.load(open(EXP + "/data/map.json", encoding="utf-8")))
    model = load_model()
    paths = sys.argv[2:]
    total = {"off": collections.Counter(), "on": collections.Counter()}
    for path in paths:
        for name, settings in (("off", {}), ("on", {"triple": True})):
            c = replay(path, geo, model, **settings)
            total[name] += c
            print(path[-26:-5], name, dict(sorted(c.items())))
    n = len(paths)
    for name in total:
        print(name, "per week:", {k: round(v / n, 1) for k, v in sorted(total[name].items())})
    print("pair_stops against chain_stops for two cars:", dict(CHECK))


if __name__ == "__main__":
    main()
