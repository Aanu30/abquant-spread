#!/bin/zsh
# Rebuilds the slides with the final's result on slide 9.   ./update_final_result.sh "The final: €15,800, 96.9% on time, 9th of 31 ranked"
# Needs node_modules with pptxgenjs next to this script (npm install pptxgenjs).
cd "$(dirname "$0")"
[ -d node_modules ] || npm install pptxgenjs >/dev/null 2>&1
FINAL_RESULT="$1" NODE_PATH="$PWD/node_modules" node build.js && python3 fitcheck.py ../Spread_jury_slides.pptx
