#!/bin/zsh
# Waits for the final's END line in the live console (read-only), then plays the two experiments on practice weeks,
# one sweep after the other (sweep.sh keeps this build at 4 practice worlds). Touches nothing in the repository root.
cd "$(dirname "$0")"
console=../logs/final_console_1115_055007.txt
until grep -q "^END" $console 2>/dev/null; do sleep 3; done
echo "$(date +%H:%M:%S) final ended: $(grep '^END' $console | tail -1)" | tee -a logs/sweeps.txt
sleep 20                                            # let the final's last requests clear the shared budget
seeds=y1,y2,y3,y4,y5,y6,y7,y8
./sweep.sh ylong "pool_long=400" $seeds yf3
./sweep.sh ytri "triple=1" $seeds yf3
