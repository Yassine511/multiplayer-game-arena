"""Tiny synthesized sound effects for the ultimates (no audio files to ship).

Everything is built from sine waves and noise at start-up. If the machine has no
audio device the mixer fails to open and every play() quietly does nothing.
"""
import array
import math
import random

import pygame

RATE = 22050


def _env(i, n, attack=0.01, release=0.3):
    t = i / RATE
    a = min(1.0, t / attack) if attack > 0 else 1.0
    r = min(1.0, (n - i) / (RATE * release)) if release > 0 else 1.0
    return a * r


def _tone(secs, f0, f1=None, vol=0.5, wave="sine", attack=0.01, release=0.2, vib=0.0):
    n = int(RATE * secs)
    f1 = f0 if f1 is None else f1
    out, ph = [], 0.0
    for i in range(n):
        f = f0 + (f1 - f0) * i / n
        f *= 1 + vib * math.sin(i / RATE * 2 * math.pi * 7)
        ph += 2 * math.pi * f / RATE
        if wave == "square":
            s = 1.0 if math.sin(ph) >= 0 else -1.0
        elif wave == "saw":
            s = (ph / math.pi) % 2 - 1
        else:
            s = math.sin(ph)
        out.append(s * vol * _env(i, n, attack, release))
    return out


def _noise(secs, vol=0.6, attack=0.002, release=None, lowpass=0.0, seed=1):
    rng = random.Random(seed)
    n = int(RATE * secs)
    release = secs if release is None else release
    out, last = [], 0.0
    for i in range(n):
        s = rng.uniform(-1, 1)
        last = last * lowpass + s * (1 - lowpass)
        out.append(last * vol * _env(i, n, attack, release))
    return out


def _mix(*parts, offsets=None):
    offsets = offsets or [0.0] * len(parts)
    n = max(int(o * RATE) + len(p) for p, o in zip(parts, offsets))
    out = [0.0] * n
    for p, o in zip(parts, offsets):
        k = int(o * RATE)
        for i, s in enumerate(p):
            out[k + i] += s
    return out


RECIPES = {
    "boom": lambda: _mix(_noise(1.4, 0.9, release=1.3, lowpass=0.93, seed=3), _tone(0.9, 90, 30, 0.7, release=0.8)),
    "charge": lambda: _tone(1.6, 160, 900, 0.32, "saw", attack=0.3, release=0.15, vib=0.03),
    "beam": lambda: _mix(_noise(1.2, 0.45, release=0.6, lowpass=0.6, seed=5), _tone(1.2, 220, 180, 0.35, "square", release=0.6)),
    "slash": lambda: _mix(_noise(0.18, 0.7, release=0.16, lowpass=0.1, seed=7), _tone(0.18, 2400, 600, 0.2, release=0.15)),
    "void": lambda: _mix(_tone(2.4, 55, 50, 0.4, attack=0.6, release=1.0, vib=0.02),
                         _tone(2.4, 82.5, 80, 0.25, attack=0.8, release=1.0)),
    "cash": lambda: _mix(_tone(0.12, 1760, vol=0.3, release=0.1), _tone(0.3, 2637, vol=0.3, release=0.28),
                         offsets=[0, 0.08]),
    "blip": lambda: _tone(0.07, 880, 1320, 0.25, "square", release=0.04),
    "whoosh": lambda: _noise(0.6, 0.5, attack=0.25, release=0.35, lowpass=0.85, seed=9),
    "alarm": lambda: _mix(_tone(0.25, 660, vol=0.25, wave="square", release=0.05),
                          _tone(0.25, 880, vol=0.25, wave="square", release=0.05), offsets=[0, 0.28]),
    "drop": lambda: _tone(1.0, 1400, 300, 0.25, release=0.1),
    "hit": lambda: _mix(_noise(0.35, 0.8, release=0.3, lowpass=0.8, seed=11), _tone(0.3, 140, 60, 0.5, release=0.25)),
}


class Sfx:
    def __init__(self):
        self.sounds = {}
        self.ok = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 2, 512)
            freq, _fmt, channels = pygame.mixer.get_init()
            self.channels = channels
            self.freq = freq
            self.ok = True
        except Exception:
            return
        import threading                          # synthesize in the background: no hitch on first use
        threading.Thread(target=self._prebuild, name="sfx", daemon=True).start()

    def _prebuild(self):
        for name in RECIPES:
            try:
                if name not in self.sounds:
                    self.sounds[name] = self._build(name)
            except Exception:
                self.ok = False
                return

    def _build(self, name):
        samples = RECIPES[name]()
        if self.freq != RATE:                     # resample (nearest) to whatever the device opened at
            k = RATE / self.freq
            samples = [samples[min(len(samples) - 1, int(i * k))] for i in range(int(len(samples) / k))]
        a = array.array("h")
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 30000)
            for _ in range(self.channels):
                a.append(v)
        return pygame.mixer.Sound(buffer=a.tobytes())

    def play(self, name, volume=0.8):
        if not self.ok or name not in RECIPES:
            return
        try:
            snd = self.sounds.get(name)
            if snd is None:
                snd = self.sounds[name] = self._build(name)
            snd.set_volume(volume)
            snd.play()
        except Exception:
            self.ok = False
