"""The features of a car, computed the same way when fitting on revealed weeks and when quoting live."""
from __future__ import annotations

import math
from collections import Counter

from .geo import DAY, Geo

LATE_NAMES = ["const", "log_lead_h", "lead_under_4h", "log_drive_h", "log_drivers_pickup", "log_drivers_delivery",
              "late_hour", "same_day", "private_pickup", "private_delivery", "premium", "note", "open_orders_100", "open_near_20", "friday"]
FEE_NAMES = LATE_NAMES


def driver_counts(geo: Geo, roster: list) -> dict:
    """For each place: how many drivers live within 30 km (all, and experienced only)."""
    homes, homes_exp = Counter(), Counter()
    for d in roster:
        homes[d["homePlaceId"]] += 1
        if d["rating"] >= 4.8 and d["completedGigs"] >= 50:
            homes_exp[d["homePlaceId"]] += 1
    return {
        "all": {p: sum(homes[h] for h in geo.near[p]) for p in geo.places},
        "exp": {p: sum(homes_exp[h] for h in geo.near[p]) for p in geo.places},
    }


def car_features(geo: Geo, dens: dict, request: dict, option: str, now: int, last_pickup_at: int,
                 open_orders: int, open_near: int) -> dict:
    legs = request["legs"]
    pickup, delivery = legs[0]["pickup"], legs[-1]["delivery"]
    premium = any(leg["car"]["premium"] for leg in legs)
    pool = dens["exp"] if premium else dens["all"]
    drive = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
    lead_h = max(0.25, (last_pickup_at - now) / 60)
    hour = now % DAY / 60
    return {
        "const": 1.0,
        "log_lead_h": math.log(lead_h),
        "lead_under_4h": 1.0 if lead_h < 4 else 0.0,
        "log_drive_h": math.log(max(10, drive) / 60),
        "log_drivers_pickup": math.log1p(pool[pickup["placeId"]]),
        "log_drivers_delivery": math.log1p(pool[delivery["placeId"]]),
        "late_hour": max(0.0, hour - 12) / 6,
        "same_day": 1.0 if option == "same_day" else 0.0,
        "private_pickup": 1.0 if any(leg["pickup"]["privateAddress"] for leg in legs) else 0.0,
        "private_delivery": 1.0 if any(leg["delivery"]["privateAddress"] for leg in legs) else 0.0,
        "premium": 1.0 if premium else 0.0,
        "note": 1.0 if request.get("note") else 0.0,
        "open_orders_100": open_orders / 100,
        "open_near_20": open_near / 20,
        "friday": 1.0 if now // DAY % 7 == 4 else 0.0,
    }


def dot(coef: list, names: list, x: dict) -> float:
    return sum(c * x[n] for c, n in zip(coef, names))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)
