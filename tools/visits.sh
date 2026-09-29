#!/usr/bin/env bash
# Visits on the production sites, from Caddy's access log on the droplet.
#   tools/visits.sh "2026-09-29T10:50:00Z"          # since a moment (UTC or with offset)
#   tools/visits.sh "2h"                            # or a docker-style duration
set -euo pipefail
since="${1:-1h}"
host="${DROPLET:-root@161.35.79.4}"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" \
  "cd /opt/kanalchi && docker compose -f infra/compose.yml --env-file infra/.env logs --since '$since' --no-log-prefix caddy 2>/dev/null | grep '\"request\"'" \
| python3 - "$since" <<'PY'
import sys, json, re, collections
since = sys.argv[1]
BOT = re.compile(r"bot|crawl|spider|slurp|curl|wget|python-requests|facebookexternalhit|linkedinbot|telegrambot|whatsapp|preview|headless|monitor|uptime", re.I)
SKIP = re.compile(r"^/(_next/|media/|uploads/|favicon|robots|sitemap|api/internal|internal/)")
rows = []
for line in sys.stdin:
    try:
        l = json.loads(line)
    except ValueError:
        continue
    r = l.get("request", {})
    ua = (r.get("headers", {}).get("User-Agent") or [""])[0]
    rows.append({
        "ts": l.get("ts", 0), "host": r.get("host", ""), "uri": r.get("uri", ""),
        "ip": r.get("client_ip") or r.get("remote_ip", ""), "status": l.get("status"),
        "ref": (r.get("headers", {}).get("Referer") or [""])[0], "ua": ua, "bot": bool(BOT.search(ua)),
        "method": r.get("method", ""),
    })
pages = [x for x in rows if x["method"] == "GET" and not SKIP.match(x["uri"]) and not x["uri"].startswith("/api/") and 200 <= (x["status"] or 0) < 400]
humans = [x for x in pages if not x["bot"]]
print(f"since {since}: {len(rows)} requests, {len(pages)} page views, {len(humans)} by browsers, {len(pages)-len(humans)} by bots")
print(f"distinct visitors (browser, by address): {len({x['ip'] for x in humans})}")
print("\npage views by host (browsers):")
for h, n in collections.Counter(x["host"] for x in humans).most_common(): print(f"  {n:5d} {h}  ({len({x['ip'] for x in humans if x['host']==h})} visitors)")
print("\ntop pages (browsers):")
for (h, u), n in collections.Counter((x["host"], re.sub(r"\?.*", "", x["uri"])) for x in humans).most_common(20): print(f"  {n:5d} {h}{u}")
refs = collections.Counter(re.sub(r"^https?://([^/]+).*", r"\1", x["ref"]) for x in humans if x["ref"] and not any(d in x["ref"] for d in ("osor.uz", "bakiroo.uz")))
if refs:
    print("\nreferrers:")
    for ref, n in refs.most_common(15): print(f"  {n:5d} {ref}")
asks = [x for x in rows if x["method"] == "POST" and x["uri"].startswith("/api/signup/quote")]
print(f"\nprice checks on /start: {len(asks)} from {len({x['ip'] for x in asks})} addresses")
bots = collections.Counter(x["ua"][:60] for x in pages if x["bot"])
if bots:
    print("\nbots:")
    for ua, n in bots.most_common(8): print(f"  {n:5d} {ua}")
PY
