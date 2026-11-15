"""The map, straight-line distances, opening hours and simple feasibility arithmetic."""
from __future__ import annotations

import json
import math
import os
from typing import Optional

from .env import ROOT

HOUR, DAY = 60, 24 * 60


def haversine(a: dict, b: dict) -> float:
    r = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class Geo:
    def __init__(self, world_map: Optional[dict] = None):
        if world_map is None:
            with open(os.path.join(ROOT, "data", "map.json"), encoding="utf-8") as f:
                world_map = json.load(f)
        self.places = {p["id"]: p for p in world_map["places"]}
        self._min: dict = {}
        self._km: dict = {}
        for r in world_map["roads"]:
            self._min[(r["from"], r["to"])] = r["minutes"]
            self._km[(r["from"], r["to"])] = r["km"]
        self.line = {(a, b): haversine(self.places[a], self.places[b]) for a in self.places for b in self.places}
        # places whose drivers get a notification for a pickup here (30 km straight line)
        self.pool = {a: [b for b in self.places if self.line[(a, b)] <= 30.0] for a in self.places}

    def minutes(self, a: str, b: str) -> int:
        return self._min.get((a, b), 0 if a == b else 600)

    def km(self, a: str, b: str) -> float:
        return self._km.get((a, b), 0.0 if a == b else 600.0)


# ---------------------------------------------------------------- opening hours
def _weekdays(hours: dict) -> set:
    days = set(hours.get("weekdays") or [])
    if days and max(days) <= 4:
        return days  # 0 = Monday
    return {d - 1 for d in days}  # ISO 1 = Monday


def open_interval(hours: Optional[dict], day: int) -> Optional[tuple]:
    """(opens, closes) in world minutes on world day `day`, or None when closed. None hours = always open."""
    if hours is None:
        return (day * DAY, day * DAY + DAY)
    dow = day % 7
    if dow == 6:
        return None
    if dow == 5:
        sat = hours.get("saturday")
        if not sat:
            return None
        return (day * DAY + sat["opens"], day * DAY + sat["closes"])
    if dow not in _weekdays(hours):
        return None
    return (day * DAY + hours["opens"], day * DAY + hours["closes"])


def next_open(hours: Optional[dict], t: int) -> int:
    """The first minute at or after t when the site is open (t itself for a private address)."""
    if hours is None:
        return t
    for k in range(10):
        iv = open_interval(hours, t // DAY + k)
        if iv is None:
            continue
        o, c = iv
        if t < c:
            return max(t, o)
    return t + 10 * DAY


def last_open_by(hours: Optional[dict], deadline: int) -> int:
    """The latest minute at or before `deadline` when the site is open: the real delivery deadline."""
    if hours is None:
        return deadline
    for k in range(10):
        iv = open_interval(hours, deadline // DAY - k)
        if iv is None:
            continue
        o, c = iv
        if o <= deadline:
            return min(c, deadline)
    return deadline - 10 * DAY


def weekday_name(t: int) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][(t // DAY) % 7]


def clock(t: int) -> str:
    return f"{weekday_name(t)} {(t % DAY) // 60:02d}:{t % 60:02d}"
