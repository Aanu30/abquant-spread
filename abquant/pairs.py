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


def charging(geo, leg: dict) -> bool:
    car = leg["car"]
    return bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
                and geo.km(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) > 200)


def pair_audience(desk, a: dict, b: dict) -> dict:
    fa, fb = desk.facts_of(desk.requests[a["id"]]), desk.facts_of(desk.requests[b["id"]])
    return {"experienced": any(leg["car"]["premium"] for o in (a, b) for leg in o["legs"]), "manualLicence": bool(fa.manual or fb.manual)}
