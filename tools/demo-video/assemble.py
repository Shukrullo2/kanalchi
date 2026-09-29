"""Assemble the demo: title cards, recorded scenes with captions, one H.264 file."""
from __future__ import annotations
import os, sys
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio.v2 as imageio

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1920, 1080, 24
NAVY, SURFACE, INK, MUTED, GOLD, SKY = (14, 24, 48), (22, 34, 63), (246, 243, 234), (170, 178, 196), (245, 197, 24), (86, 198, 240)
TTC = "/System/Library/Fonts/Avenir Next.ttc"

@lru_cache(maxsize=None)
def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    for i in range(16):
        try:
            f = ImageFont.truetype(TTC, size, index=i)
        except OSError:
            break
        if f.getname()[1].lower() == style.lower():
            return f
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)

def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ---- title cards ------------------------------------------------------------------------
def card(title: str, subtitle: str = "", kicker: str = "", foot: str = "", accent_last=True) -> Image.Image:
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    # a soft gold glow top-right, like the site's final panel
    glow = Image.new("RGB", (W, H), NAVY)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W - 900, -500, W + 500, 700), fill=(52, 56, 52))
    im = Image.blend(im, glow, 0.55); d = ImageDraw.Draw(im)
    # mark
    d.rounded_rectangle((160, 150, 160 + 84, 150 + 84), radius=22, fill=GOLD)
    d.text((160 + 42, 150 + 42), "O", font=font("Heavy", 54), fill=NAVY, anchor="mm")
    d.text((270, 150 + 42), "Osor", font=font("Heavy", 54), fill=INK, anchor="lm")
    # The kicker sits on its own line above the title; the title is laid out from its
    # ascender ("la"), so a tall first line can never climb back into the kicker.
    y = 330
    if kicker:
        d.text((160, y), kicker.upper(), font=font("Demi Bold", 26), fill=SKY, anchor="ls")
        y += 42
    tf = font("Heavy", 96)
    lh = 112
    lines = wrap(d, title, tf, W - 320)
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        if accent_last and last and " " in line:
            head, tail = line.rsplit(" ", 1)
            d.text((160, y), head + " ", font=tf, fill=INK, anchor="la")
            d.text((160 + d.textlength(head + " ", font=tf), y), tail, font=tf, fill=GOLD, anchor="la")
        else:
            d.text((160, y), line, font=tf, fill=GOLD if (accent_last and last and len(lines) > 1) else INK, anchor="la")
        y += lh
    if subtitle:
        y += 34
        for line in wrap(d, subtitle, font("Medium", 40), W - 400):
            d.text((160, y), line, font=font("Medium", 40), fill=MUTED, anchor="la"); y += 56
    if foot:
        d.text((160, H - 120), foot, font=font("Demi Bold", 34), fill=GOLD, anchor="ls")
    return im

# ---- captions ----------------------------------------------------------------------------
@lru_cache(maxsize=None)
def caption_layer(text: str) -> Image.Image:
    """A full-width band along the bottom, so a caption never fights the page's own text."""
    f = font("Demi Bold", 40)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = wrap(tmp, text, f, W - 260)
    lh = 54
    band_h = max(120, lh * len(lines) + 56)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y0 = H - band_h
    # a soft rise above the band, then the band itself
    for i in range(40):
        d.rectangle((0, y0 - 40 + i, W, y0 - 40 + i + 1), fill=(14, 24, 48, int(238 * i / 40)))
    d.rectangle((0, y0, W, H), fill=(14, 24, 48, 238))
    d.rectangle((96, y0 + 28, 104, H - 28), fill=GOLD + (255,))
    ty = y0 + (band_h - lh * len(lines)) // 2 + 2
    for i, line in enumerate(lines):
        d.text((132, ty + i * lh), line, font=f, fill=INK + (255,))
    return layer

# ---- scenes -----------------------------------------------------------------------------
def scene_frames(name: str, speed: float = 1.0, trim_start: float = 0.0, trim_end: float = 0.0, cap: float | None = None):
    d = os.path.join(HERE, "scenes", name)
    rows = [l.split() for l in open(os.path.join(d, "times.txt")) if l.strip()]
    times = [(int(t) / 1000.0, f) for t, f in rows]
    t0 = times[0][0] + trim_start
    t_end = times[-1][0] - trim_end
    if cap is not None:
        t_end = min(t_end, t0 + cap)
    dur = (t_end - t0) / speed
    n = int(dur * FPS)
    j = 0
    out = []
    for k in range(n):
        t = t0 + (k / FPS) * speed
        while j + 1 < len(times) and times[j + 1][0] <= t:
            j += 1
        out.append((k / FPS, os.path.join(d, times[j][1])))
    return out, dur

def load(path):
    im = Image.open(path).convert("RGB")
    return im if im.size == (W, H) else im.resize((W, H), Image.LANCZOS)

