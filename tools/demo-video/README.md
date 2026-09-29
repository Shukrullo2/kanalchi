# Demo video

Records the osor.uz funnel and the example channel with headless Chrome, then cuts the frames
into a 1080p clip with Uzbek captions, title cards and a synthesised background track.

- `rec.mjs` — one scene per run, frames + timestamps into `scenes/<name>/` (Node 20+, `--experimental-websocket`).
- `stage.py` — stages the local database so the public form can price @the_bakiroo (`hold` parks the
  local tenant, `finalize` stands in for the reader account's measurement, `cleanup` restores both).
- `run.sh` — records every scene in order: the quote on the local stack, then the production pages.
- `assemble.py` — cards, captions, encoding (`.venv` with imageio, imageio-ffmpeg, pillow, numpy).
- `music.py` — the background bed, generated, so nothing needs a licence.

Needs the local stack (`make api`, `make web`) and the production sites reachable. The chat scene asks
the live assistant a real question, which costs a few cents of Anthropic credit.
