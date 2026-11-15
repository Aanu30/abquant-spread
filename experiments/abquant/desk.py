"""The ABQuant desk.

One rule prices every request (the proposal's reservation price):

    price = expected fee + late risk x (refund + trust lost) + markup + pool price - (1 - late risk) x trust earned

  markup       P / |P'| of a logistic acceptance curve around an online estimate of the competitor's level
  trust        tau and T come from one table V(n, k): the value of a dealer at trust count n with k requests to come
  pool price   rises with the cars we hold that have no driver yet

Posting, retries, reposts and rejoin are the kit starter's (spread.starter.Desk), which this desk extends.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import NamedTuple, Optional

import numpy as np
from spread import starter
from spread.client import SpreadError
from spread.starter import Retry, pickups, undelivered, without_windows

from . import notes
from .env import DATA
from .features import FEE_NAMES, LATE_NAMES, car_features, dot, driver_counts, sigmoid
from .geo import DAY, Geo, last_pickup, next_open, open_interval
from .pairs import chain_audience, chain_stops, pair_audience, pair_stops
from .regime import Regime


@dataclass
class Params:
    # ---- dealer side: the acceptance curve and how fast we learn the competitor's level
    theta0: float = 0.0          # competitor price / list at trust 0; 0 = take the fitted value from model.json
    s: float = 0.0               # logistic scale in log price; 0 = fitted value
    sd_world: float = 0.06       # prior sd of each part of the log level (world, dealer, pickup place, delivery place, day)
    sd_dealer: float = 0.04
    sd_from: float = 0.03
    sd_to: float = 0.03
    sd_day: float = 0.03
    sd_len: float = 0.04         # ... and of the part by lane length; its prior means come from this desk's own practice weeks
    len0: float = -0.055        # under 1 hour
    len1: float = 0.002        # 1 to 2 hours
    len2: float = 0.038        # 2 to 4 hours
    len3: float = 0.061        # 4 hours and over
    r_lo: float = 1.02
    r_hi: float = 2.60
    min_ev: int = 100            # decline when the expected profit of the best price is under this many cents
    min_margin: int = 200        # never quote under expected fee plus this many cents
    price_mult: float = 1.0      # a check on the acceptance curve: the chosen price times this
    fri_mult: float = 1.0        # the same, on Friday only
    decline_mult: float = 4.0
    regimes: bool = True         # detect the price-war day and the outage day from the day's wins and losses
    regime_v: int = 1            # 2 = judge the day against the level frozen at its start, over a grid of common shifts
    regime_cap: float = 0.6      # version 2: the most the prior may say that an event still to come is today
    regime_lo: float = -0.06     # version 2, Monday: the world's level may lie this far under the fitted one ...
    regime_hi: float = 0.14      # ... and this far over it (worlds seen: -0.02 to +0.10)
    regime_sd: float = 0.035     # version 2, later days: how far today's level may sit from yesterday's
    timers: bool = True          # practice only: stop the clock at the minute a pooled car falls due, as the live loop does
    trade_ins: bool = False
    multi_option: bool = False   # quote every option worth selling, not only the best one
    multi_share: float = 0.6     # ... whose expected profit is at least this share of the best option's
    # ---- trust: one table V(n, k) per build of the level estimate
    trust_gain: float = 0.0      # scale on tau, the value of one more on-time order (0 switches investing off)
    trust_loss: float = 1.0      # scale on T, the trust a late order destroys (0 switches protecting off)
    cbar: float = 1.10           # typical cost per order, in list prices, in the trust table (fee, risk, scarce drivers)
    pibar: float = 0.04          # typical late risk in the trust table
    prior_weeks: float = 0.5     # weight of the fitted dealer sizes against this week's own count
    sat_loss: float = 0.0        # scale on the goodwill a late order costs: the dealer then accepts lower prices all week
    sat_pass: float = 0.5        # share of a lower acceptable price that turns into lost margin
    lane_prior: float = 0.0      # weight of the lane and dealer levels learned in earlier practice weeks (data/priors.json)
    # ---- cost
    fee_scale: float = 1.0       # multiplies the fitted cost / typical fee
    late_scale: float = 1.0      # multiplies the fitted late risk
    pi_max: float = 0.15         # never sell an option whose late risk is above this
    note_unsure: float = 0.05    # late risk added when a note holds a time the reader could not place
    refund: float = 0.0          # expected refund share of the price when late; 0 = fitted
    late_extra: float = 0.0      # extra driver cost (x typical fee) of a car that runs late; 0 = fitted
    cap_open: int = 70           # stop winning when this many won cars have no driver
    # ---- the driver budget: each town's drivers supply cap_rate gigs a day; a car draws on the pickup and delivery ends
    cap_rate: float = 0.15       # gigs per roster driver per day (measured: 0.12 when saturated, 0.2 on good days)
    w_pickup: float = 0.55       # share of a car's demand that falls on drivers living near the pickup
    reach: float = 30.0          # km: drivers beyond 30 km count too, discounted by exp(-(km - 30) / reach); 0 = only within 30 km
    mu_kink: float = 0.60        # utilisation at which the pool price leaves zero
    mu_scale: float = 0.25       # pool price, x typical fee, per unit of (u - kink) / (1 - u)
    u_max: float = 0.97          # at this utilisation the pool takes no more cars
    # ---- over the budget: a finite price in place of a quote that always loses (in use since Sunday 05:50; over_mu=0 turns it off)
    over_mu: float = 1.0         # price of scarce drivers for a car over the budget, x typical fee (0 = quote 4x list as before)
    over_pi: float = 0.10        # late risk added to such a car
    over_long: bool = True       # only for long gigs (83 of the 94 over-budget requests a week are long hauls)
    over_cap: float = 2.0        # no price at all past this utilisation: bounds the overshoot (and excludes the 9.9 of a lane with no drivers)
    pi_u: float = 0.0            # late risk added per unit of utilisation above pi_u0 (measured: 2% late below 0.3, 10% at 0.6-0.8)
    pi_u0: float = 0.4
    # ---- the ranking needs 90% of won orders on time: when the week's own share sinks, stop taking risky cars
    guard_below: float = 0.0     # smoothed on-time share under which the guard is on (0 = never)
    guard_pi: float = 0.06       # the late-risk cut-off while the guard is on
    guard_pi_u: float = 0.30     # and the late risk then counts how full the drivers are (measured: +3 points per 0.1 above 0.4)
    guard_prior: int = 100       # orders at 96% on time that the smoothing starts from
    # ---- late risk the fitted model cannot see: how used the day's drivers are, by the budget and by what is on the board.
    # Measured on 12 fresh weeks. Cars for today: 4% late under 40% utilisation, 13% at 50-60%, 22% above 60%; and 4-7% late
    # with under 9 posted cars unbooked for an hour, 13% with 9-13, 25% with 13-20, 60% above. Later days: 2.5%, 5%, 9%.
    pi_same: float = 0.0         # late risk added to a car for today, per unit of utilisation above pi_same0
    pi_same0: float = 0.45
    pi_later: float = 0.0        # the same for a car planned on a later day, above pi_later0
    pi_later0: float = 0.40
    brake_k: float = 0.02        # late risk added to a car for today, per posted car unbooked for an hour above brake_s0
    brake_s0: int = 4
    long_brake: float = 0.0      # late risk added to a long gig, per long haul of ours that is stuck or came in late in the last day (0 = off)
    gig_minutes: int = 200       # a gig of this many minutes (drive plus overhead) uses one unit of the budget
    overhead: int = 60           # minutes a gig costs a driver besides the drive
    # ---- the driver's day: long gigs leave in the morning and few drivers take them (measured: about 20 a day per 1,000 drivers)
    long_min: int = 240          # a gig with this many minutes of driving is a long gig
    long_start_by: int = 630     # a long gig needs a pickup by 10:30 on its day
    cap_long: float = 0.020      # long gigs per roster driver per day
    long_reach: float = 0.0      # km: the same discount with distance, for long gigs (54% of their drivers live near neither end); 0 = as `reach`
    long_mu: float = 0.15        # standing price of a long gig's scarce drivers, x typical fee
    base_mu: float = 0.0         # standing price of any gig's drivers, x typical fee: capacity sold early is capacity refused later
    home_by: int = 1230          # a same-day driver should be home by 20:30, counting the drive time again for the trip back
    # ---- feasibility
    find_min: int = 45           # minutes a driver needs to see a gig and set off
    min_slack: int = 75          # least minutes between the answer and the last on-time pickup
    drive_buffer: float = 0.10   # share of the drive kept as a margin
    # ---- driver side: the fee schedule (x typical fee) and rescue
    f_open: float = 0.80         # the opening fee: most bookings come in the first half hour, when drivers are notified
    s0: float = 0.90             # an optional small step after hold0 minutes (0 = none): a cheaper opening, then the usual fee
    hold0: int = 30
    s1: float = 1.30             # first step: o1 minutes before the deadline warning, but hold the opening fee hold1 minutes
    o1: int = 300
    hold1: int = 40
    s2: float = 1.45
    o2: int = 120
    hold2: int = 60
    s3: float = 1.70
    o3: int = 30
    hold3: int = 45
    age1: int = 0                # also step to s1 once a gig has been open this many daytime minutes (0 = only before the warning)
    age2: int = 480              # and to s2 this many daytime minutes after that
    drop_bump: float = 1.25      # a dropped gig comes back at this multiple of the fee it was booked at
    safety: float = 0.08         # share of the drive kept clear before the last pickup and the deadline in the gig's own windows
    safety_min: int = 15
    rescue_share: float = 0.5    # after the warning, pay up to this share of what a late car would cost us
    rescue_max: float = 3.0
    late1: float = 1.2           # once a car cannot be on time, an ordinary fee finds the next day's driver
    late2: float = 1.5           # ... rising as the next day's last pickup nears
    offers: int = 3              # direct offers sent at the warning
    # ---- two cars in one gig: a driver takes a pair for less than two single fees (fork experiment: 0.70 books like a single at 0.90)
    pair: bool = True
    pair_open: float = 0.70      # opening fee of a pair, x the two typical fees
    pair_s1: float = 0.85        # after pair_hold minutes
    pair_s2: float = 1.00        # after three times pair_hold
    pair_hold: int = 60
    pair_transfer: int = 45      # the second car starts within this many minutes' drive of where the first ends
    pair_lead: int = 300         # only cars with this many minutes to their last pickup wait for a partner
    pool_wait: int = 60          # minutes a car for today waits for a partner
    pool_release: int = 1050     # a car for a later day is posted at 17:30 the day before, with whatever partner it has found
    pair_fee: float = 1.0        # expected fee of a car that can wait for a partner, x the fitted single-car fee
    lane_fee: float = 0.0        # weight of the lane's own expected fee: its share of cars that found a partner in practice
    lane_set: int = 0            # which table of lane shares: 0 = all practice weeks; 1, 2 = one half, to test on the other
    pair_ratio: float = 0.77     # fee paid for a car in a pair, x typical (measured 0.76)
    pair_open0: float = 0.0      # a first, lower fee for a pair, held pair_hold0 minutes (0 = none)
    pair_hold0: int = 30
    pair_rt0: float = 0.0        # opening fee of a round trip, in place of pair_open (round trips book within a minute at 0.70)
    pair_weight: float = 1.0     # share of a driver's day that a car which can go in a pair draws from the budget
    pair_posted: bool = False    # a pooled car may also pair with a car already posted alone that no driver has taken
    pair_reserve: bool = True    # two pooled cars that make a round trip keep each other: no third car may take one of them
    # ---- three cars in one gig (an experiment, off): a car that would go up alone joins a one-way pair, before its first car or after its last
    triple: bool = False
    triple_open: float = 0.0     # opening fee of a three-car gig, x the three typical fees (0 = as a pair)
    triple_max: int = 360        # the most planned driving minutes of a three-car gig, the drives between the cars included
                                 # (one-way pairs of 360 to 450 planned minutes are 4.7% late, under 300 minutes 1 to 2.6%)
    triple_posted: bool = True   # the third car may be one that is up alone and not taken: it comes down and joins at the end
    triple_wait: bool = True     # the third car may be one that still waits for a partner of its own
    triple_loop: bool = False    # only where the third car brings the driver back to where the gig began
    triple_rt: bool = False      # a round trip may take a third car too (it then no longer ends where it began)
    # ---- long hauls with a second car (an experiment, off): 48 of 52 long hauls a week had a car of ours that could go with them
    pool_long: int = 0           # a car with up to this many minutes of driving may wait for a partner (0 = only under long_min)
    pool_long_now: bool = False  # ... but it does not wait: it takes a partner that is waiting now, or goes up alone at once
                                 # (waiting until the evening doubled the late share of long hauls: 9% -> 18% on 12 weeks)
    # ---- inventory skew (the paper's skew toward flow that offsets what we hold): a request that completes a pair with a car we hold is worth more to us
    skew: float = 0.0            # share of the partner's fee saving credited to the request (0 = off)
    skew_fee: float = 0.80       # expected fee of a car with a partner waiting, x typical
    skew_gain: float = 0.25      # what a partner saves on the waiting car's fee, x its typical fee
    skew_rt: bool = True         # only for a request that makes a round trip with a waiting car
    offer_post: bool = False     # also offer each new gig to drivers who live at the delivery end
    chain: bool = False          # offer a new car to a driver of ours who will finish near its pickup: for them it is a ride onward
    chain_ratio: float = 0.6     # the fee of a chain offer, x typical fee
    chain_wait: int = 180        # the most minutes such a driver would wait at the pickup
    offer_post_ratio: float = 0.9


class Quoted(NamedTuple):
    kind: str
    price: int
    ratio: float
    ev: float
    prob: float
    keys: tuple
    offset: float      # the known part of the logit numerator: trust and option shifts minus ln(price / list)
    pi: float
    fee: float
    tau: float
    T: float
    mu: float
    lpa: int
    day: int = 0       # the day the car is planned to be driven
    u: float = 0.0     # utilisation of its driver pools on that day
    place: str = ""    # the pickup place, for the regime detector
    shift: float = 0.0 # the regime shift used in this quote


class Level:
    """The log of the competitor's price level, as a sum of parts, each with a Gaussian belief (mean, variance).
    Every win or loss updates all the parts of that request by one extended-Kalman step, so a part with a wide
    prior learns fast and a settled one barely moves. This is Bayes' rule with a Gaussian approximation."""

    def __init__(self, base: float, s: float, sds: dict, minutes=None, length_means=(0.0, 0.0, 0.0, 0.0)):
        self.base, self.s, self.sds, self.minutes = base, s, sds, minutes
        self.m: dict = {("len", b): m for b, m in enumerate(length_means)}
        self.v: dict = {("len", b): sds["len"] ** 2 for b in range(4)}

    def keys(self, request: dict, day: int) -> tuple:
        leg = request["legs"][0]
        minutes = self.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"])
        bucket = 0 if minutes < 60 else 1 if minutes < 120 else 2 if minutes < 240 else 3
        return (("world",), ("dealer", request["dealerId"]), ("from", leg["pickup"]["placeId"]),
                ("to", leg["delivery"]["placeId"]), ("day", day), ("len", bucket))

    def value(self, keys: tuple) -> float:
        total = self.base
        for k in keys:
            if k not in self.m:
                self.m[k], self.v[k] = 0.0, self.sds[k[0]] ** 2
            total += self.m[k]
        return total

    def update(self, keys: tuple, offset: float, won: bool) -> None:
        a = self.value(keys)
        V = sum(self.v[k] for k in keys)
        p = sigmoid((a + offset) / self.s)
        H = p * (1 - p) / self.s
        S = H * H * V + p * (1 - p) + 1e-9
        for k in keys:
            K = self.v[k] * H / S
            self.m[k] += K * ((1.0 if won else 0.0) - p)
            self.v[k] = max(1e-6, self.v[k] * (1 - K * H))

    def new_day(self) -> None:
        """The competitor moves its prices by place and by dealer some mornings: widen those beliefs a little."""
        for k in self.v:
            if k[0] in ("dealer", "from", "to"):
                self.v[k] = min(self.sds[k[0]] ** 2, self.v[k] + 0.015 ** 2)

    def world_level(self) -> float:
        return math.exp(self.base + self.m.get(("world",), 0.0))


