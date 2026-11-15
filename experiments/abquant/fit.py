"""Fits the curves the desk prices with, from revealed practice weeks, and writes data/model.json.

  acceptance  P(dealer picks us | price / list, trust count)   logistic regression (ST202 6.4), weeks with random prices
  late risk   P(order late | car, load)                        logistic regression
  fee         E(driver cost / typical fee | car, load)          least squares, on delivered orders (cost given a win)
  dealers     requests a week by dealer id, and when in the week requests arrive (Poisson rates, ST202 6.7)

  python -m abquant.fit            # fits on every revealed week it finds
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy.optimize import minimize

from .env import DATA, PROJECT, REVEALED
from .features import FEE_NAMES, LATE_NAMES, car_features, driver_counts
from .geo import DAY, Geo


def load_worlds() -> list:
    runs = {}
    for path in (os.path.join(PROJECT, "spread_bot", "data", "runs.jsonl"), os.path.join(DATA, "runs.jsonl")):
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                r = json.loads(line)
                runs[r["world"]] = r
    out = []
    for folder in (REVEALED, os.path.join(DATA, "worlds")):
        for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
            wid = os.path.basename(path)[:-5]
            run = runs.get(wid, {})
            if run.get("level", 8) != 8:
                continue
            out.append((wid, run.get("tag", "?"), path))
    return out


def world_rows(d: dict, geo: Geo) -> tuple:
    """One row per request (for acceptance) and one per won order (for late risk and fee)."""
    dens = driver_counts(geo, d["roster"])
    requests = {rr["request"]["id"]: rr for rr in d["reveal"]["requests"]}
    gig_orders = {g["id"]: sorted({s["orderId"] for s in g["stops"]}) for g in d["snapshot"]["gigs"]}
    won, booked_at, ledger, revenue_at = {}, {}, defaultdict(Counter), {}
    for e in d["events"]:
        k = e["kind"]
        if k == "order_won":
            won[e["order"]["id"]] = e
        elif k == "gig_booked":
            for oid in gig_orders.get(e["gigId"], []):
                booked_at.setdefault(oid, e["at"])
        elif k == "ledger":
            line = e["line"]
            if line["orderId"]:
                ledger[line["orderId"]][line["kind"]] += line["cents"]
                if line["kind"] == "revenue":
                    revenue_at[line["orderId"]] = line["at"]
    cancelled = {e["orderId"] for e in d["events"] if e["kind"] == "order_cancelled"}
    # trust count and late history per dealer, as the dealer saw them when each request arrived
    timeline = sorted((t, won[o]["order"]["dealerId"], ledger[o]["late_refund"] < 0) for o, t in revenue_at.items() if o in won)
    count, lates, i = Counter(), Counter(), 0
    accept_rows, order_rows = [], []
    wins = sorted((e["at"], oid) for oid, e in won.items())
    for rr in sorted(requests.values(), key=lambda z: z["request"]["arrivedAt"]):
        r = rr["request"]
        while i < len(timeline) and timeline[i][0] <= r["arrivedAt"]:
            _, dealer, late = timeline[i]
            if late:
                count[dealer] //= 2
                lates[dealer] += 1
            else:
                count[dealer] = min(25, count[dealer] + 1)
            i += 1
        quote = rr.get("quote") or {}
        if len(quote) == 1 and rr["outcome"] in ("won", "lost"):
            kind, price = next(iter(quote.items()))
            option = next((o for o in r["options"] if o["kind"] == kind), None)
            if option and price < 2.6 * option["listPriceCents"]:
                leg = r["legs"][0]
                fastest = r["options"][0]["kind"]
                accept_rows.append({
                    "won": rr["outcome"] == "won", "ratio": price / option["listPriceCents"], "trust": count[r["dealerId"]],
                    "lates": lates[r["dealerId"]], "kind": kind, "slower": kind != fastest, "dealer": r["dealerId"],
                    "drive": geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]),
                    "dpu": dens["all"][leg["pickup"]["placeId"]], "dde": dens["all"][leg["delivery"]["placeId"]],
                    "day": r["arrivedAt"] // DAY, "trade": len(r["legs"]) > 1,
                    "private": any(l["pickup"]["privateAddress"] or l["delivery"]["privateAddress"] for l in r["legs"]),
                })
    for at, oid in wins:
        if oid in cancelled or oid not in requests:
            continue
        order, r = won[oid]["order"], requests[oid]["request"]
        open_now = [o for t, o in wins if t <= at and o != oid and booked_at.get(o, 10**9) > at and o not in cancelled]
        pu = r["legs"][0]["pickup"]["placeId"]
        near = sum(1 for o in open_now if requests[o]["request"]["legs"][0]["pickup"]["placeId"] in geo.near[pu])
        x = car_features(geo, dens, r, order["option"], at, order["lastPickupAt"], len(open_now), near)
        L = ledger[oid]
        cost = -(L["driver_fee"] + L["failed_visit"] + L["release_fee"] + L["waiting"] + L["fine"])
        order_rows.append({
            "x": x, "late": L["late_refund"] < 0 or L["undelivered_penalty"] < 0, "delivered": L["revenue"] > 0,
            "cost_ratio": cost / r["referenceFeeCents"], "ref": r["referenceFeeCents"], "price": order["priceCents"],
            "refund_share": -(L["late_refund"] + L["undelivered_penalty"]) / max(1, order["priceCents"]), "legs": len(r["legs"]),
            "book_min": booked_at.get(oid, 10**9) - at,
        })
    arrivals = [(r["request"]["arrivedAt"], r["request"]["dealerId"]) for r in requests.values()]
    return accept_rows, order_rows, arrivals


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> np.ndarray:
    def nll(w):
        z = X @ w
        return np.sum(np.logaddexp(0, z) - y * z) + 0.5 * l2 * np.sum(w[1:] ** 2)

    def grad(w):
        p = 1 / (1 + np.exp(-(X @ w)))
        g = X.T @ (p - y)
        g[1:] += l2 * w[1:]
        return g

    return minimize(nll, np.zeros(X.shape[1]), jac=grad, method="BFGS").x


def fit_acceptance(rows: list, world_of: list) -> dict:
    """P(win) = sigmoid((a_world + b.x - ln(ratio) + ln(1 + trust/100)) / s). Returns s, the mean level and b."""
    worlds = sorted(set(world_of))
    W = np.array([[1.0 if w == ww else 0.0 for ww in worlds] for w in world_of])
    feats = ["slower", "next_day", "within_3_days", "log_drive_h", "log_dde", "log_dpu", "log1p_lates"]
    F = np.array([[1.0 * r["slower"], 1.0 * (r["kind"] == "next_day"), 1.0 * (r["kind"] == "within_3_days"),
                   math.log(max(10, r["drive"]) / 60), math.log1p(r["dde"]), math.log1p(r["dpu"]), math.log1p(r["lates"])] for r in rows])
    F = F - F.mean(axis=0)
    off = np.array([-math.log(r["ratio"]) + math.log(1 + r["trust"] / 100) for r in rows])
    y = np.array([1.0 * r["won"] for r in rows])
    nw, nf = W.shape[1], F.shape[1]

    def nll(p):
        s = math.exp(p[-1])
        z = (W @ p[:nw] + F @ p[nw:nw + nf] + off) / s
        return np.sum(np.logaddexp(0, z) - y * z)

    p0 = np.concatenate([np.full(nw, math.log(1.38)), np.zeros(nf), [math.log(0.1)]])
    res = minimize(nll, p0, method="L-BFGS-B")
    p = res.x
    return {"s": float(math.exp(p[-1])), "levels": {w: float(math.exp(a)) for w, a in zip(worlds, p[:nw])},
            "theta": float(math.exp(np.mean(p[:nw]))), "b": dict(zip(feats, map(float, p[nw:nw + nf]))), "n": len(rows)}


def main() -> None:
    geo = Geo(json.load(open(os.path.join(PROJECT, "spread_bot", "data", "map.json"))))
    worlds = load_worlds()
    accept, accept_world, orders, order_tag, arrivals_by_world = [], [], [], [], []
    for wid, tag, path in worlds:
        d = json.load(open(path))
        a, o, arr = world_rows(d, geo)
        if tag.startswith("probe"):
            accept += a
            accept_world += [wid] * len(a)
        orders += o
        order_tag += [tag] * len(o)
        arrivals_by_world.append(arr)
    print(f"weeks: {len(worlds)}  {dict(Counter(t for _, t, _ in worlds))}; acceptance rows {len(accept)}; orders {len(orders)}")

    model = {}
    # ---- acceptance
    acc = fit_acceptance(accept, accept_world)
    model["accept"] = acc
    print(f"acceptance: s = {acc['s']:.3f}, level at trust 0 = {acc['theta']:.3f} x list (by week: {', '.join(f'{v:.2f}' for v in acc['levels'].values())})")
    print("   shifts of the log level:", {k: round(v, 3) for k, v in acc["b"].items()})
    # does the 1% per trust count hold? refit with a free coefficient on ln(1 + trust/100)
    for r in accept:
        r["_t"] = r["trust"]
    lo = [r for r in accept if r["trust"] < 5]
    hi = [r for r in accept if r["trust"] >= 15]
    for name, grp in (("trust 0-4", lo), ("trust 15-25", hi)):
        if grp:
            z = np.array([(math.log(acc["theta"]) - math.log(r["ratio"]) + math.log(1 + r["trust"] / 100)) / acc["s"] for r in grp])
            print(f"   {name}: n={len(grp)}, won {np.mean([r['won'] for r in grp]):.1%}, model says {np.mean(1 / (1 + np.exp(-z))):.1%}")

    # ---- late risk and cost: on this desk's own weeks once there are enough of them (its fees and windows differ from
    # the other build's), else on the other weeks whose policy resembles ours (not the probe weeks, which ran without limits)
    mine = [i for i, t in enumerate(order_tag) if t.startswith("fb_")]
    keep = mine if len(mine) >= 1500 else [i for i, t in enumerate(order_tag) if not t.startswith(("probe", "smoke"))]
    print(f"late and fee models fitted on {'this desk\'s own' if keep is mine else 'the other build\'s'} weeks: {len(keep)} orders")
    X = np.array([[orders[i]["x"][n] for n in LATE_NAMES] for i in keep])
    y = np.array([1.0 * orders[i]["late"] for i in keep])
    w = fit_logistic(X, y, l2=4.0 if keep is mine else 2.0)
    model["late"] = {"names": LATE_NAMES, "coef": list(map(float, w)), "n": len(keep), "base": float(y.mean())}
    print(f"late risk: n={len(keep)}, late {y.mean():.1%}; coefficients:")
    print("   " + ", ".join(f"{n} {c:+.2f}" for n, c in zip(LATE_NAMES, w)))
    dl = [i for i in keep if orders[i]["delivered"] and orders[i]["legs"] == 1]
    Xf = np.array([[orders[i]["x"][n] for n in FEE_NAMES] for i in dl])
    yf = np.array([orders[i]["cost_ratio"] for i in dl])
    wf, *_ = np.linalg.lstsq(Xf, yf, rcond=None)
    model["fee"] = {"names": FEE_NAMES, "coef": list(map(float, wf)), "n": len(dl), "mean": float(yf.mean())}
    resid = yf - Xf @ wf
    print(f"fee: n={len(dl)}, mean cost/typical {yf.mean():.3f}, residual sd {resid.std():.3f}; coefficients:")
    print("   " + ", ".join(f"{n} {c:+.3f}" for n, c in zip(FEE_NAMES, wf)))
    late_rows = [orders[i] for i in keep if orders[i]["late"]]
    model["refund_share"] = float(np.mean([r["refund_share"] for r in late_rows])) if late_rows else 0.3
    model["late_cost_extra"] = float(np.mean([r["cost_ratio"] for r in late_rows]) - yf.mean()) if late_rows else 0.5
    print(f"late orders: mean refund {model['refund_share']:.1%} of price; cost/typical {np.mean([r['cost_ratio'] for r in late_rows]):.2f} vs {yf.mean():.2f} overall")

    # ---- dealers and arrivals
    per_world = [Counter(dl_ for _, dl_ in arr) for arr in arrivals_by_world]
    ids = sorted({d for c in per_world for d in c})
    mean = {d: float(np.mean([c.get(d, 0) for c in per_world])) for d in ids}
    sd = {d: float(np.std([c.get(d, 0) for c in per_world])) for d in ids}
    top = sorted(ids, key=lambda d: -mean[d])[:12]
    print("dealer sizes (requests a week, mean and sd across weeks):", ", ".join(f"{d} {mean[d]:.0f}±{sd[d]:.0f}" for d in top))
    model["dealer_requests"] = mean
    total = float(np.mean([sum(c.values()) for c in per_world]))
    # share of the week's requests that has arrived by each half hour (from Monday 00:00 to Friday 24:00)
    grid = list(range(0, 5 * DAY + 1, 30))
    cdf = []
    for g in grid:
        cdf.append(float(np.mean([sum(1 for t, _ in arr if t <= g) / max(1, len(arr)) for arr in arrivals_by_world])))
    model["arrivals"] = {"step": 30, "cdf": cdf, "week_total": total}
    print(f"requests a week {total:.0f}; arrived by end of Mon {cdf[DAY // 30]:.0%}, Tue {cdf[2 * DAY // 30]:.0%}, Wed {cdf[3 * DAY // 30]:.0%}, Thu {cdf[4 * DAY // 30]:.0%}")
    with open(os.path.join(DATA, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, indent=1)
    print("wrote", os.path.join(DATA, "model.json"))


if __name__ == "__main__":
    sys.exit(main())
