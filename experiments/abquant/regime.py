"""Which kind of day is it? Level 8 has two unannounced events, each on one working day, never the same day:

  price war   the competitor quotes 20% under its usual prices everywhere, 08:00 to 18:00
  outage      the competitor is down in one region (a town and the places within 80 km); dealers there use a backup
              that costs about 30% more

Each win or loss of the day is evidence. The detector keeps the likelihood of the day's outcomes under every hypothesis
(a normal day, a price war, an outage centred on each town) and turns them into posterior probabilities with Bayes'
rule (ST202 11.1). With n working days left and an event still to come, today is its day with probability 1/n.
Quotes then use the expected shift of the competitor's log price for the request's place.

Version 2 (grid) fixes a blind spot of the first. The desk also learns the competitor's level during the day, and that
learner would explain a price war as "a cheap day": the evidence then fades, the war is never confirmed, and on Friday
the 1/n prior becomes certainty of a war that is not there. So version 2
- judges every outcome against the level as it stood when the day began, not the level that has adapted since;
- allows for the part of today's level that is honestly unknown (the whole world level on Monday, the day factor
  later) by summing each hypothesis over a grid of common shifts, with a prior on that grid;
- never lets the prior reach certainty: a missed event must not be forced onto a later day.
"""
from __future__ import annotations

import math
from collections import Counter

from .features import sigmoid
from .geo import Geo

WAR = math.log(0.80)
OUTAGE = math.log(1.30)
REGION_KM = 80.0


class Regime:
    def __init__(self, geo: Geo, s: float, grid: bool = False, cap: float = 1.0):
        self.s = s
        self.regions = {c: {p for p in geo.places if geo.air[(c, p)] <= REGION_KM} for c in geo.places}
        self.war_pending, self.outage_pending = True, True
        self.volume: Counter = Counter()          # requests seen by pickup place: busy regions go down more often
        self.day = -1
        self.history: list = []
        self.use_grid, self.cap = grid, cap
        self._weights = None
        self.start_day(0)

    def start_day(self, day: int, shifts: tuple = (0.0,), prior: tuple = (1.0,)) -> None:
        """`shifts` are the values today's common level may take around the reference, `prior` their weights."""
        if self.day >= 0 and self.day != day:
            self.close_day()
        self.day = day
        left = max(1, 5 - day) if day < 5 else 0   # working days left this week, today included
        self.prior_war = min(self.cap, 1 / left) if self.war_pending and left else 0.0
        self.prior_outage = min(self.cap, 1 / left) if self.outage_pending and left else 0.0
        if self.prior_war + self.prior_outage > 0.95:
            scale = 0.95 / (self.prior_war + self.prior_outage) if self.cap < 1.0 else 1.0 / (self.prior_war + self.prior_outage)
            self.prior_war, self.prior_outage = self.prior_war * scale, self.prior_outage * scale
        if not self.use_grid:
            shifts, prior = (0.0,), (1.0,)
        total = sum(prior)
        self.grid = tuple(shifts)
        self.grid_prior = tuple(p / total for p in prior)
        g = len(self.grid)
        self.ll_normal, self.ll_war = [0.0] * g, [0.0] * g
        self.ll_outage = {c: [0.0] * g for c in self.regions}
        self.n = 0
        self._weights = None

    def close_day(self) -> None:
        p_war, p_outage, centre = self.posterior()
        if self.n >= 8:
            if p_war > 0.8:
                self.war_pending = False
            if p_outage > 0.8:
                self.outage_pending = False
        self.history.append({"day": self.day, "p_war": round(p_war, 3), "p_outage": round(p_outage, 3), "centre": centre, "n": self.n})

    def _marginal(self, lls: list, top: float) -> float:
        return sum(p * math.exp(ll - top) for p, ll in zip(self.grid_prior, lls))

    def weights(self) -> tuple:
        """Unnormalised posterior weights: (normal, war, {centre: outage there})."""
        if self._weights is not None:
            return self._weights
        total_volume = sum(self.volume.values()) or 1
        region_prior = {c: (sum(self.volume[p] for p in places) + 1) / (total_volume + 1) for c, places in self.regions.items()}
        z = sum(region_prior.values())
        top = max(max(self.ll_normal), max(self.ll_war), max(max(v) for v in self.ll_outage.values()))
        w_normal = max(0.0, 1 - self.prior_war - self.prior_outage) * self._marginal(self.ll_normal, top)
        w_war = self.prior_war * self._marginal(self.ll_war, top)
        w_out = {c: self.prior_outage * region_prior[c] / z * self._marginal(ll, top) for c, ll in self.ll_outage.items()}
        self._weights = (w_normal, w_war, w_out)
        return self._weights

    def posterior(self) -> tuple:
        w_normal, w_war, w_out = self.weights()
        total = w_normal + w_war + sum(w_out.values())
        if total <= 0:
            return 0.0, 0.0, None
        centre = max(w_out, key=w_out.get) if w_out else None
        return w_war / total, sum(w_out.values()) / total, centre

    def shift(self, place: str) -> float:
        """The expected shift of the competitor's log price today, for a request whose dealer is at this place."""
        w_normal, w_war, w_out = self.weights()
        total = w_normal + w_war + sum(w_out.values())
        if total <= 0:
            return 0.0
        here = sum(w for c, w in w_out.items() if place in self.regions[c])
        return (w_war * WAR + here * OUTAGE) / total

    def seen(self, place: str) -> None:
        self.volume[place] += 1
        self._weights = None

    def observe(self, won: bool, logit_numerator: float, place: str) -> None:
        """One answer from a dealer. `logit_numerator` is the usual log level minus the log of our price ratio, so the
        chance of a win under a hypothesis is sigmoid((logit_numerator + its shift) / s)."""
        def ll(shift: float) -> float:
            p = min(1 - 1e-6, max(1e-6, sigmoid((logit_numerator + shift) / self.s)))
            return math.log(p) if won else math.log(1 - p)

        for g, common in enumerate(self.grid):
            normal, war, outage = ll(common), ll(common + WAR), ll(common + OUTAGE)
            self.ll_normal[g] += normal
            self.ll_war[g] += war
            for c, places in self.regions.items():
                self.ll_outage[c][g] += outage if place in places else normal
        self.n += 1
        self._weights = None
