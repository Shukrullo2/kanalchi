"""A quiet, royalty-free background bed, synthesised here: a slow pad over Am–F–C–G, a soft
plucked arpeggio, a round bass, gentle fades. Nothing sampled, nothing licensed."""
import numpy as np, wave, sys
SR = 44100
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 140.0
bpm = 84; beat = 60 / bpm; bar = 4 * beat
t = np.arange(int(dur * SR)) / SR
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)
# chords as MIDI note sets (A minor, F major, C major, G major), one bar each, looping
chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]]
def lowpass(x, cutoff):
    # one-pole IIR, stable and cheap
    a = np.exp(-2 * np.pi * cutoff / SR); y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = a * acc + (1 - a) * x[i]; y[i] = acc
    return y
out = np.zeros_like(t)
n_bars = int(np.ceil(dur / bar))
rng = np.random.default_rng(7)
for b in range(n_bars):
    notes = chords[b % 4]
    s0, s1 = int(b * bar * SR), int(min(dur, (b + 1) * bar + 0.6) * SR)
    seg = t[s0:s1] - b * bar
    env = np.clip(seg / 0.8, 0, 1) * np.clip((bar + 0.6 - seg) / 0.8, 0, 1)
    pad = np.zeros_like(seg)
    for n in notes:
        f = midi(n)
        for det in (-0.4, 0.0, 0.4):
            ff = f * 2 ** (det / 1200)
            pad += 0.25 * np.sin(2 * np.pi * ff * seg + 0.3 * np.sin(2 * np.pi * 0.11 * seg)) + 0.08 * np.sin(2 * np.pi * 2 * ff * seg)
    out[s0:s1] += 0.12 * pad * env
    # bass: root, two octaves down, with a soft attack
    root = midi(notes[0] - 24)
    out[s0:s1] += 0.16 * np.sin(2 * np.pi * root * seg) * np.clip(seg / 0.15, 0, 1) * np.exp(-seg / (bar * 0.9))
    # arpeggio: eighth notes, chord tones, gently randomised octave
    for k in range(8):
        n = notes[(k * 3) % 4] + 12 * (1 if rng.random() < 0.35 else 0)
        st = k * beat / 2
        idx = seg >= st
        tt = seg[idx] - st
        pl = np.sin(2 * np.pi * midi(n) * tt) * np.exp(-tt * 5.5) * 0.11
        out[s0:s1][idx] += pl
out = lowpass(out, 2400)
# whole-piece fades
fade = np.minimum(1.0, np.minimum(t / 3.0, (dur - t) / 4.0)); out *= np.clip(fade, 0, 1)
out /= max(1e-9, np.max(np.abs(out))); out *= 0.55
with wave.open("music.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((out * 32767).astype(np.int16).tobytes())
print("music", round(dur), "s")