class Writer:
    def __init__(self, path):
        self.w = imageio.get_writer(path, fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=None)
        self.n = 0
    def frame(self, im: Image.Image, fade: float = 1.0):
        if fade < 1.0:
            im = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), im, fade)
        self.w.append_data(np.asarray(im)); self.n += 1
    def close(self): self.w.close()

def play_card(wr, im, seconds, fade=0.6):
    n = int(seconds * FPS)
    for k in range(n):
        t = k / FPS
        f = min(1.0, t / fade, (seconds - t) / fade)
        wr.frame(im, max(0.0, f))

def play_scene(wr, name, captions=(), speed=1.0, trim_start=0.0, trim_end=0.0, cap=None, fade_in=0.35, fade_out=0.35):
    frames, dur = scene_frames(name, speed, trim_start, trim_end, cap)
    last_path, im = None, None
    for t, path in frames:
        if path != last_path:
            im = load(path); last_path = path
        out = im
        for (a, b, text) in captions:
            if a <= t < (b if b is not None else 1e9):
                out = Image.alpha_composite(im.convert("RGBA"), caption_layer(text)).convert("RGB")
                break
        f = min(1.0, t / fade_in if fade_in else 1.0, (dur - t) / fade_out if fade_out else 1.0)
        wr.frame(out, max(0.0, f))
    print(f"  {name}: {dur:.1f}s", flush=True)

def main(out="demo.mp4"):
    wr = Writer(os.path.join(HERE, out))
    play_card(wr, card("Kanalingiz tarixini onlayn asarga aylantiring", "Osor bilan ikki daqiqada tanishing: Telegram kanal qidiruvli saytga aylanadi.", kicker="Namoyish", foot="osor.uz"), 4.5)
    play_scene(wr, "landing", [
        (0, 2.6, "osor.uz — kirish eshigi"),
        (2.6, 7.0, "Kanal — lenta. Osor — kitob."),
        (7.0, 13.2, "Qidiruv, teglar, statistika, xarita — va postlar asosida javob beruvchi yordamchi"),
        (13.2, 17.4, "Siz faqat importga to‘laysiz (asosan AI xarajati). Birinchi oy hosting bepul."),
        (17.4, None, "Kanalni ulaymiz"),
    ], speed=1.1)
    play_scene(wr, "quote", [
        (0, 4.0, "Kanal username’ini yozing — kirish shart emas"),
        (4.0, 9.0, "Hajmi darhol hisoblanadi, keyin Telegramdan aniqlashtiriladi"),
        (9.0, 15.5, "12 965 ta post — bitta narx, so‘mda. Birinchi oy hosting bepul"),
        (15.5, None, "Keyingi qadam: adminga yozish, to‘lovdan keyin import boshlanadi"),
    ])
    play_card(wr, card("Bir necha soatdan so‘ng…", "Har bir post o‘qildi, teglandi va indekslandi. Kanal the-bakiroo.uz manzilida ishlamoqda.", kicker="Import ishlaydi", accent_last=False), 4.0)
    play_scene(wr, "site_home", [
        (0, 3.2, "the-bakiroo.uz — 2019-yildan beri 12 000 post, endi sayt"),
        (3.2, 8.5, "Arxiv nimani biladi: mavzular, shaxslar, idoralar"),
        (8.5, None, "Statistika: qachon yozadi, nima haqida, qanday o‘qiladi"),
    ], speed=1.15)
    play_scene(wr, "site_posts", [(0, 4.5, "Har bir post — alohida sahifa"), (4.5, None, "Rasmlar, havolalar, reaksiyalar — va har postda teglar")], speed=1.1)
    play_scene(wr, "site_tags", [(0, None, "Mavzular va shaxslar ko‘rsatkichi — sun’iy intellekt tuzgan")], speed=1.1)
    play_scene(wr, "site_search", [(0, None, "Lotin, kirill va rus tilida qidiruv, filtrlar bilan")], speed=1.1)
    play_scene(wr, "site_chat", [(0, 5.0, "Arxivga oddiy tilda savol bering"), (5.0, None, "Javob kanalning o‘z postlariga tayanadi va ularga havola beradi")], speed=1.25, cap=42)
    play_scene(wr, "site_graph", [(0, None, "Kanal mavzulari qanday bog‘langani — xaritada")])
    play_scene(wr, "site_stories", [(0, None, "Bir-birini davom ettirgan postlar syujet bo‘ladi")], speed=1.1)
    play_scene(wr, "site_top", [(0, None, "Eng ko‘p o‘qilgan postlar — bir qarashda")], speed=1.1)
    play_card(wr, card("Kanalingiz tarixini onlayn asarga aylantiring", "Telegram orqali kiring, kanalingizni qo‘shing, narxini ko‘ring. Birinchi oy hosting bepul.", kicker="Osor", foot="osor.uz/start"), 6.0, fade=0.8)
    wr.close()
    print("frames", wr.n, "≈", round(wr.n / FPS), "s")

if __name__ == "__main__":
    main(*sys.argv[1:])
