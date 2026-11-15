"""The live final, and a rehearsal of it on a practice world.

  python -m abquant.live --final                    # plays the team's copy of the final; never exits on an error
  python -m abquant.live --rehearse r1              # a practice world whose clock a second thread moves at the final's speeds
  python -m abquant.live --rehearse r1 --fast 3     # the same, three times faster
  python -m abquant.live --world WORLD_ID           # joins a world whose clock something else moves (abquant.clock)

In the final the clock moves by itself: 18 real seconds an hour by day, so a quote window of 15 minutes is 4.5 seconds,
and 1.5 seconds on Saturday. The loop therefore does one thing: a reader thread puts stream events in a queue; the main
loop takes every event that has arrived, lets the desk answer them in order, and sends one batch of actions.

It is built to keep going:
- The desk's whole state is saved to disk every few seconds. After any stop the process loads it, reads the events it
  missed, checks itself against the world's snapshot, and carries on. With no saved state it rebuilds from the history.
- A fault in the answer to one event is logged and that event is skipped. The loop does not stop.
- A send that gets no answer keeps its actions. The loop then reads the world's state before it acts again.
- Twice a minute the books are checked against the world. A difference that stays is repaired from the snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import queue
import sys
import threading
import time
import traceback

from .env import DATA, LOGS, load_key

load_key()
from spread.client import Client, SpreadError  # noqa: E402

from .clock import move  # noqa: E402
from .desk import Desk, Params, load_model  # noqa: E402
from .geo import DAY, Geo, clock  # noqa: E402
from .run import parse_set, world_map  # noqa: E402

SAVE_EVERY = 4.0      # real seconds between state saves
AUDIT_EVERY = 30.0    # real seconds between checks of the books against the world
CLOCK_EVERY = 1.0     # real seconds between reads of the clock while no event comes


def state_path(world_id: str) -> str:
    return os.path.join(DATA, f"live_state_{world_id}.pkl")


def save_state(desk: Desk, last_seq: int) -> None:
    world, desk.world = desk.world, None                 # the connection is not part of the state
    try:
        blob = pickle.dumps({"desk": desk, "last_seq": last_seq})
    finally:
        desk.world = world
    tmp = state_path(world.id) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, state_path(world.id))                # atomic: a crash mid-write leaves the old state


def load_state(world):
    path = state_path(world.id)
    if not os.path.exists(path):
        return None, -1
    try:
        with open(path, "rb") as f:
            saved = pickle.load(f)
        saved["desk"].world = world
        return saved["desk"], saved["last_seq"]
    except Exception:                                    # noqa: BLE001  a damaged file is the same as none
        traceback.print_exc()
        return None, -1


def fault(label: str, what: str) -> None:
    """A fault in the desk's own code: written down, never fatal."""
    text = f"[{time.strftime('%H:%M:%S')}] {label}: {what}\n{traceback.format_exc()}\n"
    sys.stderr.write(text)
    with open(os.path.join(LOGS, "live_faults.log"), "a", encoding="utf-8") as f:
        f.write(text)


def start_reader(world, after: int, events: "queue.Queue", stop: threading.Event) -> threading.Thread:
    def read() -> None:
        try:
            for event in world.stream(after=after, idle=1.0):
                if stop.is_set():
                    return
                if event is not None:
                    events.put(event)
            events.put(EOFError("the stream ended"))
        except BaseException as error:                   # noqa: BLE001  the main loop starts a new reader
            events.put(error)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    return thread


