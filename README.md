# Spread: the ABQuant desk

A dispatch desk for the Bahn Express Spread challenge (Junction 2026). It quotes car deliveries to dealers against a
hidden competitor and buys freelance drivers for the cars it wins. One rule prices every request:

```
price = argmax over p of  P(win at p) x ( p x (1 - late risk x refund) - cost )
cost  = expected driver fee + late risk x (trust lost + late driver cost) + price of scarce drivers
```

It is the first-order condition of expected profit from *Market Making Optimisation Theories* (Proposition 1, with the
richer marginal cost of Proposition 3): the dealer is the counterparty, the competitor's price is the mid, and drivers
are the inventory that runs out.


## What is in this repository

Team ABQuant's whole Junction 2026 project. The desk that played the final is at the root; the rest is in folders.

| Where | What it holds |
|---|---|
| `abquant/`, `data/`, `run_final.sh` | The ABQuant desk, version f3, as it played the final. The tag `submitted` marks the state behind the code link handed in at 10:00. |
| `final_run/` | The final as played: the launcher's console and the desk's own log of every action. |
| `experiments/` | What was tested after the final (three-car gigs, pairs for long hauls) and the backtests: `BACKTEST_FIXES.md`, `TRIPLES_POTENTIAL.md`, `BACKTEST.md`. |
| `other_build/` | The first desk (v1 to v4), built in parallel; v4 was the fallback for the final. |
| `submission/` | The jury slides with the final's result, the jury Q&A, and the script that builds the slides. |
| `coordination/` | How the team of AI agents worked: the shared log `COORDINATION.md`, the final's runbook, the improvement plan, a sizing analysis. |
| `proposals/` | The two project proposals written at the start. |

**The final:** 25th of 58 ranked teams, margin EUR 17,130.10, 463 orders won, 94.4% on time.

Not included: the team key and every `.env` file, virtual environments, raw practice-world data and run logs, saved
live state, the organisers' kit, handbook, guide and videos (the kit is served by the Spread server at `/kit/`), and
the team's private chats.

## Four findings carry the result

Each was found in the data of revealed practice weeks, then tested on the same weeks before and after (the world is
deterministic, so the difference is the change and nothing else).

1. **Two cars in one gig.** A driver's cost is the time at the wheel plus the trip to the first pickup and the trip
   home. A second car that starts where the first one ends removes a trip. A fork experiment (`abquant/exp_pairs.py`:
   the same future, posted two ways) showed that a pair books at 0.65 to 0.80 of the two typical fees, where single
   cars need 0.9 and more. Won cars now wait in a pool for a partner (an hour for today's cars, until the evening
   before for later ones). Fees paid: pairs 0.76 x typical, round trips 0.75 and booked in a median of one minute;
   cars alone 1.08 to 1.30. About 280 of 440 cars a week go in pairs.
2. **Drivers come from far.** Drivers are notified of a gig only within 30 km of its first pickup, so the first
   budget counted only those drivers. In 2,642 bookings of revealed weeks, only 40% of the drivers who took a gig live
   inside that circle; 40% live near the delivery end; the median driver lives 64 km from the pickup. Hyvinkaa's gigs
   are mostly taken by Helsinki, Vantaa and Espoo drivers. Counting drivers beyond 30 km at a discount
   exp(-(km - 30) / 30) stopped the desk from refusing about 240 requests a week: **+2,448 a week, better in 12 of 12
   weeks**.
3. **Stop when the board says the drivers are used up.** Twelve fresh weeks, never used for tuning, kept the margin
   but not the punctuality: three of them at 92% on time or under, one at 90.4%, on the edge of the ranking. The
   logs showed why: on a day when drivers ran out, the desk kept winning cars for the same day. Same-day cars
   quoted while fewer than 9 posted cars had sat unbooked for an hour were 4 to 7% late; with 13 to 20 such cars,
   25%; above 20, 60%. So that count is now part of the late risk of a same-day car (2 points per car beyond four).
   On 24 weeks: **+359 a week, better in 18 of 24, and the worst week went from 90.4% to 94.1% on time.**
