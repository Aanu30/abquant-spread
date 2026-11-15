#!/bin/zsh
# usage: [PAR=2] ./sweep.sh NAME "k=v k=v" [seeds] [BASE]   -> plays the seeds (default: t1-t6 and v1-v6), then compares with BASE
# Only one sweep runs at a time (a lock), so this build never holds more than 4 practice worlds. PAR sets how many
# weeks run at once (default 4; use less while a rehearsal holds a world).
cd "$(dirname "$0")"
seeds=${3:-t1,t2,t3,t4,t5,t6,v1,v2,v3,v4,v5,v6}
base=${4:-base}
par=${PAR:-4}
lock=logs/.sweep.lock
while true; do
  if mkdir $lock 2>/dev/null; then echo $$ > $lock/pid; break; fi
  holder=$(cat $lock/pid 2>/dev/null)
  if [[ -n $holder ]] && ! kill -0 $holder 2>/dev/null; then rm -rf $lock; continue; fi
  sleep 2
done
trap 'rm -rf $lock' EXIT INT TERM
caffeinate -i .venv/bin/python -m abquant.run --seeds $seeds --tag $1 --parallel $par --set ${=2} 2>&1 | grep -E "^==|FAILED|Error" | sed "s/^/$(date +%H:%M) [${2}] /" >> logs/sweeps.txt
{ echo "$(date +%H:%M) [${2}]"; .venv/bin/python -m abquant.compare $1 $base; } | tee -a logs/sweeps.txt
