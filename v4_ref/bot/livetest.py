"""Rehearse the live final on a practice world: one thread moves the clock, the desk only listens to the stream.

  python3 -m bot.livetest --seed live1 --step 10 --sleep 0.03
"""
from __future__ import annotations

import argparse
import threading
import time

from .env import ROOT  # noqa: F401
from spread.client import Client
from .desk import Params
from .run import parse_set, play_final


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="live1")
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--sleep", type=float, default=0.03)
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--stop", type=int, default=0, help="stop at this world minute")
    ap.add_argument("--restart-at", type=int, default=0, help="drop the desk at this minute and rejoin with a fresh one")
    args = ap.parse_args()
    params = Params(**parse_set(args.set))
    client = Client()
    world = client.create(level=8, seed=args.seed)
    print("world", world.id, flush=True)
    done = threading.Event()
    clock_now = [0]

    def mover():
        c2 = Client()
        w2 = c2.world(world.id)
        snap = w2.snapshot()
        now, ends = snap["now"], snap["endsAt"]
        while now < ends and (not args.stop or now < args.stop):
            now = w2.advance(by=args.step)["now"]
            clock_now[0] = now
            day_hour = (now % 1440) / 60
            time.sleep(args.sleep if 8 <= day_hour < 18.5 else 0.02)
        done.set()

    t = threading.Thread(target=mover, daemon=True)
    t0 = time.time()
    t.start()
    w_clock = Client().world(world.id)
    if args.restart_at:
        play_final(client, world, params, clock=lambda: clock_now[0], stop_at=args.restart_at)
        print("desk dropped at", clock_now[0], "- rejoining", flush=True)
        time.sleep(2)
    play_final(client, world, params, clock=lambda: clock_now[0], stop_at=args.stop)
    t.join()
    import collections, json, os
    from .env import ROOT
    rows = [json.loads(x) for x in open(os.path.join(ROOT, "logs", f"final_{world.id}.jsonl"))]
    print("log kinds", dict(collections.Counter(r["kind"] for r in rows)))
    print("refusals", collections.Counter(r.get("reason", "")[:40] for r in rows if r["kind"] == "refused").most_common(4))
    if args.stop:
        world.delete()
    s = world.score()
    print(f"LIVE {args.seed}: margin €{s['marginCents']/100:,.0f} won {s['wonOrders']} on time {s['onTimeShare']:.1%} "
          f"ranked {s['ranked']} ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
