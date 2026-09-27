#!/bin/zsh
set -u
S=${DEMO_SCRATCH:-$HOME/.cache/osor-demo}
cd $S/video
export SID=$(awk '/sid/{print $7}' $S/jar-demo)
rec() { echo "== $1 $(date +%H:%M:%S)"; rm -rf scenes/$1; node --experimental-websocket rec.mjs "$@" 2>&1 | grep -v ExperimentalWarning; echo "   frames: $(ls scenes/$1 | grep -c jpg)"; }
BK=/Users/user/Documents/blogger/backend
py() { (cd $BK && uv run python $S/video/stage.py "$@" 2>&1 | grep -v Warning); }

# 1. the fake registration on the local stack
py hold
rec signin
py quote
FID=$(py flow_id | tail -1)
export FLOW_URL="http://osor.localhost:3001/start/$FID"
echo "flow url $FLOW_URL"
rec quote "$SID"
py cleanup

# 2. production pages
rec landing
for s in site_home site_posts site_tags site_search site_chat_idle site_graph site_stories site_top; do rec $s; done
echo ALL_DONE
