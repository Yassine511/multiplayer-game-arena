"""Pixel-station UI kit: palette, pixel text, framed panels, buttons, inputs.

The look follows the map art: deep indigo space, navy hull plates, bright cyan
room frames with clipped corners, teal corridor plates, amber hazard accents.
Everything is drawn at half resolution without anti-aliasing and doubled, so
the widgets sit on the same chunky pixel grid as the art.
"""
import math
import random

import pygame

from client import pixfont

# --- palette (sampled from the map) -------------------------------------------------------
SPACE = (22, 10, 66)
INK = (8, 10, 30)
HULL = (26, 24, 70)
HULL_HI = (64, 74, 116)
PANEL = (16, 18, 54)
PANEL_HI = (36, 46, 104)
FIELD = (9, 11, 36)
CYAN = (92, 220, 236)
TEAL = (48, 168, 176)
TEAL_DK = (24, 98, 116)
ICE = (218, 246, 252)
MUTED = (140, 152, 204)
GOOD = (104, 232, 150)
BAD = (250, 96, 104)
WARN = (250, 190, 70)
ORANGE = (236, 128, 56)
GREY = (110, 114, 140)

# names the screens use
BG = SPACE
TEXT = ICE
ACCENT = CYAN
BORDER = TEAL

BTN_PRIMARY = TEAL
BTN_GO = (58, 170, 104)
BTN_DANGER = (196, 70, 86)
BTN_QUIET = (70, 80, 140)

PX = 2                      # widget pixel size

_text_cache = {}
_surf_cache = {}


def shade(c, f):
    """Lighter (f > 1) or darker (f < 1) version of a colour."""
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# --- text ---------------------------------------------------------------------------------
def render(s, size=20, color=TEXT, bold=False, shadow=True):
    """Text as a hard-edged pixel surface in the built-in bitmap font (client/pixfont.py)."""
    key = (s, size, color, bold, shadow)
    img = _text_cache.get(key)
    if img is None:
        img = pixfont.render(s or " ", size, color, bold, shadow, INK).convert_alpha()
        if len(_text_cache) > 900:
            _text_cache.clear()
        _text_cache[key] = img
    return img


def text(surf, s, pos, size=20, color=TEXT, bold=False, anchor="topleft", shadow=True, alpha=None):
    img = render(str(s), size, color, bold, shadow)
    rect = img.get_rect(**{anchor: pos})
    # Centre on the capital letters, not on the whole surface: the surface also holds
    # an empty row above, the descender rows and the shadow, which would pull it off.
    k = pixfont.scale_for(size)
    if anchor in ("center", "midleft", "midright"):
        rect.y += k
    if anchor in ("center", "midtop", "midbottom"):
        rect.x += k // 2
    if alpha is not None and alpha < 255:
        img = img.copy()
        img.set_alpha(max(0, int(alpha)))
    surf.blit(img, rect)
    return rect


def text_width(s, size, bold=False):
    return pixfont.width(s, size, bold)


def wrap(s, size, width, bold=False):
    """Split into lines no wider than `width`; a word too long for one line (a link,
    a join string) is broken between characters instead of running past the edge."""
    lines, line = [], ""
    for word in str(s).split():
        if text_width(word, size, bold) > width and "/" in word:   # links: break after a slash
            parts = word.replace("/", "/ ").split()
            lines_w = wrap(" ".join(parts), size, width, bold)
            joined = [l.replace("/ ", "/") for l in lines_w]
            if line:
                lines.append(line)
            lines.extend(joined[:-1])
            line = joined[-1] if joined else ""
            continue
        trial = (line + " " + word).strip()
        if text_width(trial, size, bold) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        while text_width(line, size, bold) > width and len(line) > 1:
            cut = len(line) - 1
            while cut > 1 and text_width(line[:cut], size, bold) > width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line:
        lines.append(line)
    return lines


def fit(s, size, width, bold=False):
    """Shorten with '..' until it fits."""
    s = str(s)
    if text_width(s, size, bold) <= width:
        return s
    while len(s) > 1 and text_width(s + "..", size, bold) > width:
        s = s[:-1]
    return s + ".."