def play(client: Client, world, params: Params, level: int = 8, is_final: bool = True, stop_at: int = 0, label: str = "final") -> dict:
    """Plays a world whose clock moves by itself, from wherever it is now, until it ends."""
    snapshot = world.snapshot()
    ends = snapshot["endsAt"]
    if snapshot["now"] >= ends:
        return world.score()
    desk, last_seq = load_state(world)
    if desk is None:
        geo = Geo(world_map(client))
        desk = Desk(world, level, snapshot["now"], params, geo, world.roster(), load_model(), name=label)
        history = world.events()
        desk.now = snapshot["now"]
        desk.rebuild(snapshot, history)
        last_seq = history[-1]["seq"] if history else -1
        print(f"[{label}] started fresh at {clock(snapshot['now'])}, {len(history)} events of history", flush=True)
    else:
        missed = world.events(after=last_seq)
        desk.now = max(desk.now, snapshot["now"])
        for event in missed:
            try:
                desk.handle(event)
            except Exception:                            # noqa: BLE001
                fault(label, f"event {event.get('kind')} seq {event.get('seq')} while catching up")
            last_seq = max(last_seq, event["seq"])
        try:
            desk.tick()
            desk.reconcile(world.snapshot())
        except Exception:                                # noqa: BLE001
            fault(label, "reconcile after a restart")
        print(f"[{label}] resumed from saved state at {clock(snapshot['now'])}, {len(missed)} events missed", flush=True)
    desk.send()

    def read_clock() -> int:
        return client.final()["now"] if is_final else world.snapshot()["now"]

    events: "queue.Queue" = queue.Queue()
    stop = threading.Event()
    start_reader(world, last_seq, events, stop)
    log_path = os.path.join(LOGS, f"live_{label}_{world.id}.jsonl")
    logged, day = 0, desk.now // DAY
    saved_at = audit_at = clock_at = time.time()
    drift_before: set = set()
    stats = {"batches": 0, "quote_batches": 0, "slowest_quote_ms": 0.0, "slowest_think_ms": 0.0, "slowest_send_ms": 0.0, "slowest_save_ms": 0.0,
             "largest_batch": 0, "faults": 0, "repairs": 0, "readers": 1, "send_failures": 0}
    try:
        while True:
            try:
                batch = [events.get(timeout=0.25)]
            except queue.Empty:
                batch = []
            while True:
                try:
                    batch.append(events.get_nowait())
                except queue.Empty:
                    break
            t0, quotes = time.time(), False
            for event in batch:
                if isinstance(event, BaseException):     # the reader stopped: start another from the last event seen
                    print(f"[{label}] stream reader stopped ({event}); starting a new one", flush=True)
                    time.sleep(1.0)
                    start_reader(world, last_seq, events, stop)
                    stats["readers"] += 1
                    continue
                if event["seq"] <= last_seq:
                    continue                             # a repeat after a reconnect
                last_seq = event["seq"]
                desk.now = max(desk.now, event["at"])
                quotes = quotes or event["kind"] == "price_request"
                try:
                    desk.handle(event)
                except Exception:                        # noqa: BLE001
                    stats["faults"] += 1
                    fault(label, f"event {event.get('kind')} seq {event.get('seq')}")
            if not batch and time.time() - clock_at > CLOCK_EVERY:
                clock_at = time.time()
                try:
                    desk.now = max(desk.now, read_clock())
                except SpreadError:
                    pass
            try:
                desk.tick()
            except Exception:                            # noqa: BLE001
                stats["faults"] += 1
                fault(label, "tick")
            t1 = time.time()
            desk.send()
            t2 = time.time()
            if desk.sync_needed:
                stats["send_failures"] += 1
            if batch:
                stats["batches"] += 1
                stats["largest_batch"] = max(stats["largest_batch"], len(batch))
            if quotes:
                stats["quote_batches"] += 1
                stats["slowest_quote_ms"] = max(stats["slowest_quote_ms"], 1000 * (t2 - t0))
                stats["slowest_think_ms"] = max(stats["slowest_think_ms"], 1000 * (t1 - t0))
                stats["slowest_send_ms"] = max(stats["slowest_send_ms"], 1000 * (t2 - t1))
            if desk.sync_needed or time.time() - audit_at > AUDIT_EVERY:
                audit_at = time.time()
                try:
                    view = world.snapshot()
                    desk.now = max(desk.now, view["now"])
                    drift = set(desk.audit(view))
                    if desk.sync_needed or (drift & drift_before):      # a difference that stayed for two checks is real
                        stats["repairs"] += 1
                        desk.log.append({"t": desk.now, "kind": "repair", "why": sorted(drift & drift_before)[:6], "after_failed_send": desk.sync_needed})
                        print(f"[{label}] {clock(desk.now)} repairing the books: {sorted(drift & drift_before)[:3]} failed send: {desk.sync_needed}", flush=True)
                        desk.reconcile(view)
                        desk.send()
                        drift = set()
                    drift_before = drift
                except SpreadError as error:
                    print(f"[{label}] cannot read the world: {error}", flush=True)
                    time.sleep(1.0)
                except Exception:                        # noqa: BLE001
                    stats["faults"] += 1
                    fault(label, "audit")
            if time.time() - saved_at > SAVE_EVERY:
                t3 = time.time()
                save_state(desk, last_seq)
                saved_at = time.time()
                stats["slowest_save_ms"] = max(stats["slowest_save_ms"], 1000 * (saved_at - t3))
                with open(log_path, "a", encoding="utf-8") as f:
                    for row in desk.log[logged:]:
                        f.write(json.dumps(row) + "\n")
                logged = len(desk.log)
            if desk.now // DAY > day:
                day = desk.now // DAY
                try:
                    s = world.score()
                    print(f"[{label}] {clock(desk.now)}  margin €{s['marginCents'] / 100:,.0f}  won {s['wonOrders']}  on time {s['onTimeShare']:.1%}  "
                          f"slowest quote batch {stats['slowest_quote_ms']:.0f} ms of {stats['quote_batches']}  faults {stats['faults']}  repairs {stats['repairs']}", flush=True)
                except SpreadError:
                    pass
            if desk.now >= ends or (stop_at and desk.now >= stop_at):
                break
    finally:
        stop.set()
        try:
            save_state(desk, last_seq)
            with open(log_path, "a", encoding="utf-8") as f:
                for row in desk.log[logged:]:
                    f.write(json.dumps(row) + "\n")
        except Exception:                                # noqa: BLE001
            fault(label, "final save")
    print(f"[{label}] loop ended at {clock(desk.now)}: {json.dumps(stats)}", flush=True)
    return world.score()


