# Three-car gigs: how much is there to gain?

Sunday 15 Nov, about 09:00. From the logs of 48 weeks of the current bot (`logs/fb_yf3__y*.jsonl`) and the map. Nothing was played.

**Answer: adding a third car to our one-way pairs can absorb about 22 cars a week, worth at most about EUR 0.4k to 0.5k a week (about 3% of the margin). Triples that close the loop: 2 to 3 cars and under EUR 50 a week.**

## Method

1. Base: every one-way pair a→b the desk posted (time t). Third-car candidates: cars that were never in a pair (`result.pair` false) with under 240 minutes of driving.
2. A candidate c fits when it can go at the end (b's delivery to c's pickup at most 45 drive minutes) or at the start (c's delivery to a's pickup at most 45), and all driving plus hops is at most 690 minutes.
3. Timing is rough: c was delivered on the same day as the pair, and c was won on the day of t, between 6 hours before t and 1 hour after ("won" = time of our quote; the log has no win row).
4. Each pair takes one extra car and each car is used once, greedy: loop-closing triples first (last delivery within 30 km of the first pickup), then the shortest hop.
5. Saving per absorbed car = (ratio alone - 0.77) x typical fee, with ratio alone 1.30 under 60 minutes, 1.10 for 60 to 120, 1.08 for 120 to 240, and typical fee = 16.4 + 0.381 x drive minutes.

## Results (mean per week over 48 weeks; standard error in brackets)

| | Cars or gigs / week | EUR / week |
| --- | ---: | ---: |
| **For scale** | | |
| Cars won; margin; driver fees | 435.8 | 16,047; 24,161 |
| One-way pairs posted (driven as pairs: 62.8) | 69.8 | |
| Round-trip pairs posted | 68.1 | |
| Cars that were in a pair | 273.5 | |
| Cars never in a pair, all | 161.7 | 3,863 above 0.77 x typical |
| under 60 min / 60 to 120 / 120 to 240 | 23.5 / 37.8 / 48.5 | 2,262 above 0.77 (the part a triple can reach) |
| 240 min and more (never pooled) | 51.9 | 1,601 above 0.77 |
| Fee paid, one-car gigs (180.4 cars) | 1.09 x typical (1.05 fee-weighted) | |
| Fee paid, two-car gigs (258.3 cars) | 0.76 x typical (0.77 fee-weighted) | |
| **Third car added to a one-way pair** | | |
| All triples (rule above) | **22.3** (0.8) cars absorbed | **425** (16) |
| of which loop-closing | **2.6** (0.2) | **47** (4) |
| The same cars at the fee they really paid | | 323 all; 34 loops |
| Chain capped at 540 minutes instead of 690 | 21.7; loops 2.5 | 406; loops 45 |
| Stricter: c untaken when the pair went up, or won in the next hour while the pair was untaken | 23.1; loops 2.0 | 463; loops 39 (at fees paid: 442; 41) |
| Hindsight ceiling: any such car driven that day, whenever won | 36.8; loops 5.8 | 712; loops 106 (at fees paid: 592; 85) |

Of the 69.8 one-way pairs, 39.8 have at least one candidate; 36.6 cars have at least one pair; one use each leaves 22.3.
Absorbed cars by drive: 9.3 under 60 minutes, 5.8 at 60 to 120, 7.3 at 120 to 240; 10.1 go at the end, 12.2 at the start.
Paid fee of cars alone by drive: 1.30, 1.09, 1.07, 1.00, so the assumed ratios match the logs.

## What it means

- Of the EUR 3.9k a week that cars alone cost above the pair rate, triples reach about EUR 0.4k. The rest is 52 long hauls a week (EUR 1.6k, they never wait for a partner) and about 88 shorter cars: 73 with no one-way pair that fits on their day, 14 that lose their pair to another car.
- Loop-closing triples are rare because the round trips are already taken as pairs first.

## Caveats

