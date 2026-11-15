#!/bin/zsh
# Plays the live final (or a test final) with a frozen release. Keeps the Mac awake and restarts on any crash.
#   ./run_final.sh            uses releases/v4
#   ./run_final.sh v4         uses releases/v4
REL=${1:-v4}
cd "$(dirname "$0")/releases/$REL" || exit 1
echo "release $REL, started $(date)"
while true; do
  caffeinate -i python3 -u -m bot.run --final 2>&1 | tee -a logs/final_console.txt
  code=${pipestatus[1]}
  echo "bot exited with code $code at $(date)"
  [ "$code" = "0" ] && break
  sleep 3
done
