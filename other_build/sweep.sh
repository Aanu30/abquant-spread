#!/bin/zsh
# usage: ./sweep.sh TAG "k=v k=v" [seeds]
cd "$(dirname "$0")"
python3 -m bot.run --seeds ${3:-6} --prefix ${PREFIX:-t} --tag $1 --parallel 3 --set ${=2} 2>&1 | grep -E "^==|FAILED|Traceback"
