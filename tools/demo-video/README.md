# Demo video

Records the osor.uz funnel and the example channel with headless Chrome, then cuts the frames
into a 1080p clip with Uzbek captions, title cards and a synthesised background track.

- `rec.mjs` — one scene per run, frames + timestamps into `scenes/<name>/` (Node 20+, `--experimental-websocket`).
- `stage.py` — stages the local database for the fake registration (`hold` / `quote` / `flow_id` / `cleanup`).
- `run.sh` — records every scene in order; `run3.sh` re-records only the staged sign-in and quote scenes.
- `assemble.py` — cards, captions, encoding (`.venv` with imageio, imageio-ffmpeg, pillow, numpy).
- `music.py` — the background bed, generated, so nothing needs a licence.

Needs the local stack (`make api`, `make web`) with a platform-host dev session in `jar-demo`
(`POST /api/auth/dev-login` on `osor.localhost` as "Bakiroo"), and the production sites reachable.
The chat scene only shows an answer when the Anthropic account has credit.
