#!/bin/zsh
# Plays the final and keeps playing: if the player ever exits, it starts again and rejoins from its saved state.
# It does not stop when a final ends: it waits for the next one, so a test final in the night cannot leave the
# real final unplayed. Exactly one bot may play the final: this refuses to start while another launcher of this desk or
# final player is alive. Start it once, before 07:45; it waits for the final by itself.
#   ./run_final.sh                 # the frozen settings
#   ./run_final.sh "pi_max=0.12"   # with overrides
# To stop it:  pkill -f run_final.sh; pkill -f 'abquant.live --final'
cd "$(dirname "$0")"
mkdir -p logs
lock=logs/.final.lock
alive=""
# a launcher that holds the lock: its pid must be alive and must be a run_final.sh
holder=$(cat $lock/pid 2>/dev/null)
if [[ -n $holder ]] && kill -0 $holder 2>/dev/null && ps -o args= -p $holder | grep -q "run_final"; then
  alive="launcher (pid $holder)"
fi
# a player without a lock (started by an older launcher): only a python process counts, never a shell whose
# command line merely contains the words
if [[ -z $alive ]]; then
  for p in $(pgrep -i python); do
    if ps -o args= -p $p | grep -q "abquant\.live --final"; then alive="final player (pid $p)"; break; fi
  done
fi
if [[ -n $alive ]]; then
  echo "Another $alive is already running. Not starting a second one."
  echo "To watch it:  tail -f \"\$(ls -t logs/final_console_*.txt | head -1)\""
  echo "To stop it:   pkill -f run_final.sh; pkill -f 'abquant.live --final'"
  exit 1
fi
rm -rf $lock
mkdir $lock || { echo "Another launcher took the lock just now. Not starting a second one."; exit 1; }
echo $$ > $lock/pid
trap 'rm -rf $lock' EXIT
trap 'exit 130' INT TERM
console=logs/final_console_$(date +%m%d_%H%M%S).txt
echo "console log: $console"
while true; do
  caffeinate -i .venv/bin/python -m abquant.live --final --set ${=1} 2>&1 | tee -a $console
  code=${pipestatus[1]}
  if [[ $code -eq 0 ]] && tail -3 $console | grep -q "^END "; then
    echo "$(date +%H:%M:%S) a final has ended; waiting for the next one" | tee -a $console
  else
    echo "$(date +%H:%M:%S) final process exited ($code); restarting in 2 s" | tee -a $console
  fi
  sleep 2
done
