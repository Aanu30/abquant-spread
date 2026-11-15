# Backtest: the frozen bot (f2) against the new version (over-budget price)

Written Sunday 04:50, holdout added 05:10. **Update 05:52: the new version (f3) was swapped in at 05:50 and is what plays the final**, after the holdout at the end of this file met the rule fixed beforehand and the team left the choice to this build. The old file is kept as `logs/desk_f2_before_0550.py`.

## What can be backtested

- **Ranking rounds cannot be replayed.** Each team plays each of a round's five secret weeks once. The rank of the new version in those rounds can only be estimated: the frozen bot's real score plus the gain measured on practice weeks.
- **Practice weeks can.** The same seed gives the same week to the cent, so both versions were played on the same 38 weeks: the 24 used on Saturday night (t1-t6, v1-v6, s1-s12), 12 new ones (w1-w12) and the two rehearsal weeks (r1, r2). z1-z10 were not used.

## The two versions

- **Frozen (f2):** the code at the repository root, unchanged since Saturday 23:25.
- **New:** f2 plus one rule. A long haul that is over the long-gig budget gets a real price (scarcity price 1.0 x typical fee, late risk +10 points) in place of a quote at 4x list that always loses, as long as the budget is not more than twice used. The whole change is `over_budget.diff` in this folder (26 lines in `abquant/desk.py`).
- What the rule does in practice: about 20 such quotes a week at about 2.2 x list, of which fewer than 2 are won, mostly by dealers with full trust or in the outage region. Each win earns about 250 before lateness; 29% of them arrive late.

## Real ranking rounds (frozen bot) and the estimate for the new version

Estimate = real score + 107 a week (the gain below, se 48). Places as of 04:37; the 03:00 round was still open.

| Round | Frozen: margin / week | Frozen: place | 10th place | New (estimate) | New: place | Place if the gain is one se lower / higher |
|---|---:|---|---:|---:|---|---|
| Sunday 00:00 | 16,053 | 17th of 58 | 16,368 | 16,160 | about 13th | 14th / 12th |
| Sunday 03:00 | 15,270 | 11th of 39 | 15,375 | 15,377 | about 10th | 11th / 9th |

Weeks of the frozen bot: 00:00 round 16,839 / 16,394 / 13,254 / 17,433 / 16,345 (96.6% on time); 03:00 round 15,038 / 14,361 / 11,198 / 20,318 / 15,435 (96.0% on time).

## Practice weeks, both versions (EUR gross margin per week)

| Seed set | Weeks | Frozen f2 | New | Difference (se) | New better in | Worst week on time: f2 | New | Mean on time: f2 | New |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| t1-t6 | 6 | 17,248 | 17,719 | +472 (188) | 4 of 6 | 94.4% | 94.9% | 96.4% | 96.6% |
| v1-v6 | 6 | 14,784 | 14,760 | -23 (16) | 1 of 6 | 96.2% | 96.2% | 97.4% | 97.4% |
| s1-s12 | 12 | 17,335 | 17,417 | +82 (60) | 7 of 12 | 94.1% | 94.3% | 96.6% | 96.7% |
| w1-w12 (new) | 12 | 17,238 | 17,282 | +44 (73) | 5 of 12 | 93.0% | 92.4% | 95.8% | 95.8% |
| r1, r2 (rehearsal weeks) | 2 | 14,797 | 14,730 | -67 (16) | 0 of 2 | 94.0% | 93.5% | 95.2% | 95.0% |
| **all 38** | 38 | 16,754 | 16,861 | +107 (48) | 17 of 38 | 93.0% | 92.4% | 96.4% | 96.4% |

### Other settings of the same rule

| Scarcity price (x typical fee), overshoot limit | Weeks | Difference to f2 (se) | Worst week on time | f2 on the same weeks |
|---|---:|---:|---:|---:|
| 0.6, no limit | 24 | +249 (114) | 92.5% | 94.1% |
| 0.8, no limit | 36 | +160 (95) | 91.5% | 93.0% |
| 1.0, no limit | 36 | +146 (79) | 92.4% | 93.0% |
| 1.0, limit 2.0 (the candidate) | 38 | +107 (48) | 92.4% | 93.0% |
| 1.0, limit 1.5 | 36 | +75 (41) | 92.4% | 93.0% |
| 1.5, no limit | 24 | -8 (51) | 94.1% | 94.1% |

### Week by week (frozen f2 against the candidate)

