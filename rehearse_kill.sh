#!/bin/zsh
# A live rehearsal with forced stops: one process moves a practice world's clock at the final's speeds, a supervisor
# loop plays it live, and the player is killed (kill -9) at the given real seconds. With a 4th argument the saved state
# is removed too, so the player must rebuild from the world's history.
#   ./rehearse_kill.sh SEED FAST "KILL_AT_SECONDS ..." [wipe]
cd "$(dirname "$0")"
seed=$1; fast=$2; kills=(${=3}); wipe=$4
log=logs/rehearse_kill_${seed}.txt; : > $log; : > logs/clock_${seed}.txt
.venv/bin/python -m abquant.clock --seed $seed --fast $fast > logs/clock_${seed}.txt 2>&1 &
clock_pid=$!
while [[ ! -s logs/clock_${seed}.txt ]]; do sleep 0.2; done
world=$(head -1 logs/clock_${seed}.txt)
echo "world $world seed $seed fast $fast kills $kills wipe '$wipe'" >> $log
( while true; do
    .venv/bin/python -m abquant.live --world $world >> $log 2>&1
    code=$?
    if [[ $code -eq 0 ]]; then break; fi
    echo "$(date +%H:%M:%S) player exited ($code); restarting" >> $log
    sleep 2
  done ) &
loop_pid=$!
start=$(date +%s)
for k in $kills; do
  while (( $(date +%s) - start < k )); do sleep 1; done
  pkill -9 -f "abquant.live --world $world"
  echo "$(date +%H:%M:%S) killed the player at ${k}s" >> $log
  if [[ -n $wipe ]]; then rm -f data/live_state_${world}.pkl; echo "saved state removed" >> $log; fi
done
wait $loop_pid
wait $clock_pid
.venv/bin/python - $world >> $log 2>&1 <<'PY'
import os, sys
from abquant.env import load_key, DATA
load_key()
from spread.client import Client
w = Client().world(sys.argv[1])
s = w.score()
print(f"SCORE margin {s['marginCents']/100:,.0f} won {s['wonOrders']} on time {s['onTimeShare']:.1%} ranked {s['ranked']}")
w.delete()
p = os.path.join(DATA, f"live_state_{sys.argv[1]}.pkl")
if os.path.exists(p): os.remove(p)
PY
tail -3 $log
