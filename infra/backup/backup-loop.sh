#!/bin/sh
# Runs backup.sh once a day at ~03:00 UTC; simple loop instead of cron to keep the image tiny.
while true; do
  now=$(date -u +%H%M)
  if [ "$now" = "0300" ]; then sh /backup.sh || echo "backup failed"; sleep 61; fi
  sleep 30
done