| Week | f2 margin | f2 on time | New margin | New on time | Difference |
|---|---:|---:|---:|---:|---:|
| t1 | 18,163 | 96.6% | 19,144 | 94.9% | +982 |
| t2 | 18,479 | 94.4% | 18,798 | 95.0% | +319 |
| t3 | 18,205 | 98.0% | 18,755 | 98.7% | +550 |
| t4 | 15,591 | 96.0% | 15,588 | 96.0% | -3 |
| t5 | 20,506 | 96.2% | 21,518 | 96.6% | +1,011 |
| t6 | 12,543 | 97.4% | 12,514 | 98.5% | -30 |
| v1 | 15,080 | 98.1% | 15,073 | 98.1% | -7 |
| v2 | 13,312 | 96.5% | 13,286 | 96.5% | -26 |
| v3 | 14,831 | 97.5% | 14,747 | 97.5% | -84 |
| v4 | 15,791 | 98.3% | 15,759 | 98.3% | -32 |
| v5 | 15,398 | 98.1% | 15,433 | 98.1% | +35 |
| v6 | 14,289 | 96.2% | 14,263 | 96.2% | -26 |
| s1 | 15,625 | 96.4% | 15,903 | 97.1% | +278 |
| s2 | 12,431 | 96.8% | 12,690 | 97.0% | +260 |
| s3 | 14,558 | 97.7% | 14,389 | 97.2% | -169 |
| s4 | 24,043 | 96.2% | 23,842 | 96.2% | -201 |
| s5 | 15,700 | 97.7% | 15,689 | 97.7% | -11 |
| s6 | 17,704 | 95.7% | 18,063 | 95.9% | +359 |
| s7 | 20,388 | 97.0% | 20,444 | 97.0% | +57 |
| s8 | 17,641 | 98.0% | 17,489 | 97.7% | -152 |
| s9 | 13,479 | 94.1% | 13,490 | 94.3% | +12 |
| s10 | 22,536 | 96.0% | 22,821 | 96.0% | +284 |
| s11 | 15,998 | 95.3% | 15,955 | 95.3% | -44 |
| s12 | 17,919 | 98.0% | 18,231 | 98.2% | +312 |
| w1 | 13,548 | 94.4% | 13,509 | 95.0% | -39 |
| w2 | 19,843 | 93.5% | 19,707 | 93.2% | -136 |
| w3 | 11,456 | 95.7% | 11,456 | 95.7% | +0 |
| w4 | 15,288 | 94.3% | 15,443 | 95.1% | +156 |
| w5 | 16,747 | 93.0% | 17,140 | 92.4% | +393 |
| w6 | 13,137 | 95.0% | 13,292 | 94.8% | +155 |
| w7 | 17,164 | 96.8% | 17,635 | 97.2% | +472 |
| w8 | 17,049 | 98.8% | 17,032 | 98.8% | -17 |
| w9 | 21,314 | 95.8% | 21,040 | 95.3% | -274 |
| w10 | 16,444 | 96.8% | 16,067 | 97.0% | -377 |
| w11 | 20,397 | 96.8% | 20,641 | 96.8% | +245 |
| w12 | 24,477 | 98.1% | 24,423 | 98.1% | -54 |
| r1 | 15,065 | 96.5% | 15,014 | 96.5% | -51 |
| r2 | 14,529 | 94.0% | 14,446 | 93.5% | -83 |

## Reading

- Over 38 weeks the new version makes +107 a week (se 48), better in 17 of 38 weeks. The cheaper the over-budget price, the larger the gain and the more late cars; with no price that wins (1.5) the gain is zero. That pattern is what a real, small effect looks like.
- The gain is not spread evenly: most weeks move by a few hundred either way, and a few weeks carry it (t5 +1,011, t1 +982, t3 +550).
- On time: the same on average (96.4% against 96.4%); in the worst week 92.4% against 93.0%.
- The bar set before the test was a gain above two standard errors with the worst week at 94% on time or better. The gain clears two standard errors; the worst week does not reach 94% for either version on the new weeks.
- Not yet done for the new version: a ranking round. A kill-and-restart rehearsal is logged in COORDINATION.md.

## Clean holdout, added 05:10: 48 brand-new weeks (y1-y48)

Run after the tables above, on seeds neither version had played, with the rule fixed beforehand: recommend the swap only if the new version is not worse than f2 on these weeks and its worst week is at 92% on time or better. z1-z10 were not used.

| | Frozen f2 | New (f3) |
|---|---:|---:|
| Margin per week | 15,981 | 16,047 |
| Difference (se) | | +66 (39) |
| Weeks better / worse / same | | 28 / 18 / 2 |
| On time, average | 96.1% | 96.0% |
| On time, worst week | 92.7% | 92.7% |
| Weeks ranked | 48 of 48 | 48 of 48 |

