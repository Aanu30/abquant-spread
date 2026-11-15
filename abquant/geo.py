"""The map, straight-line distances, opening hours, and the arithmetic of "can this car still be on time"."""
from __future__ import annotations

import math
from typing import Optional

HOUR, DAY = 60, 24 * 60
NOTIFY_KM = 30.0          # a driver hears of a new gig when its first pickup is within 30 km of home (RULES.md)


def haversine(a: dict, b: dict) -> float:
    r = 6371.0
    dl, dn = math.radians(b["lat"] - a["lat"]), math.radians(b["lon"] - a["lon"])
    x = math.sin(dl / 2) ** 2 + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dn / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


class Geo:
    def __init__(self, world_map: dict):
        self.places = {p["id"]: p for p in world_map["places"]}
        self._min = {(r["from"], r["to"]): r["minutes"] for r in world_map["roads"]}
        self._km = {(r["from"], r["to"]): r["km"] for r in world_map["roads"]}
        ids = list(self.places)
        self.air = {(a, b): haversine(self.places[a], self.places[b]) for a in ids for b in ids}
        self.near = {a: [b for b in ids if self.air[(a, b)] <= NOTIFY_KM] for a in ids}

    def minutes(self, a: str, b: str) -> int:
        return self._min[(a, b)]

    def km(self, a: str, b: str) -> float:
        return self._km[(a, b)]


# ---------------------------------------------------------------- opening hours (minutes of the day; Sunday is closed)
def open_interval(hours: Optional[dict], day: int) -> Optional[tuple]:
    """The site's open interval on an absolute day, in world minutes, or None when it is closed that day."""
    if hours is None:                       # a private address has no hours: its window is the booked slot
        return day * DAY, (day + 1) * DAY - 1
    weekday = day % 7
    if weekday in hours["weekdays"]:
        return day * DAY + hours["opens"], day * DAY + hours["closes"]
    saturday = hours.get("saturday")
    if weekday == 5 and saturday:
        return day * DAY + saturday["opens"], day * DAY + saturday["closes"]
    return None


def next_open(hours: Optional[dict], t: int, horizon_days: int = 10) -> int:
    """The first minute at or after t at which the site is open."""
    if hours is None:
        return t
    for day in range(t // DAY, t // DAY + horizon_days):
        interval = open_interval(hours, day)
        if interval and interval[1] > t:
            return max(t, interval[0])
    return t + horizon_days * DAY


def is_business_day(day: int) -> bool:
    return day % 7 < 5


def clock(t: int) -> str:
    return f"{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][t // DAY % 7]} {t % DAY // 60:02d}:{t % 60:02d}"


def last_pickup(geo: Geo, leg: dict, deadline: int, earliest: int, extra_minutes: int = 0) -> Optional[int]:
    """The latest minute to collect the car and still deliver it by the deadline, with both sites open
    (same-day pickup and delivery, which is conservative). None when no pickup from `earliest` on can be on time."""
    pickup, delivery = leg["pickup"], leg["delivery"]
    drive = geo.minutes(pickup["placeId"], delivery["placeId"]) + extra_minutes
    lo = max(earliest, pickup["window"]["from"])
    hi = min(pickup["window"]["to"], deadline)
    day = deadline // DAY
    while day >= lo // DAY:
        d_open = open_interval(None if delivery["privateAddress"] else delivery["hours"], day)
        p_open = open_interval(None if pickup["privateAddress"] else pickup["hours"], day)
        if d_open and p_open:
            latest_arrival = min(d_open[1], deadline)
            start = max(p_open[0], lo)
            latest = min(p_open[1], hi, latest_arrival - drive)
            if latest >= start:
                return latest
        day -= 1
    return None
