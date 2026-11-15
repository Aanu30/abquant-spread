"""Offline replay of logged quotes to tune the acceptance learner (ST202 ch. 11: online Bayesian updating with shrinkage)."""
from __future__ import annotations

import json
import math

from .analyze import fetch, logs_for, runs_for
from spread.client import Client


def sigmoid(z):
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def load(tags):
    c = Client()
    weeks = []
    for tag in tags:
        for run in runs_for(tag):
            d = fetch(c, run["world"])
            reqs = {r["request"]["id"]: r for r in d["reveal"]["requests"]}
            rows = []
            for x in logs_for(run):
                if x["kind"] != "quote":
                    continue
                rr = reqs[x["rid"]]
                req = rr["request"]
                lane = (req["legs"][0]["pickup"]["placeId"], req["legs"][0]["delivery"]["placeId"])
                rows.append((x["t"], math.log(x["ratio"]), lane, req["dealerId"], req["arrivedAt"] // 1440, 1.0 if rr["outcome"] == "won" else 0.0))
            rows.sort()
            weeks.append(rows)
    return weeks


def bayes_logloss(weeks, s, m0, v_g, v_lane, v_dealer, v_day, v_pu=0.0):
    tot, n = 0.0, 0
    for rows in weeks:
        g = [m0, v_g]
        eff = {}
        for t, lr, lane, dealer, day, y in rows:
            keys = [("lane", lane, v_lane), ("dealer", dealer, v_dealer), ("day", day, v_day)]
            if v_pu > 0:
                keys.append(("pu", lane[0], v_pu))
            th = g[0] + sum(eff.get((k, key), [0.0, var])[0] for k, key, var in keys)
            P = sigmoid((th - lr) / s)
            P = min(1 - 1e-6, max(1e-6, P))
            tot += -(y * math.log(P) + (1 - y) * math.log(1 - P))
            n += 1
            h = P * (1 - P) / s ** 2
            gr = (y - P) / s
            g[1] = 1 / (1 / g[1] + h)
            g[0] += g[1] * gr
            for k, key, var in keys:
                if var <= 0:
                    continue
                e = eff.setdefault((k, key), [0.0, var])
                e[1] = 1 / (1 / e[1] + h)
                e[0] += e[1] * gr
    return tot / n


def sgd_logloss(weeks, s, m0, lr_g, lr_lane, lr_dealer, lr_day):
    tot, n = 0.0, 0
    for rows in weeks:
        g = m0
        eff = {}
        for t, lr, lane, dealer, day, y in rows:
            th = g + eff.get(("l", lane), 0) + eff.get(("d", dealer), 0) + eff.get(("y", day), 0)
            P = min(1 - 1e-6, max(1e-6, sigmoid((th - lr) / s)))
            tot += -(y * math.log(P) + (1 - y) * math.log(1 - P))
            n += 1
            err = y - P
            g += lr_g * err
            for k, key, lrk in (("l", lane, lr_lane), ("d", dealer, lr_dealer), ("y", day, lr_day)):
                eff[(k, key)] = eff.get((k, key), 0) + lrk * err
    return tot / n


if __name__ == "__main__":
    weeks = load(["U1", "VU1", "U4", "T4"])
    print("weeks", len(weeks), "quotes", sum(len(w) for w in weeks))
    base = sum(w[-1] for rows in weeks for w in rows) / sum(len(r) for r in weeks)
    print(f"constant model log-loss {-(base*math.log(base)+(1-base)*math.log(1-base)):.4f}")
    print(f"current SGD learner      {sgd_logloss(weeks, 0.108, math.log(1.38), 0.04, 0.03, 0.03, 0.06):.4f}")
    best = None
    for s in (0.08, 0.108, 0.15, 0.2):
        for vg in (0.01, 0.04):
            for vl in (0.0, 0.003, 0.01):
                for vd in (0.0, 0.003, 0.01):
                    for vy in (0.0, 0.002):
                        for vp in (0.0, 0.004):
                            ll = bayes_logloss(weeks, s, math.log(1.38), vg, vl, vd, vy, vp)
                            if best is None or ll < best[0]:
                                best = (ll, s, vg, vl, vd, vy, vp)
    print("best Bayesian learner: logloss %.4f  s=%.3f var_global=%.3f var_lane=%.3f var_dealer=%.3f var_day=%.3f var_pickup=%.3f" % best)