4. **Read the note, know the day.** Dealers write ready times, real opening hours, tighter deadlines, gearbox, plates
   and tyres in Finnish, Swedish and English, with typos and corrections. The desk's reader agrees with the revealed
   truth on 99.8% of ready times and 100% of the rest. A Bayes detector looks for the week's price-war day and its
   outage day in the day's wins and losses (prior: 1 / days left).

## Results

Mean gross margin per practice week at level 8, same seeds, every week ranked.

| Step | Margin (EUR / week) | Seeds |
| --- | ---: | --- |
| Kit starter | -72,613 | spread-1 |
| First desk of our own (price rule only) | -2,804 | t1-t6 |
| Driver budget by town | 3,803 | t1-t6 |
| Fee schedule with few steps | 5,491 | t1-t6 |
| A workable day for the driver (home by evening, long gigs in the morning) | 9,072 | 3 seeds |
| Own note reader | 11,370 | t1-t6 |
| Price-war and outage detector | 11,828 | t1-t6 |
| Standing price on long gigs | 12,319 | t1-t6 |
| Late mode: a car that cannot be on time goes back to ordinary fees | 13,057 | t1-t6 |
| Opening fee 0.8, then 0.9 after 30 minutes | 13,292 | t1-t6 |
| Two cars in one gig | 14,933 | t1-t6 |
| the same, on 12 weeks | 13,572 | t1-t6, v1-v6 |
| Drivers counted beyond 30 km | 16,020 | t1-t6, v1-v6 |
| the same, on 24 weeks (12 of them fresh) | 16,317 | t, v, s1-s12 |
| The live brake, a tighter budget, round trips kept for each other | 16,675 | t, v, s1-s12 |
| A real price for long hauls that are over the budget | 16,829 | t, v, s1-s12 |

The last-but-one line by seed set: 17,248 on t1-t6, 14,784 on v1-v6, 17,335 on the fresh s1-s12. On time: 96.8% on
average, 94.1% in the worst of the 24 weeks.

The last line is the version that plays the final. A long haul that is over the long-gig budget used to get a quote at
four times list, which always loses; it now gets a real price of about 2.2 x list, as long as the budget is not more
than twice used. Under one such car a week is won, mostly by dealers with full trust or in the outage region, at about
250 a win before lateness. Because the first 24 weeks were also used to choose the setting, it was then checked on 48
weeks that neither version had played, with the rule fixed beforehand (not worse, worst week at 92% on time or
better): +66 a week (se 39), better in 28 weeks and worse in 18, worst week 92.7% for both. Over all 86 paired weeks:
about +84 a week (se 30), on time 96.2% on average for both. Every week is in `experiments/BACKTEST.md`.

In the real ranking rounds the version before this one made 16,053 a week at Sunday 00:00 (17th of 58 ranked teams)
and 15,270 at Sunday 03:00 (13th). This version made 15,384 a week at Sunday 06:00 (13th of 51 ranked teams).

**The final (Sunday 09:00, one secret week on a live clock): 17,130 margin, 463 orders won, 94.4% on time, ranked 25th
of 58 teams.** Tenth place made 19,084, first place 22,931. The desk ran the whole week without a fault, a repair or a
failed send (10,610 batches of events, slowest quote batch 155 ms against a 4.5 second window). Revenue 45,494, driver
fees 27,242 (60%), late refunds 1,062. Tuesday and Wednesday were short of drivers: 26 cars were late. 169 of the 463
cars went alone, at 1.10 x the typical fee, and 294 in pairs at 0.77: the price side sits at its optimum, the driver
side does not, and that is where the distance to the top teams is (see "After the final" below).

Against the team's other build (v4), paired on the same weeks at 20:55 on Saturday: +3,118 (se 697) on t1-t6 and
+1,923 (se 373) on v1-v6, before findings 2 and 3. House best, the organisers' own system, made about 12,850 a week
in the Saturday 15:00 ranking round.

## After the final: the driver side, tested

The final showed where the money is: cars that go alone cost 1.10 x the typical fee, cars in pairs 0.77, and 37% of the
cars go alone. Ways to shrink that share were built in a copy of the code during and after the final and played on 48
practice weeks against the version that played the final (same weeks, paired; none of it was in the final):

