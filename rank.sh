#!/bin/zsh
# Plays the next ranking round at level 8 with the desk's defaults: waits until a round newer than AFTER has started,
# takes the sweep lock (so this build never holds more than 4 practice worlds), plays its five worlds one at a time.
#   ./rank.sh AFTER_SEASON TAG       e.g.  ./rank.sh 9 rank0000
cd "$(dirname "$0")"
after=$1; tag=$2
.venv/bin/python - $after <<'PY'
import sys, time
from abquant.env import load_key
load_key()
from spread.client import Client, SpreadError
after = int(sys.argv[1])
client = Client()
while True:
    try:
        cur = client.board(8).get("current")
        if cur and cur["season"] > after:
            print("ranking round", cur["season"], cur["name"], "started", cur["startedAt"], flush=True)
            break
    except SpreadError as error:
        print("board:", error, flush=True)
    time.sleep(30)
PY
lock=logs/.sweep.lock
while true; do
  if mkdir $lock 2>/dev/null; then echo $$ > $lock/pid; break; fi
  holder=$(cat $lock/pid 2>/dev/null)
  if [[ -n $holder ]] && ! kill -0 $holder 2>/dev/null; then rm -rf $lock; continue; fi
  sleep 2
done
trap 'rm -rf $lock' EXIT INT TERM
caffeinate -i .venv/bin/python -m abquant.run --board 5 --tag $tag 2>&1 | tee -a logs/rank_$tag.txt | tail -8
