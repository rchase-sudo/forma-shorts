"""Cue-driven music + SFX bed for flip.html, with sidechain ducking under the voiceover.
Usage: python3 music.py cues.json vo.wav out_mix.wav
"""
import sys, json, wave
import numpy as np
import soundfile as sf

SR = 48000
C = json.load(open(sys.argv[1]))
vo, vsr = sf.read(sys.argv[2])
if vo.ndim > 1: vo = vo.mean(1)
vo = np.interp(np.arange(int(len(vo) * SR / vsr)) / SR, np.arange(len(vo)) / vsr, vo)

FLIP = C['hook2a'][0] + 0.62
PROC = C['p1'][0] - 0.25
CTA = C['cta1'][0] - 0.2
END = C['_end']
STEPS = [C['p1'][0], C['p2'][0], C['p3'][0], C['p4'][0]]
N = int(SR * END)
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(3)
BPM = 128; BEAT = 60 / BPM

def add(sig, t, g=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N or i + len(sig) <= 0: return
    if i < 0: sig = sig[-i:]; i = 0
    s = sig[:N - i] * g
    L[i:i + len(s)] += s * (1 - max(pan, 0)); R[i:i + len(s)] += s * (1 + min(pan, 0))

def env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / max(a, 1e-4), 1) * np.exp(-t / d)

def lp(x, a):
    from scipy.signal import lfilter
    return lfilter([a], [1, a - 1], x)

def hp(x, a): return x - lp(x, a)

def kick(g=1.0):
    n = int(.5 * SR); t = np.arange(n) / SR
    f = 42 + 130 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * env(n, .002, .2) + .3 * np.tanh(5 * np.sin(ph)) * env(n, .001, .025)) * g

