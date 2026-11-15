"""Our dispatch desk.

Quote rule (paper, Prop. 3):  price = cost + markup + mu * (capacity used) + nu * (late risk - target)
  cost   = expected driver fee + expected lateness cost (refund tiers, dealer trust)
  markup = P / |P'| from a logistic acceptance curve around an online estimate of the competitor's price
  mu     = shadow price of drivers in the pickup pool on that day: zero while the pool is slack
  nu     = shadow price of the 90% on-time gate: zero while the forecast late share is under target

Posting, retries, reposts and rejoin come from the kit's starter (spread.starter)."""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from .env import ROOT  # noqa: F401  (puts the kit on sys.path)
from spread.client import World
from spread.starter import (
    Retry, pickups, retry_from, stops_for, undelivered, window_from_note, without_windows,
)
from .geo import DAY, HOUR, Geo, last_open_by, next_open


@dataclass
class Params:
    # acceptance curve (fitted on probe1: s = 0.108, competitor 1.25-1.49 x list)
    comp_prior: float = 1.38      # competitor price / list price, prior (level 8 middle)
    slope: float = 0.10           # logistic scale of acceptance, in log price
    # late model (fitted on probe1) and the costs of a late car
    model: bool = True
    late_refund: float = 0.5      # expected refund share of price when late
    late_fee: float = 1.0         # extra fee (x typical) spent rescuing a late car
    q_scale: float = 1.0          # multiplies the fitted inventory effect (our load differs from the probe's)
    pi_max: float = 0.065         # never quote an option whose late probability exceeds this
    fee_grid_lo: float = 0.9
    fee_grid_hi: float = 2.4
    fee_rise: float = 1.35        # schedule rises from f* to f* x fee_rise before the deadline warning
    fee_for_risk: bool = False    # buy a car under the risk cut-off with a higher fee instead of declining it
    post_mult: float = 1.0        # multiply the posted opening fee (the model still prices at the chosen fee)
    eq_k: float = 0.0             # >0: per-car opening fee that equalises booking speed (0 = off)
    eq_center: float = 0.9
    eq_lo: float = 0.6
    eq_hi: float = 1.6
    steps: bool = True            # stepped schedule: hold the opening fee, then step up near the warning
    s1: float = 1.3
    s2: float = 1.6
    s3: float = 2.0
    o1: int = 300                 # minutes before the warning for each step
    o2: int = 180
    o3: int = 60
    rho_on: bool = True           # charge the shadow price of inventory
    dp: bool = False              # fee schedule by backward induction on the booking hazard
    dp_slots: int = 16
    dp_min_slot: int = 30
    dp_lo: float = 0.5
    dp_hi: float = 3.0
    dp_cap: float = 1.8           # top fee before the warning, as a multiple of the opening fee (drivers learn raises)
    rescue_late: float = 0.6      # chance a car still unbooked at the warning ends late
    resid_late: float = 0.03      # late risk from drops, failed visits and slow drives once booked
    haz_mult: float = 3.0         # calibration of the probe-fitted hazard to our (lower) load
    lr_global: float = 0.04
    lr_lane: float = 0.03
    lr_dealer: float = 0.03
    lr_day: float = 0.06
    bayes: bool = True            # online Bayesian (Laplace) updates with shrinkage instead of SGD (ST202 ch. 11)
    v_global: float = 0.01
    v_lane: float = 0.02
    v_dealer: float = 0.003
    v_day: float = 0.008
    v_pu: float = 0.002
    # cost of a car
    fee_expect: float = 1.55      # expected booked fee / typical fee
    fee_density: float = 0.0      # extra fee multiple when few drivers live near the pickup
    late_base: float = 0.02
    late_scale: float = 0.5
    late_tau: float = 120.0
    note_risk: float = 0.02
    # time feasibility
    find_min: int = 90            # minutes from the win until a driver can be at the pickup
    min_slack: int = 45           # least slack (minutes) to offer an option
    # capacity (shadow price of drivers)
    batch_frac: float = 0.5       # quote to win at most this x notified drivers of a batch's yard (0 = no cap)
    batch_min: int = 2
    batch_max: int = 10
    pool_cap: float = 0.0         # >0: orders per pickup place and day <= pool_cap x (notified drivers + 1)
    cap_frac: float = 0.8         # orders per pool-day <= cap_frac * weighted drivers near the pickup
    cap_global: float = 1.0       # orders per day <= cap_global * drivers in the world
    tau_pool: float = 45.0        # minutes: weight of a driver = exp(-road minutes home->pickup / tau)
    kink: float = 0.6             # utilisation where the shadow price starts
    q_max: int = 60               # hard budget: open (unbooked) orders we may hold; decline at the limit
    q_kink: float = 0.6           # the inventory shadow price starts at q_kink x q_max (Prop. 4: zero while slack)
    q_mu: float = 0.6             # shadow price at the limit, as a multiple of the typical fee
    mu_scale: float = 1.0         # extra cost at full utilisation, as a multiple of the typical fee
    # on-time gate
    late_target: float = 0.05
    gate_hi: float = 0.08         # forecast late share at which the risk cut-off is tightest
    gate_floor: float = 0.3       # the tightest risk cut-off, as a share of pi_max
    nu_scale: float = 4.0         # extra cost per unit late probability, x price, once the gate is at risk
    # fees
    fee_open: float = 1.25        # opening fee / typical fee
    fee_top: float = 2.0          # planned top fee / typical fee before the deadline warning
    rescue: float = 1.8           # fee / typical fee from the deadline warning
    rescue_top: float = 2.6
    offers: int = 3               # direct offers on a deadline warning
    offers_on_post: int = 3       # direct offers sent when a gig is posted, for cars in thin pools
    thin_pool: int = 60           # notified drivers below which a pool counts as thin
    chain: bool = False           # offer open gigs to our drivers who finish nearby
    chain_minutes: int = 45       # road minutes from the delivery to the next pickup
    chain_fee: float = 1.0        # offer at this x the gig's current fee
    # quoting
    min_margin: int = 300         # cents of expected margin before we quote to win
    decline_mult: int = 4         # decline = this x list price
    multi_option: bool = False
    r_lo: float = 1.15
    r_hi: float = 1.9
    price_shade: float = 1.0      # multiply the chosen price (tests the acceptance model's markup)
    # probes (data collection): random quote ratios and flat random opening fees
    probe: bool = False
    probe_lo: float = 1.0
    probe_hi: float = 1.8
    fee_probe: bool = False
    fee_probe_lo: float = 0.9
    fee_probe_hi: float = 2.6