# --- shapes -------------------------------------------------------------------------------
def _chamfer(w, h, c, inset=0):
    """Rectangle with clipped corners, like the room frames on the map."""
    x0, y0, x1, y1 = inset, inset, w - 1 - inset, h - 1 - inset
    c = max(0, min(c, (x1 - x0) // 2, (y1 - y0) // 2))
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c),
            (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]


def _cached(key, build):
    s = _surf_cache.get(key)
    if s is None:
        if len(_surf_cache) > 500:
            _surf_cache.clear()
        s = _surf_cache[key] = build()
    return s


def panel(surf, rect, color=PANEL, radius=10, border=CYAN, alpha=236, rivets=True):
    """Station-frame panel: ink outline, bright frame, dark inner line, navy fill.

    `radius` is the corner clip in screen px. `border=None` gives a plain plate.
    """
    rect = pygame.Rect(rect)
    w, h = max(4, rect.w // PX), max(4, rect.h // PX)
    cut = max(1, radius // PX)

    def build():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(s, INK, _chamfer(w, h, cut))
        if border:
            pygame.draw.polygon(s, border, _chamfer(w, h, cut, 1))
            pygame.draw.polygon(s, shade(border, 0.45), _chamfer(w, h, cut, 3))
            pygame.draw.polygon(s, (*color, alpha), _chamfer(w, h, cut, 4))
            inner = 4
        else:
            pygame.draw.polygon(s, (*color, alpha), _chamfer(w, h, cut, 1))
            inner = 1
        if rivets and border and w > 40 and h > 30:
            for px, py in ((inner + 3, inner + 3), (w - inner - 4, inner + 3),
                           (inner + 3, h - inner - 4), (w - inner - 4, h - inner - 4)):
                s.set_at((px, py), (*shade(border, 0.7), 255))
        return pygame.transform.scale(s, (w * PX, h * PX)).convert_alpha()

    surf.blit(_cached(("panel", w, h, color, cut, border, alpha, rivets), build), rect.topleft)


def plate(surf, rect, color=PANEL, alpha=225, cut=4):
    """Small dark backing for labels on top of the map."""
    panel(surf, rect, color, cut, None, alpha, rivets=False)


def hazard(surf, rect, a=WARN, b=INK):
    """Yellow / black warning stripes, as on the station doors."""
    rect = pygame.Rect(rect)
    w, h = max(1, rect.w // PX), max(1, rect.h // PX)

    def build():
        s = pygame.Surface((w, h))
        for x in range(w):
            for y in range(h):
                s.set_at((x, y), a if ((x + y) // 3) % 2 == 0 else b)
        return pygame.transform.scale(s, (w * PX, h * PX)).convert()

    surf.blit(_cached(("hazard", w, h, a, b), build), rect.topleft)


def stitch(surf, x0, x1, y, color=TEAL_DK, dash=8, gap=6, thick=2):
    """Dashed seam line, as on the corridor plates."""
    x = x0
    while x < x1:
        pygame.draw.rect(surf, color, (x, y, min(dash, x1 - x), thick))
        x += dash + gap


def heading(surf, label, pos, width, color=CYAN, size=16):
    """Section heading with a seam line running to the right edge."""
    r = text(surf, label, pos, size, color, bold=True)
    stitch(surf, r.right + 10, pos[0] + width, r.centery, shade(color, 0.5))
    return r


def keycap(surf, label, pos, anchor="topleft", size=14):
    """A keyboard key: [E], [1] ..."""
    tw = text_width(label, size, True)
    r = pygame.Rect(0, 0, max(26, tw + 14), 26)
    setattr(r, anchor, pos)
    pygame.draw.rect(surf, INK, r)
    pygame.draw.rect(surf, shade(ICE, 0.62), r.inflate(-4, -4))
    pygame.draw.rect(surf, ICE, (r.x + 2, r.y + 2, r.w - 4, r.h - 8))
    text(surf, label, (r.centerx, r.y + 2 + (r.h - 8) // 2), size, INK, bold=True, anchor="center", shadow=False)
    return r


def chip(surf, color, pos, size=12):
    """Square colour swatch for a player."""
    r = pygame.Rect(0, 0, size, size)
    r.center = pos
    pygame.draw.rect(surf, INK, r.inflate(4, 4))
    pygame.draw.rect(surf, color, r)
    pygame.draw.rect(surf, shade(color, 1.35), (r.x, r.y, size, max(2, size // 4)))
    return r


def dim(surf, alpha=150, color=(10, 6, 40)):
    if alpha <= 0:
        return
    key = ("dim", surf.get_size(), color)

    def build():
        s = pygame.Surface(surf.get_size()).convert()
        s.fill(color)
        return s

    veil = _cached(key, build)
    veil.set_alpha(min(255, int(alpha)))       # one opaque surface, blended with a surface alpha
    surf.blit(veil, (0, 0))


# --- widgets ------------------------------------------------------------------------------
class Button:
    def __init__(self, rect, label, on_click, color=BTN_PRIMARY, size=18, enabled=True):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.color = color
        self.size = size
        self.enabled = enabled
        self.hover = False

    def handle(self, e):
        if e.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.enabled:
            if self.rect.collidepoint(e.pos):
                self.on_click()
                return True
        return False

    def draw(self, surf):
        lit = self.hover and self.enabled
        base = self.color if self.enabled else (58, 62, 98)
        if lit:
            base = shade(base, 1.22)
        w, h = self.rect.w // PX, self.rect.h // PX

        def build():
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.polygon(s, INK, _chamfer(w, h, 3))
            pygame.draw.polygon(s, shade(base, 0.58), _chamfer(w, h, 3, 1))          # bottom lip
            pygame.draw.polygon(s, base, [(x, min(y, h - 5)) for x, y in _chamfer(w, h, 3, 1)])
            pygame.draw.line(s, shade(base, 1.45), (4, 1), (w - 5, 1))                 # top light
            for x in range(6, w - 6, 5):                                               # corridor seam
                s.set_at((x, h - 7), shade(base, 0.72))
                s.set_at((x + 1, h - 7), shade(base, 0.72))
            return pygame.transform.scale(s, (w * PX, h * PX)).convert_alpha()

        surf.blit(_cached(("btn", w, h, base), build), self.rect.topleft)
        text(surf, self.label, (self.rect.centerx, self.rect.centery - 4), self.size,
             ICE if self.enabled else MUTED, bold=True, anchor="center")


def clipboard_text():
    """Text on the system clipboard (or the path of a file copied in Explorer), "" if none."""
    from client.osutil import clipboard_text as read
    return read()


class TextInput:
    def __init__(self, rect, placeholder="", secret=False, max_len=32, allowed=None, label=None):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.secret = secret
        self.max_len = max_len
        self.allowed = allowed
        self.label = label
        self.value = ""
        self.focused = False

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.focused = self.rect.collidepoint(e.pos)
            return self.focused
        if e.type == pygame.KEYDOWN and self.focused:
            if e.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return True
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB, pygame.K_ESCAPE):
                return False
            if e.key == pygame.K_v and e.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
                for ch in " ".join(clipboard_text().split()):
                    if len(self.value) >= self.max_len:
                        break
                    if self.allowed is None or ch in self.allowed:
                        self.value += ch
                return True
            if e.key == pygame.K_BACKSPACE and e.mod & pygame.KMOD_CTRL:
                self.value = ""
                return True
            ch = e.unicode
            if ch and ch.isprintable() and len(self.value) < self.max_len:
                if self.allowed is None or ch in self.allowed:
                    self.value += ch
                return True
        return False

    def draw(self, surf):
        r = self.rect
        if self.label:
            text(surf, self.label, (r.x + 2, r.y - 22), 14, CYAN if self.focused else MUTED, bold=True)
        panel(surf, r, FIELD, 6, CYAN if self.focused else TEAL_DK, 255, rivets=False)
        size = 20
        shown = ("*" * len(self.value)) if self.secret else self.value
        room = r.w - 40
        while shown and text_width(shown, size) > room:      # keep the end visible
            shown = shown[1:]
        x = r.x + 16
        if shown:
            tr = text(surf, shown, (x, r.centery), size, ICE, anchor="midleft")
            x = tr.right
        elif not self.focused:
            text(surf, self.placeholder, (x, r.centery), size, shade(MUTED, 0.7), anchor="midleft", shadow=False)
        if self.focused and (pygame.time.get_ticks() // 450) % 2 == 0:
            pygame.draw.rect(surf, CYAN, (x + 4, r.centery - 8, 10, 16))


class Toasts:
    """Short messages that fade after a few seconds."""

    def __init__(self):
        self.items = []

    def add(self, msg, color=TEXT, seconds=3.0):
        self.items.append([msg, color, seconds, seconds])
        self.items = self.items[-4:]

    def update(self, dt):
        for it in self.items:
            it[2] -= dt
        self.items = [it for it in self.items if it[2] > 0]

    def draw(self, surf, center_x, y):
        for msg, color, left, total in self.items:
            age = total - left
            slide = int(max(0.0, 1 - age / 0.15) * -14)            # drop in from above
            w = text_width(msg, 18, True) + 44
            bg = pygame.Rect(0, 0, w, 40)
            bg.midtop = (center_x, y + slide)
            panel(surf, bg, PANEL, 8, color, 240, rivets=False)
            text(surf, msg, (bg.centerx, bg.centery), 18, color, bold=True, anchor="center")
            y += bg.height + 6


# --- animated backdrop ----------------------------------------------------------------------
_ROCK_COLS = [((58, 132, 196), (96, 178, 226), (30, 74, 138)),
              ((70, 150, 210), (120, 200, 236), (36, 84, 150)),
              ((48, 110, 176), (84, 160, 214), (26, 62, 120))]


def _rock_sprite(rng, size):
    """A chunky pixel asteroid in the palette of the login art (drawn at half res, doubled)."""
    n = max(3, size // PX)
    s = pygame.Surface((n + 2, n + 2), pygame.SRCALPHA)
    base, hi, lo = rng.choice(_ROCK_COLS)
    c = (n + 1) / 2
    # lumpy outline: radius varies with angle
    lumps = [0.78 + rng.random() * 0.3 for _ in range(7)]
    for y in range(n + 2):
        for x in range(n + 2):
            dx, dy = x - c, (y - c) * 1.15
            d = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) + math.pi) / (2 * math.pi) * 7
            i = int(ang) % 7
            f = ang - int(ang)
            r = (lumps[i] * (1 - f) + lumps[(i + 1) % 7] * f) * n / 2
            if d <= r:
                col = base
                if dx + dy < -r * 0.35:
                    col = hi
                elif dx + dy > r * 0.55:
                    col = lo
                s.set_at((x, y), col)
    # a crater or two
    for _ in range(rng.randint(1, 2)):
        cx, cy = rng.randint(2, max(2, n - 2)), rng.randint(2, max(2, n - 2))
        if s.get_at((cx, cy)).a and s.get_at((cx + 1, cy)).a:
            s.set_at((cx, cy), lo)
            s.set_at((cx + 1, cy), lo)
    out = pygame.Surface(((n + 4), (n + 4)), pygame.SRCALPHA)
    ink = pygame.mask.from_surface(s).to_surface(setcolor=(*INK, 200), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(ink, (dx + 0, dy + 0))
    out.blit(s, (1, 1))
    return pygame.transform.scale(out, (out.get_width() * PX, out.get_height() * PX)).convert_alpha()


class Backdrop:
    """A full-screen painting with twinkling stars and, optionally, drifting asteroids.

    The painting itself stays still: panning a large image by a couple of pixels a
    second can only move in whole-pixel jumps, which reads as stutter. Motion comes
    from small sprites moving at a steady, clearly visible speed instead.
    """

    def __init__(self, image, size, stars=34, star_band=0.6, tint=None, seed=7, rocks=0, rock_band=(0.2, 0.5)):
        self.size = size
        w, h = size
        self.img = pygame.Surface(size).convert()
        if image is not None:
            iw, ih = image.get_size()
            if iw >= w and ih >= h:                   # big enough: crop, every pixel stays crisp
                big = image
            else:
                k = max(w / iw, h / ih)
                big = pygame.transform.scale(image, (int(iw * k + 0.999), int(ih * k + 0.999)))
            self.img.blit(big, ((w - big.get_width()) // 2, (h - big.get_height()) // 2))
        else:
            self.img.fill(SPACE)
        if tint:                                      # baked once instead of blended every frame
            veil = pygame.Surface(size, pygame.SRCALPHA)
            veil.fill(tint)
            self.img.blit(veil, (0, 0))
        rng = random.Random(seed)
        self.stars = [(rng.randrange(w), rng.randrange(int(h * star_band)), rng.random() * 6.28,
                       0.6 + rng.random() * 1.6, rng.choice((2, 2, 2, 4))) for _ in range(stars)]
        self.rocks = []
        y0, y1 = int(h * rock_band[0]), int(h * rock_band[1])
        for i in range(rocks):
            size_px = rng.choice((16, 20, 24, 28, 32, 38, 44))
            spr = _rock_sprite(rng, size_px)
            depth = size_px / 44                       # bigger rocks are nearer, so faster
            speed = 20 + 45 * depth + rng.random() * 10
            self.rocks.append({
                "img": spr, "x": rng.uniform(-60, w + 60), "y": rng.uniform(y0, y1),
                "vx": -speed, "vy": rng.uniform(-3, 3), "bob": rng.random() * 6.28,
                "y0": y0, "y1": y1,
            })
        self.rocks.sort(key=lambda r: r["img"].get_width())
        self._last = None

    def draw(self, surf):
        now = pygame.time.get_ticks() / 1000
        dt = 0.0 if self._last is None else min(0.1, now - self._last)
        self._last = now
        surf.blit(self.img, (0, 0))
        w = self.size[0]
        for r in self.rocks:
            r["x"] += r["vx"] * dt
            r["y"] += r["vy"] * dt
            rw = r["img"].get_width()
            if r["x"] < -rw - 10:
                r["x"] += w + rw + 40
            if r["y"] < r["y0"] or r["y"] > r["y1"]:
                r["vy"] = -r["vy"]
            surf.blit(r["img"], (round(r["x"]), round(r["y"] + math.sin(now * 0.8 + r["bob"]) * 2)))
        for x, y, ph, sp, sz in self.stars:
            a = math.sin(now * sp + ph)
            if a > 0.25:
                c = ICE if a > 0.8 else (150, 170, 240)
                surf.fill(c, (x, y, sz, sz))
                if a > 0.8:                                   # four-point sparkle, like the art
                    for dx, dy in ((-sz, 0), (sz, 0), (0, -sz), (0, sz)):
                        surf.fill((150, 170, 240), (x + dx, y + dy, sz, sz))
