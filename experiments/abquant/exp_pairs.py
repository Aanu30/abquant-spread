"""A fork experiment: do drivers take two cars in one gig for less than two single fees?

The desk plays a practice week up to a chosen minute, holding back the orders it wins in the last stretch. The held
orders are matched into pairs (the second car starts within 30 minutes' drive of where the first ends). The world is
then copied once per arm with `fork`, which keeps the same future: one arm posts the paired cars as singles at
0.9 x typical, the others post them as two-car gigs at a share of the two typical fees. Each copy runs on for a few
hours with no further action, and the bookings are compared.

  python -m abquant.exp_pairs --seed t1 --hold-from 560 --until 690 --watch 300 --ratios 0.65,0.8,0.95
"""
from __future__ import annotations

import argparse
import time

from .env import load_key

load_key()
from spread.client import Client, SpreadError  # noqa: E402
from spread.starter import Retry  # noqa: E402

from .desk import Desk, Params, load_model  # noqa: E402
from .geo import Geo, clock  # noqa: E402
from .pairs import pair_audience, pair_stops  # noqa: E402
from .run import WAKE_ON, advance, world_map  # noqa: E402


class HoldDesk(Desk):
    holding = False

    def win(self, order: dict) -> None:
        if self.holding and len(order["legs"]) == 1:
            self.orders[order["id"]] = order
            self.held.append(order)
        else:
            super().win(order)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="t1")
    ap.add_argument("--hold-from", type=int, default=560)
    ap.add_argument("--until", type=int, default=690)
    ap.add_argument("--watch", type=int, default=300)
    ap.add_argument("--ratios", default="0.65,0.8,0.95")
    args = ap.parse_args()
    client = Client()
    geo = Geo(world_map(client))
    world = client.create(level=8, seed=args.seed)
    forks = []
    try:
        snapshot = world.snapshot()
        desk = HoldDesk(world, 8, snapshot["now"], Params(), geo, world.roster(), load_model(), name="exp")
        desk.held = []
        while desk.now < args.until:
            desk.holding = desk.now >= args.hold_from
            actions, desk.outbox = desk.outbox, []
            step = advance(world, WAKE_ON, args.until, actions)
            desk.read_results(actions, step["results"])
            desk.now = step["now"]
            for event in step["events"]:
                desk.holding = event["at"] >= args.hold_from
                desk.handle(event)
            desk.tick()
        actions, desk.outbox = desk.outbox, []
        if actions:
            desk.read_results(actions, world.act(actions))
        now = desk.now
        held = [o for o in desk.held if o["id"] in desk.orders]
        # greedy matching: round trips first, then the shortest total drive
        options = []
        for a in held:
            for b in held:
                plan = pair_stops(desk, a, b, now)
                if plan:
                    options.append((0 if plan[2] else 1, plan[1], a["id"], b["id"], plan))
        used, pairs = set(), []
        for _, _, ia, ib, plan in sorted(options, key=lambda x: (x[0], x[1])):
            if ia not in used and ib not in used:
                used |= {ia, ib}
                pairs.append((desk.orders[ia], desk.orders[ib], plan))
        print(f"{clock(now)}: held {len(held)} orders, {len(options)} feasible ordered pairs, matched {len(pairs)} pairs "
              f"({sum(1 for p in pairs if p[2][2])} round trips)", flush=True)
        if not pairs:
            return
        ref = lambda o: desk.requests[o["id"]]["referenceFeeCents"]  # noqa: E731
        arms = [("singles at 0.90", None)] + [(f"pairs at {float(r):.2f}", float(r)) for r in args.ratios.split(",")]
        for label, ratio in arms:
            fork = world.fork()
            forks.append(fork)
            posts, meta = [], []
            for a, b, (stops, drive, round_trip) in pairs:
                if ratio is None:
                    for o in (a, b):
                        facts = desk.facts_of(desk.requests[o["id"]])
                        posts.append({"type": "post", "stops": desk.stops_for(o, [0], Retry()),
                                      "audience": {"experienced": any(l["car"]["premium"] for l in o["legs"]), "manualLicence": bool(facts.manual)},
                                      "schedule": [{"at": now, "feeCents": int(0.9 * ref(o))}]})
                        meta.append((1, ref(o)))
                else:
                    posts.append({"type": "post", "stops": stops, "audience": pair_audience(desk, a, b),
                                  "schedule": [{"at": now, "feeCents": int(ratio * (ref(a) + ref(b)))}]})
                    meta.append((2, ref(a) + ref(b)))
            results = fork.act(posts)
            gigs = {r["id"]: m for r, m in zip(results, meta) if r["ok"]}
            refused = [r["reason"] for r in results if not r["ok"]]
            step = fork.advance(by=args.watch)
            booked = {}
            for e in step["events"]:
                if e["kind"] == "gig_booked" and e["gigId"] in gigs and e["at"] >= now:
                    booked.setdefault(e["gigId"], e)
                if e["kind"] in ("gig_dropped", "no_show") and e["gigId"] in gigs:
                    booked.pop(e["gigId"], None)
            cars = sum(m[0] for m in gigs.values())
            cars_booked = sum(gigs[g][0] for g in booked)
            fees = sum(e["feeCents"] for e in booked.values())
            typical = sum(gigs[g][1] for g in booked)
            waits = sorted(e["at"] - now for e in booked.values())
            print(f"   {label:16} cars posted {cars:3d}  booked within {args.watch} min: {cars_booked:3d} ({cars_booked / max(1, cars):.0%})  "
                  f"fee paid / typical {fees / max(1, typical):.2f}  median wait {waits[len(waits) // 2] if waits else '-'} min"
                  + (f"  refused {len(refused)}: {refused[0][:90]}" if refused else ""), flush=True)
            fork.delete()
            forks.remove(fork)
    finally:
        for w in forks + [world]:
            try:
                w.delete()
            except SpreadError:
                pass


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"({time.time() - t0:.0f} s)")