def trust_table(theta: float, s: float, cbar: float, pibar: float, kmax: int = 420) -> np.ndarray:
    """V[k][n]: expected future margin, in list prices, from a dealer at trust count n with k requests still to come.
    Backward induction over k (Green Book 5.3): each request is priced to maximise margin now plus the change in V.
    A win lifts the count by one, or halves it with the late risk; a loss leaves it."""
    r = np.linspace(1.0, 2.8, 181)
    n = np.arange(26)
    P = 1 / (1 + np.exp(-((math.log(theta) + np.log1p(0.01 * n))[:, None] - np.log(r)[None, :]) / s))
    up, half = np.minimum(25, n + 1), n // 2
    V = np.zeros((kmax + 1, 26))
    for k in range(1, kmax + 1):
        prev = V[k - 1]
        dv = (1 - pibar) * prev[up] + pibar * prev[half] - prev
        V[k] = prev + np.maximum(0.0, np.max(P * (r[None, :] - cbar + dv[:, None]), axis=1))
    return V


def merged_hours(hours: Optional[dict], opens: Optional[int], closes: Optional[int]) -> Optional[dict]:
    """The site's stated hours narrowed by the hours its note gives."""
    if hours is None or (opens is None and closes is None):
        return hours
    o = max(hours["opens"], opens) if opens is not None else hours["opens"]
    c = min(hours["closes"], closes) if closes is not None else hours["closes"]
    if o >= c:
        return hours
    out = dict(hours, opens=o, closes=c)
    saturday = hours.get("saturday")
    if saturday:
        so, sc = max(saturday["opens"], o), min(saturday["closes"], c)
        out["saturday"] = {"opens": so, "closes": sc} if so < sc else None
    return out


def effective_leg(leg: dict, facts: notes.Facts) -> dict:
    """The leg as the world will act on it: ready time, release and real opening hours from the note."""
    pickup, delivery = dict(leg["pickup"]), dict(leg["delivery"])
    if facts.pickup_from is not None and facts.pickup_from > pickup["window"]["from"]:
        pickup["window"] = {"from": facts.pickup_from, "to": max(pickup["window"]["to"], facts.pickup_from)}
    if not pickup["privateAddress"]:
        pickup["hours"] = merged_hours(pickup["hours"], facts.pickup_open, facts.pickup_close)
    if not delivery["privateAddress"]:
        delivery["hours"] = merged_hours(delivery["hours"], facts.delivery_open, facts.delivery_close)
    return {**leg, "pickup": pickup, "delivery": delivery}


def daytime_after(t: int, minutes: int) -> int:
    """The minute that lies `minutes` of daytime (07:00 to 23:00) after t."""
    left = minutes
    while left > 0:
        day, clock_minute = t // DAY, t % DAY
        if clock_minute < 420:
            t = day * DAY + 420
        elif clock_minute >= 1380:
            t = (day + 1) * DAY + 420
        else:
            step = min(left, 1380 - clock_minute)
            t, left = t + step, left - step
    return t


def load_model() -> dict:
    with open(os.path.join(DATA, "model.json"), encoding="utf-8") as f:
        return json.load(f)