def unit_hash(text: str) -> float:
    import hashlib
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


@dataclass
class Quoted:
    rid: str
    kind: str
    price: int
    ratio: float
    theta: float
    keys: tuple
    pool: str
    day: int
    pi: float
    fee: float
    terms: dict = field(default_factory=dict)


_LATE = None
_HAZ = None


def hazard_model() -> dict:
    global _HAZ
    if _HAZ is None:
        with open(os.path.join(ROOT, "data", "hazard_model.json"), encoding="utf-8") as f:
            m = json.load(f)
        _HAZ = dict(zip(m["names"], m["coef"]))
    return _HAZ


def late_model() -> dict:
    global _LATE
    if _LATE is None:
        path = os.path.join(ROOT, "data", "late_model.json")
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        _LATE = dict(zip(m["names"], m["coef"]))
    return _LATE


class Desk:
    def __init__(self, world: World, level: int, now: int, params: Optional[Params] = None, geo: Optional[Geo] = None,
                 roster: Optional[list] = None, name: str = "desk"):
        self.world, self.level, self.now = world, level, now
        self.p = params or Params()
        self.geo = geo or Geo()
        self.name = name
        self.outbox: list = []
        self.requests: dict = {}
        self.orders: dict = {}
        self.leg_gigs: dict = {}
        self.booked: set = set()
        self.posts: dict = {}
        self.urgent: set = set()
        # learning
        self.theta_g = math.log(self.p.comp_prior)
        self.theta_lane: dict = {}
        self.theta_dealer: dict = {}
        self.theta_day: dict = {}
        self.g = [math.log(self.p.comp_prior), self.p.v_global]   # Bayesian: global level [mean, var]
        self.eff: dict = {}                                        # Bayesian: (kind, key) -> [mean, var]
        self.quoted: dict = {}           # request id -> Quoted (only quotes meant to win)
        self.trust: dict = {}            # dealer -> on-time count (level 8)
        # capacity
        self.roster = roster or []
        self.drivers = {d["id"]: d for d in self.roster}
        self.wdrivers = self._weighted_drivers()
        homes: dict = {}
        for d in self.roster:
            homes[d["homePlaceId"]] = homes.get(d["homePlaceId"], 0) + 1
        self.pool_n = {pl: sum(homes.get(h, 0) for h in self.geo.pool[pl]) for pl in self.geo.places}
        self.batch_q: dict = {}          # batch id -> quotes meant to win
        self.load: dict = {}             # (pickup place, day) -> orders won
        self.load_day: dict = {}         # day -> orders won
        self.order_pool: dict = {}       # order id -> (place, day)
        self.order_pi: dict = {}         # order id -> late probability at quote time
        self.order_L: dict = {}          # order id -> cost of the order being late (cents)
        self.order_f: dict = {}          # order id -> chosen opening fee / typical
        self.late_orders = 0
        self.ontime_orders = 0
        self._finished: set = set()      # orders delivered or cancelled
        # drivers' activity
        self.last_view: dict = {}        # driver id -> minute of last view
        self.offers_today: dict = {}     # (driver, day) -> offers sent
        self.offer_open: dict = {}       # gig id -> open offers
        self.log: list = []
        self.gig_driver: dict = {}       # gig id -> driver id
        self.z_bar = None                # running mean of the hazard score
        self.chain_sent: set = set()     # (driver, gig) pairs offered by chaining

    # ------------------------------------------------------------------ capacity model
    def _weighted_drivers(self) -> dict:
        w = {p: 0.0 for p in self.geo.places}
        for d in self.roster:
            h = d["homePlaceId"]
            for p in self.geo.places:
                w[p] += math.exp(-self.geo.minutes(h, p) / self.p.tau_pool)
        return w

    def capacity(self, place: str) -> float:
        if not self.roster:
            return 1e9
        if self.p.pool_cap > 0:
            return self.p.pool_cap * (self.pool_n.get(place, 0) + 1)
        return self.p.cap_frac * self.wdrivers.get(place, 0.0)

    def utilisation(self, place: str, day: int) -> float:
        cap = self.capacity(place)
        u_pool = self.load.get((place, day), 0) / cap if cap > 0 else 9.0
        gcap = self.p.cap_global * max(1, len(self.roster)) if self.roster else 1e9
        u_glob = self.load_day.get(day, 0) / gcap
        return max(u_pool, u_glob)

    def open_orders(self) -> list:
        """Won orders that no driver holds now: the desk's inventory q."""
        out = []
        for oid in self.orders:
            if oid in self._finished:
                continue
            gigs = self.gigs_of(oid)
            if not gigs or not any(g in self.booked for g in gigs):
                out.append(oid)
        return out

    def pi_model(self, ref_ratio: float, same_day: bool, lead_h: float, pu: str, de: str, drive: int, hour: float,
                 q: float, trade: int, req: Optional[dict] = None) -> float:
        b = late_model()
        extra = 0.0
        if req is not None:
            legs = req["legs"]
            extra = (b.get("premium", 0.0) * (1.0 if any(l["car"]["premium"] for l in legs) else 0.0)
                     + b.get("private", 0.0) * (1.0 if any(l["pickup"]["privateAddress"] or l["delivery"]["privateAddress"] for l in legs) else 0.0)
                     + b.get("note", 0.0) * (1.0 if req.get("note") else 0.0)
                     + b.get("electric", 0.0) * (1.0 if any(l["car"]["electric"] for l in legs) else 0.0))
        dens = self.wdrivers if self.roster else {}
        z = (b["const"] + b["log fee ratio"] * math.log(max(0.2, ref_ratio)) + b["same_day"] * (1.0 if same_day else 0.0)
             + b["log lead h"] * math.log(max(lead_h, 0.5)) + b["lead<6h"] * (1.0 if lead_h < 6 else 0.0)
             + b["log dens pickup"] * math.log(1 + dens.get(pu, 20.0)) + b["log dens delivery"] * math.log(1 + dens.get(de, 20.0))
             + b["log drive"] * math.log(drive + 30) + b["hour/24"] * hour / 24
             + self.p.q_scale * b["open orders global/100"] * q / 100 + b["trade-in"] * trade + extra)
        return sigmoid(z)

    def fee_plan(self, ref: float, lead_min: float, pu: str, de: str, drive: int, hour: float, q: float, trade: int, L: float):
        """Backward induction (Green Book 5.3) over slots before the deadline warning.
        V_K = rescue cost; V_k = min_f P_k(f) f ref + (1 - P_k(f)) V_{k+1}, with P_k(f) = 1 - exp(-h(f) dt)
        and h the fitted booking hazard (ST202 6.5). Returns (expected cost V_0, [(offset, fee ratio)])."""
        p = self.p
        b = hazard_model()
        dens = self.wdrivers if self.roster else {}
        horizon = max(float(p.dp_min_slot), lead_min - 210.0)
        K = max(1, min(p.dp_slots, int(horizon // p.dp_min_slot)))
        dt = horizon / K
        base = (b["const"] + b["log lead h"] * math.log(max(lead_min / 60.0, 0.5))
                + b["log dens pickup"] * math.log(1 + dens.get(pu, 20.0)) + b["log dens delivery"] * math.log(1 + dens.get(de, 20.0))
                + b["log drive"] * math.log(drive + 30) + b["open orders global/100"] * q / 100 + b["trade-in"] * trade)
        grid = [p.dp_lo + 0.1 * i for i in range(int(round((p.dp_hi - p.dp_lo) / 0.1)) + 1)]
        V = ref * p.rescue + p.rescue_late * L
        plan = []
        for k in range(K - 1, -1, -1):
            hr = (hour + (k * dt) / 60.0) % 24
            night = 7 <= hr < 23
            best = None
            for f in grid:
                h = p.haz_mult * math.exp(base + b["log fee ratio"] * math.log(f) + b["hour/24"] * hr / 24) * (1.0 if night else 0.15)
                P = 1.0 - math.exp(-h * dt)
                v = P * f * ref + (1 - P) * V
                if best is None or v < best[0]:
                    best = (v, f)
            V = best[0]
            plan.append((int(k * dt), best[1]))
        plan.reverse()
        # fees never fall, and the top before the warning stays within dp_cap x the opening fee
        out, top = [], plan[0][1] * p.dp_cap
        last = 0.0
        for off, f in plan:
            f = min(max(f, last), top)
            if not out or f > out[-1][1] + 1e-9:
                out.append((off, f))
            last = f
        return V, out

    def rho_cost(self) -> float:
        """Shadow price of one more open order (cents): its effect on every open order's late risk times that order's late cost."""
        if not self.p.rho_on:
            return 0.0
        bq = self.p.q_scale * late_model()["open orders global/100"] / 100
        total = 0.0
        for oid in self.open_orders():
            pi = self.order_pi.get(oid, 0.1)
            total += bq * pi * (1 - pi) * self.order_L.get(oid, 5000.0)
        return total

    def mu_cost(self, u: float, ref: float) -> float:
        """Shadow price of the pool, in cents: zero while slack (u <= kink), steep near capacity."""
        if u <= self.p.kink:
            return 0.0
        x = (u - self.p.kink) / max(1e-6, 1.0 - self.p.kink)
        return self.p.mu_scale * ref * x * x

    def late_share_forecast(self) -> float:
        """Forecast late share of the week: late so far, plus open orders already past their deadline, plus the
        expected lateness of the rest."""
        done = self.late_orders + self.ontime_orders
        open_ids = [o for o in self.orders if o not in self._finished]
        overdue = sum(1 for o in open_ids if self.orders[o]["deadline"] < self.now)
        open_pi = sum(self.order_pi.get(o, 0.0) for o in open_ids if self.orders[o]["deadline"] >= self.now)
        n = done + len(open_ids)
        return (self.late_orders + overdue + open_pi) / n if n >= 20 else 0.0

    def pi_cut(self) -> float:
        """The risk cut-off, tightened as the forecast late share nears the gate (the multiplier on the 90% rule)."""
        f = self.late_share_forecast()
        p = self.p
        if f <= p.late_target:
            return p.pi_max
        x = min(1.0, (f - p.late_target) / max(1e-6, p.gate_hi - p.late_target))
        return p.pi_max * (1.0 - (1.0 - p.gate_floor) * x)

    # ------------------------------------------------------------------ acceptance model
    def lane_key(self, req: dict) -> tuple:
        leg = req["legs"][0]
        return (leg["pickup"]["placeId"], leg["delivery"]["placeId"])

    def _bkeys(self, lane, dealer, day) -> list:
        p = self.p
        return [("lane", lane, p.v_lane), ("dealer", dealer, p.v_dealer), ("day", day, p.v_day), ("pu", lane[0], p.v_pu)]

    def theta(self, req: dict) -> float:
        day = req["arrivedAt"] // DAY
        lane = self.lane_key(req)
        if self.p.bayes:
            th = self.g[0] + sum(self.eff.get((k, key), (0.0, 0.0))[0] for k, key, _ in self._bkeys(lane, req["dealerId"], day))
        else:
            th = self.theta_g + self.theta_lane.get(lane, 0.0) + self.theta_dealer.get(req["dealerId"], 0.0) + self.theta_day.get(day, 0.0)
        if self.level >= 8:
            th += math.log(1.0 + 0.01 * self.trust.get(req["dealerId"], 0))
        return th

    def learn(self, rid: str, won: bool) -> None:
        q = self.quoted.get(rid)
        if q is None:
            return
        if self.p.bayes:
            lane, dealer, day = q.keys
            keys = self._bkeys(lane, dealer, day)
            th = self.g[0] + sum(self.eff.get((k, key), (0.0, 0.0))[0] for k, key, _ in keys)
            if self.level >= 8:
                th += math.log(1.0 + 0.01 * self.trust.get(dealer, 0))
            s_ = self.p.slope
            P = sigmoid((th - math.log(q.ratio)) / s_)
            h = P * (1 - P) / s_ ** 2
            gr = ((1.0 if won else 0.0) - P) / s_
            self.g[1] = 1 / (1 / self.g[1] + h)
            self.g[0] += self.g[1] * gr
            for k, key, var in keys:
                e = self.eff.setdefault((k, key), [0.0, var])
                e[1] = 1 / (1 / e[1] + h)
                e[0] += e[1] * gr
            return
        z = (q.theta - math.log(q.ratio)) / self.p.slope
        err = (1.0 if won else 0.0) - sigmoid(z)
        lane, dealer, day = q.keys
        self.theta_g += self.p.lr_global * err
        self.theta_lane[lane] = self.theta_lane.get(lane, 0.0) + self.p.lr_lane * err
        self.theta_dealer[dealer] = self.theta_dealer.get(dealer, 0.0) + self.p.lr_dealer * err
        self.theta_day[day] = self.theta_day.get(day, 0.0) + self.p.lr_day * err

    # ------------------------------------------------------------------ feasibility
    def arrival(self, req: dict, start: int) -> int:
        note = req.get("note")
        t, place = start, None
        for leg in req["legs"]:
            pu, de, car = leg["pickup"], leg["delivery"], leg["car"]
            w = window_from_note(note, pu["window"], "pickup")
            tp = max(t, w["from"])
            if place is not None and place != pu["placeId"]:
                tp = max(tp, t + self.geo.minutes(place, pu["placeId"]))
            if not pu["privateAddress"]:
                tp = next_open(pu.get("hours"), tp)
            drive = self.geo.minutes(pu["placeId"], de["placeId"])
            if car.get("electric") and (car.get("chargePercent") if car.get("chargePercent") is not None else 100) < 30 \
                    and self.geo.km(pu["placeId"], de["placeId"]) > 200:
                drive += 40
            ta = tp + drive
            if de["privateAddress"]:
                ta = max(ta, de["window"]["from"])
            else:
                ta = next_open(de.get("hours"), ta)
            t, place = ta, de["placeId"]
        return t

    def due(self, req: dict, deadline: int) -> int:
        """The real deadline of the last delivery: the option's deadline, cut by the site's hours and the note."""
        note = req.get("note")
        de = req["legs"][-1]["delivery"]
        d = deadline
        if not de["privateAddress"]:
            d = last_open_by(de.get("hours"), d)
        base = {"from": de["window"]["from"], "to": max(de["window"]["from"], deadline)}
        d = min(d, window_from_note(note, base, "delivery")["to"])
        return d

    # ------------------------------------------------------------------ quoting
    def evaluate(self, req: dict, opt: dict) -> Optional[Quoted]:
        if not self.p.model:
            return self.evaluate_heuristic(req, opt)
        p = self.p
        start = req["respondBy"] + p.find_min
        arr = self.arrival(req, start)
        due = self.due(req, opt["deadline"])
        slack = due - arr
        if slack < p.min_slack:
            self._why = "slack"
            return None
        legs = req["legs"]
        pu, de = legs[0]["pickup"]["placeId"], legs[-1]["delivery"]["placeId"]
        drive = sum(self.geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
        lead_h = max(0.5, (due - drive - req["respondBy"]) / 60.0)
        day = max(start, legs[0]["pickup"]["window"]["from"]) // DAY
        u = self.utilisation(pu, day)
        if u >= 1.0:
            self._why = "capacity"
            return None
        ref = float(req["referenceFeeCents"])
        q = len(self.open_orders())
        if q >= p.q_max:
            self._why = "budget"
            return None
        k0 = p.q_kink * p.q_max
        mu_q = p.q_mu * ref * ((q - k0) / (p.q_max - k0)) ** 2 if q > k0 else 0.0
        hour = (req["respondBy"] % DAY) / 60.0
        th = self.theta(req)
        lst = opt["listPriceCents"]
        trust = self.trust.get(req["dealerId"], 0) if self.level >= 8 else 0
        price_guess = lst * math.exp(th) * 0.95
        L = price_guess * (p.late_refund + 0.02 * trust) + p.late_fee * ref
        # the fee rule: raise the opening fee while one more euro buys at least one euro of avoided lateness
        if p.dp:
            V0, plan = self.fee_plan(ref, lead_h * 60.0, pu, de, drive, hour, q, len(legs) - 1, L)
            fr = plan[0][1]
            pi = self.pi_model(fr, opt["kind"] == "same_day", lead_h, pu, de, drive, hour, q, len(legs) - 1, req)
            if req.get("note"):
                pi = min(0.95, pi + p.note_risk)
            cost_fee = V0 + p.resid_late * L
        elif p.eq_k > 0:
            # equalise booking speed: f_i = centre x exp(-k (z_i - z_bar) / b_fee), z = hazard score without the fee
            hb = hazard_model()
            dens = self.wdrivers if self.roster else {}
            z = (hb["log lead h"] * math.log(max(lead_h, 0.5)) + hb["log dens pickup"] * math.log(1 + dens.get(pu, 20.0))
                 + hb["log dens delivery"] * math.log(1 + dens.get(de, 20.0)) + hb["log drive"] * math.log(drive + 30)
                 + hb["trade-in"] * (len(legs) - 1))
            self.z_bar = z if self.z_bar is None else 0.98 * self.z_bar + 0.02 * z
            fr = p.eq_center * math.exp(-p.eq_k * (z - self.z_bar) / hb["log fee ratio"])
            fr = min(p.eq_hi, max(p.eq_lo, fr))
            pi = self.pi_model(fr, opt["kind"] == "same_day", lead_h, pu, de, drive, hour, q, len(legs) - 1, req)
            if req.get("note"):
                pi = min(0.95, pi + p.note_risk)
            cost_fee = None
        else:
            best_f, any_f = None, None
            cut = self.pi_cut() if p.fee_for_risk else 1.0
            f = p.fee_grid_lo
            while f <= p.fee_grid_hi + 1e-9:
                pi_f = self.pi_model(f, opt["kind"] == "same_day", lead_h, pu, de, drive, hour, q, len(legs) - 1, req)
                if req.get("note"):
                    pi_f = min(0.95, pi_f + p.note_risk)
                c = f * ref * (1 + 0.15 * (p.fee_rise - 1)) + pi_f * L
                if any_f is None or c < any_f[0]:
                    any_f = (c, f, pi_f)
                if pi_f <= cut and (best_f is None or c < best_f[0]):
                    best_f = (c, f, pi_f)  # the cheapest fee that keeps the car under the risk cut-off
                f += 0.1
            cost0, fr, pi = best_f if best_f is not None else any_f
            cost_fee = None
        if pi > self.pi_cut():
            self._why = "risk"
            return None
        rho = self.rho_cost()
        gate = max(0.0, self.late_share_forecast() - p.late_target)
        mu = self.mu_cost(u, ref) + mu_q
        best = None
        r = p.r_lo
        while r <= p.r_hi + 1e-9:
            price = int(round(lst * r / 100.0)) * 100
            if price > 0:
                prob = sigmoid((th - math.log(price / lst)) / p.slope)
                Lp = price * (p.late_refund + 0.02 * trust) + p.late_fee * ref
                nu = p.nu_scale * gate * pi * price
                if cost_fee is not None:
                    margin = price - cost_fee - (Lp - L) * (p.rescue_late * 0.3 + p.resid_late) - rho - mu - nu
                else:
                    margin = price - fr * ref * (1 + 0.15 * (p.fee_rise - 1)) - pi * Lp - rho - mu - nu
                ev = prob * margin
                if best is None or ev > best[0]:
                    best = (ev, price, prob, margin, Lp, nu)
            r += 0.01
        ev, price, prob, margin, Lp, nu = best
        if p.price_shade != 1.0:
            price = int(round(price * p.price_shade / 100.0)) * 100
            prob = sigmoid((th - math.log(price / lst)) / p.slope)
            margin = margin - (best[1] - price)
            ev = prob * margin
        if p.probe:
            r = p.probe_lo + (p.probe_hi - p.probe_lo) * unit_hash(req["id"] + "q")
            price = int(round(lst * r / 100.0)) * 100
            ev = 1e6
        elif margin < p.min_margin or ev <= 0:
            self._why = "margin"
            return None
        keys = (self.lane_key(req), req["dealerId"], req["arrivedAt"] // DAY)
        qd = Quoted(req["id"], opt["kind"], price, price / lst, th, keys, pu, day, pi, fr * ref,
                    {"ev": round(ev), "prob": round(prob, 3), "margin": round(margin), "fr": round(fr, 2), "pi": round(pi, 3),
                     "rho": round(rho), "mu": round(mu), "nu": round(nu), "slack": slack, "q": q, "comp": round(math.exp(th), 3)})
        qd.terms["L"] = round(Lp)
        if cost_fee is not None:
            qd.terms["cfee"] = round(cost_fee)
        return qd

    def evaluate_heuristic(self, req: dict, opt: dict) -> Optional[Quoted]:
        p = self.p
        start = req["respondBy"] + p.find_min
        arr = self.arrival(req, start)
        slack = self.due(req, opt["deadline"]) - arr
        if slack < p.min_slack:
            return None
        pu = req["legs"][0]["pickup"]
        place = pu["placeId"]
        day = max(start, pu["window"]["from"]) // DAY
        u = self.utilisation(place, day)
        if u >= 1.0:
            return None
        ref = float(req["referenceFeeCents"])
        dens = self.wdrivers.get(place, 0.0) if self.roster else 10.0
        fee = ref * p.fee_expect * (1.0 + p.fee_density / (1.0 + dens))
        if (arr // DAY) % 7 == 5:
            fee *= 1.15
        pi = p.late_base + p.late_scale * math.exp(-slack / p.late_tau)
        if req.get("note"):
            pi += p.note_risk
        pi *= 1.0 + 2.0 * max(0.0, u - p.kink)
        pi = min(0.9, pi)
        mu = self.mu_cost(u, ref)
        gate = max(0.0, self.late_share_forecast() - p.late_target)
        trust = self.trust.get(req["dealerId"], 0) if self.level >= 8 else 0
        th = self.theta(req)
        lst = opt["listPriceCents"]
        best = None
        r = p.r_lo
        while r <= p.r_hi + 1e-9:
            price = int(round(lst * r / 100.0)) * 100
            if price > 0:
                prob = sigmoid((th - math.log(price / lst)) / p.slope)
                late_cost = pi * price * (0.3 + 0.02 * trust)
                nu = p.nu_scale * gate * pi * price
                margin = price - fee - late_cost - mu - nu
                ev = prob * margin
                if best is None or ev > best[0]:
                    best = (ev, price, prob, margin, late_cost, nu)
            r += 0.01
        ev, price, prob, margin, late_cost, nu = best
        if p.probe:
            r = p.probe_lo + (p.probe_hi - p.probe_lo) * unit_hash(req["id"] + "q")
            price = int(round(lst * r / 100.0)) * 100
            prob = sigmoid((th - math.log(price / lst)) / p.slope)
            late_cost = pi * price * 0.3
            margin = price - fee - late_cost - mu
            ev = prob * margin + 1e6  # always quote
        elif margin < p.min_margin or ev <= 0:
            return None
        keys = (self.lane_key(req), req["dealerId"], req["arrivedAt"] // DAY)
        return Quoted(req["id"], opt["kind"], price, price / lst, th, keys, place, day, pi, fee,
                      {"ev": round(ev), "prob": round(prob, 3), "margin": round(margin), "fee": round(fee), "late": round(late_cost),
                       "mu": round(mu), "nu": round(nu), "slack": slack, "u": round(u, 3), "comp": round(math.exp(th), 3)})

    def quote(self, req: dict) -> None:
        self.requests[req["id"]] = req
        if self.now >= req["respondBy"]:
            return
        whys = []
        cands = []
        for o in req["options"]:
            self._why = "?"
            q = self.evaluate(req, o)
            if q is None:
                whys.append(self._why)
            else:
                cands.append(q)
        if not cands:
            o = req["options"][0]
            self.outbox.append({"type": "quote", "requestId": req["id"], "prices": {o["kind"]: o["listPriceCents"] * self.p.decline_mult}})
            self.log.append({"t": self.now, "kind": "decline", "rid": req["id"], "why": ",".join(whys)})
            return
        bid = req.get("batchId")
        if bid and self.p.batch_frac > 0 and self.roster:
            yard = req["legs"][0]["pickup"]["placeId"]
            cap = min(self.p.batch_max, max(self.p.batch_min, int(self.p.batch_frac * self.pool_n.get(yard, 0))))
            if self.batch_q.get(bid, 0) >= cap:
                o = req["options"][0]
                self.outbox.append({"type": "quote", "requestId": req["id"], "prices": {o["kind"]: o["listPriceCents"] * self.p.decline_mult}})
                self.log.append({"t": self.now, "kind": "decline", "rid": req["id"], "why": "batch"})
                return
            self.batch_q[bid] = self.batch_q.get(bid, 0) + 1
        best = max(cands, key=lambda q: q.terms["ev"])
        prices = {best.kind: best.price}
        if self.p.multi_option:
            for q in cands:
                prices.setdefault(q.kind, q.price)
        self.quoted[req["id"]] = best
        self.outbox.append({"type": "quote", "requestId": req["id"], "prices": prices})
        self.log.append({"t": self.now, "kind": "quote", "rid": req["id"], "opt": best.kind, "price": best.price,
                         "ratio": round(best.ratio, 3), **best.terms})

    # ------------------------------------------------------------------ events
    def handle(self, event: dict) -> None:
        k = event["kind"]
        if k == "price_request":
            self.quote(event["request"])
        elif k == "order_won":
            self.learn(event["order"]["id"], True)
            self.win(event["order"])
        elif k == "order_lost":
            self.learn(event["requestId"], False)
        elif k == "order_changed":
            self.change(event["order"])
        elif k == "order_cancelled":
            oid = event["orderId"]
            for books in (self.orders, self.leg_gigs):
                books.pop(oid, None)
            self._finished.add(oid)
        elif k == "visit_failed":
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif k == "gig_expired":
            self.repost(event["gigId"])
        elif k == "deadline_close":
            self.raise_fees(event["orderId"])
        elif k == "gig_booked":
            self.booked.add(event["gigId"])
            self.gig_driver[event["gigId"]] = event["driverId"]
        elif k in ("gig_dropped", "no_show"):
            self.booked.discard(event["gigId"])
        elif k == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
        elif k == "offer_answered":
            g = event["gigId"]
            self.offer_open[g] = max(0, self.offer_open.get(g, 1) - 1)
            if event["answer"] == "accepted":
                self.booked.add(g)
        elif k == "delivered":
            self.delivered(event["orderId"], event["leg"], event["at"])
            if self.p.chain:
                self.chain_offer(event["gigId"], event["placeId"])

    def delivered(self, order_id: str, leg: int, at: int) -> None:
        self.leg_gigs.get(order_id, {}).pop(leg, None)
        order = self.orders.get(order_id)
        if order is None:
            return
        order["deliveredAt"][leg] = at
        if all(x is not None for x in order["deliveredAt"]) and order_id not in self._finished:
            self._finished.add(order_id)
            on_time = max(order["deliveredAt"]) <= order["deadline"]
            d = order["dealerId"]
            if on_time:
                self.ontime_orders += 1
                self.trust[d] = min(25, self.trust.get(d, 0) + 1)
            else:
                self.late_orders += 1
                self.trust[d] = self.trust.get(d, 0) // 2

    def win(self, order: dict) -> None:
        if order["id"] in self.requests and order["id"] not in self.orders:
            self.orders[order["id"]] = order
            q = self.quoted.get(order["id"])
            req = self.requests[order["id"]]
            place = req["legs"][0]["pickup"]["placeId"]
            day = q.day if q else self.now // DAY
            self.load[(place, day)] = self.load.get((place, day), 0) + 1
            self.load_day[day] = self.load_day.get(day, 0) + 1
            self.order_pool[order["id"]] = (place, day)
            self.order_pi[order["id"]] = q.pi if q else 0.1
            self.order_L[order["id"]] = q.terms.get("L", 5000) if q else 5000
            self.order_f[order["id"]] = q.terms.get("fr", self.p.fee_open) if q else self.p.fee_open
            self.post(order, undelivered(order))

    def change(self, order: dict) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.withdraw(order["id"]):
                self.post(order, undelivered(order))

    def repost(self, gig_id: str) -> None:
        action = self.posts.get(gig_id)
        if action is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
            return
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        order = self.orders.get(action["stops"][0]["orderId"])
        if order is None:
            return
        stops = without_windows(action["stops"], float("inf"))
        self.urgent.add(order["id"])  # an expired gig is late or nearly so: go steep
        self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, pickups(action))})

    def raise_fees(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        if order is None:
            return
        self.urgent.add(order_id)
        self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id not in self.booked:
                sched = self.fees_for(order, pickups(self.posts[gig_id]))
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": sched})
                self.send_offers(order, gig_id, sched[0]["feeCents"])

    # ------------------------------------------------------------------ fees
    def ref_share(self, order: dict, cars: int) -> float:
        return self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])

    def fees_for(self, order: dict, cars: int) -> list:
        ref = self.ref_share(order, cars)
        p, now = self.p, self.now
        if order["id"] in self.urgent:
            steps = [(now + k * 30, ref * (p.rescue + (p.rescue_top - p.rescue) * k / 4)) for k in range(5)]
        elif p.fee_probe:
            m = p.fee_probe_lo + (p.fee_probe_hi - p.fee_probe_lo) * unit_hash(order["id"] + "f" + str(cars))
            steps = [(now, ref * m)]
        elif p.model and p.dp:
            req = self.requests[order["id"]]
            legs = req["legs"]
            pu, de = legs[0]["pickup"]["placeId"], legs[-1]["delivery"]["placeId"]
            drive = sum(self.geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
            lead = order["lastPickupAt"] - now
            L = self.order_L.get(order["id"], 5000.0)
            _, plan = self.fee_plan(ref, float(lead), pu, de, drive, (now % DAY) / 60.0, len(self.open_orders()), len(legs) - 1, L)
            steps = [(now + off, ref * f) for off, f in plan]
        elif p.steps:
            f0 = self.order_f.get(order["id"], p.fee_open) * p.post_mult
            warn = order["lastPickupAt"] - 3 * HOUR
            steps = [(now, ref * f0)]
            for k, (off, mult) in enumerate(((p.o1, p.s1), (p.o2, p.s2), (p.o3, p.s3))):
                at = max(now + 60 * (k + 1), warn - off)
                steps.append((at, ref * f0 * mult))
        else:
            f0 = self.order_f.get(order["id"], p.fee_open) if p.model else p.fee_open
            ftop = f0 * p.fee_rise if p.model else p.fee_top
            end = order["lastPickupAt"] - 3 * HOUR - 30
            n = 4
            if end <= now + 60:
                steps = [(now, ref * (f0 + ftop) / 2), (now + 60, ref * ftop)]
            else:
                steps = [(now + int((end - now) * k / (n - 1)), ref * (f0 + (ftop - f0) * k / (n - 1))) for k in range(n)]
        out, last = [], 0
        for at, fee in steps:
            f = max(last, int(fee + 0.5), 1)
            if out and at <= out[-1]["at"]:
                at = out[-1]["at"] + 1
            out.append({"at": int(at), "feeCents": f})
            last = f
        self.log.append({"t": now, "kind": "fees", "oid": order["id"], "cars": cars, "ref": round(ref), "urgent": order["id"] in self.urgent,
                         "f0": out[0]["feeCents"], "ftop": out[-1]["feeCents"], "lpa": order["lastPickupAt"]})
        return out

    def offer_on_post(self, action: dict, gig_id: str) -> None:
        k = self.p.offers_on_post
        if k <= 0 or not self.roster:
            return
        hour = (self.now % DAY) / 60
        if not (7 <= hour < 21):
            return
        order = self.orders.get(action["stops"][0]["orderId"])
        if order is None or order["id"] in self.urgent:
            return
        place = order["legs"][action["stops"][0]["leg"]]["pickup"]["placeId"]
        if self.pool_n.get(place, 0) >= self.p.thin_pool:
            return
        saved, self.p.offers = self.p.offers, k
        try:
            self.send_offers(order, gig_id, action["schedule"][0]["feeCents"])
        finally:
            self.p.offers = saved

    def send_offers(self, order: dict, gig_id: str, fee: int) -> None:
        if self.level < 3 or not self.roster or self.p.offers <= 0:
            return
        action = self.posts.get(gig_id)
        if not action:
            return
        first = action["stops"][0]
        leg = order["legs"][first["leg"]]
        place = leg["pickup"]["placeId"]
        need_exp = action["audience"].get("experienced", False)
        need_man = action["audience"].get("manualLicence", False)
        day = self.now // DAY
        cands = []
        for d in self.roster:
            if need_exp and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if need_man and d["licence"] != "manual":
                continue
            if self.offers_today.get((d["id"], day), 0) >= 3:
                continue
            active = 1 if self.last_view.get(d["id"], -10 ** 9) >= self.now - 12 * HOUR else 0
            mins = self.geo.minutes(d["homePlaceId"], place)
            cands.append((-active, mins, d["drops"], d["id"]))
        cands.sort()
        k = max(0, min(self.p.offers, 3 - self.offer_open.get(gig_id, 0)))
        for _, _, _, did in cands[:k]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": did, "feeCents": int(fee)})
            self.offers_today[(did, day)] = self.offers_today.get((did, day), 0) + 1
            self.offer_open[gig_id] = self.offer_open.get(gig_id, 0) + 1

    def current_fee(self, gig_id: str) -> int:
        sched = self.posts[gig_id]["schedule"]
        fee = sched[0]["feeCents"]
        for st in sched:
            if st["at"] <= self.now:
                fee = st["feeCents"]
        return fee

    def chain_offer(self, gig_id: str, place: str) -> None:
        """Our driver has just delivered at `place`: offer them an open gig that starts nearby (a chain)."""
        did = self.gig_driver.get(gig_id)
        if did is None or self.level < 3:
            return
        action = self.posts.get(gig_id)
        if action and action["stops"][-1]["kind"] != "delivery":
            return
        if any(s["kind"] == "pickup" and self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id
               for s in (action or {}).get("stops", [])[1:]):
            return
        day = self.now // DAY
        if self.offers_today.get((did, day), 0) >= 3:
            return
        drv = self.drivers.get(did, {})
        best = None
        for oid in self.open_orders():
            order = self.orders.get(oid)
            for g in self.gigs_of(oid):
                if g in self.booked or (did, g) in self.chain_sent or self.offer_open.get(g, 0) >= 3:
                    continue
                post = self.posts.get(g)
                if not post:
                    continue
                if post["audience"].get("experienced") and not (drv.get("rating", 0) >= 4.8 and drv.get("completedGigs", 0) >= 50):
                    continue
                if post["audience"].get("manualLicence") and drv.get("licence") != "manual":
                    continue
                first = post["stops"][0]
                pu = order["legs"][first["leg"]]["pickup"]["placeId"]
                m = self.geo.minutes(place, pu)
                if m > self.p.chain_minutes:
                    continue
                # prefer gigs that end near the driver's home
                home = drv.get("homePlaceId", pu)
                last = order["legs"][post["stops"][-1]["leg"]]["delivery"]["placeId"]
                score = m + 0.5 * self.geo.minutes(last, home)
                if best is None or score < best[0]:
                    best = (score, g)
        if best is None:
            return
        g = best[1]
        fee = int(self.current_fee(g) * self.p.chain_fee)
        self.outbox.append({"type": "offer", "gigId": g, "driverId": did, "feeCents": max(1, fee)})
        self.offers_today[(did, day)] = self.offers_today.get((did, day), 0) + 1
        self.offer_open[g] = self.offer_open.get(g, 0) + 1
        self.chain_sent.add((did, g))
        self.log.append({"t": self.now, "kind": "chain", "gig": g, "driver": did, "fee": fee})

    # ------------------------------------------------------------------ posting (from the starter)
    def retry(self, order_id: str, leg: int, reason: str) -> None:
        if order_id in self.orders:
            order = self.orders[order_id]
            self.leg_gigs.get(order_id, {}).pop(leg, None)
            car_not_there = reason in ("not_ready", "closed")
            pickup_from = retry_from(order, self.requests[order_id], leg, self.now) if car_not_there else 0
            self.post(order, [leg], Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates"))

    def post(self, order: dict, legs: list, retry: Retry = Retry()) -> None:
        audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]), "manualLicence": retry.manual_licence}
        note = self.requests[order["id"]].get("note")
        stops = without_windows(stops_for(order, legs, note, retry), self.now)
        if note:
            text = note["text"].lower()
            if any(w in text for w in ("manuaali", "manual", "manuell", "käsivaiht")):
                audience["manualLicence"] = True
            if any(w in text for w in ("kilv", "plates", "skylt", "rekisterikilv", "no plates", "ilman kilpiä")):
                for s in stops:
                    if s["kind"] == "pickup":
                        s["withPlates"] = True
        self.outbox.append({"type": "post", "stops": stops, "audience": audience, "schedule": self.fees_for(order, len(legs))})
        if len(legs) == 1:
            return
        self.send()
        if not self.gigs_of(order["id"]):
            for leg in legs:
                self.post(order, [leg], retry)

    def gigs_of(self, order_id: str) -> list:
        return list(dict.fromkeys(self.leg_gigs.get(order_id, {}).values()))

    def carry(self, action: dict, gig_id: str) -> None:
        for stop in action["stops"]:
            self.leg_gigs.setdefault(stop["orderId"], {})[stop["leg"]] = gig_id
        self.posts[gig_id] = action

    def withdraw(self, order_id: str) -> bool:
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(g in self.booked for g in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": g} for g in gigs]
        return True

    def send_post_of(self, order_id: str) -> None:
        if any(a["type"] == "post" and a["stops"][0]["orderId"] == order_id for a in self.outbox):
            self.send()

    def send(self) -> None:
        actions, self.outbox = self.outbox, []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def read_results(self, actions: list, results: list) -> None:
        for action, result in zip(actions, results):
            if action["type"] == "post" and result.get("ok") is True:
                self.carry(action, result["id"])
                self.offer_on_post(action, result["id"])
            elif result.get("ok") is False:
                self.log.append({"t": self.now, "kind": "refused", "action": action["type"], "reason": result.get("reason", "")[:200]})

    # ------------------------------------------------------------------ rejoin after a restart (final)
    def rejoin(self, snapshot: dict, history: list) -> None:
        posted: dict = {}
        self.booked = {g["id"] for g in snapshot["gigs"] if g["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            posted.setdefault(gig["stops"][0]["orderId"], []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry({"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}, gig["id"])
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        self.urgent = {e["orderId"] for e in history if e["kind"] == "deadline_close"}
        self.orders = {o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"}
        for e in history:  # rebuild learning, loads and trust from the record
            k = e["kind"]
            if k == "gig_viewed":
                self.last_view[e["driverId"]] = e["at"]
            elif k == "order_won":
                o = e["order"]
                req = self.requests.get(o["id"])
                if req:
                    place = req["legs"][0]["pickup"]["placeId"]
                    day = max(req["respondBy"] + self.p.find_min, req["legs"][0]["pickup"]["window"]["from"]) // DAY
                    self.load[(place, day)] = self.load.get((place, day), 0) + 1
                    self.load_day[day] = self.load_day.get(day, 0) + 1
                    self.order_pool[o["id"]] = (place, day)
                    self.order_pi[o["id"]] = 0.05
        for o in snapshot["orders"]:
            if o["status"] == "delivered" and o["id"] not in self._finished:
                self._finished.add(o["id"])
                d = o["dealerId"]
                if max(x for x in o["deliveredAt"] if x is not None) <= o["deadline"]:
                    self.ontime_orders += 1
                    self.trust[d] = min(25, self.trust.get(d, 0) + 1)
                else:
                    self.late_orders += 1
                    self.trust[d] = self.trust.get(d, 0) // 2
        for order in self.orders.values():
            if order["status"] == "waiting" and not self.gigs_of(order["id"]):
                self.post(order, undelivered(order))
        for event in history:
            order = self.orders.get(event.get("orderId", ""))
            if order is None:
                continue
            if event["kind"] == "visit_failed" and order["deliveredAt"][event["leg"]] is None:
                later = [g for g in posted.get(order["id"], []) if g["postedAt"] >= event["at"] and g["id"] != event["gigId"]]
                if not any(stop["leg"] == event["leg"] for gig in later for stop in gig["stops"]):
                    self.retry(order["id"], event["leg"], event["reason"])
        for request in snapshot["openRequests"]:
            self.quote(request)

    # ------------------------------------------------------------------ state for restarts
    def save_state(self, path: str) -> None:
        state = {"g": self.g, "eff": [[k, list(key) if isinstance(key, tuple) else key, v] for (k, key), v in self.eff.items()],
                 "trust": self.trust, "theta_g": self.theta_g, "theta_lane": [[list(k), v] for k, v in self.theta_lane.items()],
                 "theta_dealer": self.theta_dealer, "theta_day": {str(k): v for k, v in self.theta_day.items()},
                 "params": asdict(self.p)}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)

    def load_state(self, path: str) -> None:
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        self.theta_g = s["theta_g"]
        if "g" in s:
            self.g = s["g"]
            self.eff = {(k, tuple(key) if isinstance(key, list) else key): v for k, key, v in s["eff"]}
            self.trust = {k: int(v) for k, v in s.get("trust", {}).items()}
        self.theta_lane = {tuple(k): v for k, v in s["theta_lane"]}
        self.theta_dealer = s["theta_dealer"]
        self.theta_day = {int(k): v for k, v in s["theta_day"].items()}