| Change | EUR / week (standard error) | Worst week on time | What happened |
| --- | ---: | ---: | --- |
| Three cars in one gig: a one-way pair takes a third car | +84 (125) | 90.8% (played: 92.7%) | Drivers take them at once: 12 a week, 99% booked as three, at 0.75 x typical, in 2 minutes, 1% late. But only 5 fewer cars a week go alone: the third car would mostly have found a partner anyway |
| Long hauls wait for a partner until the evening before | -83 (126) | 91.7% | 33 fewer cars alone and the pairs book (81%, at 0.82), but long hauls are late 17% of the time, not 10% |
| A long haul takes a partner only if one is waiting when it is won | -200 (121) | 90.6% | Pairs book (94%, at 0.84) and 30 fewer cars go alone, but long hauls are late 13% of the time and the cars with them inherit it |
| Three cars, with a lower opening fee (0.65 in place of 0.70) | +22 (102) | 91.2% | No better: 0.73 x typical in place of 0.75, and 6 minutes to a booking in place of 2 |
| **Three cars, and a round trip may take a third car too** | **+365 (123)** | 91.1% | 46 three-car gigs a week at 0.76 x typical, booked in 2 minutes, 1.1% late; 23 fewer cars a week go alone |
| the same, on 48 fresh weeks (the rule to pass was fixed before the run) | +136 (112) | 89.6% in the one week where the played version has 88.4% | 48 three-car gigs a week; cars alone 135 against 158 |
| the same, on all 134 practice weeks the played version has | +147 (70) | 89.6% against 88.4% | On the 86 weeks not used to pick it: +26 (83) |

The best of them, every pair (round trips included) taking a third car, looked like a find on the weeks where it was
picked (+365) and held on fresh weeks (+136), but the full backtest on all 134 weeks is **+147 a week (standard error
70), and +26 (83) on the 86 weeks that were not used to pick it**. Fair statement: somewhere between nothing and about
150 a week. Drivers do take three-car gigs at once (0.76 x typical, within two minutes, 1% late) and 23 fewer cars a
week go alone: driver fees fall by about 260 a week, of which about 60 goes back in late refunds and 60 in revenue.
Pairing long hauls costs more in lateness than it saves in fees.

What our stats would have been with it (the backtest's difference added to the real scores): the final 17,160 to
17,280 in place of 17,130, 23rd to 25th in place of 25th; the Sunday 06:00 and 03:00 ranking rounds 11th to 13th in
place of 13th. The top ten of the final needed 1,954 more in that week. So the gap to the top teams is on the driver
side, and nothing built here closes it. Every week of the backtest: `experiments/BACKTEST_FIXES.md`; the
study behind it: `experiments/TRIPLES_POTENTIAL.md`; the setting is `triple=1 triple_rt=1` in
`experiments/abquant/desk.py` (`add_thirds`, `post_chain`) and `experiments/abquant/pairs.py` (`chain_stops`).

## What did not work

Tested on the same weeks and switched off because they lost money. Each is a parameter that can be turned on again.

| Idea | Effect (EUR / week) | Why |
| --- | ---: | --- |
| A discount to build dealer trust (the "invest" half of the trust table) | about -900 | Drivers are the scarce input: an order won at a discount takes a driver from an order at full price |
| Direct offers to drivers near the delivery end | 4 accepted of 666 | A driver who wants the gig books it from the board |
| Offers to drivers finishing a gig nearby | 1 accepted of 450 | The same |
| Several options quoted at once | -440 | Dealers take the cheaper one |
| Fee steps by the age of the gig | -900 to -1,700 | Drivers learn the raises and wait |
| A lower first fee step for pairs | -609 | The same: an extra step is a reason to wait |
| A price cut for a request that completes a pair | -711 | 105 more orders a week, which cost more in fees than they earn |
| Refitting late risk and fee on the desk's own weeks | -400 | Selection: the desk only sees the cars it chose |
| A larger long-gig budget | -230 | Few drivers take a gig of four hours or more |
| Prices 2% lower, or 2% higher | -285, -433 | The price rule already sits at its optimum |
| Lane price levels from earlier weeks as priors | -116, +57 | The learner finds them within the first morning |
| Late risk that rises with budget use, on top of the brake | -219 to -422 | It turns away cars that would have been on time |
| A rewritten price-war detector | -267 | No better: the price learner already corrects a missed day within hours |
| Two-car trade-in requests | declined | 43.6% late in revealed weeks: the return car cannot make its deadline when the one-way drive is over about 100 minutes |

## How it decides, step by step

1. **Can a driver have a workable day?** A same-day job must let the driver be home in the evening. A long gig (four
   hours or more of driving) needs a morning pickup, and has its own small budget.
2. **What does the note change?** Ready times, payment releases, real opening hours and tighter deadlines replace the
   stated ones before anything is priced. When real hours differ from the stated hours, which drivers plan by, the gig
   is pinned to one day inside the real hours.
3. **Which day?** A later option moves to the feasible day on which its drivers are least used.
4. **What price?** The price that maximises expected profit on a grid, for each option; the best option is quoted. The
   competitor's level is learned during the week from every win and loss, as a sum of parts (world, dealer, pickup
   place, delivery place, lane length, day). A request with no workable option gets four times list: a losing quote is
   free, silence is not.
