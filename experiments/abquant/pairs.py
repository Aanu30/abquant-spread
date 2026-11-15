"""Two cars in one gig: the second car starts near where the first one ends, so one driver takes both.

For a driver a gig costs the time at the wheel, the trip to the first pickup and the trip home from the last delivery
(HANDBOOK.md). A second car that starts where the first ends adds wheel time but no second trip to a pickup, and when it
heads back toward the first pickup it also removes the trip home. So a pair can clear at less than two single fees.

`pair_stops` returns the four stops of a pair with windows that make the sequence work on one day, or None.
"""
from __future__ import annotations

from typing import Optional

from .geo import DAY, last_pickup, next_open, open_interval


def site_hours(place: dict) -> Optional[dict]:
    return None if place["privateAddress"] else place["hours"]


def pair_stops(desk, a: dict, b: dict, now: int, transfer_max: int = 30, slack: int = 20) -> Optional[tuple]:
    """Order a first, then order b, both single cars. Returns (stops, planned driving minutes, round trip?) or None."""
    from .desk import effective_leg

    if len(a["legs"]) != 1 or len(b["legs"]) != 1 or a["id"] == b["id"]:
        return None
    fa, fb = desk.facts_of(desk.requests[a["id"]]), desk.facts_of(desk.requests[b["id"]])
    la, lb = effective_leg(a["legs"][0], fa), effective_leg(b["legs"][0], fb)
    if la["pickup"]["privateAddress"] or lb["pickup"]["privateAddress"] or la["delivery"]["privateAddress"] or lb["delivery"]["privateAddress"]:
        return None
    geo, p = desk.geo, desk.p
    drive_a = geo.minutes(la["pickup"]["placeId"], la["delivery"]["placeId"])
    drive_b = geo.minutes(lb["pickup"]["placeId"], lb["delivery"]["placeId"])
    transfer = geo.minutes(la["delivery"]["placeId"], lb["pickup"]["placeId"])
    if transfer > transfer_max or drive_a + transfer + drive_b > 690:
        return None
    dl_a = min(a["deadline"], fa.deadline) if fa.deadline is not None else a["deadline"]
    dl_b = min(b["deadline"], fb.deadline) if fb.deadline is not None else b["deadline"]
    margin_a = max(p.safety_min, int(p.safety * drive_a))
    margin_b = max(p.safety_min, int(p.safety * drive_b))
    gap = int(drive_a * (1 + p.drive_buffer)) + transfer + slack          # from a's pickup to b's pickup
    start = now + p.find_min
    for day in range(start // DAY, min(dl_a, dl_b) // DAY + 1):
        day_start, day_end = max(start, day * DAY + 6 * 60), (day + 1) * DAY - 1
        a_first = next_open(site_hours(la["pickup"]), max(day_start, la["pickup"]["window"]["from"]))
        a_last = last_pickup(geo, la, min(dl_a - margin_a, day_end), day_start, 30 if fa.plates else 0)
        b_first = next_open(site_hours(lb["pickup"]), max(day_start, lb["pickup"]["window"]["from"]))
        b_last = last_pickup(geo, lb, min(dl_b - margin_b, day_end), day_start, 30 if fb.plates else 0)
        if a_last is None or b_last is None or a_first // DAY != day or b_first // DAY != day or a_last // DAY != day or b_last // DAY != day:
            continue
        ta_lo = max(a_first, b_first - gap)
        ta_hi = min(a_last, b_last - gap)
        if ta_hi - ta_lo < 20:
            continue
        long = drive_a + drive_b >= p.long_min
        if long and ta_lo % DAY > p.long_start_by:
            continue
        d_open_a = open_interval(site_hours(la["delivery"]), day)
        d_open_b = open_interval(site_hours(lb["delivery"]), day)
        if not d_open_a or not d_open_b:
            continue
        stops = [
            {"orderId": a["id"], "leg": 0, "kind": "pickup", "withPlates": bool(fa.plates), "withCharging": charging(geo, la),
             "window": {"from": ta_lo, "to": ta_hi}},
            {"orderId": a["id"], "leg": 0, "kind": "delivery",
             "window": {"from": max(d_open_a[0], la["delivery"]["window"]["from"]), "to": min(d_open_a[1], dl_a - margin_a)}},
            {"orderId": b["id"], "leg": 0, "kind": "pickup", "withPlates": bool(fb.plates), "withCharging": charging(geo, lb),
             "window": {"from": max(b_first, ta_lo + gap - slack), "to": b_last}},
            {"orderId": b["id"], "leg": 0, "kind": "delivery",
             "window": {"from": max(d_open_b[0], lb["delivery"]["window"]["from"]), "to": min(d_open_b[1], dl_b - margin_b)}},
        ]
        if any(s["window"]["to"] <= s["window"]["from"] for s in stops):
            continue
        round_trip = lb["delivery"]["placeId"] in geo.near[la["pickup"]["placeId"]]
        return stops, drive_a + transfer + drive_b, round_trip
    return None


def chain_stops(desk, orders: list, now: int, transfer_max: int = 30, slack: int = 20) -> Optional[tuple]:
    """Single cars in the order given, one after another for one driver: `pair_stops` for any number of cars (the
    same windows for two). Returns (stops, planned driving minutes, ends where it began?) or None.

    The world's limit for a gig with more than one car is 12 hours of driving, the drives between the cars included."""
    from .desk import effective_leg

    if len({o["id"] for o in orders}) != len(orders) or any(len(o["legs"]) != 1 for o in orders):
        return None
    facts = [desk.facts_of(desk.requests[o["id"]]) for o in orders]
    legs = [effective_leg(o["legs"][0], f) for o, f in zip(orders, facts)]
    if any(leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] for leg in legs):
        return None
    geo, p = desk.geo, desk.p
    drives = [geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs]
    hops = [geo.minutes(legs[i]["delivery"]["placeId"], legs[i + 1]["pickup"]["placeId"]) for i in range(len(legs) - 1)]
    total = sum(drives) + sum(hops)
    if any(hop > transfer_max for hop in hops) or total > 690:
        return None
    deadlines = [min(o["deadline"], f.deadline) if f.deadline is not None else o["deadline"] for o, f in zip(orders, facts)]
    margins = [max(p.safety_min, int(p.safety * drive)) for drive in drives]
    offsets = [0]                                          # minutes from the first pickup to each later pickup
    for i, hop in enumerate(hops):
        offsets.append(offsets[-1] + int(drives[i] * (1 + p.drive_buffer)) + hop + slack)
    start = now + p.find_min
    for day in range(start // DAY, min(deadlines) // DAY + 1):
        day_start, day_end = max(start, day * DAY + 6 * 60), (day + 1) * DAY - 1
        firsts = [next_open(site_hours(leg["pickup"]), max(day_start, leg["pickup"]["window"]["from"])) for leg in legs]
        lasts = [last_pickup(geo, leg, min(deadline - margin, day_end), day_start, 30 if f.plates else 0)
                 for leg, deadline, margin, f in zip(legs, deadlines, margins, facts)]
        if any(t is None for t in lasts) or any(t // DAY != day for t in firsts + lasts):
            continue
        lo = max(first - offset for first, offset in zip(firsts, offsets))
        hi = min(last - offset for last, offset in zip(lasts, offsets))
        if hi - lo < 20:
            continue
        if sum(drives) >= p.long_min and lo % DAY > p.long_start_by:
            continue
        opens = [open_interval(site_hours(leg["delivery"]), day) for leg in legs]
        if not all(opens):
            continue
        stops = []
        for i, (o, leg, f) in enumerate(zip(orders, legs, facts)):
            window = {"from": lo, "to": hi} if i == 0 else {"from": max(firsts[i], lo + offsets[i] - slack), "to": lasts[i]}
            stops.append({"orderId": o["id"], "leg": 0, "kind": "pickup", "withPlates": bool(f.plates), "withCharging": charging(geo, leg),
                          "window": window})
            stops.append({"orderId": o["id"], "leg": 0, "kind": "delivery",
                          "window": {"from": max(opens[i][0], leg["delivery"]["window"]["from"]), "to": min(opens[i][1], deadlines[i] - margins[i])}})
        if any(s["window"]["to"] <= s["window"]["from"] for s in stops):
            continue
        loop = legs[-1]["delivery"]["placeId"] in geo.near[legs[0]["pickup"]["placeId"]]
        return stops, total, loop
    return None


def chain_audience(desk, orders: list) -> dict:
    facts = [desk.facts_of(desk.requests[o["id"]]) for o in orders]
    return {"experienced": any(leg["car"]["premium"] for o in orders for leg in o["legs"]), "manualLicence": any(bool(f.manual) for f in facts)}


def charging(geo, leg: dict) -> bool:
    car = leg["car"]
    return bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
                and geo.km(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) > 200)


def pair_audience(desk, a: dict, b: dict) -> dict:
    fa, fb = desk.facts_of(desk.requests[a["id"]]), desk.facts_of(desk.requests[b["id"]])
    return {"experienced": any(leg["car"]["premium"] for o in (a, b) for leg in o["legs"]), "manualLicence": bool(fa.manual or fb.manual)}
