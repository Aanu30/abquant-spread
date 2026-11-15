"""Plays practice weeks with the ABQuant desk, a few at a time, and records each week.

  python -m abquant.run --seeds t1,t2 --tag v1                 # named seeds (the same seed is the same week)
  python -m abquant.run --n 6 --prefix t --tag v1 --set f_open=0.95 pi_max=0.12
  python -m abquant.run --n 2 --prefix t --tag v1 --reveal     # also save each week's reveal for fitting

At most 4 weeks run at once: the team key is shared with another build.
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

from .env import DATA, LOGS, load_key

load_key()
from spread.client import Client, SpreadError, Unreachable  # noqa: E402

from .desk import Desk, Params, load_model  # noqa: E402
from .geo import DAY, Geo  # noqa: E402

WAKE_ON = ["price_request", "order_won", "order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close", "gig_dropped", "no_show"]
MAX_PARALLEL = 4


def parse_set(items: list) -> dict:
    types = {f.name: f.type for f in fields(Params)}
    out = {}
    for item in items or []:
        k, v = item.split("=", 1)
        t = types[k]
        out[k] = (v.lower() in ("1", "true", "yes")) if t in (bool, "bool") else int(v) if t in (int, "int") else float(v)
    return out


def world_map(client: Client) -> dict:
    path = os.path.join(DATA, "map.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(client.map(), f)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def advance(world, wake: list, until: int, actions: list) -> dict:
    """One step of the practice clock. A server restart is waited out; actions it may have applied are not resent.
    If the server rejects the batch (one malformed action), the actions go one by one so the rest still land."""
    for _ in range(40):
        try:
            return world.advance(until=wake, max=until, actions=actions)
        except Unreachable:
            time.sleep(5)
            actions = []
        except SpreadError as error:
            if error.status != 400 or not actions:
                raise
            results = []
            for action in actions:
                try:
                    results += world.act([action])
                except SpreadError as one:
                    results.append({"ok": False, "reason": f"rejected: {one}"})
            step = world.advance(until=wake, max=until)
            return {**step, "results": results}
    raise Unreachable(0, "server unreachable for 200 s")


def play(seed: str, level: int, params: Params, tag: str, model: dict, reveal: bool = False, board: bool = False) -> dict:
    client = Client()
    geo = Geo(world_map(client))
    world = client.create(level=level, seed=None if board else seed, board=board)
    started = time.time()
    try:
        snapshot = world.snapshot()
        desk = Desk(world, level, snapshot["now"], params, geo, world.roster(), model, name=tag)
        ends = snapshot["endsAt"]
        while desk.now < ends:
            limit = min(ends, (desk.now // DAY + 1) * DAY)
            timer = desk.next_timer() if params.timers else None
            if timer is not None and timer > desk.now:
                limit = min(limit, timer)                 # the live loop acts on the minute: the practice loop must too
            actions, desk.outbox = desk.outbox, []
            step = advance(world, WAKE_ON, limit, actions)
            desk.read_results(actions, step["results"])
            for action, result in zip(actions, step["results"]):
                if not result["ok"]:
                    desk.log.append({"t": desk.now, "kind": "refused", "action": action["type"], "reason": result["reason"]})
            desk.now = step["now"]
            for event in step["events"]:
                desk.handle(event)
            desk.tick()
        score = world.score()
    except BaseException:
        if not board:
            try:
                world.delete()
            except SpreadError:
                pass
        raise
    kinds = {}
    for row in desk.log:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    out = {"tag": tag, "seed": seed, "level": level, "world": world.id, "secs": round(time.time() - started, 1),
           "margin": score["marginCents"] / 100, "revenue": score["revenueCents"] / 100, "won": score["wonOrders"],
           "ontime": round(score["onTimeShare"], 4), "undelivered": round(score["undeliveredShare"], 4), "ranked": score["ranked"],
           "quotes": kinds.get("quote", 0), "declines": kinds.get("decline", 0), "refused": kinds.get("refused", 0),
           "offers": kinds.get("offer", 0), "theta": round(desk.level_est.world_level(), 3),
           "trust_end": dict(desk.trust.most_common(6)), "ledger": {k: round(v / 100) for k, v in desk.ledger.items()},
           "rescues": sum(1 for row in desk.log if row["kind"] == "fees" and row["urgent"]), "why": dict(desk.why.most_common()), "regime": desk.regime.history,
           "level_parts": {"|".join(map(str, k)): round(v, 4) for k, v in desk.level_est.m.items() if k[0] in ("from", "to", "dealer", "world")},
           "offer_answers": {a: sum(1 for row in desk.log if row["kind"] == "offer_answer" and row["answer"] == a) for a in ("accepted", "declined", "expired")}}
    with open(os.path.join(LOGS, f"{tag}__{seed}__{world.id}.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"summary": out, "params": asdict(params)}) + "\n")
        for row in desk.log:
            f.write(json.dumps(row) + "\n")
    with open(os.path.join(DATA, "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({**out, "params": asdict(params)}) + "\n")
    if reveal and not board:
        os.makedirs(os.path.join(DATA, "worlds"), exist_ok=True)
        full = {"reveal": world.reveal(), "events": world.events(), "snapshot": world.snapshot(), "roster": world.roster()}
        with open(os.path.join(DATA, "worlds", f"{world.id}.json"), "w", encoding="utf-8") as f:
            json.dump(full, f)
    return out


def run(seeds: list, level: int, params: Params, tag: str, parallel: int, reveal: bool, board: bool = False) -> list:
    model, results = load_model(), []
    with cf.ThreadPoolExecutor(max_workers=1 if board else min(parallel, MAX_PARALLEL)) as pool:
        futures = {pool.submit(play, s, level, params, tag, model, reveal, board): s for s in seeds}
        for fut in cf.as_completed(futures):
            s = futures[fut]
            try:
                r = fut.result()
                results.append(r)
                print(f"{tag:<10} {s:<8} margin €{r['margin']:>9,.0f}  won {r['won']:>4}  on time {r['ontime']:.1%}  undeliv {r['undelivered']:.1%}  "
                      f"quotes {r['quotes']:>4}  rescues {r['rescues']:>3}  level {r['theta']:.2f}  ranked {r['ranked']}  ({r['secs']}s)  "
                      f"fees €{-r['ledger'].get('driver_fee', 0):,} refunds €{-r['ledger'].get('late_refund', 0):,} trust {r['trust_end']}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"{tag:<10} {s:<8} FAILED: {e}", flush=True)
                traceback.print_exc()
    if results:
        n = len(results)
        print(f"== {tag}: mean margin €{sum(r['margin'] for r in results) / n:,.0f}/week over {n} weeks, mean won {sum(r['won'] for r in results) / n:.0f}, "
              f"worst on-time {min(r['ontime'] for r in results):.1%}, ranked {sum(1 for r in results if r['ranked'])}/{n}", flush=True)
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--seeds", default="")
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--prefix", default="t")
    ap.add_argument("--tag", default="dev")
    ap.add_argument("--parallel", type=int, default=MAX_PARALLEL)
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--reveal", action="store_true")
    ap.add_argument("--board", type=int, default=0, help="play this many ranking runs of the current round, one after another")
    args = ap.parse_args()
    # runs are recorded as fb_<tag>; the bake-off script of the other build looks for its own tag, so "bake..." stays as given
    tag = args.tag if args.tag.startswith(("fb_", "bake")) else "fb_" + args.tag
    if args.board:
        run([f"board{i}" for i in range(1, args.board + 1)], args.level, Params(**parse_set(args.set)), tag, 1, False, board=True)
        return
    seeds = args.seeds.split(",") if args.seeds else [f"{args.prefix}{i}" for i in range(1, args.n + 1)]
    if not seeds:
        sys.exit("give --seeds a,b or --n 6")
    run(seeds, args.level, Params(**parse_set(args.set)), tag, args.parallel, args.reveal)


if __name__ == "__main__":
    main()