def next_final(client: Client):
    """The team's copy of the final that is set or runs now. Waits while none is set and while the last one has ended."""
    said = False
    while True:
        try:
            world = client.world(client.final()["worldId"])
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        except SpreadError as error:
            if error.status not in (0, 404):
                print(f"waiting for the final: {error}", flush=True)
        if not said:
            print("No final is set yet. Waiting for it.", flush=True)
            said = True
        time.sleep(5)


def final(params: Params) -> None:
    client, world = Client(), None
    while True:
        try:
            if world is None:
                world = next_final(client)
                print(f"Final world {world.id}", flush=True)
            s = play(client, world, params)
            print(f"END  margin €{s['marginCents'] / 100:,.2f}  won {s['wonOrders']}  on time {s['onTimeShare']:.1%}  ranked {s['ranked']}", flush=True)
            return
        except KeyboardInterrupt:
            print("Stopped by hand. The world keeps running; start again to rejoin.", flush=True)
            return
        except Exception as error:      # noqa: BLE001  never die in the final: rejoin from the saved state
            traceback.print_exc()
            print(f"error: {error}; rejoining in 2 s", file=sys.stderr, flush=True)
            time.sleep(2)
            try:
                client = Client()
                world = client.world(world.id) if world is not None else None
            except Exception:           # noqa: BLE001
                pass


def join(world_id: str, params: Params, stop_at: int = 0) -> None:
    """Plays an existing practice world live while another process moves its clock."""
    client = Client()
    world = client.world(world_id)
    while True:
        try:
            s = play(client, world, params, is_final=False, stop_at=stop_at, label="rehearsal")
            print(f"END  margin €{s['marginCents'] / 100:,.2f}  won {s['wonOrders']}  on time {s['onTimeShare']:.1%}  ranked {s['ranked']}", flush=True)
            return
        except KeyboardInterrupt:
            return
        except Exception as error:      # noqa: BLE001
            traceback.print_exc()
            print(f"error: {error}; rejoining in 2 s", file=sys.stderr, flush=True)
            time.sleep(2)
            client = Client()
            world = client.world(world_id)


def rehearse(seed: str, params: Params, fast: float, stop_at: int, keep: bool) -> None:
    """A practice world played like the final: one thread moves the clock at the final's speeds (divided by `fast`),
    while the desk only listens to the stream."""
    client = Client()
    world = client.create(level=8, seed=seed)
    print(f"[rehearsal] world {world.id} on seed {seed}, {fast:g}x the final's speed", flush=True)
    running = threading.Event()
    running.set()
    thread = threading.Thread(target=move, args=(world.id, fast, stop_at, running), daemon=True)
    thread.start()
    started = time.time()
    try:
        s = play(client, world, params, is_final=False, stop_at=stop_at, label="rehearsal")
        print(f"[rehearsal] margin €{s['marginCents'] / 100:,.0f}  won {s['wonOrders']}  on time {s['onTimeShare']:.1%}  ranked {s['ranked']}  "
              f"({time.time() - started:.0f} s)", flush=True)
    finally:
        running.clear()
        thread.join(timeout=10)
        if not keep:
            try:
                world.delete()
            except SpreadError:
                pass
            if os.path.exists(state_path(world.id)):
                os.remove(state_path(world.id))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--rehearse", default="", help="a seed: create a practice world and play it live")
    ap.add_argument("--world", default="", help="a world id: join it live; abquant.clock moves its clock")
    ap.add_argument("--fast", type=float, default=1.0)
    ap.add_argument("--stop", type=int, default=0, help="stop at this world minute")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--set", nargs="*", default=[])
    args = ap.parse_args()
    params = Params(**parse_set(args.set))
    if args.final:
        final(params)
    elif args.rehearse:
        rehearse(args.rehearse, params, args.fast, args.stop, args.keep)
    elif args.world:
        join(args.world, params, args.stop)
    else:
        sys.exit("give --final, --rehearse SEED or --world ID")


if __name__ == "__main__":
    main()
