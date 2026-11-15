# Experiments after the final

A copy of the desk at the repository root, with five driver-side experiments. Each is a setting that is off by default:
with everything off, this copy sends exactly the same actions as the desk that played the final (checked on nine
replayed weeks). None of it was in the final.

## What was tried

The final showed where the money is: a car that goes alone costs 1.10 x the typical fee, a car in a pair 0.77, and 37%
of the cars go alone. Each row is the same practice weeks played twice, once by the desk that played and once with the
change.

| Change | Setting | Weeks | EUR / week (standard error) | Worst week on time, change / played |
| --- | --- | ---: | ---: | ---: |
| Three cars in one gig, round trips included | `triple=1 triple_rt=1` | 134 | +147 (70); +26 (83) on the 86 weeks not used to pick it | 89.6% / 88.4% |
| Three cars in one gig, one-way pairs only | `triple=1` | 48 | +84 (125) | 90.8% / 92.7% |
| The same with a lower opening fee | `triple=1 triple_open=0.65` | 48 | +22 (102) | 91.2% / 92.7% |
| Long hauls wait for a partner | `pool_long=400` | 48 | -83 (126) | 91.7% / 92.7% |
| A long haul takes a partner that is already waiting | `pool_long=400 pool_long_now=1` | 48 | -200 (121) | 90.6% / 92.7% |

Drivers take a three-car gig at once (0.76 x the typical fees, within two minutes, 1% of the cars late) and 23 fewer
cars a week go alone, but the gain is between nothing and about 150 a week. Pairing long hauls costs more in lateness
than it saves in fees. With the best of them, the final would have been about 17,160 to 17,280 in place of 17,130:
23rd to 25th in place of 25th.

## Read first

| File | What it holds |
| --- | --- |
| `BACKTEST_FIXES.md` | Every change against the desk that played, by set of weeks and week by week, and what our real results would have been. `python backtest_fixes.py` rebuilds it from `data/runs.jsonl` (the cars-alone figures also need the raw run logs, which are not in the repository). |
| `TRIPLES_POTENTIAL.md` | The study in the order it happened: the estimate from logs, the offline replays, the practice results, and two claims of mine that the later weeks took back. |
| `BACKTEST.md` | The earlier backtest behind the version that played the final (f2 against f3). |
| `logs/sweeps.txt` | The result line of every sweep, with the rule that was fixed before the confirmation run. |
| `data/runs.jsonl` | One row for every practice week played here: settings, margin, cars won, share on time, ledger. |

## The code

| File | What it does |
| --- | --- |
| `abquant/desk.py` | The desk with the new settings: `triple`, `triple_rt`, `triple_open`, `triple_max`, `triple_posted`, `triple_wait`, `triple_loop` (`add_thirds`, `post_chain`); `pool_long`, `pool_long_now` (`release_time`); `long_brake` (written, never tested). |
| `abquant/pairs.py` | `chain_stops`: the stops of any number of cars for one driver. For two cars it returns exactly what `pair_stops` returns (checked on 185,657 calls). |
| `triples.diff`, `over_budget.diff`, `long_brake.diff` | The changes as diffs. |
| `replay_triples.py`, `replay_variants.py`, `replay_long.py`, `replay_stress.py` | Offline replays with no server: the requests and wins of saved weeks go through the real pool and matching, every post is accepted and a stand-in takes the gigs. They test which gigs form and that their stops can be driven, not the fees. They need saved weeks in `../data/worlds/` (a practice week played with `--reveal`), which are not in the repository. |
| `long_pairs_report.py`, `triples_report.py` | How the new gigs booked, from the raw run logs. |
| `sweep.sh`, `after_final.sh`, `more_tests*.sh` | The paired test (`./sweep.sh NAME "setting=value" seeds BASE`), and the runs of Sunday morning in the order they were queued. |

## Run a paired test

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install spread-0.1.0-py3-none-any.whl          # the kit wheel from the challenge site
export SPREAD_KEY=...                                          # your team key
./sweep.sh try3 "triple=1 triple_rt=1" y1,y2,y3,y4 yf3         # four practice weeks, compared with the played desk
```
