#!/bin/zsh
S=${DEMO_SCRATCH:-$HOME/.cache/osor-demo}
cd $S/video
export SID=$(awk '/sid/{print $7}' $S/jar-demo)
BK=/Users/user/Documents/blogger/backend
py() { (cd $BK && uv run python $S/video/stage.py "$@" 2>&1 | grep -v Warning); }
rec() { echo "== $1"; rm -rf scenes/$1; node --experimental-websocket rec.mjs "$@" 2>&1 | grep -v ExperimentalWarning; printf "   frames %s  %.1fs\n" "$(ls scenes/$1 | grep -c jpg)" "$(awk 'NR==1{a=$1} END{print ($1-a)/1000}' scenes/$1/times.txt)"; }
py hold
rec signin
py quote
FID=$(py flow_id | tail -1); export FLOW_URL="http://osor.localhost:3001/start/$FID"; echo "flow $FLOW_URL"
rec quote "$SID"
py cleanup