def snare():
    n = int(.3 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * env(n, .001, .05)
    nz = hp(rng.standard_normal(n), .3) * env(n, .001, .09)
    return body * .6 + nz * .7

def hat(o=False):
    n = int((.22 if o else .05) * SR)
    return hp(rng.standard_normal(n), .5) * env(n, .001, .08 if o else .012)

def impact(len_=3.0):
    n = int(len_ * SR); t = np.arange(n) / SR
    boom = np.tanh(2.2 * np.sin(2 * np.pi * (32 + 70 * np.exp(-t * 7)) * t)) * env(n, .002, .8)
    crash = lp(rng.standard_normal(n), .3) * env(n, .001, .5)
    return boom + .45 * crash

def riser(length, top=.6):
    n = int(length * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n)
    y = np.zeros(n); acc = 0.0; a = .01 + top * (t / length) ** 2
    from scipy.signal import lfilter
    # time-varying lowpass via chunks
    out = np.zeros(n); zi = np.zeros(1); ch = 480
    for s in range(0, n, ch):
        aa = a[min(s, n - 1)]
        out[s:s + ch], zi = lfilter([aa], [1, aa - 1], x[s:s + ch], zi=zi)
    tone = np.sin(2 * np.pi * np.cumsum(200 + 1400 * (t / length) ** 2) / SR) * .25
    return (out + tone) * (t / length) ** 2.4

def whoosh(length=.5, up=True):
    n = int(length * SR); t = np.arange(n) / SR
    x = lp(rng.standard_normal(n), .15)
    e = np.sin(np.pi * t / length) ** 2
    return x * e

def reverse_cymbal(length=1.0):
    n = int(length * SR)
    c = hp(rng.standard_normal(n), .2) * env(n, .001, length / 3)
    return c[::-1]

def saw(f, t): return 2 * ((f * t) % 1) - 1

def pad(t0, t1, freqs, g, cutoff=.03):
    n = int((t1 - t0) * SR); t = np.arange(n) / SR
    s = sum(saw(f * (1 + d), t) for f in freqs for d in (-.003, .003)) / (2 * len(freqs))
    s = lp(s, cutoff)
    fade = np.minimum(np.minimum(t / .4, 1), np.minimum((t1 - t0 - t) / .5, 1))
    add(s * fade, t0, g, .0)

def bassnote(t, f, length):
    n = int(length * SR); tt = np.arange(n) / SR
    s = lp(np.tanh(3 * saw(f, tt)), .08) * env(n, .003, length * .7)
    add(s, t, .5)

def tick(f=2400, g=.3, t0=0, pan=0):
    n = int(.03 * SR); tt = np.arange(n) / SR
    add(np.sin(2 * np.pi * f * tt) * env(n, .0005, .006), t0, g, pan)

# ---------- HOOK: tension (0 -> FLIP) ----------
pad(0, FLIP + .1, (110, 130.8, 164.8), .5, .02)         # dark Am drone
for k in range(int(FLIP / BEAT) + 1):                    # heartbeat, accelerating into flip
    tt = FLIP - (k + 1) * BEAT
    if tt > .2: add(lp(kick(), .25), tt, .7)
add(riser(FLIP - .2, .7), .2, .55)
add(reverse_cymbal(1.1), FLIP - 1.1, .5)
add(whoosh(.6), C['hook2a'][0] - .1, .7, .2)

# ---------- DROP at FLIP ----------
add(impact(3.2), FLIP, 1.1)
for k in range(10): tick(3000 - k * 120, .25, FLIP + .1 + k * .06, (-.5 if k % 2 else .5))  # counter ticks

# ---------- GROOVE: FLIP -> END ----------
prog = [(55.0, (220, 261.6, 329.6)), (43.65, (174.6, 220, 261.6)), (65.41, (196, 261.6, 329.6)), (49.0, (196, 246.9, 293.7))]
bar_len = 4 * BEAT
t = FLIP; bar = 0
while t < END - .4:
    root, ch = prog[bar % 4]
    pad(t, min(t + bar_len, END), ch, .28, .05)
    for b in range(4):
        tb = t + b * BEAT
        if tb >= END - .3: break
        add(kick(), tb, .95)
        if b % 2: add(snare(), tb, .55)
        add(hat(), tb + BEAT / 2, .3, .3)
        add(hat(), tb + BEAT / 4, .1, -.3); add(hat(), tb + 3 * BEAT / 4, .12, -.3)
        bassnote(tb, root, BEAT * .45); bassnote(tb + BEAT / 2, root * 2, BEAT * .3)
    t += bar_len; bar += 1

# ---------- PROCESS transitions ----------
add(whoosh(.7), PROC - .35, .9)
for s in STEPS[1:]:
    add(whoosh(.45), s - .3, .8, .3)
    add(impact(1.2), s - .15, .3)
for k in range(4): tick(1600 + k * 200, .45, STEPS[0] - .18 + .35 + k * .22)  # chips pop
for k in range(4): tick(1300, .4, STEPS[3] - .03 + k * .12)                   # pages land

# ---------- CTA ----------
add(riser(1.0, .5), CTA - 1.0, .4)
add(impact(3.0), CTA, 1.0)
add(impact(2.0), C['cta2'][0] + 1.1, .5)         # button slam
if 'cta3' in C: add(whoosh(.4), C['cta3'][0] - .15, .6, -.3); tick(2600, .5, C['cta3'][0])
pad(C['cta2'][0], END, (220, 329.6, 440, 554.4), .25, .06)

# ---------- mix: music bus ducked under VO ----------
music = np.stack([L, R], 1)
music /= np.max(np.abs(music)) + 1e-9
music = np.tanh(1.6 * music) / np.tanh(1.6)
v = np.zeros(N); v[:min(N, len(vo))] = vo[:N]
venv = lp(np.abs(v), .002); venv /= venv.max() + 1e-9
duck = 1 - .55 * np.clip(venv * 3, 0, 1)
mix = music * duck[:, None] * .55 + v[:, None] * .95
fade = np.ones(N); fl = int(.5 * SR); fade[-fl:] = np.linspace(1, 0, fl)
mix *= fade[:, None]
mix /= np.max(np.abs(mix)) + 1e-9
mix *= .93
with wave.open(sys.argv[3], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
print('ok', END, FLIP)