- **Geometry and rough timing only, so an upper bound.** No opening hours, ready times, pickup windows or deadlines inside the day. 4% of the chosen chains are over 540 minutes and 19% over 420.
- It assumes a triple books at 0.77 like a pair. Not tested: a one-way chain of three leaves the driver further from home. It needs the fork experiment that was done for pairs.
- "Same day" uses the day each car was really delivered. A car with a later deadline could have moved days; the hindsight row bounds that side.
- Not counted: the driver freed by each triple (22 fewer gigs to fill of about 310 a week, which may allow more volume), a car put between a and b, triples on round-trip pairs, four cars.
- `result.pair` stays true when a pair breaks up: about 19 cars a week were in a pair and still went alone. They are not candidates here.

The analysis script ran from the session's scratchpad (`triples.py`) and is not kept in the project.

## The code, and what the desk's own matching does with it (09:05, offline)

Written in this folder only, off by default (`triple=1` turns it on): `chain_stops` in `abquant/pairs.py` (the stops of
any number of cars for one driver; for two cars it returns exactly what `pair_stops` returns, checked on 185,657 calls),
`add_thirds` and `post_chain` in `abquant/desk.py` (diff: `triples.diff`). A one-way pair that is about to go up takes a
third car before its first car or after its last: first a car that would be alone (due with no partner, or up alone and
not taken), then a car that still waits. At most 360 planned minutes, on the day the pair was planned for.

`replay_triples.py` and `replay_variants.py` replay the requests and wins of the 9 saved weeks through the real desk
with no server: every post is accepted and a stand-in "driver" takes a single car after 60 minutes and a pair or a
three after 10. It tests the pool, the matching and the stops, not the fees. Per week:

| Setting | Cars alone | Pairs | Threes | Share of cars alone |
| --- | ---: | ---: | ---: | ---: |
| As played (hop between cars at most 45 minutes) | 167.7 | 113.9 | 0 | 42.4% |
| Three cars | 165.4 | 97.2 | 11.9 | 41.8% |
| Three cars, third car only from cars that would be alone | 163.8 | 109.9 | 4.0 | 41.4% |
| Hop at most 60 | 157.0 | 119.2 | 0 | 39.7% |
| Hop at most 75 | 144.8 | 125.3 | 0 | 36.6% |
| Hop at most 90 | 139.9 | 127.8 | 0 | 35.4% |
| Hop at most 120 | 114.8 | 140.3 | 0 | 29.0% |
| Three cars and hop at most 75 | 142.0 | 109.2 | 11.7 | 35.9% |

Every three-car gig it built can be driven inside its windows at both ends of the first pickup window.

**Reading.** About 12 three-car gigs a week form, but only 2 to 4 of their third cars would have been alone: the others
would have found a partner anyway. A car is alone because no car of ours starts where it ends, not because a driver may
take only two. So three cars in one gig is worth tens of euros a week, not hundreds, unless a three books at a lower
share of the typical fees than a pair (not known: it needs practice weeks).

**The larger lever is the hop.** Letting the second car start up to 75 minutes' drive from where the first ends would
pair 23 more cars a week. But one-way pairs book worse as the hop grows (48 weeks of the bot that plays the final):

| Hop, minutes | One-way pairs posted | Booked as a pair | Fee x typical | Late | Round trips booked as a pair | Fee |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 to 10 | 222 | 99% | 0.75 | 0.9% | 100% | 0.73 |
| 10 to 20 | 375 | 96% | 0.78 | 1.3% | 99% | 0.73 |
| 20 to 30 | 2,246 | 91% | 0.79 | 2.6% | 98% | 0.75 |
| 30 to 40 | 378 | 88% | 0.78 | 2.0% | 98% | 0.75 |
| 40 to 45 | 127 | 81% | 0.80 | 2.0% | 99% | 0.76 |

By total length: one-way pairs of 360 to 450 planned minutes are 4.7% late and above 450 minutes 11.5%, against 1 to
2.6% under 300. Hence the 360-minute cap on a three.

Both settings need paired practice weeks before any claim. Neither is in the bot that plays the final.

## A larger lever found on the way: long hauls never get a second car (09:10, offline)