class Desk(starter.Desk):
    def __init__(self, world, level: int, now: int, params: Params, geo: Geo, roster: list, model: dict, name: str = ""):
        super().__init__(world, level, now)
        self.p, self.geo, self.model, self.name = params, geo, model, name
        self.roster = {d["id"]: d for d in roster}
        self.dens = driver_counts(geo, roster)
        acc = model["accept"]
        self.s = params.s or acc["s"]
        self.shift = acc["b"]
        self.level_est = Level(math.log(params.theta0 or acc["theta"]), self.s, {
            "world": params.sd_world, "dealer": params.sd_dealer, "from": params.sd_from, "to": params.sd_to, "day": params.sd_day,
            "len": params.sd_len}, geo.minutes, (params.len0, params.len1, params.len2, params.len3))
        if params.lane_prior:
            path = os.path.join(DATA, {1: "priors_t.json", 2: "priors_v.json"}.get(params.lane_set, "priors.json"))
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for key, mean in json.load(f).items():
                        k = tuple(key.split("|"))
                        if k[0] in ("from", "to", "dealer"):
                            self.level_est.m[k] = params.lane_prior * mean
                            self.level_est.v[k] = self.level_est.sds[k[0]] ** 2
        self.pair_rates: dict = {}
        if params.lane_fee:
            path = os.path.join(DATA, {1: "pair_rates_tv.json", 2: "pair_rates_s.json"}.get(params.lane_set, "pair_rates.json"))
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    self.pair_rates = json.load(f)
        self.refund = params.refund or model["refund_share"]
        self.late_extra = params.late_extra or model["late_cost_extra"]
        self.grid = np.arange(params.r_lo, params.r_hi + 1e-9, 0.01)
        self.log_grid = np.log(self.grid)
        self.V = trust_table(self.level_est.world_level(), self.s, params.cbar, params.pibar)
        self.day = now // DAY
        self.regime = Regime(geo, self.s, grid=params.regime_v == 2, cap=params.regime_cap if params.regime_v == 2 else 1.0)
        self.ref_m: dict = {}             # the level's parts as they stood when the day began (regime version 2)
        self.start_regime_day()
        # what the desk tracks beyond the starter
        self.quoted: dict = {}            # request id -> Quoted, until the dealer answers
        self.quoted_all: dict = {}        # request id -> {option: Quoted} when several options were quoted
        self.answered: set = set()        # request ids we have sent a quote for
        self.dealer_of: dict = {}         # order id -> dealer
        self.trust: Counter = Counter()   # dealer -> on-time count, as the rules count it
        self.lates: Counter = Counter()   # dealer -> late orders so far
        self._revenue: dict = {}          # order id -> minute of its revenue line, until settled
        self._late: set = set()
        self.seen: Counter = Counter()    # dealer -> requests so far
        self.list_sum: Counter = Counter()
        self.unbooked: set = set()        # won orders that no driver holds
        self.gig_driver: dict = {}
        self.gig_posted: dict = {}        # gig -> (minute posted, typical fee of its cars)
        self.gig_end: dict = {}           # booked gig -> (place of its last delivery, minute we expect the driver there)
        self.floor: dict = {}             # order id -> the least opening fee ratio after a drop
        self.dropped: list = []           # gigs a driver gave back since the last tick
        self.booked_ratio: dict = {}      # gig -> fee / typical at its last booking
        self.pool: dict = {}              # order id -> minute by which it is posted, while it waits for a partner
        self.paired: set = set()          # order ids that were posted in a pair
        self.mate: dict = {}              # pooled order id -> the pooled order it keeps a round trip with
        self.post_tries: Counter = Counter()   # order id -> posts the world refused
        self.pending_chain: list = []     # order ids whose new gig should be offered to drivers finishing nearby
        self.busy: set = set()            # drivers who hold one of our gigs
        self.last_view: dict = {}         # driver -> last minute they opened one of our gigs
        self.offers_sent: Counter = Counter()   # (driver, day) -> offers
        self.offer_open: Counter = Counter()    # gig -> open offers
        self.pending_offers: list = []    # order ids whose gig should get offers once the world has named it
        self.homes: Counter = Counter(d["homePlaceId"] for d in roster)   # drivers by home town
        # the towns whose drivers a place draws on. Only 40% of bookings come from within 30 km of the first pickup
        # (revealed weeks): drivers browse further out, so with `reach` the towns beyond count at a discount.
        self.catch: dict = {}
        for place in geo.places:
            towns = []
            for h in self.homes:
                km = geo.air[(place, h)]
                wt = 1.0 if km <= 30.0 else math.exp(-(km - 30.0) / params.reach) if params.reach else 0.0
                if wt >= 0.05:
                    towns.append((h, wt))
            self.catch[place] = towns
        self.n_eff = {place: sum(wt * self.homes[h] for h, wt in towns) for place, towns in self.catch.items()}
        self.catch_long, self.n_long = self.catch, self.n_eff
        if params.long_reach:
            self.catch_long = {}
            for place in geo.places:
                towns = [(h, 1.0 if geo.air[(place, h)] <= 30.0 else math.exp(-(geo.air[(place, h)] - 30.0) / params.long_reach)) for h in self.homes]
                self.catch_long[place] = [(h, wt) for h, wt in towns if wt >= 0.05]
            self.n_long = {place: sum(wt * self.homes[h] for h, wt in towns) for place, towns in self.catch_long.items()}
        self.facts: dict = {}             # request id -> what its note means
        self.forecasts: list = []         # snow forecasts
        self.demand: Counter = Counter()  # (town, day) -> gigs already promised against that town's drivers
        self.demand_long: Counter = Counter()  # the same, for long gigs only
        self.planned: dict = {}           # order id -> (pickup place, delivery place, day), while it draws on the budget
        self.won_quote: dict = {}         # order id -> the Quoted it was won with
        self.ledger: Counter = Counter()  # account lines by kind, in cents
        self.results: Counter = Counter()
        self.why: Counter = Counter()      # why an option was not quoted
        self.log: list = []
        self.sync_needed = False          # a send failed: read the world's state before acting again
        self.late_long: list = []         # minutes at which a long haul of ours was settled late

    # ------------------------------------------------------------------ the driver budget
    def _ends(self, pu: str, de: str) -> list:
        """The towns whose drivers a car draws on, with weights: the pickup end (they are notified) and the delivery end
        (they need no trip home). An end with no drivers passes its weight to the other."""
        n_pu, n_de = self.n_eff[pu], self.n_eff[de]
        if not n_pu and not n_de:
            return []
        w = 1.0 if not n_de else 0.0 if not n_pu else self.p.w_pickup
        return [(pu, w, n_pu), (de, 1 - w, n_de)]

    def utilisation(self, pu: str, de: str, day: int, long: bool = False) -> float:
        """The share of the day's drivers already promised, for the towns this car draws on. A long gig is also
        measured against the smaller budget of drivers who take long gigs."""
        ends = self._ends(pu, de)
        if not ends:
            return 9.9
        u = sum(w * sum(wt * self.demand[(h, day)] for h, wt in self.catch[place]) / (self.p.cap_rate * n) for place, w, n in ends if w)
        if long:
            u_long = sum(w * sum(wt * self.demand_long[(h, day)] for h, wt in self.catch_long[place]) / (self.p.cap_long * max(1e-9, self.n_long[place]))
                         for place, w, n in ends if w)
            u = max(u, u_long)
        return u

    def commit(self, order_id: str, pu: str, de: str, day: int, long: bool = False, weight: float = 1.0, sign: float = 1.0) -> None:
        size = weight * min(2.0, (self.geo.minutes(pu, de) + self.p.overhead) / self.p.gig_minutes)   # a short hop uses less of a driver's day
        for place, w, n in self._ends(pu, de):
            if w:
                for h, wt in self.catch[place]:
                    self.demand[(h, day)] += sign * size * w * wt * self.homes[h] / n
                if long:
                    for h, wt in self.catch_long[place]:
                        self.demand_long[(h, day)] += sign * w * wt * self.homes[h] / max(1e-9, self.n_long[place])
        if sign > 0:
            self.planned[order_id] = (pu, de, day, long, weight)
        else:
            self.planned.pop(order_id, None)

    def plan_day(self, leg: dict, deadline: int, earliest: int, extra: int) -> Optional[tuple]:
        """The feasible day on which this car's drivers are least used: (day, utilisation). A day is feasible when
        a driver can collect the car, deliver it in time, and still have a day that works: home in the evening
        for a same-day job, and a morning start for a long gig. A later option can move to a quieter day."""
        p = self.p
        pickup, delivery = leg["pickup"], leg["delivery"]
        pu, de = pickup["placeId"], delivery["placeId"]
        drive = self.geo.minutes(pu, de)
        long = drive >= p.long_min
        best = None
        for day in range(earliest // DAY, deadline // DAY + 1):
            start = max(earliest, day * DAY + 6 * 60)
            first = next_open(None if pickup["privateAddress"] else pickup["hours"], max(start, pickup["window"]["from"]))
            lp = last_pickup(self.geo, leg, min(deadline, (day + 1) * DAY - 1), start, extra)
            if lp is None or lp // DAY != day or first // DAY != day or lp - first < (p.min_slack if day == earliest // DAY else 0):
                continue
            if long and first % DAY > p.long_start_by:
                continue
            if not long and day == earliest // DAY and first % DAY + 2 * drive > p.home_by:
                continue
            u = self.utilisation(pu, de, day, long)
            if best is None or u < best[1] - 1e-9:
                best = (day, u)
        return best

    # ------------------------------------------------------------------ small helpers
    def arrivals_share(self, t: int) -> float:
        cdf, step = self.model["arrivals"]["cdf"], self.model["arrivals"]["step"]
        return cdf[min(len(cdf) - 1, max(0, t // step))]

    def remaining_requests(self, dealer: str) -> int:
        """Expected requests still to come from this dealer: the fitted size and this week's count, blended."""
        share = self.arrivals_share(self.now)
        prior = self.model["dealer_requests"].get(dealer, 5.0)
        w = self.p.prior_weeks
        total = (prior * w + self.seen[dealer]) / (w + share)
        return int(round(total * (1 - share)))

    def open_near(self, place: str) -> int:
        near = self.geo.near[place]
        return sum(1 for oid in self.unbooked if oid in self.orders and oid not in self.pool
                   and self.orders[oid]["legs"][0]["pickup"]["placeId"] in near)

    def waiting(self) -> int:
        """Won cars that are on the board with no driver. Cars still waiting for a partner are not stuck, so they do not count."""
        return sum(1 for oid in self.unbooked if oid not in self.pool)

    def trust_terms(self, dealer: str) -> tuple:
        """(tau, T) in list prices: the value of one more on-time order, and the value a late order destroys.
        T has two parts: the trust count halves (the table), and the dealer accepts lower prices from then on
        (the fitted shift of the log level per late order, on the requests still to come)."""
        n = self.trust[dealer]
        k = self.remaining_requests(dealer)
        row = self.V[min(len(self.V) - 1, k)]
        lates = self.lates[dealer]
        drop = -self.shift["log1p_lates"] * (math.log(2 + lates) - math.log(1 + lates))     # fall of the log level
        goodwill = self.p.sat_loss * self.p.sat_pass * drop * 0.4 * k * 1.4                 # x share won x price in list prices
        return float(row[min(25, n + 1)] - row[n]), float(row[n] - row[n // 2]) + goodwill

    def facts_of(self, request: dict) -> notes.Facts:
        if request["id"] not in self.facts:
            self.facts[request["id"]] = notes.read(request.get("note"), request["arrivedAt"])
        return self.facts[request["id"]]

    def snow(self, pu: str, de: str, start: int, end: int) -> bool:
        return any(f["from"] < end and f["to"] > start and (pu in f["placeIds"] or de in f["placeIds"]) for f in self.forecasts)

    # ------------------------------------------------------------------ quoting
    def evaluate(self, req: dict, opt: dict) -> Optional[Quoted]:
        p = self.p
        legs = req["legs"]
        if len(legs) > 1 and not p.trade_ins:
            self.why["trade-in"] += 1
            return None
        facts = self.facts_of(req)
        leg = effective_leg(legs[0], facts)
        pu, de = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
        t0, L, ref, dealer = req["respondBy"], opt["listPriceCents"], req["referenceFeeCents"], req["dealerId"]
        car = leg["car"]
        charging = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30 and self.geo.km(pu, de) > 200
        drive = self.geo.minutes(pu, de)
        extra = int(p.drive_buffer * drive) + (30 if facts.plates else 0) + (40 if charging else 0)
        deadline = min(opt["deadline"], facts.deadline) if facts.deadline is not None else opt["deadline"]
        earliest = t0 + p.find_min
        if facts.summer_tyres and self.snow(pu, de, earliest, deadline):
            self.why["summer tyres in snow"] += 1
            return None                                   # summer tyres cannot be collected or delivered in snow
        lpa = last_pickup(self.geo, leg, deadline, earliest, extra)
        if lpa is None or lpa - t0 < p.min_slack:
            self.why["no time left"] += 1
            return None
        planned = self.plan_day(leg, deadline, earliest, extra)
        over = False
        if planned is None or planned[1] >= p.u_max:
            over = planned is not None and p.over_mu > 0 and planned[1] < p.over_cap and (drive >= p.long_min or not p.over_long)
            if not over:
                self.why["no driver day" if planned is None else "pool full"] += 1
                return None
            self.why["over budget, priced"] += 1
        day, u = planned
        x = car_features(self.geo, self.dens, req, opt["kind"], t0, lpa, self.waiting(), self.open_near(pu))
        late = self.model["late"]
        guard = self.guarded()
        if day == t0 // DAY:
            brake = p.pi_same * max(0.0, u - p.pi_same0) + (p.brake_k * max(0, self.stale() - p.brake_s0) if p.brake_k else 0.0)
        else:
            brake = p.pi_later * max(0.0, u - p.pi_later0)
        pi = min(0.95, p.late_scale * sigmoid(dot(late["coef"], LATE_NAMES, x)) + (p.note_unsure if facts.unsure else 0.0)
                 + (max(p.pi_u, p.guard_pi_u) if guard else p.pi_u) * max(0.0, u - p.pi_u0) + brake)
        if p.long_brake and drive >= p.long_min:
            pi = min(0.95, pi + p.long_brake * self.stuck_long())
        if over:
            pi = min(0.95, pi + p.over_pi)
        if pi > (p.guard_pi if guard else p.pi_max) + (p.over_pi if over else 0.0):
            self.why["late risk" + (" (private delivery)" if leg["delivery"]["privateAddress"] else " (premium)" if car["premium"] else "")] += 1
            return None
        fee = max(0.6, p.fee_scale * dot(self.model["fee"]["coef"], FEE_NAMES, x)) * ref
        gain = 0.0
        if (p.pair and drive < p.long_min and lpa - t0 >= p.pair_lead and not car["premium"]
                and not leg["pickup"]["privateAddress"] and not leg["delivery"]["privateAddress"]):
            fee *= p.pair_fee                             # it can share a driver: most such cars go out in a pair
            if p.lane_fee:                                # paired cars cost 0.77 x typical; alone 1.08 to 1.30 by length
                n, k = self.pair_rates.get(f"{pu}|{de}", (0, 0))
                share = (k + 10 * (0.80 if drive < 60 else 0.62 if drive < 120 else 0.50)) / (n + 10)
                alone = 1.30 if drive < 60 else 1.10 if drive < 120 else 1.08
                fee = (1 - p.lane_fee) * fee + p.lane_fee * (share * p.pair_ratio + (1 - share) * alone) * ref
            if p.skew:
                partner = self.partner_for(req, opt, lpa)
                if partner is not None:                   # a car of ours waits for exactly this one
                    fee = min(fee, p.skew_fee * ref)
                    gain = p.skew * p.skew_gain * self.requests[partner]["referenceFeeCents"]
        # trust: the dealer's own average list price turns the table's list-price units into cents
        mean_list = self.list_sum[dealer] / self.seen[dealer] if self.seen[dealer] else L
        tau, T = self.trust_terms(dealer)
        tau, T = p.trust_gain * tau * mean_list, p.trust_loss * T * mean_list
        # the pool price: zero while the drivers are slack, steep near the limit (paper, Prop. 4)
        mu = p.mu_scale * ref * max(0.0, u - p.mu_kink) / (1 - min(u, 0.99)) + (p.long_mu * ref if drive >= p.long_min else 0.0) + p.base_mu * ref
        if over:
            mu = p.over_mu * ref                          # past the budget the formula above explodes: a flat, high price instead
        cost = fee + pi * (T + self.late_extra * ref) + mu - (1 - pi) * tau - gain
        # the acceptance curve: learned level, then the known shifts (trust, option, the dealer's late history)
        keys = self.level_est.keys(req, self.day)
        fixed = math.log1p(0.01 * self.trust[dealer]) + self.shift["log1p_lates"] * math.log1p(self.lates[dealer])
        if opt["kind"] != req["options"][0]["kind"]:
            fixed += self.shift["slower"]
        fixed += self.shift.get(opt["kind"], 0.0)
        shift = self.regime.shift(pu) if p.regimes and (p.regime_v != 2 or 480 <= t0 % DAY < 1095) else 0.0
        a = self.level_est.value(keys) + fixed + shift
        prob = 1 / (1 + np.exp(-(a - self.log_grid) / self.s))
        price = self.grid * L
        ev = np.where(price >= fee + p.min_margin, prob * (price * (1 - pi * self.refund) - cost), -1e18)
        i = int(np.argmax(ev))
        if ev[i] <= -1e17:
            self.why["no price pays"] += 1
            return None
        cents = int(round(price[i] * p.price_mult * (p.fri_mult if t0 // DAY == 4 else 1.0) / 100.0)) * 100
        ratio = cents / L
        return Quoted(opt["kind"], cents, ratio, float(ev[i]), float(prob[i]), keys, fixed + shift - math.log(ratio), pi, fee, tau, T, mu, lpa, day, u, pu, shift)

    def quote(self, request: dict) -> None:
        self.requests[request["id"]] = request
        dealer = request["dealerId"]
        self.seen[dealer] += 1
        self.list_sum[dealer] += request["options"][0]["listPriceCents"]
        self.regime.seen(request["legs"][0]["pickup"]["placeId"])
        if request["respondBy"] <= self.now:
            return                                        # its window closed while we were away
        best = None
        options = []
        leg0 = request["legs"][0]
        drive = self.geo.minutes(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"])
        before = Counter(self.why)
        if self.waiting() < self.p.cap_open:
            for opt in request["options"]:
                q = self.evaluate(request, opt)
                if q:
                    options.append(q)
                if q and (best is None or q.ev > best.ev):
                    best = q
        reasons = sorted((self.why - before).elements())
        if best is None or best.ev < self.p.min_ev:
            first = request["options"][0]
            self.outbox.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: int(first["listPriceCents"] * self.p.decline_mult)}})
            self.answered.add(request["id"])
            self.log.append({"t": self.now, "kind": "decline", "rid": request["id"], "dealer": dealer, "ev": round(best.ev) if best else None,
                             "drive": drive, "why": reasons, "options": [o["kind"] for o in request["options"]],
                             "pu": leg0["pickup"]["placeId"], "de": leg0["delivery"]["placeId"], "open": self.waiting()})
            return
        self.quoted[request["id"]] = best
        self.answered.add(request["id"])
        prices = {best.kind: best.price}
        if self.p.multi_option:
            sold = {q.kind: q for q in options if q.ev >= max(self.p.min_ev, self.p.multi_share * best.ev)}
            prices = {kind: q.price for kind, q in sold.items()}
            self.quoted_all[request["id"]] = sold
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})
        self.log.append({"t": self.now, "kind": "quote", "rid": request["id"], "dealer": dealer, "opt": best.kind, "price": best.price,
                         "ratio": round(best.ratio, 3), "prob": round(best.prob, 3), "ev": round(best.ev), "pi": round(best.pi, 3),
                         "fee": round(best.fee), "tau": round(best.tau), "T": round(best.T), "mu": round(best.mu), "u": round(best.u, 2),
                         "n": self.trust[dealer], "k": self.remaining_requests(dealer), "open": self.waiting(), "pool": len(self.pool), "drive": drive, "shift": round(best.shift, 3),
                         "pu": leg0["pickup"]["placeId"], "de": leg0["delivery"]["placeId"], "stale": self.stale(),
                         "list": next(o["listPriceCents"] for o in request["options"] if o["kind"] == best.kind)})

    def win(self, order: dict) -> None:
        """A won order is posted at once, or waits a while in the pool for a second car to share its driver."""
        if order["id"] not in self.requests or order["id"] in self.orders:
            return
        self.orders[order["id"]] = order
        release = self.release_time(order) if self.p.pair else None
        if release is None:
            self.post(order, undelivered(order))
        else:
            self.pool[order["id"]] = release
            if self.p.pair_reserve:
                self.reserve(order)

    def reserve(self, order: dict) -> None:
        """A car new to the pool looks for a round trip among the cars that wait: each ends where the other starts,
        the pair a driver likes best. The two then keep each other. Cars for today go up at once; cars for a later
        day go up together when the first of them falls due."""
        x = order["id"]
        x_pu, x_de = order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"]
        best = None
        for y in self.pool:
            oy = self.orders.get(y)
            if y == x or y in self.mate or oy is None:
                continue
            y_pu, y_de = oy["legs"][0]["pickup"]["placeId"], oy["legs"][0]["delivery"]["placeId"]
            if y_pu not in self.geo.near[x_de] or y_de not in self.geo.near[x_pu]:
                continue
            for a, b, hop in ((order, oy, self.geo.minutes(x_de, y_pu)), (oy, order, self.geo.minutes(y_de, x_pu))):
                if hop <= self.p.pair_transfer and (best is None or hop < best[0]):
                    plan = pair_stops(self, a, b, self.now, self.p.pair_transfer)
                    if plan and plan[2]:
                        best = (hop, y)
        if best is None:
            return
        y = best[1]
        self.mate[x], self.mate[y] = y, x
        due = min(self.pool[x], self.pool[y])
        if due <= self.now + self.p.pool_wait:
            due = self.now                                 # for today: nothing better can come, so do not wait
        self.pool[x] = self.pool[y] = due

    def release_time(self, order: dict) -> Optional[int]:
        """When a pooled order must be posted. None when it should not wait at all."""
        p, now = self.p, self.now
        leg = order["legs"][0]
        if (len(order["legs"]) != 1 or leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] or leg["car"]["premium"]
                or order["lastPickupAt"] - now < p.pair_lead
                or self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) >= max(p.long_min, p.pool_long)):
            return None                                    # a long gig needs its driver early: it goes up at once
        if p.pool_long_now and self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) >= p.long_min:
            return now                                     # a long haul keeps its hours on the board: a partner now, or alone now
        q = self.won_quote.get(order["id"])
        day = q.day if q is not None else max(now, leg["pickup"]["window"]["from"]) // DAY
        if day > now // DAY:                               # a car for a later day: the evening before, when most drivers plan
            evening = (day - 1) * DAY + p.pool_release
            if evening > now:
                return min(evening, order["lastPickupAt"] - p.pair_lead)
        return min(now + p.pool_wait, order["lastPickupAt"] - p.pair_lead)

    def match_pool(self) -> None:
        """Posts the pooled orders that are due: as pairs where a second car fits, else alone. Round trips first."""
        if not self.pool:
            return
        for oid in [o for o in self.pool if o not in self.orders]:
            del self.pool[oid]
        for oid in [o for o, m in self.mate.items() if o not in self.pool or m not in self.pool]:
            del self.mate[oid]                             # its partner has gone up or was cancelled: free again
        due = [oid for oid, t in self.pool.items() if t <= self.now]
        if not due:
            return
        options = []
        posted = self.posted_alone() if self.p.pair_posted else []
        for x in due:
            ox = self.orders[x]
            x_pu, x_de = ox["legs"][0]["pickup"]["placeId"], ox["legs"][0]["delivery"]["placeId"]
            if x in self.mate:                             # a kept round trip: only its partner
                partners = [(self.mate[x], self.orders[self.mate[x]], 0)]
            else:
                partners = [(y, self.orders[y], 0) for y in self.pool if y != x and y not in self.mate] + [(y, self.orders[y], 1) for y in posted]
            for y, oy, up in partners:
                y_pu, y_de = oy["legs"][0]["pickup"]["placeId"], oy["legs"][0]["delivery"]["placeId"]
                # a car already posted has had its notification: as the second car it costs nothing, as the first it does
                for a, b, hop, rank in ((ox, oy, self.geo.minutes(x_de, y_pu), up), (oy, ox, self.geo.minutes(y_de, x_pu), 2 * up)):
                    if hop <= self.p.pair_transfer:
                        plan = pair_stops(self, a, b, self.now, self.p.pair_transfer)
                        if plan:
                            options.append((0 if plan[2] else 1, rank, hop, plan[1], a["id"], b["id"], plan))
        used = set()
        chosen = []
        for _, _, _, _, a, b, plan in sorted(options, key=lambda o: o[:6]):
            if a not in used and b not in used:
                used |= {a, b}
                chosen.append(([a, b], plan))
        if self.p.triple:
            self.add_thirds(chosen, used, due)
        for ids, plan in chosen:
            if len(ids) == 2:
                self.post_pair(self.orders[ids[0]], self.orders[ids[1]], plan)
            else:
                self.post_chain([self.orders[i] for i in ids], plan)
        for x in due:
            if x not in used and x in self.pool:
                self.post(self.orders[x], undelivered(self.orders[x]))

    def add_thirds(self, chosen: list, used: set, due: list) -> None:
        """A third car for a one-way pair that is about to go up. First a car that would otherwise be alone: one that
        is due and found no partner, or one that is up alone and not taken (alone, a car costs 1.05 to 1.30 of its
        typical fee; in a pair 0.76). Then a car that still waits for a partner. It joins before the pair's first car
        or after its last, wherever it ends or starts close enough, on the day the pair was planned for; a third car
        that brings the driver back to the start comes first."""
        p = self.p
        thirds = [(c, 0, True) for c in due if c not in used and c not in self.mate and c in self.pool]
        if p.triple_posted:
            thirds += [(c, 0, False) for c in self.posted_alone() if c not in used]        # had its notification: only at the end
        if p.triple_wait:
            thirds += [(c, 1, True) for c in self.pool if c not in used and c not in self.mate and self.pool[c] > self.now]
        options = []
        for k, (ids, plan) in enumerate(chosen):
            if plan[2] and not p.triple_rt:
                continue                                   # a round trip stays as it is: a third car would break the loop
            a, b = self.orders[ids[0]], self.orders[ids[1]]
            a_pu, b_de = a["legs"][0]["pickup"]["placeId"], b["legs"][0]["delivery"]["placeId"]
            day = plan[0][0]["window"]["from"] // DAY
            for c, rank, may_lead in thirds:
                oc = self.orders.get(c)
                if oc is None or c in ids:
                    continue
                c_pu, c_de = oc["legs"][0]["pickup"]["placeId"], oc["legs"][0]["delivery"]["placeId"]
                for seq, hop in (([a, b, oc], self.geo.minutes(b_de, c_pu)), ([oc, a, b], self.geo.minutes(c_de, a_pu) if may_lead else None)):
                    if hop is None or hop > p.pair_transfer:
                        continue
                    new = chain_stops(self, seq, self.now, p.pair_transfer)
                    if new is None or new[1] > p.triple_max or (p.triple_loop and not new[2]) or new[0][0]["window"]["from"] // DAY != day:
                        continue
                    options.append((0 if new[2] else 1, rank, hop, new[1], k, c, [o["id"] for o in seq], new))
        taken = set()
        for _, _, _, _, k, c, ids, new in sorted(options, key=lambda o: o[:6]):
            if k not in taken and c not in used:
                taken.add(k)
                used.add(c)
                chosen[k] = (ids, new)

    def partner_for(self, req: dict, opt: dict, lpa: int) -> Optional[str]:
        """A car of ours that waits for a partner (or is up alone, not taken) and can share a driver with this request."""
        mine = {"id": req["id"], "legs": req["legs"], "deadline": opt["deadline"], "lastPickupAt": lpa}
        pu, de = req["legs"][0]["pickup"]["placeId"], req["legs"][0]["delivery"]["placeId"]
        best = None
        for y in list(self.pool) + (self.posted_alone() if self.p.pair_posted else []):
            oy = self.orders.get(y)
            if oy is None or y in self.mate:
                continue
            y_pu, y_de = oy["legs"][0]["pickup"]["placeId"], oy["legs"][0]["delivery"]["placeId"]
            if self.p.skew_rt and (y_pu not in self.geo.near[de] or y_de not in self.geo.near[pu]):
                continue
            for a, b, hop in ((mine, oy, self.geo.minutes(de, y_pu)), (oy, mine, self.geo.minutes(y_de, pu))):
                if hop <= self.p.pair_transfer and (best is None or hop < best[0]):
                    plan = pair_stops(self, a, b, self.now, self.p.pair_transfer)
                    if plan and (plan[2] or not self.p.skew_rt):
                        best = (hop, y)
        return best[1] if best else None

    def stale(self, minutes: int = 60) -> int:
        """Cars that must be collected today, posted at least `minutes` ago, that no driver has taken: a live sign
        that today's drivers are used up."""
        today_end = (self.now // DAY + 1) * DAY
        count = 0
        for oid in self.unbooked:
            order = self.orders.get(oid)
            if order is None or oid in self.pool or order["lastPickupAt"] >= today_end:
                continue
            posted = [self.gig_posted[g][0] for g in self.gigs_of(oid) if g in self.gig_posted and g not in self.booked]
            if posted and self.now - min(posted) >= minutes:
                count += 1
        return count

    def stuck_long(self) -> int:
        """Long hauls of ours that reached their deadline warning with no driver, plus those that came in late in the
        last day: a live sign that the few drivers who take long gigs are used up this week."""
        count = sum(1 for t in getattr(self, "late_long", []) if t > self.now - DAY)
        for oid in self.unbooked:
            order = self.orders.get(oid)
            if order is None or oid not in self.urgent or oid in self.pool:
                continue
            leg = order["legs"][0]
            if self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) >= self.p.long_min:
                count += 1
        return count

    def guarded(self) -> bool:
        """True while the week's on-time share, smoothed toward 96%, is under the guard level."""
        p = self.p
        if not p.guard_below:
            return False
        done = self.results["on_time"] + self.results["late"]
        return (self.results["on_time"] + 0.96 * p.guard_prior) / (done + p.guard_prior) < p.guard_below

    def posted_alone(self) -> list:
        """Cars posted alone that no driver has taken, with time left: they can still join a pair."""
        out = []
        for oid in self.unbooked:
            order = self.orders.get(oid)
            if order is None or oid in self.pool or oid in self.urgent or len(order["legs"]) != 1 or oid not in self.requests:
                continue
            gigs = self.gigs_of(oid)
            if len(gigs) != 1 or gigs[0] in self.booked or len(self.orders_of(gigs[0])) != 1:
                continue
            leg = order["legs"][0]
            if (leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] or leg["car"]["premium"]
                    or order["lastPickupAt"] - self.now < self.p.pair_lead
                    or self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) >= self.p.long_min):
                continue
            out.append(oid)
        return sorted(out)

    def post_pair(self, a: dict, b: dict, plan: tuple) -> None:
        stops, drive, round_trip = plan
        p, now = self.p, self.now
        for o in (a, b):                                   # a car that was up alone comes down first
            for gig_id in self.gigs_of(o["id"]):
                self.outbox.append({"type": "withdraw", "gigId": gig_id})
                self.log.append({"t": now, "kind": "joined", "oid": o["id"], "gig": gig_id})
            self.leg_gigs.pop(o["id"], None)
        total = self.requests[a["id"]]["referenceFeeCents"] + self.requests[b["id"]]["referenceFeeCents"]
        end = stops[0]["window"]["to"]                      # the gig leaves the app when its first window ends
        first = [(now, p.pair_open0)] if p.pair_open0 and now + p.pair_hold0 < end - 60 else []
        t0 = now + p.pair_hold0 if first else now
        opening = p.pair_rt0 if round_trip and p.pair_rt0 else p.pair_open
        steps = first + [(t0, opening)] + [(t, r) for t, r in ((t0 + p.pair_hold, p.pair_s1), (t0 + 3 * p.pair_hold, p.pair_s2)) if t < end - 30]
        schedule = [{"at": int(t), "feeCents": int(total * r + 0.5)} for t, r in steps]
        self.outbox.append({"type": "post", "stops": stops, "audience": pair_audience(self, a, b), "schedule": schedule})
        for o in (a, b):
            self.pool.pop(o["id"], None)
            self.paired.add(o["id"])
        self.log.append({"t": now, "kind": "pair", "a": a["id"], "b": b["id"], "drive": drive, "round_trip": round_trip, "ref": total})

    def post_chain(self, orders: list, plan: tuple) -> None:
        """Three cars for one driver, posted as a pair is: one fee for the lot, on the pair's steps."""
        stops, drive, loop = plan
        p, now = self.p, self.now
        for o in orders:                                   # a car that was up alone comes down first
            for gig_id in self.gigs_of(o["id"]):
                self.outbox.append({"type": "withdraw", "gigId": gig_id})
                self.log.append({"t": now, "kind": "joined", "oid": o["id"], "gig": gig_id})
            self.leg_gigs.pop(o["id"], None)
        total = sum(self.requests[o["id"]]["referenceFeeCents"] for o in orders)
        end = stops[0]["window"]["to"]                      # the gig leaves the app when its first window ends
        opening = min(p.pair_s1, p.triple_open or p.pair_open)
        steps = [(now, opening)] + [(t, r) for t, r in ((now + p.pair_hold, p.pair_s1), (now + 3 * p.pair_hold, p.pair_s2)) if t < end - 30]
        schedule = [{"at": int(t), "feeCents": int(total * r + 0.5)} for t, r in steps]
        self.outbox.append({"type": "post", "stops": stops, "audience": chain_audience(self, orders), "schedule": schedule})
        for o in orders:
            self.pool.pop(o["id"], None)
            self.paired.add(o["id"])
        self.log.append({"t": now, "kind": "triple", "oids": [o["id"] for o in orders], "drive": drive, "round_trip": loop, "ref": total})

    def unpair(self, gig_id: str, withdraw: bool) -> None:
        """A pair that found no driver goes back up as two single gigs."""
        oids = self.orders_of(gig_id)
        if withdraw:
            self.outbox.append({"type": "withdraw", "gigId": gig_id})
        for oid in oids:
            legs = self.leg_gigs.get(oid, {})
            for leg in [leg for leg, g in legs.items() if g == gig_id]:
                legs.pop(leg, None)
        for oid in oids:
            order = self.orders.get(oid)
            if order is not None and not self.gigs_of(oid) and undelivered(order):
                self.post(order, undelivered(order))

    def learn(self, rid: str, won: bool) -> Optional[Quoted]:
        q = self.quoted.pop(rid, None)
        if q is not None:
            if self.p.regimes and self.p.regime_v == 2:
                if 480 <= self.now % DAY < 1095:           # the events run 08:00 to 18:00; a quote is answered within 15 minutes
                    usual = self.level_est.base + sum(self.ref_m.get(k, 0.0) for k in q.keys)
                    self.regime.observe(won, usual + q.offset - q.shift, q.place)
            elif self.p.regimes:    # the detector sees the outcome against the usual level, without today's shift
                self.regime.observe(won, self.level_est.value(q.keys) + q.offset - q.shift, q.place)
            self.level_est.update(q.keys, q.offset, won)
        return q

    def start_regime_day(self) -> None:
        """A new day for the detector. Version 2 freezes the level here: the day is judged against it, with a grid of
        common shifts for what is honestly unknown: the whole world level on Monday, the day factor afterwards."""
        p = self.p
        if p.regime_v != 2:
            self.regime.start_day(self.day)
            return
        self.ref_m = dict(self.level_est.m)
        if self.day == 0:
            steps = int(round((p.regime_hi - p.regime_lo) / 0.02))
            shifts = tuple(p.regime_lo + 0.02 * i for i in range(steps + 1))
            prior = tuple(1.0 for _ in shifts)
        else:
            shifts = tuple(0.02 * i for i in range(-4, 5))
            prior = tuple(math.exp(-0.5 * (x / p.regime_sd) ** 2) for x in shifts)
        self.regime.start_day(self.day, shifts, prior)

    # ------------------------------------------------------------------ sending
    def send(self) -> None:
        """Sends the outbox now, quotes first, 50 actions a request. A batch the world rejects as malformed goes one
        action at a time, so one bad action cannot block the rest. When the world does not answer, the unsent actions
        stay in the outbox, and `sync_needed` tells the live loop to read the world's state before it acts again.
        Never raises: it is also called from inside the event handlers."""
        actions, self.outbox = self.outbox, []
        if not actions:
            return
        actions.sort(key=lambda a: 0 if a["type"] == "quote" else 1)
        done = 0
        try:
            for i in range(0, len(actions), 50):
                chunk = actions[i:i + 50]
                try:
                    results = self.world.act(chunk)
                except SpreadError as error:
                    if error.status != 400:
                        raise
                    results = []
                    for action in chunk:
                        try:
                            results += self.world.act([action])
                        except SpreadError as one:
                            if one.status != 400:
                                raise
                            results.append({"ok": False, "reason": f"rejected: {one}"})
                done = i + len(chunk)
                self.read_results(chunk, results)
                for action, result in zip(chunk, results):
                    if not result["ok"]:
                        self.log.append({"t": self.now, "kind": "refused", "action": action["type"], "reason": result["reason"][:200]})
        except SpreadError as error:
            self.outbox = actions[done:] + self.outbox
            self.sync_needed = True
            self.log.append({"t": self.now, "kind": "send_failed", "error": str(error)[:200], "kept": len(actions) - done})

    def next_timer(self) -> Optional[int]:
        """The next minute at which the desk has work without an event: a pooled order falls due."""
        return min(self.pool.values(), default=None)

    # ------------------------------------------------------------------ events
    def handle(self, event: dict) -> None:
        k = event["kind"]
        if k == "order_won":
            order = event["order"]
            sold = self.quoted_all.pop(order["id"], None)
            if sold and order["option"] in sold:
                self.quoted[order["id"]] = sold[order["option"]]     # learn from the option the dealer took
            q = self.learn(order["id"], True)
            self.dealer_of[order["id"]] = order["dealerId"]
            self.unbooked.add(order["id"])
            if q is not None:
                self.won_quote[order["id"]] = q
                leg = order["legs"][0]
                pu_, de_ = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
                shares = self.p.pair and self.p.pair_weight != 1.0 and self.release_time(order) is not None
                self.commit(order["id"], pu_, de_, q.day, self.geo.minutes(pu_, de_) >= self.p.long_min, self.p.pair_weight if shares else 1.0)
            super().handle(event)
        elif k == "order_lost":
            self.quoted_all.pop(event["requestId"], None)
            self.learn(event["requestId"], False)
        elif k == "gig_booked":
            super().handle(event)
            self.gig_driver[event["gigId"]] = event["driverId"]
            posted = self.gig_posted.get(event["gigId"])
            if posted:
                self.booked_ratio[event["gigId"]] = event["feeCents"] / max(1, posted[1])
                home = self.roster.get(event["driverId"], {}).get("homePlaceId")
                self.log.append({"t": event["at"], "kind": "booked", "gig": event["gigId"], "ratio": round(event["feeCents"] / max(1, posted[1]), 3),
                                 "age": event["at"] - posted[0], "home": home, "oids": self.orders_of(event["gigId"])})
            self.busy.add(event["driverId"])
            for oid in self.orders_of(event["gigId"]):
                self.unbooked.discard(oid)
            post = self.posts.get(event["gigId"])
            order = self.orders.get(post["stops"][-1]["orderId"]) if post else None
            if order is not None:
                leg = order["legs"][post["stops"][-1]["leg"]]
                drive = self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"])
                self.gig_end[event["gigId"]] = (leg["delivery"]["placeId"], max(event["at"] + 60, leg["pickup"]["window"]["from"]) + drive)
        elif k == "picked_up":
            order = self.orders.get(event["orderId"])
            if order is not None and event["gigId"] in self.gig_end:
                leg = order["legs"][event["leg"]]
                self.gig_end[event["gigId"]] = (leg["delivery"]["placeId"], event["at"] + self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]))
        elif k in ("gig_dropped", "no_show"):
            self.gig_end.pop(event["gigId"], None)
            super().handle(event)
            self.dropped.append(event["gigId"])
            self.busy.discard(event["driverId"])
            for oid in self.orders_of(event["gigId"]):
                if oid in self.orders:
                    self.unbooked.add(oid)
        elif k == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
        elif k == "offer_answered":
            self.offer_open[event["gigId"]] = max(0, self.offer_open[event["gigId"]] - 1)
            self.log.append({"t": event["at"], "kind": "offer_answer", "gig": event["gigId"], "answer": event["answer"], "driver": event["driverId"]})
        elif k == "delivered":
            super().handle(event)
            order = self.orders.get(event["orderId"])
            if order is not None and all(t is not None for t in order["deliveredAt"]):
                self.unbooked.discard(event["orderId"])
                self.busy.discard(self.gig_driver.get(event["gigId"], ""))
                self.gig_end.pop(event["gigId"], None)
                if self.p.chain:                      # the driver is free here now: any open car of ours nearby is a ride onward
                    self.chain_from(self.gig_driver.get(event["gigId"]), event["placeId"], event["at"])
        elif k == "order_cancelled":
            partners = {o for g in event.get("gigs", []) if g["outcome"] == "withdrawn" for o in self.orders_of(g["gigId"]) if o != event["orderId"]}
            super().handle(event)
            self.pool.pop(event["orderId"], None)
            for oid in partners:
                self.leg_gigs.pop(oid, None)
                order = self.orders.get(oid)
                if order is not None and undelivered(order):
                    self.post(order, undelivered(order))
            self.unbooked.discard(event["orderId"])
            if event["orderId"] in self.planned:
                self.commit(event["orderId"], *self.planned[event["orderId"]], sign=-1.0)
        elif k == "ledger":
            line = event["line"]
            self.ledger[line["kind"]] += line["cents"]
            if line["orderId"]:
                if line["kind"] == "revenue":
                    self._revenue[line["orderId"]] = line["at"]
                elif line["kind"] in ("late_refund", "undelivered_penalty"):
                    self._late.add(line["orderId"])
        elif k == "forecast":
            self.forecasts.append(event)
        elif k == "visit_failed":
            request = self.requests.get(event["orderId"], {})
            self.log.append({"t": event["at"], "kind": "visit_failed", "oid": event["orderId"], "reason": event["reason"],
                             "pair": len(self.orders_of(event["gigId"])) > 1, "note": (request.get("note") or {}).get("text")})
            super().handle(event)
        else:
            super().handle(event)

    def carry(self, action: dict, gig_id: str) -> None:
        super().carry(action, gig_id)
        if gig_id not in self.gig_posted:
            total = 0.0
            for stop in action["stops"]:
                order, request = self.orders.get(stop["orderId"]), self.requests.get(stop["orderId"])
                if stop["kind"] == "pickup" and order is not None and request is not None:
                    total += request["referenceFeeCents"] / len(order["legs"])
            if total:
                self.gig_posted[gig_id] = (self.now, total)

    # ------------------------------------------------------------------ after a stop: rebuild and reconcile
    def rebuild(self, snapshot: dict, history: list) -> None:
        """A start in the middle of a week with no saved state: take what the history and the snapshot can give.
        Trust counts come back exactly (they are in the ledger); the learned price level starts from its prior."""
        for event in history:
            k = event["kind"]
            if k == "price_request":
                r = event["request"]
                self.requests[r["id"]] = r
                self.seen[r["dealerId"]] += 1
                self.list_sum[r["dealerId"]] += r["options"][0]["listPriceCents"]
                self.regime.seen(r["legs"][0]["pickup"]["placeId"])
                self.answered.add(r["id"])
            elif k == "order_won":
                self.dealer_of[event["order"]["id"]] = event["order"]["dealerId"]
            elif k == "gig_viewed":
                self.last_view[event["driverId"]] = event["at"]
            elif k == "forecast":
                self.forecasts.append(event)
            elif k == "ledger":
                line = event["line"]
                self.ledger[line["kind"]] += line["cents"]
                if line["orderId"]:
                    if line["kind"] == "revenue":
                        self._revenue[line["orderId"]] = line["at"]
                    elif line["kind"] in ("late_refund", "undelivered_penalty"):
                        self._late.add(line["orderId"])
        self.tick()
        for request in snapshot["openRequests"]:
            self.answered.discard(request["id"])
        super().rejoin(snapshot, history)                 # the starter's books: orders, gigs, missing posts, open requests
        self.after_snapshot(snapshot)

    def reconcile(self, snapshot: dict) -> None:
        """After loading saved state and reading the missed events: make the books agree with the server."""
        self.booked = {g["id"] for g in snapshot["gigs"] if g["status"] in ("booked", "working", "done")}
        self.leg_gigs = {}
        carried = set()
        for gig in snapshot["gigs"]:
            if gig["status"] in ("open", "booked", "working"):
                self.carry({"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}, gig["id"])
                carried |= {(stop["orderId"], stop["leg"]) for stop in gig["stops"]}
        # an action kept from a send that got no answer may have reached the world after all
        open_ids = {request["id"] for request in snapshot["openRequests"]}
        self.outbox = [a for a in self.outbox
                       if not (a["type"] == "post" and any((s["orderId"], s["leg"]) in carried for s in a["stops"]))
                       and not (a["type"] == "quote" and a["requestId"] not in open_ids)]
        pending = {stop["orderId"] for a in self.outbox if a["type"] == "post" for stop in a["stops"]}
        for order in snapshot["orders"]:
            if order["id"] not in self.requests:
                continue
            if order["status"] == "cancelled":
                self.orders.pop(order["id"], None)
                self.pool.pop(order["id"], None)
                continue
            self.orders[order["id"]] = order
            if order["status"] == "waiting" and not self.gigs_of(order["id"]) and order["id"] not in self.pool and order["id"] not in pending:
                self.post(order, undelivered(order))
        for request in snapshot["openRequests"]:
            if request["id"] not in self.answered:
                self.quote(request)
        self.after_snapshot(snapshot)
        self.sync_needed = False

    def audit(self, snapshot: dict) -> list:
        """Where the desk's books disagree with the world: a won car with no gig, or a gig the desk does not know."""
        live = [g for g in snapshot["gigs"] if g["status"] in ("open", "booked", "working")]
        carried = {stop["orderId"] for g in live for stop in g["stops"]}
        pending = {stop["orderId"] for a in self.outbox if a["type"] == "post" for stop in a["stops"]}
        out = [f"order {o['id']} waits with no gig" for o in snapshot["orders"]
               if o["status"] == "waiting" and o["id"] in self.requests and o["id"] not in carried and o["id"] not in self.pool and o["id"] not in pending]
        out += [f"gig {g['id']} is not in the books" for g in live if g["id"] not in self.posts]
        return out

    def after_snapshot(self, snapshot: dict) -> None:
        """The desk's own books, from the server's view of orders and gigs."""
        self.unbooked, self.busy = set(), set()
        for gig in snapshot["gigs"]:
            if gig["status"] in ("booked", "working") and gig.get("driverId"):
                self.gig_driver[gig["id"]] = gig["driverId"]
                self.busy.add(gig["driverId"])
            if gig["status"] in ("open", "booked", "working") and gig["id"] not in self.gig_posted:
                order = self.orders.get(gig["stops"][0]["orderId"])
                request = self.requests.get(gig["stops"][0]["orderId"])
                if order is not None and request is not None:
                    cars = sum(1 for stop in gig["stops"] if stop["kind"] == "pickup")
                    self.gig_posted[gig["id"]] = (gig["postedAt"], request["referenceFeeCents"] * cars / len(order["legs"]))
        for order in snapshot["orders"]:
            oid = order["id"]
            if oid not in self.orders:
                continue
            self.dealer_of[oid] = order["dealerId"]
            if order["status"] == "waiting" and not any(g in self.booked for g in self.gigs_of(oid)):
                self.unbooked.add(oid)
            if oid not in self.planned and order["status"] in ("waiting", "booked"):
                leg = order["legs"][0]
                pu, de = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
                self.commit(oid, pu, de, max(self.now, leg["pickup"]["window"]["from"]) // DAY, self.geo.minutes(pu, de) >= self.p.long_min)

    def orders_of(self, gig_id: str) -> list:
        post = self.posts.get(gig_id)
        return list(dict.fromkeys(s["orderId"] for s in post["stops"])) if post else []

    def tick(self) -> None:
        """After each batch of events: settle the trust counts, and start a new day when midnight has passed."""
        for oid, at in list(self._revenue.items()):
            if at < self.now:                              # a late refund comes in the same minute as the revenue: wait for the minute to pass
                dealer = self.dealer_of.get(oid)
                if dealer is not None:
                    late = oid in self._late
                    if late:
                        self.trust[dealer] //= 2
                        self.lates[dealer] += 1
                        done = self.orders.get(oid)
                        if done is not None and self.geo.minutes(done["legs"][0]["pickup"]["placeId"], done["legs"][0]["delivery"]["placeId"]) >= self.p.long_min:
                            if not hasattr(self, "late_long"):
                                self.late_long = []
                            self.late_long.append(self.now)
                    else:
                        self.trust[dealer] = min(25, self.trust[dealer] + 1)
                    q = self.won_quote.pop(oid, None)
                    self.results["late" if late else "on_time"] += 1
                    self.log.append({"t": self.now, "kind": "result", "oid": oid, "dealer": dealer, "late": late,
                                     "pi": round(q.pi, 3) if q else None, "opt": q.kind if q else None, "u": round(q.u, 2) if q else None,
                                     "pair": oid in self.paired, "urgent": oid in self.urgent})
                del self._revenue[oid]
        if self.now // DAY > self.day:
            self.day = self.now // DAY
            self.start_regime_day()
            self.level_est.new_day()
            self.V = trust_table(self.level_est.world_level(), self.s, self.p.cbar, self.p.pibar)
        if self.p.pair:
            self.match_pool()
        for gig_id in self.dropped:                    # a gig given back was priced too close to the driver's cost: lift it now
            oids = self.orders_of(gig_id)
            if gig_id in self.booked or len(oids) != 1 or oids[0] not in self.orders or oids[0] in self.urgent:
                continue
            order = self.orders[oids[0]]
            if self.leg_gigs.get(order["id"], {}).get(self.posts[gig_id]["stops"][0]["leg"]) != gig_id:
                continue
            self.floor[order["id"]] = min(self.p.s2, max(self.floor.get(order["id"], 0.0), self.booked_ratio.get(gig_id, self.p.f_open) * self.p.drop_bump))
            self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": self.fees_for(order, pickups(self.posts[gig_id]))})
        self.dropped = []
        waiting = []
        for oid in self.pending_offers:
            gigs = self.gigs_of(oid)
            if not gigs and oid in self.orders:
                waiting.append(oid)                    # the world has not named the gig yet
            for gig_id in gigs:
                if gig_id not in self.booked:
                    self.send_offers(oid, gig_id, rescue=False)
        self.pending_offers = waiting
        waiting = []
        for oid in self.pending_chain:
            gigs = self.gigs_of(oid)
            if not gigs and oid in self.orders:
                waiting.append(oid)
            for gig_id in gigs:
                if gig_id not in self.booked:
                    self.chain_to(oid, gig_id)
        self.pending_chain = waiting

    # ------------------------------------------------------------------ gigs and fees
    def one_day(self, leg: dict, deadline: int, start: int) -> Optional[tuple]:
        """The first day on which the car can be collected and delivered inside both sites' real hours:
        ((pickup from, pickup to), (delivery from, delivery to))."""
        pickup, delivery = leg["pickup"], leg["delivery"]
        drive = int(self.geo.minutes(pickup["placeId"], delivery["placeId"]) * (1 + self.p.drive_buffer))
        for day in range(start // DAY, deadline // DAY + 1):
            p_open = open_interval(None if pickup["privateAddress"] else pickup["hours"], day)
            d_open = open_interval(None if delivery["privateAddress"] else delivery["hours"], day)
            if not p_open or not d_open:
                continue
            arrive_by = min(d_open[1], deadline)
            p_from = max(p_open[0], start, pickup["window"]["from"])
            p_to = min(p_open[1] - 10, arrive_by - drive, pickup["window"]["to"])
            d_from = max(d_open[0], delivery["window"]["from"])
            if p_to - p_from >= 20 and arrive_by > d_from:
                return (p_from, p_to), (d_from, arrive_by)
        return None

    def stops_for(self, order: dict, legs: list, retry: Retry) -> list:
        """A pickup and a delivery for each leg, with their own windows only where the note or a failed visit needs
        them. Drivers plan by the stated hours, so when a note gives different hours the gig is pinned to one day
        inside the real ones; if nobody books it that day, the expiry reposts it for the next."""
        request = self.requests[order["id"]]
        facts = self.facts_of(request)
        stops = []
        for i in legs:
            raw = order["legs"][i]
            leg = effective_leg(raw, facts)
            pickup, delivery, car = leg["pickup"], leg["delivery"], raw["car"]
            deadline = min(order["deadline"], facts.deadline) if facts.deadline is not None else order["deadline"]
            first = {"orderId": order["id"], "leg": i, "kind": "pickup", "withPlates": bool(retry.plates or facts.plates),
                     "withCharging": bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
                                          and self.geo.km(pickup["placeId"], delivery["placeId"]) > 200)}
            second = {"orderId": order["id"], "leg": i, "kind": "delivery"}
            start = max(self.now, pickup["window"]["from"], retry.pickup_from)
            hours_differ = pickup["hours"] != raw["pickup"]["hours"] or delivery["hours"] != raw["delivery"]["hours"]
            day = self.one_day(leg, deadline, start) if hours_differ and not pickup["privateAddress"] else None
            if day is None and hours_differ and not pickup["privateAddress"]:
                day = self.one_day(leg, start + 6 * DAY, start)        # late already: still only inside the real hours
            if day:
                first["window"] = {"from": day[0][0], "to": day[0][1]}
                second["window"] = {"from": day[1][0], "to": day[1][1]}
            else:
                # drive times vary, so the gig's own windows keep a margin before the last pickup and before the deadline
                drive = self.geo.minutes(pickup["placeId"], delivery["placeId"])
                margin = max(self.p.safety_min, int(self.p.safety * drive))
                latest = last_pickup(self.geo, leg, deadline - margin, start, 30 if first["withPlates"] else 0) if deadline - margin > self.now else None
                if latest is not None and latest - start >= 20 and not pickup["privateAddress"]:
                    first["window"] = {"from": start, "to": latest}
                    second["window"] = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"] + 1, deadline - margin)}
                else:                                                            # late already, or a private slot: only the facts that bind
                    if start > max(self.now, raw["pickup"]["window"]["from"]):   # ready later, released later, or a retry
                        first["window"] = {"from": start, "to": max(start, pickup["window"]["to"])}
                    if deadline < order["deadline"] and deadline > self.now:     # a tighter deadline from the note
                        second["window"] = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], deadline)}
            stops += [first, second]
        return stops

    def post(self, order: dict, legs: list, retry: Retry = Retry()) -> None:
        self.pool.pop(order["id"], None)
        facts = self.facts_of(self.requests[order["id"]])
        audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]), "manualLicence": bool(retry.manual_licence or facts.manual)}
        stops = without_windows(self.stops_for(order, legs, retry), self.now)
        for stop in stops:                     # the world refuses a window that ends before it starts: drop it instead
            window = stop.get("window")
            if window and window["to"] < window["from"]:
                del stop["window"]
        self.outbox.append({"type": "post", "stops": stops, "audience": audience, "schedule": self.fees_for(order, len(legs))})
        if self.p.offer_post and order["id"] not in self.urgent:
            self.pending_offers.append(order["id"])
        if self.p.chain:
            self.pending_chain.append(order["id"])
        if len(legs) == 1:
            return
        self.send()                            # a trade-in over the 12-hour limit goes as one gig per car
        if not self.gigs_of(order["id"]):
            for leg in legs:
                self.post(order, [leg], retry)

    def repost(self, gig_id: str) -> None:
        """A gig whose window ended with no driver goes up again, for the next day its sites are really open."""
        action = self.posts.get(gig_id)
        if action is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
            return
        if len(self.orders_of(gig_id)) > 1:
            self.unpair(gig_id, withdraw=False)
            return
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        order = self.orders.get(action["stops"][0]["orderId"])
        if order is None:
            return
        legs = sorted({s["leg"] for s in action["stops"] if s["kind"] == "pickup"})
        plates = any(s.get("withPlates") for s in action["stops"])
        self.post(order, legs, Retry(0, action["audience"]["manualLicence"], plates))

    def withdraw(self, order_id: str) -> bool:
        partners = {o for g in self.gigs_of(order_id) for o in self.orders_of(g) if o != order_id}
        done = super().withdraw(order_id)
        if done:
            for oid in partners:
                self.leg_gigs.pop(oid, None)
                order = self.orders.get(oid)
                if order is not None and undelivered(order):
                    self.post(order, undelivered(order))
        return done

    def read_results(self, actions: list, results: list) -> None:
        """Remembers each gig the world accepted. A post it refused must not strand its cars: they go up again alone,
        and the second time without windows of their own."""
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if action["type"] == "withdraw" and not result["ok"] and action["gigId"] in self.posts:
                post = self.posts[action["gigId"]]
                if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) for s in post["stops"]):
                    self.carry(post, action["gigId"])       # a driver took it first: it still carries its cars
                    for stop in post["stops"]:
                        self.paired.discard(stop["orderId"])
        for action, result in zip(actions, results):
            if action["type"] != "post" or result["ok"]:
                continue
            for oid in dict.fromkeys(stop["orderId"] for stop in action["stops"]):
                order = self.orders.get(oid)
                if order is None or self.gigs_of(oid) or not undelivered(order):
                    continue
                self.post_tries[oid] += 1
                self.log.append({"t": self.now, "kind": "post_refused", "oid": oid, "reason": result["reason"][:160], "try": self.post_tries[oid]})
                if self.post_tries[oid] == 1:
                    self.post(order, undelivered(order))
                elif self.post_tries[oid] <= 3:
                    stops = [{k: v for k, v in stop.items() if k != "window"} for stop in self.stops_for(order, undelivered(order), Retry())]
                    self.outbox.append({"type": "post", "stops": stops, "audience": action["audience"], "schedule": self.fees_for(order, len(undelivered(order)))})

    def stake(self, order: dict) -> float:
        """What a late delivery of this order would cost: the refund, and the trust it destroys with its dealer."""
        dealer = order["dealerId"]
        mean_list = self.list_sum[dealer] / self.seen[dealer] if self.seen[dealer] else order["priceCents"]
        return self.refund * order["priceCents"] + self.p.trust_loss * self.trust_terms(dealer)[1] * mean_list

    def rescue_ratio(self, order: dict, ref: float) -> float:
        """The mirror rule after the warning: a fee is worth raising only while it costs less than the loss it avoids."""
        return min(self.p.rescue_max, self.p.s2 + self.p.rescue_share * self.stake(order) / max(1.0, ref))

    def fees_for(self, order: dict, cars: int) -> list:
        """The fee schedule from now. The opening fee is held while the notified drivers look; the steps then come
        early enough to leave hours at each level before the deadline warning. After the warning the fee goes to
        what the car's lateness would cost us, and no further."""
        p = self.p
        fee = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        now = self.now
        if now >= order["lastPickupAt"] - 180:
            self.urgent.add(order["id"])                    # already inside the warning's three hours: no time for early steps
        if order["id"] in self.urgent and now < order["lastPickupAt"] - 20:
            top = self.rescue_ratio(order, fee)                     # still savable: pay up to what lateness would cost
            steps = [(now, max(p.s1, top - 0.3)), (now + 30, top)]
        elif order["id"] in self.urgent:
            nxt = order["lastPickupAt"] + DAY                       # late already: the refund tier holds for a day, so do not overpay
            while nxt // DAY % 7 >= 5:
                nxt += DAY
            steps = [(now, p.late1), (max(now + 60, nxt - 480), p.late2), (max(now + 120, nxt - 240), p.s3)]
        else:
            warning = order["lastPickupAt"] - 180
            t1 = max(now + p.hold1, min(warning - p.o1, daytime_after(now, p.age1)) if p.age1 else warning - p.o1)
            t2 = max(t1 + p.hold2, min(warning - p.o2, daytime_after(t1, p.age2)) if p.age1 else warning - p.o2)
            t3 = max(t2 + p.hold3, warning - p.o3)
            opening = max(p.f_open, self.floor.get(order["id"], 0.0))       # a dropped gig does not come back at the fee that failed
            early = [(now + p.hold0, p.s0)] if p.s0 > opening and now + p.hold0 < t1 else []
            steps = [(now, opening)] + early + [(t, max(r, opening)) for t, r in ((t1, p.s1), (t2, p.s2), (t3, p.s3)) if t < warning + 60]
        out, top_cents = [], 0
        for at, ratio in steps:
            cents = max(top_cents, int(fee * ratio + 0.5))
            if not out or cents > top_cents:
                out.append({"at": int(at), "feeCents": cents})
            top_cents = cents
        self.log.append({"t": now, "kind": "fees", "oid": order["id"], "urgent": order["id"] in self.urgent,
                         "ref": round(fee), "steps": [(s["at"] - now, s["feeCents"]) for s in out]})
        return out

    def raise_fees(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        if order is None:
            return
        self.urgent.add(order_id)
        if order_id in self.pool:                           # still waiting for a partner: no more waiting
            self.post(order, undelivered(order))
            return
        pairs = [g for g in self.gigs_of(order_id) if len(self.orders_of(g)) > 1 and g not in self.booked]
        if pairs:
            for gig_id in pairs:
                self.unpair(gig_id, withdraw=True)
            return
        super().raise_fees(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id not in self.booked:
                self.send_offers(order_id, gig_id, rescue=True)

    def offer(self, gig_id: str, driver: str, fee: int, why: str) -> bool:
        today = self.now // DAY
        if not driver or self.offers_sent[(driver, today)] >= 3 or self.offer_open[gig_id] >= 3:
            return False
        self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver, "feeCents": fee})
        self.offers_sent[(driver, today)] += 1
        self.offer_open[gig_id] += 1
        self.log.append({"t": self.now, "kind": "offer", "gig": gig_id, "driver": driver, "fee": fee, "why": why})
        return True

    def fits(self, driver: str, post: dict) -> bool:
        d = self.roster.get(driver)
        if d is None:
            return False
        if post["audience"]["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
            return False
        return not (post["audience"]["manualLicence"] and d["licence"] != "manual")

    def chain_to(self, order_id: str, gig_id: str) -> None:
        """A new car: offer it to drivers of ours who will finish near its pickup in time to take it on."""
        post, order = self.posts.get(gig_id), self.orders.get(order_id)
        if post is None or order is None or len(self.orders_of(gig_id)) != 1:
            return
        leg = order["legs"][post["stops"][0]["leg"]]
        near = self.geo.near[leg["pickup"]["placeId"]]
        fee = int(self.gig_posted.get(gig_id, (0, self.requests[order_id]["referenceFeeCents"]))[1] * self.p.chain_ratio + 0.5)
        ready = max(self.now, leg["pickup"]["window"]["from"])
        ranked = []
        for other, (place, eta) in self.gig_end.items():
            if place in near and eta <= order["lastPickupAt"] - 20 and eta >= ready - self.p.chain_wait:
                driver = self.gig_driver.get(other)
                if driver and self.fits(driver, post):
                    ranked.append((abs(eta - ready), driver))
        for _, driver in sorted(ranked)[:2]:
            self.offer(gig_id, driver, fee, "chain")

    def chain_from(self, driver: Optional[str], place: str, at: int) -> None:
        """A driver of ours has just delivered here: offer them an open car of ours that starts nearby."""
        if not driver:
            return
        best = None
        for oid in self.unbooked:
            order = self.orders.get(oid)
            if order is None or oid in self.urgent:
                continue
            for gig_id in self.gigs_of(oid):
                post = self.posts.get(gig_id)
                if post is None or gig_id in self.booked or len(self.orders_of(gig_id)) != 1 or not self.fits(driver, post):
                    continue
                leg = order["legs"][post["stops"][0]["leg"]]
                if leg["pickup"]["placeId"] not in self.geo.near[place]:
                    continue
                ready = leg["pickup"]["window"]["from"]
                if at + 15 <= order["lastPickupAt"] and ready <= at + self.p.chain_wait:
                    ref = self.gig_posted.get(gig_id, (0, self.requests[oid]["referenceFeeCents"]))[1]
                    if best is None or ref > best[0]:
                        best = (ref, gig_id)
        if best:
            self.offer(best[1], driver, int(best[0] * self.p.chain_ratio + 0.5), "chain")

    def send_offers(self, order_id: str, gig_id: str, rescue: bool) -> None:
        """Direct offers to the drivers for whom this car is cheapest: they live at the delivery end (no trip home)
        or at the pickup end, they opened the app today, and they hold no gig of ours."""
        p = self.p
        post, order = self.posts.get(gig_id), self.orders.get(order_id)
        if post is None or order is None or not p.offers:
            return
        leg = order["legs"][post["stops"][0]["leg"]]
        pu_near, de_near = self.geo.near[leg["pickup"]["placeId"]], self.geo.near[leg["delivery"]["placeId"]]
        today = self.now // DAY
        ref = self.requests[order_id]["referenceFeeCents"] * pickups(post) / len(order["legs"])
        fee = int(ref * (self.rescue_ratio(order, ref) if rescue else p.f_open * p.offer_post_ratio) + 0.5)
        ranked = []
        for d in self.roster.values():
            at_delivery, at_pickup = d["homePlaceId"] in de_near, d["homePlaceId"] in pu_near
            if not (at_delivery or at_pickup) or d["id"] in self.busy or self.offers_sent[(d["id"], today)] >= 3:
                continue
            if post["audience"]["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if post["audience"]["manualLicence"] and d["licence"] != "manual":
                continue
            active = self.last_view.get(d["id"], -1) >= today * DAY
            if not rescue and not (active and at_delivery):
                continue
            ranked.append((2.0 * active + 1.0 * at_delivery + d["rating"] / 10 - 0.05 * d["drops"], d["id"]))
        room = min(p.offers, 3 - self.offer_open[gig_id])
        for _, driver in sorted(ranked, reverse=True)[:max(0, room)]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver, "feeCents": fee})
            self.offers_sent[(driver, today)] += 1
            self.offer_open[gig_id] += 1
            self.log.append({"t": self.now, "kind": "offer", "gig": gig_id, "driver": driver, "fee": fee, "rescue": rescue})
