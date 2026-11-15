"""Fit the acceptance curve, the drivers' fee curve and late probability from finished practice worlds.

  python3 -m bot.analyze --tag probe1
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os

import numpy as np
from scipy.optimize import minimize

from .env import ROOT
from spread.client import Client
from .geo import DAY, HOUR

CACHE = os.path.join(ROOT, "data", "worlds")


def fetch(client: Client, wid: str) -> dict:
    path = os.path.join(CACHE, wid + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    w = client.world(wid)
    data = {"reveal": w.reveal(), "events": w.events(), "snapshot": w.snapshot(), "roster": w.roster()}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def runs_for(tag: str) -> list:
    out = []
    with open(os.path.join(ROOT, "data", "runs.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tag"] == tag:
                out.append(r)
    return out


def logs_for(run: dict) -> list:
    path = os.path.join(ROOT, "logs", f"{run['tag']}__{run['seed']}__{run['world']}.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f][1:]


def fit_acceptance(rows: list) -> tuple:
    """rows: (world index, log ratio, won). P(won) = sigmoid((theta_w - log r) / s)."""
    W = max(r[0] for r in rows) + 1
    w = np.array([r[0] for r in rows]); x = np.array([r[1] for r in rows]); y = np.array([r[2] for r in rows], float)

    def nll(v):
        th, s = v[:W], math.exp(v[W])
        z = (th[w] - x) / s
        return -np.sum(y * -np.logaddexp(0, -z) + (1 - y) * -np.logaddexp(0, z))

    v0 = np.concatenate([np.full(W, math.log(1.4)), [math.log(0.05)]])
    res = minimize(nll, v0, method="L-BFGS-B")
    return np.exp(res.x[:W]), math.exp(res.x[W])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    client = Client()
    runs = runs_for(args.tag)
    print(f"{len(runs)} runs for tag {args.tag}")
    acc_rows, fee_rows, late_rows, by_day = [], [], [], []
    for wi, run in enumerate(runs):
        data = fetch(client, run["world"])
        log = logs_for(run)
        reqs = {r["request"]["id"]: r for r in data["reveal"]["requests"]}
        quotes = {x["rid"]: x for x in log if x["kind"] == "quote"}
        for rid, q in quotes.items():
            rr = reqs.get(rid)
            if rr is None or rr["outcome"] == "unquoted":
                continue
            won = rr["outcome"] == "won"
            acc_rows.append((wi, math.log(q["ratio"]), 1 if won else 0))
            by_day.append((wi, rr["request"]["arrivedAt"] // DAY, math.log(q["ratio"]), 1 if won else 0, (rr["request"]["arrivedAt"] % DAY) // 60))
        # fees: first gig of each order
        booked_at = {}
        for e in data["events"]:
            if e["kind"] == "gig_booked" and e["gigId"] not in booked_at:
                booked_at[e["gigId"]] = (e["at"], e["feeCents"])
        first_gig = {}
        for g in sorted(data["snapshot"]["gigs"], key=lambda g: g["postedAt"]):
            oid = g["stops"][0]["orderId"]
            first_gig.setdefault(oid, g)
        fees = {}
        for x in log:
            if x["kind"] == "fees" and not x["urgent"]:
                fees.setdefault(x["oid"], x)
        for oid, g in first_gig.items():
            fx = fees.get(oid)
            if not fx or fx["ref"] <= 0:
                continue
            b = booked_at.get(g["id"])
            fee_rows.append({"r0": g["schedule"][0]["feeCents"] / fx["ref"], "booked": b is not None,
                             "wait": (b[0] - g["postedAt"]) if b else None, "rb": (b[1] / fx["ref"]) if b else None,
                             "lead": fx["lpa"] - g["postedAt"]})
        orders = {o["id"]: o for o in data["snapshot"]["orders"] if o["status"] != "cancelled"}
        for oid, o in orders.items():
            d = o["deliveredAt"]
            late = any(x is None for x in d) or max(d) > o["deadline"]
            q = quotes.get(oid, {})
            late_rows.append({"late": late, "slack": q.get("slack"), "u": q.get("u"), "opt": o["option"]})
    if acc_rows:
        comp, s = fit_acceptance(acc_rows)
        print(f"acceptance: slope s = {s:.4f} (log price); competitor/list by world: " + ", ".join(f"{c:.3f}" for c in comp))
        # empirical win rate by ratio bucket
        buckets = collections.defaultdict(lambda: [0, 0])
        for _, lx, y in acc_rows:
            b = round(math.exp(lx) * 20) / 20
            buckets[b][0] += y; buckets[b][1] += 1
        print("win rate by quote/list: " + "  ".join(f"{b:.2f}:{w}/{n}" for b, (w, n) in sorted(buckets.items())))
        # by day of week (pooled), relative to world fit
        dd = collections.defaultdict(lambda: [0.0, 0])
        for wi, day, lx, y, hr in by_day:
            p = 1 / (1 + math.exp(-(math.log(comp[wi]) - lx) / s))
            dd[day][0] += y - p; dd[day][1] += 1
        print("win excess by day: " + "  ".join(f"d{d}:{v/n:+.3f}(n={n})" for d, (v, n) in sorted(dd.items())))
    if fee_rows:
        b = collections.defaultdict(list)
        for r in fee_rows:
            b[round(r["r0"] * 5) / 5].append(r)
        print("opening fee/typical -> booked share, median wait (min), n")
        for k in sorted(b):
            rs = b[k]
            waits = sorted(r["wait"] for r in rs if r["wait"] is not None)
            print(f"  {k:.1f}: {sum(r['booked'] for r in rs)/len(rs):.2f}  {waits[len(waits)//2] if waits else '-'}  n={len(rs)}")
    if late_rows:
        n = len(late_rows)
        print(f"orders {n}, late {sum(r['late'] for r in late_rows)/n:.1%}")
        sb = collections.defaultdict(lambda: [0, 0])
        for r in late_rows:
            if r["slack"] is None:
                continue
            k = min(12, r["slack"] // 60)
            sb[k][0] += r["late"]; sb[k][1] += 1
        print("late share by slack hours: " + "  ".join(f"{k}h:{a}/{n}" for k, (a, n) in sorted(sb.items())))


if __name__ == "__main__":
    main()