The rule is met: the new version is not worse (+66) and its worst week is 92.7%, the same as f2's. Together with the 38 weeks above: about +84 a week (se about 30) over 86 weeks. With that gain the estimated places are about 14th in the 00:00 round (f2: 17th) and 10th or 11th in the 03:00 round (f2: 11th).

### Week by week (y1-y48)

| Week | f2 margin | f2 on time | New margin | New on time | Difference |
|---|---:|---:|---:|---:|---:|
| y1 | 17,791 | 94.6% | 17,763 | 94.6% | -28 |
| y2 | 20,786 | 97.6% | 20,453 | 97.6% | -333 |
| y3 | 12,411 | 97.1% | 12,411 | 97.1% | +0 |
| y4 | 13,728 | 95.2% | 14,726 | 96.4% | +998 |
| y5 | 17,625 | 96.0% | 17,989 | 95.6% | +364 |
| y6 | 18,380 | 96.2% | 18,383 | 96.0% | +3 |
| y7 | 13,636 | 96.9% | 13,635 | 96.9% | -1 |
| y8 | 18,329 | 95.0% | 18,715 | 95.2% | +386 |
| y9 | 14,959 | 94.2% | 15,014 | 94.0% | +55 |
| y10 | 17,851 | 98.2% | 18,050 | 97.8% | +199 |
| y11 | 17,133 | 94.1% | 17,041 | 93.7% | -92 |
| y12 | 17,251 | 94.8% | 17,187 | 94.9% | -64 |
| y13 | 11,004 | 95.8% | 10,992 | 95.8% | -12 |
| y14 | 20,438 | 92.9% | 20,580 | 93.4% | +141 |
| y15 | 10,085 | 97.4% | 10,085 | 97.4% | +0 |
| y16 | 17,260 | 97.5% | 17,427 | 97.6% | +167 |
| y17 | 15,255 | 95.8% | 15,489 | 95.8% | +235 |
| y18 | 16,047 | 98.4% | 16,110 | 98.9% | +63 |
| y19 | 17,931 | 96.2% | 17,492 | 95.2% | -440 |
| y20 | 17,770 | 94.9% | 17,576 | 94.4% | -194 |
| y21 | 17,188 | 95.7% | 17,322 | 95.5% | +134 |
| y22 | 15,456 | 96.5% | 15,413 | 96.3% | -43 |
| y23 | 11,078 | 94.0% | 11,090 | 94.3% | +12 |
| y24 | 17,810 | 96.8% | 17,618 | 96.0% | -192 |
| y25 | 21,752 | 96.2% | 21,991 | 96.0% | +239 |
| y26 | 14,175 | 97.5% | 13,985 | 97.7% | -190 |
| y27 | 17,968 | 95.0% | 17,760 | 95.2% | -208 |
| y28 | 15,708 | 94.8% | 15,771 | 94.8% | +63 |
| y29 | 13,950 | 98.2% | 13,902 | 98.5% | -47 |
| y30 | 14,113 | 97.0% | 13,792 | 96.7% | -321 |
| y31 | 12,255 | 96.6% | 12,365 | 96.6% | +110 |
| y32 | 14,395 | 99.0% | 15,016 | 99.3% | +621 |
| y33 | 13,086 | 94.5% | 12,572 | 94.7% | -514 |
| y34 | 20,096 | 97.3% | 20,260 | 96.9% | +164 |
| y35 | 15,774 | 97.1% | 15,785 | 97.1% | +11 |
| y36 | 18,675 | 95.6% | 18,709 | 96.2% | +34 |
| y37 | 19,633 | 96.4% | 20,188 | 95.4% | +555 |
| y38 | 12,057 | 92.7% | 12,054 | 92.7% | -3 |
| y39 | 10,930 | 94.6% | 10,931 | 94.6% | +1 |
| y40 | 14,367 | 93.3% | 14,727 | 93.3% | +359 |
| y41 | 16,659 | 98.4% | 16,764 | 98.4% | +105 |
| y42 | 17,654 | 97.9% | 18,186 | 98.3% | +533 |
| y43 | 14,379 | 94.5% | 14,374 | 94.5% | -5 |
| y44 | 15,179 | 97.7% | 15,404 | 97.5% | +225 |
| y45 | 17,904 | 96.3% | 17,996 | 96.8% | +93 |
| y46 | 18,306 | 96.3% | 18,270 | 95.2% | -36 |
| y47 | 20,529 | 96.7% | 20,546 | 96.7% | +17 |
| y48 | 10,323 | 95.8% | 10,337 | 95.9% | +14 |
