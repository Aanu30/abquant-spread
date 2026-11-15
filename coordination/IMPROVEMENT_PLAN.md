# Improvement plan for the final (setup session; corrected 03:5x Sun)

Information for DESK and the team lead, not an instruction. DESK builds and tests; the team lead decides what is swapped in.

## Correction
My 03:46 premise was wrong. f2 quotes every request: when no option is workable it sends a losing quote at 4x list (`decline_mult`, desk.py:612). The "228 not quoted" in runs.jsonl are those 4x quotes, and `why` counts options, not requests (DESK, 03:5x, from 5 revealed weeks: 5,179 requests, 0 unquoted).

## Facts (DESK, f2, per week over 24 weeks)
- 779 priced quotes, 256 quotes at 4x: pool full 94 (83 of them long hauls of 240+ min), low value 57, late risk 30, trade-in 21, no driver day 21, no time left 15.
- On time 95-98%, worst week 94.1%; the rule is 90%. A late car costs about 30% of its price, about one typical fee in extra driver cost, and half the dealer's trust.
- Rounds: 00:00 16,053/week (17th of 58; 10th 16,368). 03:00 15,270 (10th of 27; 1st 17,057).

## What is left to try tonight
1. **`cap_rate` 0.165 and 0.18 with the brake on** (settings only, no code change). DESK is running these on 24 weeks now (about 4 min each when the server is quiet).
2. **Capped scarcity price for over-budget long hauls** (about 1.8-2.2 x list in place of 4x). Code change of about 10 lines, done in a copy: about 40-50 min including a check that the copy reproduces f2 and a kill-and-restart rehearsal. DESK expects +0 to +400 a week at best, sign uncertain. Needs the team lead's word.
3. Dropped: `u_max` alone (no effect past 0.99), short trade-ins (about 100 a week at most), three-car gigs (too large for tonight).

**Keep a change only if:** paired gain > 2 se on 24 weeks, z1-z10 (unused, fresh) not worse, worst week at or above the team lead's bar (93 or 94%).

## Safety
- Work in a copy. Do not edit the desk's folder (repo root) while the launcher waits: it restarts from those files.
- At most 4 practice worlds. Never two launchers.
- Swap only on the team lead's word, finished by 07:15: stop the launcher (`pkill -f run_final.sh; pkill -f 'abquant.live --final'`), copy the tested files into the desk's folder (repo root), start exactly one `./run_final.sh`, check `pgrep -fl 'abquant.live --final'` shows 2 lines and the console says "No final is set yet". The setup watchdog will say "bot stopped" during the swap; that is expected.
- If nothing passes by 06:30, f2 plays as it is.

## Timeline (Helsinki)
03:50-06:15 tests. 06:30 results to the team lead. 06:45-07:15 swap if approved. 07:30 final is set; 07:31 check "Final world <id>". 07:30-08:40 quiet window.
