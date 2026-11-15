"""Moves a practice world's clock the way the final's clock moves, for rehearsals.

The final's clock (API.md): 18 real seconds an hour from 06:00 to 22:00 on weekdays, 6 on Saturday, 9 on the last
Monday, and 3 at night, on Sunday, and from the last Monday 22:00 to the end. About 34 minutes in all.

  python -m abquant.clock --seed r1 --fast 2      # creates a practice world, prints its id, and moves its clock
  python -m abquant.clock --world WORLD_ID        # moves the clock of an existing practice world
"""
from __future__ import annotations

import argparse
import threading
import time

from .env import load_key

load_key()
from spread.client import Client, SpreadError  # noqa: E402

DAY = 1440


def seconds_per_hour(now: int) -> float:
    day, hour = now // DAY, (now % DAY) / 60
    if now >= 7 * DAY + 22 * 60 or not 6 <= hour < 22 or day % 7 == 6:
        return 3.0
    if day == 7:
        return 9.0
    if day % 7 == 5:
        return 6.0
    return 18.0


def move(world_id: str, fast: float = 1.0, stop_at: int = 0, running: threading.Event = None) -> None:
    """Steps the clock in whole minutes so that each step takes about a fifth of a second of real time."""
    world = Client().world(world_id)
    snapshot = world.snapshot()
    now, ends = snapshot["now"], snapshot["endsAt"]
    if stop_at:
        ends = min(ends, stop_at)
    due = time.time()
    while now < ends and (running is None or running.is_set()):
        per_minute = seconds_per_hour(now) / 60 / fast
        step = max(1, min(30, int(0.2 / per_minute)))
        step = min(step, ends - now, 60 - now % 60)          # never across an hour: the speed may change there
        try:
            now = world.advance(by=step)["now"]
        except SpreadError as error:
            print("clock:", error, flush=True)
            time.sleep(1)
            continue
        due += step * per_minute
        time.sleep(max(0.0, due - time.time()))
        if due < time.time() - 2:                            # fell behind (a slow server): do not try to catch up
            due = time.time()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="")
    ap.add_argument("--world", default="")
    ap.add_argument("--fast", type=float, default=1.0)
    ap.add_argument("--stop", type=int, default=0)
    args = ap.parse_args()
    if args.world:
        world_id = args.world
    else:
        world_id = Client().create(level=8, seed=args.seed or None).id
    print(world_id, flush=True)
    move(world_id, args.fast, args.stop)
    print("clock done", flush=True)


if __name__ == "__main__":
    main()