A car with four hours of driving or more is posted at once and never waits for a partner (`release_time`). In the
48 logged weeks of the bot that plays the final there are 51.9 such cars a week. They are booked alone at 0.99 x the
typical fee on average: 71% at the first two fees (0.80, 0.90; 2 to 3% late), 21% at about 1.2 to 1.3 (27% late),
8% above. 10.1% of them are late. By geometry and day alone, 47.9 of the 51.9 had a car of ours that could go with
them (hop at most 45 minutes, at most 690 planned minutes), and for 33.5 of them that car went alone as well.

New setting in this folder, off by default: `pool_long=400` lets a car of up to 400 driving minutes wait for a partner
like any other car (a car for a later day goes up at 17:30 the evening before). Replay of the 9 saved weeks through the
real matching (`replay_variants.py`, `replay_long.py`), per week:

| Setting | Cars alone | Pairs | Share of cars alone |
| --- | ---: | ---: | ---: |
| As played | 167.7 | 113.9 | 42.4% |
| Long hauls up to 330 minutes may wait | 145.7 | 124.9 | 36.8% |
| Long hauls up to 400 minutes may wait | 127.2 | 134.1 | 32.2% |
| Long hauls up to 480 minutes may wait | 123.7 | 135.9 | 31.3% |
| Up to 400 minutes, and hop at most 75 | 104.1 | 145.7 | 26.3% |

With 400: 26.3 pairs a week hold a long haul (both cars long in 1.6, a round trip in 1.6); the long haul goes first in
53%; planned minutes 473 at the median (quartiles 406 and 528); the other car drives 103 minutes at the median.

**What it could be worth, and what could go wrong.** If such a pair books like today's one-way pairs of that length
(0.80 x typical; 80 to 92% booked as a pair), each saves about EUR 37 (the long haul 0.99 -> 0.80, the other car 1.09
-> 0.80): several hundred euros a week. Against it: today's one-way pairs over 450 planned minutes are 11.5% late, and a
long haul that waits until 17:30 the evening before and then finds no partner has lost hours on the board. It needs
paired practice weeks, with the on-time share watched. Not in the bot that plays the final.

**Check that nothing else moved.** With every experiment off, this folder's desk sends exactly the same actions and
keeps exactly the same log as the desk that plays the final, on all 9 replayed weeks (hash of every action and log row).
The stress replay (`replay_stress.py`: three-car gigs that expire, get a deadline warning, lose a car to a
cancellation, are dropped or refused) leaves no order without a gig.

## Practice results after the final (09:35 to 09:55): none of it closes the gap

Played on y1-y48 (stepped practice weeks, at most 4 at a time), paired with the bot that played the final (`fb_yf3`).

| Setting | EUR / week (se) | Won | Worst week on time | Weeks better |
| --- | ---: | ---: | ---: | ---: |
| `triple=1` | +84 (125) | 437 vs 436 | 90.8% vs 92.7% | 27 of 48 |
| `pool_long=400` | -83 (126) | 441 vs 436 | 91.7% vs 92.7% | 18 of 48 |
| `pool_long=400 pool_long_now=1` | -200 (121) | 432 vs 436 | 90.6% vs 92.7% | 19 of 48 |

The first 8 weeks had said +239 (se 287) and +544 (se 458): noise, as their standard errors warned.

**Three cars.** 12.1 three-car gigs a week (0.6 ending where they began), 99% booked as three, at 0.75 x the typical
fees, median 2 minutes to a booking, 272 planned minutes, 1.0% of their cars late. So drivers like them at least as
much as round trips. But cars never in a pair or a three: 157 a week against 162. The offline replay had it right: the
third car would mostly have found a partner anyway.

**Long hauls.** Waiting until 17:30 the evening before: 21 pairs a week with a long haul, 81% booked as a pair at 0.82,
median 64 minutes; cars never in a pair 129 against 162; long hauls late 16.8% against 10.1%; on time 95.4% against
96.0% on average. Not waiting (`pool_long_now=1`: a partner that is waiting when the long haul is won, or alone at
once): 27.6 pairs a week, 94% booked as a pair at 0.84, median 69 minutes; their cars 6.0% late; long hauls late 13.0%
against 10.1%; cars never in a pair 132 against 162; and 4 fewer cars won a week. The fee saved is real, but a gig of
eight hours finds its driver slowly, and each late long haul costs a refund, the dealer's trust and a rescue fee.

