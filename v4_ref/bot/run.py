"""Run the desk on practice seeds (in parallel), a ranking run, or the live final.

  python3 -m bot.run --seeds 8 --level 8 --tag v1            # seeds s1..s8
  python3 -m bot.run --seeds a,b,c --set fee_open=1.4 --tag x
  python3 -m bot.run --board                                  # next ranking run, level 8
  python3 -m bot.run --final                                  # the live final (or a test final)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, fields

from .env import ROOT
from spread.client import Client, SpreadError, Unreachable
from .desk import Desk, Params
from .geo import DAY, Geo

WAKE_ON = ["price_request", "order_won", "order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close"]
LOGS = os.path.join(ROOT, "logs")
os.makedirs(LOGS, exist_ok=True)


def parse_set(items: list) -> dict:
    types = {f.name: f.type for f in fields(Params)}
    out = {}
    for item in items or []:
        k, v = item.split("=", 1)
        t = types[k]
        out[k] = (v.lower() in ("1", "true", "yes")) if t in (bool, "bool") else (int(v) if t in (int, "int") else float(v))
    return out


def play_practice(client: Client, seed: str, level: int, params: Params, tag: str, board: bool = False) -> dict:
    world = client.create(level=level, seed=None if board else seed, board=board)
    geo = Geo(client.map())
    try:
        snap = world.snapshot()
        roster = world.roster()
        desk = Desk(world, level, snap["now"], params, geo, roster, name=tag)
        ends = snap["endsAt"]
        t0 = time.time()
        while desk.now < ends:
            midnight = (desk.now // DAY + 1) * DAY
            actions, desk.outbox = desk.outbox, []
            for attempt in range(30):
                try:
                    step = world.advance(until=WAKE_ON + ["delivered"] if params.chain else WAKE_ON, max=min(ends, midnight), actions=actions)
                    break
                except Unreachable:
                    time.sleep(5)
                    actions = []  # the server may have applied them; quotes and posts are not resent
            else:
                raise Unreachable(0, "server unreachable for 150 s")
            desk.read_results(actions, step["results"])
            desk.now = step["now"]
            for event in step["events"]:
                desk.handle(event)
        score = world.score()
    except BaseException:
        if not board:
            try:
                world.delete()
            except SpreadError:
                pass
        raise
    out = {"tag": tag, "seed": seed, "level": level, "world": world.id, "secs": round(time.time() - t0, 1),
           "margin": score["marginCents"] / 100, "revenue": score["revenueCents"] / 100, "won": score["wonOrders"],
           "ontime": round(score["onTimeShare"], 4), "undelivered": round(score["undeliveredShare"], 4), "ranked": score["ranked"],
           "quotes": sum(1 for x in desk.log if x["kind"] == "quote"), "declines": sum(1 for x in desk.log if x["kind"] == "decline"),
           "refused": sum(1 for x in desk.log if x["kind"] == "refused")}
    with open(os.path.join(LOGS, f"{tag}__{seed}__{world.id}.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"summary": out, "params": asdict(params)}) + "\n")
        for row in desk.log:
            f.write(json.dumps(row) + "\n")
    with open(os.path.join(ROOT, "data", "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({**out, "params": asdict(params)}) + "\n")
    return out


def run_seeds(seeds: list, level: int, params: Params, tag: str, parallel: int) -> list:
    results = []

    def one(seed):
        return play_practice(Client(), seed, level, params, tag)

    with cf.ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {ex.submit(one, s): s for s in seeds}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                r = fut.result()
                results.append(r)
                print(f"{tag:<14} {s:<10} margin €{r['margin']:>10,.0f}  won {r['won']:>4}  on time {r['ontime']:.1%}  "
                      f"undeliv {r['undelivered']:.1%}  quotes {r['quotes']:>4}  ranked {r['ranked']}  ({r['secs']}s)", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"{tag:<14} {s:<10} FAILED: {e}", flush=True)
                traceback.print_exc()
    if results:
        n = len(results)
        m = sum(r["margin"] for r in results) / n
        ot = min(r["ontime"] for r in results)
        rk = sum(1 for r in results if r["ranked"])
        print(f"== {tag}: mean margin €{m:,.0f}/week over {n} seeds, worst on-time {ot:.1%}, ranked {rk}/{n}", flush=True)
    return results


# ---------------------------------------------------------------------------- the live final
def next_final(client: Client):
    said = False
    while True:
        try:
            world = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status != 404:
                raise
            world = None
        if world is not None:
            snap = world.snapshot()
            if snap["now"] < snap["endsAt"]:
                return world
        if not said:
            print("No final is set yet; waiting.", flush=True)
            said = True
        time.sleep(5)


def play_final(client: Client, world, params: Params, clock=None, level: int = 8, stop_at: int = 0) -> None:
    """Live play. A reader thread moves stream events into a queue; the main loop drains every queued event,
    handles them in order, and sends one batch of actions. Restart-safe: state is rebuilt from the world."""
    import queue
    import threading

    state_path = os.path.join(LOGS, f"final_state_{world.id}.json")
    history = world.events()
    snap = world.snapshot()
    if snap["now"] >= snap["endsAt"]:
        return
    geo = Geo(client.map())
    roster = world.roster()
    desk = Desk(world, level, snap["now"], params, geo, roster, name="final")
    desk.load_state(state_path)
    desk.rejoin(snap, history)
    desk.send()
    last_seq = history[-1]["seq"] if history else -1
    q: "queue.Queue" = queue.Queue()
    stop = threading.Event()

    def reader():
        try:
            for ev in world.stream(after=last_seq, idle=1.0):
                if stop.is_set():
                    return
                if ev is not None:
                    q.put(ev)
        except BaseException as e:  # noqa: BLE001
            q.put(e)

    threading.Thread(target=reader, daemon=True).start()
    last_save, last_clock = time.time(), 0.0
    log_path = os.path.join(LOGS, f"final_{world.id}.jsonl")
    logged, worst, n_batches = 0, 0.0, 0
    try:
        while True:
            try:
                first = q.get(timeout=1.0)
                batch = [first]
            except queue.Empty:
                batch = []
            while True:
                try:
                    batch.append(q.get_nowait())
                except queue.Empty:
                    break
            t0 = time.time()
            day = desk.now // DAY
            for ev in batch:
                if isinstance(ev, BaseException):
                    raise ev
                if ev["seq"] <= last_seq:
                    continue  # a repeat after a reconnect or restart
                last_seq = ev["seq"]
                desk.now = max(desk.now, ev["at"])
                desk.handle(ev)
            if not batch and time.time() - last_clock > 1.0:
                try:
                    desk.now = max(desk.now, clock() if clock else client.final()["now"])
                except SpreadError:
                    pass
                last_clock = time.time()
            desk.send()
            if any(not isinstance(e, BaseException) and e["kind"] == "price_request" for e in batch):
                dt = time.time() - t0
                worst = max(worst, dt)
                n_batches += 1
            if time.time() - last_save > 5:
                desk.save_state(state_path)
                last_save = time.time()
                with open(log_path, "a", encoding="utf-8") as f:
                    for row in desk.log[logged:]:
                        f.write(json.dumps(row) + "\n")
                logged = len(desk.log)
            if desk.now // DAY > day:
                try:
                    s = world.score()
                    print(f"day {day}: margin €{s['marginCents']/100:,.0f} won {s['wonOrders']} on time {s['onTimeShare']:.1%}"
                          f"  (slowest quote batch {worst*1000:.0f} ms over {n_batches})", flush=True)
                except SpreadError:
                    pass
            if desk.now >= snap["endsAt"] or (stop_at and desk.now >= stop_at):
                return
    finally:
        stop.set()
        desk.save_state(state_path)
        with open(log_path, "a", encoding="utf-8") as f:
            for row in desk.log[logged:]:
                f.write(json.dumps(row) + "\n")
        print(f"live loop ended at minute {desk.now}; slowest quote batch {worst*1000:.0f} ms", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--seeds", default="4", help="a number n (seeds s1..sn) or a comma list")
    ap.add_argument("--prefix", default="s")
    ap.add_argument("--tag", default="dev")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--board", action="store_true")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()
    params = Params(**parse_set(args.set))
    client = Client()
    if args.final:
        world = None
        while True:
            try:
                if world is None:
                    world = next_final(client)
                    print(f"Final world {world.id}", flush=True)
                play_final(client, world, params)
                s = world.score()
                print(f"END margin €{s['marginCents']/100:,.2f} won {s['wonOrders']} on time {s['onTimeShare']:.1%} ranked {s['ranked']}")
                break
            except (Unreachable, OSError) as e:
                print(f"connection problem: {e}; rejoining in 3 s", file=sys.stderr, flush=True)
                time.sleep(3)
            except Exception as e:  # noqa: BLE001  never die in the final
                traceback.print_exc()
                print(f"error: {e}; rejoining in 3 s", file=sys.stderr, flush=True)
                time.sleep(3)
        return
    if args.board:
        r = play_practice(client, "board", args.level, params, args.tag, board=True)
        print(r)
        return
    seeds = [f"{args.prefix}{i}" for i in range(1, int(args.seeds) + 1)] if args.seeds.isdigit() else args.seeds.split(",")
    run_seeds(seeds, args.level, params, args.tag, args.parallel)


if __name__ == "__main__":
    main()