5. **Alone or in a pair?** A car that can wait goes into the pool. When it falls due it is matched with the car that
   makes the best trip for one driver, round trips first; a car with no partner goes up alone.
6. **What fee?** An opening fee held while drivers look, a few steps before the deadline warning, and after the
   warning no more than lateness would cost. A car that can no longer be on time goes back to an ordinary fee.
7. **What kind of day is it?** Each answer from a dealer updates the odds of a price war or an outage, and prices
   follow.

## The live final

The final runs on a moving clock: 18 real seconds an hour by day, so a quote window is 4.5 seconds. `abquant/live.py`:

- A reader thread puts stream events in a queue. The main loop answers every waiting event in one batch.
- The desk's whole state is saved every four seconds. After any stop the process loads it, reads the events it
  missed, checks itself against the world's snapshot, and carries on. With no saved state it rebuilds from history.
- A fault in the answer to one event is logged and that event is skipped. A send with no answer keeps its actions.
  Twice a minute the books are checked against the world.

Rehearsed on practice worlds whose clock `abquant/clock.py` moves at the final's speeds. The frozen version: a full
week at the final's real speed (34 minutes; 14,867 and 97.0% on time, against 15,065 and 96.5% for the stepped run
of the same week; no faults, the desk's own work at most 14 ms for a batch of events), and a week with the player
killed twice (13,883, 95.1% on time, ranked). An earlier version also played a week with the player killed and its
saved state deleted (14,845 against 16,102, still ranked).

## Files

| File | What it does |
| --- | --- |
| `abquant/desk.py` | The desk: the quote rule, the driver budget, the pool and pairs, gig windows, fee schedules, and its books. Extends the kit starter. |
| `abquant/pairs.py` | The four stops of a two-car gig, with windows that work on one day. |
| `abquant/notes.py` | Reads dealer notes. `python -m abquant.notes` scores it against the reveals. |
| `abquant/regime.py` | The price-war and outage detector. |
| `abquant/fit.py`, `abquant/features.py`, `abquant/geo.py` | The fitted curves (acceptance, late risk, fee), a car's features, the map and opening hours. |
| `abquant/run.py`, `abquant/compare.py`, `sweep.sh` | Practice weeks on named seeds, and the paired comparison of two versions. |
| `abquant/live.py`, `abquant/clock.py`, `run_final.sh`, `rehearse_kill.sh` | The live loop, the rehearsal clock, the supervisor for the final, and the kill-and-restart rehearsal. |
| `abquant/exp_pairs.py` | The fork experiment behind finding 1. |

## Run it

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install spread-0.1.0-py3-none-any.whl          # the kit wheel
export SPREAD_KEY=...                                          # or keep it in the file abquant/env.py points to
.venv/bin/python -m abquant.run --seeds t1,t2,t3 --tag demo      # three practice weeks
.venv/bin/python -m abquant.compare demo base                    # paired against another tag
.venv/bin/python -m abquant.live --rehearse t1 --fast 4          # a week against a moving clock, 4x the final's speed
./run_final.sh                                                 # the final: waits for it, plays it, restarts if stopped
```