**What stands.** The "larger lever" above was a count of cars, not of money: on practice weeks it loses. The claim that
cars alone are the gap to the top teams still stands (1.10 x typical against 0.77 in the final), but more cars per
driver is not the way to close it with this desk. Untested ideas that remain: winning fewer of the cars that will go
alone (a lane's own expected fee, +245 to +341 a week in earlier tests but with a worst week at 91.0% on time), and
whatever the top teams do that this desk does not.

## One variant works (10:06 to 10:13): every pair may take a third car, round trips too

| Setting | Weeks | EUR / week (se) | On time, mean | Worst week on time | Weeks better |
| --- | --- | ---: | ---: | ---: | ---: |
| `triple=1 triple_open=0.65` | y1-y48 | +22 (102) | | 91.2% vs 92.7% | 26 of 48 |
| `triple=1 triple_rt=1` | y1-y48 | +365 (123) | 96.04% vs 96.02% | 91.1% vs 92.7% | 33 of 48 |
| `triple=1 triple_rt=1` | x1-x48, fresh | +136 (112) | 95.51% vs 95.46% | 89.6% vs 88.4% (x22, unranked for both) | 28 of 48 |
| `triple=1 triple_rt=1` | all 96 | **+251 (84)** | | | 61 of 96 |

The rule for the fresh weeks was written into `logs/sweeps.txt` before the run: above zero by more than one standard
error, and no week that the played version ranks falling under 90% on time. Both hold (the lowest such week is x28,
90.1% against 91.0%).

With `triple_rt=1`: 46 to 48 three-car gigs a week (8 ending where they began), 0.76 x the typical fees, median 2
minutes to a booking, 241 planned minutes, 1.1 to 1.2% of their cars late; cars never in a pair or a three 139 against
162 a week on y, 135 against 158 on x. So the gain is the 23 cars a week that no longer go alone.

Why I had it off: a round trip books within a minute because the driver ends where he began, and a third car breaks
that. The weeks say a three-car gig books just as fast without the loop. A lower opening fee (0.65) only made the gig
wait longer (6 minutes) for a fee two points lower.

Reading the sizes: five driver-side variants were tried on y1-y48, so +365 there flatters the best of them; +136 on the
fresh weeks is the fairer single figure and +251 the pooled one. In the final (17,130) about 250 more is 23rd in
place of 25th; in the Sunday 06:00 ranking round (15,384 a week, 13th) it is about 10th. Not adopted anywhere: the
competition is over. Next steps if this desk is taken further: a fourth car, and two round trips in one gig.

## Full backtest (11:00): the best variant is not a proven gain

`triple=1 triple_rt=1` was then played on the other 38 weeks the played bot has (t, v, s, w, r), so on all 134:
t1-t6 -423 (se 245), v1-v6 +420 (261), s1-s12 -211 (186), w1-w12 -194 (260), r1-r2 +293 (363), y1-y48 +365 (123),
x1-x48 +136 (112). **All 134 weeks: +147 a week (se 70). The 86 weeks not used to pick it: +26 (se 83).**

This corrects the section above ("one variant works", +251 over 96 weeks): that figure still held the weeks on which the
variant was picked as the best of five. The t, v, s and w weeks lean the other way (the played bot was tuned on them),
so the fair range is between nothing and about 150 a week. What is solid: drivers take three-car gigs at once, 23 fewer
cars a week go alone, driver fees fall by about 260 a week, and about 120 of that goes back in late refunds and revenue.

With it our real results would have been about: the final 17,160 to 17,280 (23rd to 25th, in place of 25th); the 06:00
and 03:00 ranking rounds 11th to 13th (in place of 13th). Every week and the method: `BACKTEST_FIXES.md`
(`python backtest_fixes.py` rebuilds it from `data/runs.jsonl` and the logs).
