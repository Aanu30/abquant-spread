# Final morning runbook (Sunday 15 Nov, Helsinki time). Updated 07:10.

**Rule one: only ONE bot plays the final.** Both builds use the same team key and would act on the same final world.

## What is running right now
- The ABQuant desk, version **f3**, is the bot for the final. Its launcher (`run_final.sh` at the repo root) has run since 05:50 and is waiting.
- The launcher has a lock: starting it a second time just prints "already running" and exits. It does not stop after a test final; it waits for the next one.
- The final was moved to **09:00** (reported by the team lead; confirm on the Junction page). The organisers set the final about 30 minutes before it starts.
- Quiet window (no messages to the bots): 08:30 to 09:40.

## NOW, and until the final ends: plug in the charger, keep the LID OPEN
- The Mac slept from 07:09 to 08:06 with the lid closed, and it is on battery. A closed lid puts it to sleep even though the bot keeps it awake otherwise.
- If it sleeps during the final, the bot stops and every new request goes to the competitor. Lid open, charger in, stable Wi-Fi, from now until the bot prints `END` (about 09:35).

## 08:30: check, don't start
In Terminal:
```
pgrep -fl 'abquant.live --final'
```
- **A line comes back: do nothing.** It is waiting for the final.
- **Nothing comes back** (the Mac restarted, or the launcher was stopped): start it once. If one is already alive it refuses, so this is safe:
```
cd <repo root> && ./run_final.sh
```
It prints "No final is set yet", then the final's world id, then a line per simulated day.

## 09:00-09:35 the final runs by itself
- Live leaderboard: https://spread.bahnexpress.com/leaderboard
- If the bot crashes, the launcher restarts it within seconds and it rejoins from the world's state. Do nothing.
- The launcher runs without a Terminal window, so Ctrl-C does not reach it. To stop it: `pkill -f run_final.sh; pkill -f 'abquant.live --final'`
- Last resort only (the desk's launcher fails repeatedly and the desk's session cannot fix it): stop it with the command above, check `pgrep -fl 'abquant.live --final'` shows nothing, then start v4. Never run both.
```
cd other_build/releases/v4 && python3 -u -m bot.run --final
```
- Do not stop it before it prints `END`.

## By 10:00: submission on the Junction platform
- Submission hash: entered on the Junction platform (kept out of this repository).
- Slides: `submission/Spread_jury_slides.pptx`. Slide 9 has one line left for the final's result. After the final ends, run (one minute):
```
cd submission/build && ./update_final_result.sh "The final: EUR 15,800, 96.9% on time, 9th of 31 ranked"
```
  (put the real result in the quotes). Or tell Claude and it does it. The final ends around 09:35, so submit by about 09:50.
- Code link: this repository (excludes `.env`, `.venv/`, `logs/`, `data/worlds/`).
- Jury questions: `submission/JURY_QA.md`.

## 10:30-14:00 jury (if top 10)
Final ceremony at 14:00; winners named 15:10.
