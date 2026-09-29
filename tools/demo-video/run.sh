#!/bin/zsh
S=${DEMO_SCRATCH:-$HOME/.cache/osor-demo}
cd $S/video
BK=/Users/user/Documents/blogger/backend
py() { (cd $BK && uv run python $S/video/stage.py "$@" 2>&1 | grep -v Warning); }
rec() { echo "== $1 $(date +%H:%M:%S)"; rm -rf scenes/$1; node --experimental-websocket rec.mjs "$@" 2>&1 | grep -v ExperimentalWarning; printf "   frames %s  %.1fs\n" "$(ls scenes/$1 | grep -c jpg)" "$(awk 'NR==1{a=$1} END{print ($1-a)/1000}' scenes/$1/times.txt)"; }
py hold
rec quote
py cleanup
rec landing
for s in site_home site_posts site_tags site_search site_chat site_graph site_stories site_top; do rec $s; done
echo ALL_DONE
