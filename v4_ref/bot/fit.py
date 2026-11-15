"""Fit the late-probability GLM (ST202 6.4) and the booking-hazard model (ST202 6.5) from finished worlds.

  python3 -m bot.fit --tags probe1,m1
"""
from __future__ import annotations

import argparse
import json
import math
import os

import numpy as np
from scipy.optimize import minimize

from .env import ROOT
from spread.client import Client
from .analyze import fetch, logs_for, runs_for
from .geo import DAY, Geo

NAMES = ["const", "log fee ratio", "same_day", "log lead h", "lead<6h", "log dens pickup", "log dens delivery", "log drive",
         "hour/24", "open orders global/100", "open near pickup/20", "trade-in", "probe regime", "premium", "private", "note", "electric"]


def wdens(geo: Geo, roster: list, tau: float = 45.0) -> dict:
    w = {p: 0.0 for p in geo.places}
    for d in roster:
        for p in geo.places:
            w[p] += math.exp(-geo.minutes(d["homePlaceId"], p) / tau)
    return w


def order_rows(tags: list) -> list:
    geo, client = Geo(), Client()
    rows = []
    for tag in tags:
        for run in runs_for(tag):
            d = fetch(client, run["world"])
            log = logs_for(run)
            dens = wdens(geo, d["roster"])
            reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
            f0 = {}
            for x in log:
                if x["kind"] == "fees" and not x["urgent"] and x["oid"] not in f0 and x["ref"]:
                    f0[x["oid"]] = (x["f0"] / x["ref"], x["t"], x["lpa"])
            gig_order = {g["id"]: g["stops"][0]["orderId"] for g in d["snapshot"]["gigs"]}
            booked, warned = {}, {}
            for e in d["events"]:
                if e["kind"] == "gig_booked":
                    o = gig_order.get(e["gigId"])
                    if o:
                        booked.setdefault(o, e["at"])
                elif e["kind"] == "deadline_close":
                    warned.setdefault(e["orderId"], e["at"])
            orders = [o for o in d["snapshot"]["orders"] if o["status"] != "cancelled" and o["id"] in f0]
            spans = [(f0[o["id"]][1], booked.get(o["id"], 10 ** 9), reqs[o["id"]]["legs"][0]["pickup"]["placeId"]) for o in orders]
            for o in orders:
                r, t0, lpa = f0[o["id"]]
                req = reqs[o["id"]]
                pu, de = req["legs"][0]["pickup"]["placeId"], req["legs"][-1]["delivery"]["placeId"]
                qg = sum(1 for a, b, p in spans if a <= t0 < b)
                ql = sum(1 for a, b, p in spans if a <= t0 < b and geo.minutes(p, pu) <= 60)
                dl = o["deliveredAt"]
                late = any(v is None for v in dl) or max(dl) > o["deadline"]
                lead = (o["lastPickupAt"] - t0) / 60
                drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in req["legs"])
                x = [1, math.log(r), 1.0 if o["option"] == "same_day" else 0.0, math.log(max(lead, 0.5)), 1.0 if lead < 6 else 0.0,
                     math.log(1 + dens[pu]), math.log(1 + dens[de]), math.log(drive + 30), (t0 % DAY) / 60 / 24, qg / 100, ql / 20,
                     len(req["legs"]) - 1, 1.0 if tag.startswith("probe") else 0.0,
                     1.0 if any(l["car"]["premium"] for l in req["legs"]) else 0.0,
                     1.0 if any(l["pickup"]["privateAddress"] or l["delivery"]["privateAddress"] for l in req["legs"]) else 0.0,
                     1.0 if req.get("note") else 0.0,
                     1.0 if any(l["car"]["electric"] for l in req["legs"]) else 0.0]
                # booking time before the warning (censored at the warning or at lastPickupAt - 3h)
                horizon = max(1, (warned.get(o["id"], lpa - 180)) - t0)
                b = booked.get(o["id"])
                event = b is not None and b - t0 <= horizon
                rows.append({"x": x, "late": 1.0 if late else 0.0, "t": (b - t0) if event else horizon, "event": event,
                             "flat": tag.startswith("probe")})
    return rows


def fit_logistic(X: np.ndarray, Y: np.ndarray, l2: float = 1e-3) -> np.ndarray:
    def nll(b):
        z = X @ b
        return np.sum(np.logaddexp(0, z) - Y * z) + 0.5 * l2 * np.sum(b[1:] ** 2)

    def grad(b):
        p = 1 / (1 + np.exp(-(X @ b)))
        return X.T @ (p - Y) + l2 * np.concatenate([[0], b[1:]])

    return minimize(nll, np.zeros(X.shape[1]), jac=grad, method="L-BFGS-B").x


def fit_hazard(X: np.ndarray, T: np.ndarray, D: np.ndarray) -> tuple:
    """Exponential time-to-event model with censoring: h = exp(x'b) per minute.
    loglik = sum d log h - h t. Standard errors from the observed information (ST202 9.2)."""
    def nll(b):
        z = X @ b
        return -np.sum(D * z - np.exp(z) * T)

    def grad(b):
        return -(X.T @ (D - np.exp(X @ b) * T))

    b = minimize(nll, np.zeros(X.shape[1]), jac=grad, method="L-BFGS-B").x
    H = (X * (np.exp(X @ b) * T)[:, None]).T @ X
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b, se


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    args = ap.parse_args()
    rows = order_rows(args.tags.split(","))
    X = np.array([r["x"] for r in rows])
    Y = np.array([r["late"] for r in rows])
    b = fit_logistic(X, Y)
    p = 1 / (1 + np.exp(-(X @ b)))
    print(f"late model on {len(Y)} orders, late share {Y.mean():.3f}")
    for n, v in zip(NAMES, b):
        print(f"  {n:>24} {v:+.3f}")
    idx = np.argsort(p)
    print("  calibration by quintile: " + "  ".join(
        f"{p[s].mean():.3f}/{Y[s].mean():.3f}" for s in (idx[k * len(p) // 5:(k + 1) * len(p) // 5] for k in range(5))))
    # held-out style check on the non-probe orders only
    m = X[:, -1] == 0
    if m.any():
        print(f"  non-probe orders: predicted {p[m].mean():.3f} actual {Y[m].mean():.3f} (n={int(m.sum())})")
    with open(os.path.join(ROOT, "data", "late_model.json"), "w", encoding="utf-8") as f:
        json.dump({"names": NAMES, "coef": list(b), "tags": args.tags}, f)
    # hazard of a booking before the warning, on flat-fee probe gigs only
    flat = [r for r in rows if r["flat"]]
    if flat:
        Xh = np.array([r["x"] for r in flat])
        keep = [0, 1, 3, 5, 6, 7, 8, 9, 11]  # (probe regime constant on this subset)  # const, log fee, log lead, dens pu, dens de, log drive, hour, q, trade-in
        Xh = Xh[:, keep]
        T = np.array([max(1.0, r["t"]) for r in flat])
        D = np.array([1.0 if r["event"] else 0.0 for r in flat])
        bh, se = fit_hazard(Xh, T, D)
        names = [NAMES[i] for i in keep]
        print(f"booking hazard (per minute) on {len(flat)} flat-fee gigs, {D.mean():.2f} booked before the warning")
        for n, v, s in zip(names, bh, se):
            print(f"  {n:>24} {v:+.3f}  (se {s:.3f})")
        with open(os.path.join(ROOT, "data", "hazard_model.json"), "w", encoding="utf-8") as f:
            json.dump({"names": names, "coef": list(bh), "se": list(se)}, f)


if __name__ == "__main__":
    main()
