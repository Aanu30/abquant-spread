"""Offline stress of the three-car paths that a normal replay does not reach: a three that finds no driver and
expires, a deadline warning on one of its cars, a cancelled car, a drop. No server.

  python replay_stress.py EXP_DIR
"""
import collections
import glob
import json
import sys

EXP = sys.argv[1]
sys.path.insert(0, EXP)

from abquant.desk import Desk, Params, load_model   # noqa: E402
from abquant.geo import Geo                         # noqa: E402


class NoWorld:
    def act(self, actions):
        raise RuntimeError("the offline replay has no server")


def replay(path, geo, model):
    w = json.load(open(path, encoding="utf-8"))
    desk = Desk(NoWorld(), 8, 0, Params(triple=True), geo, w["roster"], model, name="stress")
    events = [e for e in w["events"] if e["kind"] in ("price_request", "order_lost") or (e["kind"] == "order_won" and len(e["order"]["legs"]) == 1)]
    end = w["snapshot"]["endsAt"]
    driver = w["roster"][0]["id"]
    i, n, gid, threes = 0, len(events), 0, 0
    count = collections.Counter()
    todo = []                                       # (minute, kind, gig id, fee, order id)
    while True:
        t_event = events[i]["at"] if i < n else None
        timer = desk.next_timer()
        t_todo = min(todo)[0] if todo else None
        times = [t for t in (t_event, timer if timer is not None and timer > desk.now else None, t_todo) if t is not None]
        if not times or min(times) >= end:
            break
        desk.now = max(desk.now, min(times))
        for item in sorted(x for x in todo if x[0] <= desk.now):
            todo.remove(item)
            _, kind, g, fee, oid = item
            post = desk.posts.get(g)
            live = post is not None and any(desk.leg_gigs.get(st["orderId"], {}).get(st["leg"]) == g for st in post["stops"])
            if not live:
                continue
            count[kind] += 1
            if kind == "gig_booked":
                desk.handle({"kind": kind, "gigId": g, "driverId": driver, "feeCents": fee, "at": desk.now})
            elif kind == "gig_dropped":
                desk.handle({"kind": "gig_booked", "gigId": g, "driverId": driver, "feeCents": fee, "at": desk.now})
                desk.handle({"kind": kind, "gigId": g, "driverId": driver, "at": desk.now})
            elif kind == "gig_expired":
                desk.handle({"kind": kind, "gigId": g, "at": desk.now})
            elif kind == "deadline_close":
                desk.handle({"kind": kind, "orderId": oid, "lastPickupAt": desk.orders[oid]["lastPickupAt"], "at": desk.now})
            elif kind == "order_cancelled":
                desk.handle({"kind": kind, "orderId": oid, "gigs": [{"gigId": g, "outcome": "withdrawn"}], "at": desk.now})
        while i < n and events[i]["at"] <= desk.now:
            desk.handle(events[i])
            i += 1
        desk.tick()
        actions, desk.outbox = desk.outbox, []
        results = []
        for a in actions:
            if a["type"] != "post":
                results.append({"ok": True})
                continue
            gid += 1
            g = f"x{gid}"
            ids = list(dict.fromkeys(st["orderId"] for st in a["stops"]))
            count[f"gigs of {len(ids)}"] += 1
            fee = a["schedule"][0]["feeCents"]
            if len(ids) == 3:
                threes += 1
                mode = threes % 5
                if mode == 0:
                    todo.append((desk.now + 10, "gig_booked", g, fee, None))
                elif mode == 1:
                    todo.append((a["stops"][0]["window"]["to"], "gig_expired", g, fee, None))
                elif mode == 2:
                    todo.append((desk.now + 30, "deadline_close", g, fee, ids[1]))
                elif mode == 3:
                    todo.append((desk.now + 20, "order_cancelled", g, fee, ids[2]))
                else:
                    todo.append((desk.now + 15, "gig_dropped", g, fee, None))
                results.append({"ok": threes % 7 != 0, "id": g, "reason": "stress: refused"})      # every seventh is refused by the world
                if threes % 7 == 0:
                    count["threes refused"] += 1
                    results[-1].pop("id")
            else:
                todo.append((desk.now + (60 if len(ids) == 1 else 10), "gig_booked", g, fee, None))
                results.append({"ok": True, "id": g})
        desk.read_results(actions, results)
    # nothing may be stranded: every order still ours and undelivered has a gig or waits in the pool
    stranded = [oid for oid, o in desk.orders.items() if not desk.gigs_of(oid) and oid not in desk.pool]
    count["STRANDED ORDERS"] = len(stranded)
    count["orders"] = len(desk.orders)
    return count


def main():
    geo = Geo(json.load(open(EXP + "/data/map.json", encoding="utf-8")))
    model = load_model()
    total = collections.Counter()
    paths = sorted(glob.glob(EXP + "/../data/worlds/*.json"))
    if not paths:
        sys.exit("No saved weeks found. Play a practice week with --reveal first: its file goes to data/worlds/ of the desk, where these tools look.")
    for path in paths:
        total += replay(path, geo, model)
    print(dict(sorted(total.items())))


if __name__ == "__main__":
    main()
