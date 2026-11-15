"""Ultimate cutscenes: one short, fully procedural scene per character.

A player who answers config.ULT_STREAK questions in a row can fire their ultimate:
everybody else loses config.ULT_DAMAGE points and every screen in the room
(players and the spectating host) plays the caster's scene. Nothing here is
an image file: every frame is drawn with pygame shapes and the pixel font, and
the sounds come from client/sfx.py.

The game keeps running underneath (the network is polled every frame as usual);
a scene only covers the screen for about four seconds.
"""
import math
import random

import pygame

from common import characters as CH
from client import ui
from client.assets import color_of
from client.screens.base import CANVAS_H, CANVAS_W

W, H = CANVAS_W, CANVAS_H
CX, CY = W // 2, H // 2

CLAUDE_ORANGE = (217, 119, 87)
CLAUDE_CREAM = (240, 238, 230)
CLAUDE_DARK = (31, 30, 29)
BLOOD = (170, 16, 30)
NV_GREEN = (110, 255, 140)


# --- small helpers ---------------------------------------------------------------------------
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def seg(t, a, b):
    """0 before a, 1 after b, linear in between."""
    return clamp((t - a) / (b - a)) if b > a else float(t >= a)


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_in(x):
    return x ** 3


def lerp(a, b, k):
    return a + (b - a) * k


_fills = {}


def wash(surf, color, alpha):
    """Full-screen translucent colour (one cached surface per colour, alpha set per frame)."""
    if alpha <= 0:
        return
    s = _fills.get(color)
    if s is None:
        s = _fills[color] = pygame.Surface((W, H)).convert()
        s.fill(color)
    s.set_alpha(int(clamp(alpha, 0, 255)))
    surf.blit(s, (0, 0))


def glow(surf, color, center, radius, alpha=90, rings=4):
    """Soft additive-looking glow: a few translucent discs."""
    if radius < 1:
        return
    r = int(radius)
    s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    for i in range(rings, 0, -1):
        rr = int(r * i / rings)
        pygame.draw.circle(s, (*color, int(alpha / rings)), (r + 1, r + 1), rr)
    surf.blit(s, (center[0] - r - 1, center[1] - r - 1))


def big_text(surf, s, pos, size, color, anchor="center", alpha=None, aberration=0):
    """Pixel text, optionally with a red/cyan chromatic split."""
    if aberration:
        ui.text(surf, s, (pos[0] - aberration, pos[1]), size, (255, 40, 80), bold=True, anchor=anchor, shadow=False,
                alpha=alpha)
        ui.text(surf, s, (pos[0] + aberration, pos[1]), size, (40, 220, 255), bold=True, anchor=anchor, shadow=False,
                alpha=alpha)
    return ui.text(surf, s, pos, size, color, bold=True, anchor=anchor, alpha=alpha)


def pop(t, at, dur=0.18):
    """Scale-in factor for a title that lands at time `at` (overshoots a little)."""
    k = seg(t, at, at + dur)
    if k <= 0:
        return 0.0
    return lerp(1.7, 1.0, ease_out(k))          # slams in from big to its size


def stamp_text(surf, s, center, size, color, scale=1.0, angle=0.0):
    img = ui.render(s, size, color, True, True)
    if scale != 1.0:
        img = pygame.transform.scale(img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))
    if angle:
        img = pygame.transform.rotate(img, angle)
    surf.blit(img, img.get_rect(center=center))


def letterbox(surf, k, h=64):
    hh = int(h * ease_out(k))
    if hh > 0:
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, W, hh))
        pygame.draw.rect(surf, (0, 0, 0), (0, H - hh, W, hh))


# --- the context a scene gets -------------------------------------------------------------------
class Ctx:
    def __init__(self, app, m, me_id, players):
        self.app = app
        self.assets = app.assets
        self.sfx = app.sfx
        self.caster_id = m.get("player_id")
        self.name = str(m.get("name") or "?")
        self.character = m.get("character")
        self.slug = CH.CHARACTERS[self.character]["slug"] if CH.valid(self.character) else ""
        self.color = color_of(m.get("color"))
        self.damage = m.get("damage", 10)
        self.victims = list(m.get("victims") or [])
        self.me_id = me_id
        self.players = players or {}
        self.mine = self.caster_id == me_id
        self.seed = hash((self.caster_id, self.name, len(self.victims))) & 0xFFFF

    def victim_character(self, v):
        p = self.players.get(v["id"])
        return p.get("character") if p else None


# --- base scene ------------------------------------------------------------------------------------
class Scene:
    duration = 3.9
    end_card_at = 2.9           # common damage card from here on (None = the scene shows it itself)
    cues = ()                   # (seconds, sound name)

    def __init__(self, ctx):
        self.ctx = ctx
        self.t = 0.0
        self.rng = random.Random(ctx.seed)
        self._fired = set()
        self.setup()

    def setup(self):
        pass

    def update(self, dt):
        self.t += dt
        for i, (at, name) in enumerate(self.cues):
            if i not in self._fired and self.t >= at:
                self._fired.add(i)
                self.ctx.sfx.play(name)

    @property
    def done(self):
        return self.t >= self.duration

    def shake(self):
        return 0, 0

    def render(self, s):
        raise NotImplementedError

    # caster portrait
    def caster(self, s, x, y, height, direction="down", moving=False):
        return self.ctx.assets.draw_character(s, x, y, self.ctx.character, height, direction, moving, True,
                                              0, None)


# --- Gojo: Domain Expansion - Infinite Void ------------------------------------------------------------
class InfiniteVoid(Scene):
    duration = 4.0
    end_card_at = 3.0
    cues = ((0.0, "whoosh"), (0.45, "void"), (1.25, "hit"))
    WORDS = ["SEE", "FEEL", "KNOW", "EVERYTHING", "SYN", "ACK", "INFINITY", "1011010", "TTL", "FOREVER",
             "NEVER ENDING", "TCP/IP", "ALL AT ONCE", "0xFFFF", "WHY", "NOTHING"]

    def setup(self):
        r = self.rng
        self.stars = [(r.uniform(0, math.tau), r.uniform(0.15, 1.0), r.uniform(0, 1), r.choice(
            [(255, 255, 255), (160, 220, 255), (190, 140, 255), (120, 160, 255)])) for _ in range(260)]
        self.frags = [(r.choice(self.WORDS), r.randrange(40, W - 40), r.randrange(70, H - 70), r.uniform(0, 3))
                      for _ in range(40)]

    def render(self, s):
        t = self.t
        s.fill((4, 2, 12))
        if t < 0.55:                                    # the domain closes over everything
            k = ease_in(seg(t, 0.05, 0.55))
            s.fill((20, 14, 60))
            pygame.draw.circle(s, (4, 2, 12), (CX, CY), int(k * 820))
            pygame.draw.circle(s, (150, 120, 255), (CX, CY), int(k * 820), 6)
        # warp streaks pouring out of the centre
        speed = 0.35 + 1.6 * seg(t, 0.5, 1.4)
        maxr = 760
        for ang, sp, off, col in self.stars:
            d = ((off + t * sp * speed) % 1.0)
            r0 = d * d * maxr
            r1 = r0 + 8 + 90 * d * sp * speed
            x0, y0 = CX + math.cos(ang) * r0, CY + math.sin(ang) * r0 * 0.75
            x1, y1 = CX + math.cos(ang) * r1, CY + math.sin(ang) * r1 * 0.75
            pygame.draw.line(s, ui.mix((10, 6, 30), col, clamp(d * 1.6)), (x0, y0), (x1, y1), 2 if d > 0.5 else 1)
        # galaxy rings
        for i in range(7):
            ph = (t * 0.6 + i / 7) % 1.0
            rr = int(40 + ph * 640)
            col = ui.mix((140, 80, 255), (40, 160, 255), i / 6)
            ring = pygame.Rect(0, 0, rr * 2, int(rr * 1.2))
            ring.center = (CX, CY)
            pygame.draw.ellipse(s, ui.mix((4, 2, 12), col, 0.5 * (1 - ph)), ring, 2)
        # information overload
        for word, x, y, ph in self.frags:
            a = 0.5 + 0.5 * math.sin(t * 9 + ph * 7)
            if a > 0.55 and t > 0.6:
                ui.text(s, word, (x, y), 14, ui.mix((4, 2, 12), (120, 200, 255), a * 0.7), bold=True, anchor="center",
                        shadow=False)
        # the eye
        open_k = ease_out(seg(t, 0.8, 1.2))
        if open_k > 0:
            glow(s, (120, 170, 255), (CX, CY - 10), 190 + 20 * math.sin(t * 5), 90)
            eh = max(2, int(130 * open_k))
            eye = pygame.Rect(0, 0, 330, eh)
            eye.center = (CX, CY - 10)
            pygame.draw.ellipse(s, (236, 244, 255), eye)
            clip = s.get_clip()
            s.set_clip(eye)
            ix = CX + int(math.sin(t * 2.3) * 22)
            pygame.draw.circle(s, (30, 120, 255), (ix, CY - 10), 56)
            pygame.draw.circle(s, (110, 220, 255), (ix, CY - 10), 56, 8)
            pygame.draw.circle(s, (160, 240, 255), (ix, CY - 10), 40, 2)
            pygame.draw.circle(s, (6, 10, 40), (ix, CY - 10), 20)
            pygame.draw.circle(s, (255, 255, 255), (ix - 16, CY - 28), 9)
            s.set_clip(clip)
            pygame.draw.ellipse(s, (20, 30, 90), eye, 4)
        # caster, small and calm under it all
        if t > 0.55:
            self.caster(s, CX, H - 30, 170)
        # titles
        if t > 0.25:
            a = 255 * seg(t, 0.25, 0.5)
            big_text(s, "DOMAIN EXPANSION", (CX, 100), 30, (200, 210, 255), alpha=a)
        if t > 1.2:
            k = pop(t, 1.2)
            ab = 4 if int(t * 20) % 3 else 8
            stamp_text(s, "INFINITE VOID", (CX - ab, H - 250), 70, (255, 40, 120), k)
            stamp_text(s, "INFINITE VOID", (CX + ab, H - 250), 70, (40, 220, 255), k)
            stamp_text(s, "INFINITE VOID", (CX, H - 250), 70, (255, 255, 255), k)
        if t > 1.7:
            ui.text(s, f"{self.ctx.name.upper()} SHOWS THEM EVERYTHING. THEY FORGET {self.ctx.damage} POINTS.",
                    (CX, H - 190), 14, (170, 190, 255), bold=True, anchor="center",
                    alpha=255 * seg(t, 1.7, 2.0))
        letterbox(s, seg(t, 0.4, 0.8))
        if 1.18 < t < 1.3:
            wash(s, (255, 255, 255), 200 * (1 - seg(t, 1.18, 1.3)))


# --- Sukuna: Domain Expansion - Malevolent Kitchen -----------------------------------------------------
class MalevolentKitchen(Scene):
    duration = 4.0
    end_card_at = 3.05
    cues = ((0.0, "hit"), (0.55, "void"), (1.25, "slash"), (1.45, "slash"), (1.62, "slash"), (1.85, "slash"),
            (2.05, "slash"), (2.2, "slash"), (2.35, "slash"), (2.5, "slash"), (2.62, "boom"))

    def setup(self):
        r = self.rng
        self.slashes = []
        t = 1.2
        while t < 2.75:
            ang = r.uniform(-0.9, 0.9) + (math.pi / 2 if r.random() < 0.3 else 0)
            cx, cy = r.uniform(100, W - 100), r.uniform(100, H - 100)
            self.slashes.append((t, ang, cx, cy, r.choice([1, 1, 2])))
            t += r.uniform(0.04, 0.09)
        self.embers = [(r.uniform(0, W), r.uniform(0, H), r.uniform(20, 80), r.uniform(0, 6)) for _ in range(70)]

    def shake(self):
        t = self.t
        amp = 6 * seg(t, 1.2, 1.3) * (1 - seg(t, 2.7, 3.0)) + 14 * (seg(t, 2.6, 2.62) - seg(t, 2.62, 2.9))
        if amp <= 0:
            return 0, 0
        return int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp))

    def _shrine(self, s, k):
        """Black shrine silhouette rising from the bottom, kitchen edition."""
        base_y = H - 40 + int((1 - ease_out(k)) * 360)
        ink = (12, 0, 4)
        pygame.draw.rect(s, ink, (CX - 230, base_y - 60, 460, 60))              # deck
        for x in (-180, -90, 90, 180):
            pygame.draw.rect(s, ink, (CX + x - 12, base_y - 230, 24, 172))       # pillars
        for (w, y, h) in ((560, 230, 46), (420, 330, 40)):                      # two curved roofs
            top = base_y - y
            pts = [(CX - w // 2 - 40, top + h), (CX - w // 2 + 10, top + 6), (CX, top - 22),
                   (CX + w // 2 - 10, top + 6), (CX + w // 2 + 40, top + h), (CX, top + 14)]
            pygame.draw.polygon(s, ink, pts)
        # teeth on the roof edge
        for i in range(-5, 6):
            pygame.draw.polygon(s, (230, 220, 200), [(CX + i * 44 - 8, base_y - 186), (CX + i * 44 + 8, base_y - 186),
                                                     (CX + i * 44, base_y - 170)])
        # the kitchen: a giant cleaver and a pot on the deck
        cl = pygame.Rect(CX + 250, base_y - 210, 90, 120)
        pygame.draw.rect(s, (200, 205, 215), cl)
        pygame.draw.rect(s, (120, 125, 140), cl, 4)
        pygame.draw.circle(s, ink, (cl.right - 20, cl.y + 20), 9)
        pygame.draw.rect(s, (90, 40, 20), (cl.x + 30, cl.bottom, 26, 70))
        pot = pygame.Rect(CX - 360, base_y - 120, 130, 80)
        pygame.draw.rect(s, (60, 60, 70), pot, border_radius=10)
        pygame.draw.rect(s, (30, 30, 36), (pot.x - 14, pot.y + 14, 14, 10))
        pygame.draw.rect(s, (30, 30, 36), (pot.right, pot.y + 14, 14, 10))
        for i in range(3):                                                       # steam
            ph = self.t * 2 + i
            pygame.draw.circle(s, (120, 60, 70), (pot.centerx - 30 + i * 30 + int(math.sin(ph) * 8),
                                                   pot.y - 20 - int((ph * 30) % 60)), 10, 3)

    def render(self, s):
        t = self.t
        # blood-red sky in bands
        for i in range(12):
            c = ui.mix((40, 0, 8), (150, 10, 24), i / 11)
            pygame.draw.rect(s, c, (0, i * H // 12, W, H // 12 + 1))
        pygame.draw.circle(s, (255, 70, 70), (W - 210, 150), 90)                   # red moon
        pygame.draw.circle(s, (120, 0, 20), (W - 180, 140), 80)
        for x, y, sp, ph in self.embers:
            yy = (y - t * sp * 3) % H
            pygame.draw.rect(s, (255, 120 + int(60 * math.sin(t * 6 + ph)), 40), (x + math.sin(t + ph) * 10, yy, 3, 3))
        self._shrine(s, seg(t, 0.4, 1.1))
        # caster on the left, chef hat on
        r = self.caster(s, 200, H - 60, 230, "right")
        hat = pygame.Rect(0, 0, 90, 50)
        hat.midbottom = (r.centerx, r.top + 22)
        pygame.draw.rect(s, (245, 245, 240), (hat.x + 12, hat.bottom - 18, hat.w - 24, 18))
        for dx in (-26, 0, 26):
            pygame.draw.circle(s, (245, 245, 240), (hat.centerx + dx, hat.y + 18), 22)
        pygame.draw.rect(s, (200, 200, 195), (hat.x + 12, hat.bottom - 18, hat.w - 24, 18), 2)
        # slashes
        for (at, ang, cx, cy, thick) in self.slashes:
            k = (t - at) / 0.22
            if 0 <= k <= 1:
                L = 900 * ease_out(min(1, k * 2.5))
                dx, dy = math.cos(ang) * L / 2, math.sin(ang) * L / 2
                a, b = (cx - dx, cy - dy), (cx + dx, cy + dy)
                fade = 1 - k
                pygame.draw.line(s, ui.mix((150, 10, 24), (255, 60, 60), fade), a, b, 10 * thick)
                pygame.draw.line(s, ui.mix((150, 10, 24), (255, 255, 255), fade), a, b, 3 * thick)
        # titles
        if t > 0.2:
            big_text(s, "DOMAIN EXPANSION", (CX, 96), 30, (255, 200, 200), alpha=255 * seg(t, 0.2, 0.45))
        if t > 0.6:
            k = pop(t, 0.6)
            stamp_text(s, "MALEVOLENT KITCHEN", (CX + 4, 178), 58, (0, 0, 0), k)
            stamp_text(s, "MALEVOLENT KITCHEN", (CX, 172), 58, (255, 236, 236), k)
        for word, at, pos, ang in (("DISMANTLE", 1.3, (330, 300), 8), ("CLEAVE", 1.95, (W - 330, 380), -10),
                                   ("CHOP CHOP", 2.45, (CX, 470), 4)):
            if at < t < at + 0.7:
                stamp_text(s, word, pos, 44, (255, 255, 255), pop(t, at, 0.12), ang)
        if 2.6 < t < 2.95:                                                        # the final cut splits the screen
            k = seg(t, 2.6, 2.95)
            pygame.draw.line(s, (255, 255, 255), (-50, H + 50), (W + 50, -50), int(30 * (1 - k)) + 2)
            wash(s, (255, 255, 255), 230 * (1 - k))
        letterbox(s, seg(t, 0.0, 0.4))


# --- MUI Goku: Kamehameha ------------------------------------------------------------------------------------
class Kamehameha(Scene):
    duration = 4.0
    end_card_at = 3.05
    cues = ((0.0, "charge"), (1.9, "beam"), (2.05, "boom"))

    HAND = (380, 470)

    def setup(self):
        r = self.rng
        self.parts = [(r.uniform(0, math.tau), r.uniform(160, 520), r.uniform(0, 1)) for _ in range(90)]
        self.lines = [(r.uniform(0, H), r.uniform(80, 340), r.uniform(0, 1)) for _ in range(40)]

    def shake(self):
        t = self.t
        amp = 3 * seg(t, 0.6, 1.8) + 9 * (seg(t, 1.9, 2.0) - seg(t, 2.6, 3.0))
        if amp <= 0:
            return 0, 0
        return int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp))

    def render(self, s):
        t = self.t
        for i in range(10):                                         # dusk sky
            pygame.draw.rect(s, ui.mix((10, 20, 60), (60, 120, 200), i / 9), (0, i * H // 10, W, H // 10 + 1))
        for y, length, ph in self.lines:                            # speed lines
            x = W - ((t * 900 + ph * W) % (W + length))
            pygame.draw.line(s, (150, 200, 255), (x, y), (x + length, y), 2)
        pygame.draw.rect(s, (30, 26, 40), (0, H - 110, W, 110))     # rocky ground
        for i in range(0, W, 60):
            pygame.draw.polygon(s, (44, 38, 56), [(i, H - 110), (i + 30, H - 128), (i + 60, H - 110)])
        hx, hy = self.HAND
        charge = ease_out(seg(t, 0.0, 1.9))
        # aura around the caster
        glow(s, (150, 210, 255), (230, 480), 150 + 20 * math.sin(t * 20), 70)
        self.caster(s, 230, H - 100, 250, "right", moving=t < 1.9)
        # particles converging on the hands
        if t < 1.95:
            for ang, dist, ph in self.parts:
                k = (t * 1.4 + ph) % 1.0
                d = dist * (1 - k)
                x, y = hx + math.cos(ang) * d, hy + math.sin(ang) * d
                pygame.draw.rect(s, (200, 240, 255), (x, y, 3, 3))
        # the orb
        rad = 10 + 60 * charge
        if t < 3.0:
            glow(s, (90, 190, 255), (hx, hy), rad * 2.4, 160)
            pygame.draw.circle(s, (170, 230, 255), (hx, hy), int(rad))
            pygame.draw.circle(s, (255, 255, 255), (hx, hy), int(rad * 0.6 + 2 * math.sin(t * 40)))
        # the beam
        if 1.9 <= t < 3.0:
            k = seg(t, 1.9, 2.15)
            end = hx + (W + 200 - hx) * ease_out(k)
            fade = 1 - seg(t, 2.7, 3.0)
            hh = (110 + 24 * math.sin(t * 50)) * fade
            for col, f in (((60, 150, 255), 1.0), ((140, 210, 255), 0.7), ((230, 250, 255), 0.42), ((255, 255, 255), 0.2)):
                pygame.draw.rect(s, col, (hx, hy - hh * f / 2, end - hx, hh * f))
            pygame.draw.circle(s, (230, 250, 255), (int(end), hy), int(hh * 0.7))
            for i in range(12):                                     # crackle
                x = hx + (i * 97 + t * 1500) % max(1, end - hx)
                pygame.draw.line(s, (255, 255, 255), (x, hy - hh / 2 - 8), (x + 30, hy - hh / 2 - 22), 2)
        # chant
        chant = [("KA", 0.15), ("ME", 0.5), ("HA", 0.85), ("ME", 1.2)]
        shown = " ".join(w for w, at in chant if t >= at)
        if shown and t < 1.9:
            big_text(s, shown + "...", (CX + 140, 140), 48, (255, 240, 150))
        if t >= 1.9:
            k = pop(t, 1.9, 0.2)
            stamp_text(s, "HA!!!", (CX + 140, 150), 110, (255, 230, 60), k, -6)
        if 1.88 < t < 2.05:
            wash(s, (255, 255, 255), 255 * (1 - seg(t, 1.88, 2.05)))
        letterbox(s, seg(t, 0.0, 0.4))


# --- Trump: sends 5 billion to Israel --------------------------------------------------------------------------
class FiveBillion(Scene):
    duration = 4.0
    end_card_at = 3.0
    cues = tuple((0.15 + i * 0.22, "cash") for i in range(11)) + ((2.55, "alarm"),)

    def setup(self):
        r = self.rng
        bill = pygame.Surface((44, 20))
        bill.fill((96, 170, 96))
        pygame.draw.rect(bill, (40, 100, 50), bill.get_rect(), 2)
        pygame.draw.circle(bill, (60, 130, 70), (22, 10), 6)
        ui.text(bill, "$", (22, 10), 10, (230, 255, 220), bold=True, anchor="center", shadow=False)
        self.bills = [pygame.transform.rotate(bill, a) for a in range(0, 360, 30)]
        self.flying = [(r.uniform(-200, W), r.uniform(-H, 0), r.uniform(120, 320), r.uniform(-60, 60), r.randrange(12),
                        r.uniform(0, 6)) for _ in range(110)]

    def render(self, s):
        t = self.t
        s.fill((14, 40, 24))
        for y in range(0, H, 80):                                   # faint dollar wallpaper
            for x in range((y // 80) % 2 * 60, W, 120):
                ui.text(s, "$", (x, y), 30, (24, 58, 36), bold=True, shadow=False)
        # money printer
        pr = pygame.Rect(CX - 160, H - 270, 320, 180)
        jig = int(math.sin(t * 60) * 3) if t > 0.15 else 0
        pr.x += jig
        pygame.draw.rect(s, (90, 96, 110), pr, border_radius=12)
        pygame.draw.rect(s, (50, 54, 66), pr, 5, border_radius=12)
        pygame.draw.rect(s, (20, 20, 28), (pr.x + 40, pr.y + 30, pr.w - 80, 22))
        ui.text(s, "MONEY PRINTER", (pr.centerx, pr.y + 80), 16, (230, 230, 240), bold=True, anchor="center")
        lamp = (255, 70, 70) if int(t * 8) % 2 else (90, 20, 20)
        pygame.draw.circle(s, lamp, (pr.right - 30, pr.y + 120), 10)
        if t > 0.15:
            ui.text(s, "BRRRRRRR", (pr.right + 30 + jig * 2, pr.y + 40), 26, (255, 240, 160), bold=True)
        # bills raining
        for x0, y0, sp, drift, rot, ph in self.flying:
            y = y0 + t * sp * 2.2
            if -40 < y < H + 40 and t > 0.1:
                x = x0 + math.sin(t * 2 + ph) * drift
                img = self.bills[(rot + int(t * 6 + ph)) % len(self.bills)]
                s.blit(img, (x, y))
        # counter
        k = ease_out(seg(t, 0.2, 2.0))
        amount = int(5_000_000_000 * k)
        big_text(s, f"${amount:,}", (CX, 150), 64, (255, 214, 80))
        # banner
        if t > 1.0:
            b = pygame.Rect(0, 0, 900, 64)
            b.center = (CX, 250)
            b.x += int((1 - ease_out(seg(t, 1.0, 1.25))) * -1200)
            ui.panel(s, b, (20, 30, 80), 10, (255, 255, 255), 250)
            ui.text(s, "SENDING $5 BILLION TO ISRAEL", b.center, 30, (255, 255, 255), bold=True, anchor="center")
        # wire transfer bar
        if t > 1.3:
            bar = pygame.Rect(CX - 300, 310, 600, 30)
            pygame.draw.rect(s, (0, 0, 0), bar.inflate(6, 6))
            fill = seg(t, 1.3, 2.5)
            pygame.draw.rect(s, (90, 220, 110), (bar.x, bar.y, int(bar.w * fill), bar.h))
            label = f"WIRE TRANSFER {int(fill * 100)}%" if fill < 1 else "TRANSFER COMPLETE - PAID WITH YOUR POINTS"
            ui.text(s, label, (bar.centerx, bar.bottom + 22), 14, (230, 255, 230), bold=True, anchor="center")
        self.caster(s, 170, H - 40, 260, "down")
        letterbox(s, seg(t, 0.0, 0.4))


# --- Palantir Patrick: drone strike ----------------------------------------------------------------------------
class DroneStrike(Scene):
    duration = 4.1
    end_card_at = 3.15
    cues = ((0.0, "alarm"), (0.45, "blip"), (0.7, "blip"), (0.95, "blip"), (1.2, "blip"), (1.9, "drop"), (2.45, "boom"))
    GROUND = H - 150

    def setup(self):
        r = self.rng
        n = max(1, min(6, len(self.ctx.victims)))
        span = min(W - 360, 170 * n)
        self.spots = [int(CX - span / 2 + span * (i + 0.5) / n) for i in range(n)]
        self.target_x = self.spots[len(self.spots) // 2]
        self.debris = [(r.uniform(-1, 1), r.uniform(-1.4, -0.3), r.uniform(200, 600)) for _ in range(40)]
        self.scan = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 3):
            pygame.draw.line(self.scan, (0, 0, 0, 70), (0, y), (W, y))

    def shake(self):
        amp = 16 * (seg(self.t, 2.45, 2.5) - seg(self.t, 2.5, 3.0))
        if amp <= 0:
            return 0, 0
        return int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp))

    def _drone(self, s, x, y):
        """Big MQ-style quad seen from the side, drawn over the night-vision tint."""
        body, edge = (24, 40, 28), (170, 255, 170)
        spin = int(self.t * 40) % 2
        for dx in (-112, 112):
            pygame.draw.line(s, edge, (x + dx, y - 14), (x + dx, y - 30), 6)
            w = 90 if spin else 44
            pygame.draw.line(s, edge, (x + dx - w // 2, y - 32), (x + dx + w // 2, y - 32), 4)
        pygame.draw.line(s, edge, (x - 112, y - 12), (x + 112, y - 12), 9)
        hull = pygame.Rect(x - 80, y - 36, 160, 52)
        pygame.draw.ellipse(s, body, hull)
        pygame.draw.ellipse(s, edge, hull, 3)
        pygame.draw.rect(s, body, (x - 16, y + 12, 32, 22))
        pygame.draw.rect(s, edge, (x - 16, y + 12, 32, 22), 2)
        pygame.draw.circle(s, (255, 60, 60) if int(self.t * 6) % 2 else (120, 20, 20), (x + 52, y - 10), 7)
        ui.text(s, "GOTHAM-1", (x, y - 10), 12, edge, bold=True, anchor="center", shadow=False)

    def render(self, s):
        t = self.t
        ctx = self.ctx
        # a city at night (it gets the night-vision treatment below)
        s.fill((18, 22, 26))
        for i, x in enumerate(range(-20, W, 90)):
            h = 120 + (i * 53) % 170
            pygame.draw.rect(s, (34, 40, 46), (x, self.GROUND - h, 80, h))
            for wy in range(self.GROUND - h + 14, self.GROUND - 10, 26):
                if (wy + i * 7) % 3:
                    pygame.draw.rect(s, (70, 80, 60), (x + 14, wy, 12, 10))
                    pygame.draw.rect(s, (70, 80, 60), (x + 50, wy, 12, 10))
        pygame.draw.rect(s, (26, 30, 30), (0, self.GROUND, W, H - self.GROUND))
        # the victims, standing in the open; the blast throws them
        fly = ease_out(seg(t, 2.45, 2.9))
        for i, v in enumerate(ctx.victims[:len(self.spots)]):
            x = self.spots[i]
            ox = (x - self.target_x) * 1.2 * fly + (40 if x == self.target_x else 0) * fly
            oy = -160 * math.sin(fly * math.pi) if 0 < fly < 1 else 0
            ctx.assets.draw_character(s, x + ox, self.GROUND + 20 + oy, ctx.victim_character(v), 96, "down", False,
                                      True, i * 211, v.get("color"))
        # night vision: tint the whole frame green and add scanlines
        s.fill(NV_GREEN, special_flags=pygame.BLEND_RGB_MULT)
        s.blit(self.scan, (0, 0))

        hud = (170, 255, 170)
        # drone and bomb (bright, over the tint)
        dx = lerp(-200, self.target_x, ease_out(seg(t, 0.9, 1.8)))
        if t > 2.2:
            dx = lerp(self.target_x, W + 260, ease_in(seg(t, 2.2, 3.0)))
        self._drone(s, int(dx), 130 + int(math.sin(t * 4) * 6))
        if 1.9 <= t < 2.45:
            k = ease_in(seg(t, 1.9, 2.45))
            bx, by = self.target_x, lerp(170, self.GROUND, k)
            pygame.draw.ellipse(s, (30, 40, 30), (bx - 12, by - 30, 24, 44))
            pygame.draw.ellipse(s, hud, (bx - 12, by - 30, 24, 44), 2)
            pygame.draw.polygon(s, hud, [(bx - 14, by - 32), (bx + 14, by - 32), (bx, by - 46)], 2)
            pygame.draw.line(s, hud, (bx, by - 60), (bx, by - 90), 1)
        # explosion: real colours burning through the night vision
        if t >= 2.45:
            k = seg(t, 2.45, 3.3)
            cx, cy = self.target_x, self.GROUND - 10
            glow(s, (255, 140, 40), (cx, cy), 120 + 300 * ease_out(k), 140 * (1 - k))
            for col, f in (((230, 70, 20), 1.0), ((255, 160, 40), 0.72), ((255, 240, 180), 0.42)):
                r = int((40 + 230 * ease_out(k)) * f * (1 - 0.55 * k))
                if r > 0:
                    pygame.draw.circle(s, col, (cx, cy), r)
            for vx, vy, sp in self.debris:
                d = sp * k
                pygame.draw.rect(s, (255, 200, 120), (cx + vx * d, cy + vy * d + 300 * k * k, 5, 5))
            for i in range(3):
                pygame.draw.circle(s, ui.mix((40, 40, 40), (80, 80, 80), i / 2),
                                   (cx + (i - 1) * 50, int(cy - 160 * k - i * 14)), int(18 + 40 * k))
        # targeting HUD
        for i, v in enumerate(ctx.victims[:len(self.spots)]):
            lock_at = 0.45 + i * 0.25
            if t < lock_at or t > 2.45:
                continue
            k = ease_out(seg(t, lock_at, lock_at + 0.2))
            x, y = self.spots[i], self.GROUND - 40
            half = int(lerp(140, 56, k))
            box = pygame.Rect(0, 0, half * 2, half * 2 + 20)
            box.center = (x, y)
            col = (255, 80, 80) if k >= 1 and int(t * 6) % 2 else hud
            for (px, py), (sx, sy) in ((box.topleft, (1, 1)), (box.topright, (-1, 1)),
                                       (box.bottomleft, (1, -1)), (box.bottomright, (-1, -1))):
                pygame.draw.line(s, col, (px, py), (px + sx * 18, py), 3)
                pygame.draw.line(s, col, (px, py), (px, py + sy * 18), 3)
            if k >= 1:
                ui.text(s, ui.fit(str(v["name"]).upper(), 12, 150, True), (x, box.top - 14), 12, col, bold=True,
                        anchor="center")
                ui.text(s, f"MATCH 99.{7 - i % 3}%", (x, box.bottom + 14), 12, col, bold=True, anchor="center")
        ui.text(s, "PALANTIR // GOTHAM", (40, 40), 16, hud, bold=True)
        ui.text(s, f"OPERATOR {ctx.name.upper()}", (40, 66), 12, hud, bold=True)
        locks = min(len(ctx.victims), int(max(0.0, t - 0.45) / 0.25) + 1) if t >= 0.45 else 0
        ui.text(s, f"TGT LOCK {locks}/{len(ctx.victims)}", (W - 40, 40), 16, hud, bold=True, anchor="topright")
        if int(t * 2) % 2:
            pygame.draw.circle(s, (255, 60, 60), (W - 60, 82), 7)
            ui.text(s, "REC", (W - 74, 82), 12, (255, 90, 90), bold=True, anchor="midright")
        pygame.draw.line(s, hud, (CX - 30, CY), (CX + 30, CY), 1)
        pygame.draw.line(s, hud, (CX, CY - 30), (CX, CY + 30), 1)
        if 1.8 < t < 2.45:
            stamp_text(s, "STRIKE AUTHORIZED", (CX, 240), 40, (255, 70, 70) if int(t * 10) % 2 else (255, 220, 220),
                       pop(t, 1.8))
        if 2.44 < t < 2.7:
            wash(s, (255, 250, 220), 255 * (1 - seg(t, 2.44, 2.7)))
        self.caster(s, 110, H - 20, 130, "right")


# --- Claude: code review (free choice) ------------------------------------------------------------------------
class CodeReview(Scene):
    """Claude reviews the leaderboard, finds the bug (everyone else's points) and ships the fix."""
    duration = 4.6
    end_card_at = None                 # the diff is the damage report
    cues = ((0.1, "blip"), (0.75, "blip"), (1.1, "blip"), (1.45, "whoosh"), (2.45, "hit"), (3.2, "cash"))

    def setup(self):
        n = len(self.ctx.victims)
        self.lines = [
            (0.1, f"> claude review --file leaderboard.json --author {self.ctx.name}", CLAUDE_CREAM),
            (0.75, "Reading leaderboard.json ...", (160, 156, 148)),
            (1.1, f"Found {n} issue{'s' if n != 1 else ''}: other players have too many points.", (240, 200, 120)),
        ]

    def _spark(self, s, center, radius, angle, color=CLAUDE_ORANGE):
        """Claude-style starburst: uneven rays around a point."""
        pts = []
        rays = 11
        for i in range(rays * 2):
            a = angle + i * math.pi / rays
            r = radius if i % 2 == 0 else radius * 0.18
            if i % 4 == 0:
                r *= 0.82
            pts.append((center[0] + math.cos(a) * r, center[1] + math.sin(a) * r))
        pygame.draw.polygon(s, color, pts)

    def render(self, s):
        t = self.t
        s.fill(CLAUDE_DARK)
        # the spark behind everything, growing at the end
        big = ease_out(seg(t, 3.0, 3.6))
        self._spark(s, (CX, CY), 120 + 600 * big, t * 0.8, ui.mix(CLAUDE_DARK, CLAUDE_ORANGE, 0.25 + 0.5 * big))
        # window
        win = pygame.Rect(0, 0, 940, 470)
        win.center = (CX, CY + 10)
        win.y += int((1 - ease_out(seg(t, 0.0, 0.3))) * 500)
        pygame.draw.rect(s, (0, 0, 0), win.move(8, 10), border_radius=14)
        pygame.draw.rect(s, (38, 37, 35), win, border_radius=14)
        bar = pygame.Rect(win.x, win.y, win.w, 40)
        pygame.draw.rect(s, (52, 50, 47), bar, border_top_left_radius=14, border_top_right_radius=14)
        for i, c in enumerate(((236, 95, 90), (240, 190, 70), (100, 200, 100))):
            pygame.draw.circle(s, c, (bar.x + 26 + i * 24, bar.centery), 7)
        ui.text(s, "claude  ~/arena", (bar.centerx, bar.centery), 14, (200, 196, 186), bold=True, anchor="center")
        self._spark(s, (bar.right - 30, bar.centery), 13, t * 2)
        # typed lines
        x, y = win.x + 30, win.y + 62
        for at, line, col in self.lines:
            if t < at:
                break
            n = int((t - at) * 90)
            ui.text(s, line[:n], (x, y), 14, col, bold=True, shadow=False)
            y += 28
        # the diff
        if t > 1.45:
            ui.text(s, "--- a/leaderboard.json", (x, y + 4), 14, (160, 156, 148), bold=True, shadow=False)
            ui.text(s, "+++ b/leaderboard.json", (x, y + 26), 14, (160, 156, 148), bold=True, shadow=False)
            y += 58
            for i, v in enumerate(self.ctx.victims[:6]):
                at = 1.55 + i * 0.12
                if t < at:
                    break
                before = v["score"] + v["lost"]
                k = ease_out(seg(t, at, at + 0.15))
                ox = int((1 - k) * 40)
                me = v["id"] == self.ctx.me_id
                tag = "  <- you" if me else ""
                pygame.draw.rect(s, (70, 30, 32), (x - 10 + ox, y - 3, win.w - 40, 22))
                ui.text(s, f"-  \"{v['name']}\": {before},{tag}", (x + ox, y), 14, (255, 140, 140), bold=True, shadow=False)
                pygame.draw.rect(s, (28, 64, 38), (x - 10 + ox, y + 21, win.w - 40, 22))
                ui.text(s, f"+  \"{v['name']}\": {v['score']},{tag}", (x + ox, y + 24), 14, (150, 240, 160), bold=True,
                        shadow=False)
                y += 50
            if len(self.ctx.victims) > 6:
                ui.text(s, f"   ... and {len(self.ctx.victims) - 6} more", (x, y), 14, (160, 156, 148), shadow=False)
        if t > 2.9:
            msg = f"Applied. -{self.ctx.damage} for everyone else. You're absolutely right, this was the bug."
            n = int((t - 2.9) * 70)
            ui.text(s, msg[:n], (x, win.bottom - 40), 14, CLAUDE_ORANGE, bold=True, shadow=False)
        # stamp
        if t > 2.45:
            k = seg(t, 2.45, 2.6)
            scale = lerp(2.4, 1.0, ease_out(k))
            stamp_text(s, "CHANGES REQUESTED", (win.right - 190, win.bottom - 110), 34, (240, 80, 70), scale, 12)
        big_text(s, "CLAUDE  //  CODE REVIEW", (CX, 52), 26, CLAUDE_CREAM)
        letterbox(s, seg(t, 0.0, 0.3), 30)


# --- Sam Altman: steal their RAM -------------------------------------------------------------------------------
class RamHeist(Scene):
    duration = 4.1
    end_card_at = 3.15
    cues = ((0.0, "blip"), (1.0, "whoosh"), (1.3, "whoosh"), (1.6, "whoosh"), (1.9, "whoosh"), (2.6, "cash"))

    def setup(self):
        r = self.rng
        n = max(1, min(6, len(self.ctx.victims)))
        self.cols = [int(120 + (W - 240) * (i + 0.5) / n) for i in range(n)]
        self.gb = [r.choice((16, 32, 64)) for _ in range(n)]
        self.dc = pygame.Rect(CX + 150, H - 330, 260, 250)

    def _stick(self, s, center, scale=1.0, angle=0.0):
        w, h = int(120 * scale), int(30 * scale)
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        img.fill((30, 120, 60))
        for i in range(6):
            pygame.draw.rect(img, (20, 20, 24), (6 * scale + i * 18 * scale, 5 * scale, 13 * scale, 14 * scale))
        for i in range(0, w, max(2, int(5 * scale))):
            pygame.draw.rect(img, (230, 190, 60), (i, h - 6 * scale, max(1, 3 * scale), 6 * scale))
        pygame.draw.rect(img, (16, 70, 34), img.get_rect(), max(1, int(2 * scale)))
        if angle:
            img = pygame.transform.rotate(img, angle)
        s.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))

    def render(self, s):
        t = self.t
        ctx = self.ctx
        for i in range(10):
            pygame.draw.rect(s, ui.mix((8, 16, 24), (16, 50, 60), i / 9), (0, i * H // 10, W, H // 10 + 1))
        # the data centre that eats everything
        dc = self.dc
        pygame.draw.rect(s, (24, 28, 36), dc)
        pygame.draw.rect(s, (90, 100, 120), dc, 4)
        for row in range(6):
            for col in range(4):
                on = (row * 4 + col + int(t * 12)) % 5
                pygame.draw.rect(s, (90, 255, 140) if on else (30, 60, 40),
                                 (dc.x + 24 + col * 56, dc.y + 46 + row * 30, 40, 8))
        ui.text(s, "STARGATE", (dc.centerx, dc.y + 20), 16, (220, 230, 255), bold=True, anchor="center")
        mouth = (dc.centerx, dc.y + 4)
        # victims: name, gauge, their RAM flying into the data centre
        for i, v in enumerate(ctx.victims[:len(self.cols)]):
            x = self.cols[i]
            me = v["id"] == ctx.me_id
            ui.text(s, ui.fit(str(v["name"]).upper(), 16, 180, True), (x, 110), 16,
                    (255, 220, 120) if me else (220, 240, 255), bold=True, anchor="center")
            start = 0.9 + i * 0.3
            k = seg(t, start, start + 0.9)
            gb = int(round(self.gb[i] * (1 - k)))
            g = pygame.Rect(x - 70, 132, 140, 14)
            pygame.draw.rect(s, (0, 0, 0), g.inflate(4, 4))
            pygame.draw.rect(s, (255, 80, 80) if gb == 0 else (90, 230, 140), (g.x, g.y, int(g.w * (1 - k)), g.h))
            ui.text(s, f"{gb} GB RAM", (x, 164), 12, (255, 120, 120) if gb == 0 else (180, 220, 200), bold=True,
                    anchor="center")
            if k <= 0:
                self._stick(s, (x, 210), 1.0)
            elif k < 1:                                          # bezier into the data centre
                e = ease_in(k)
                p0, p1, p2 = (x, 210), ((x + mouth[0]) / 2, -40), mouth
                bx = (1 - e) ** 2 * p0[0] + 2 * (1 - e) * e * p1[0] + e * e * p2[0]
                by = (1 - e) ** 2 * p0[1] + 2 * (1 - e) * e * p1[1] + e * e * p2[1]
                self._stick(s, (bx, by), 1.0 - 0.6 * e, k * 540)
        # Sam
        self.caster(s, 300, H - 70, 250, "right", moving=t > 1.0)
        prog = seg(t, 0.9, 2.6)
        bar = pygame.Rect(CX - 360, 268, 460, 20)
        pygame.draw.rect(s, (0, 0, 0), bar.inflate(6, 6))
        pygame.draw.rect(s, (120, 200, 255), (bar.x, bar.y, int(bar.w * prog), bar.h))
        ui.text(s, f"DOWNLOADING YOUR RAM ... {int(prog * 100)}%", (bar.x, bar.y - 22), 12, (200, 230, 255), bold=True)
        title = "SAM ALTMAN IS STEALING YOUR RAM"
        big_text(s, title[:int(t * 40) + 1], (CX, 52), 30, (255, 255, 255))
        if t > 2.6:
            k = pop(t, 2.6)
            stamp_text(s, "THANKS FOR THE COMPUTE", (CX - 120, 340), 40, (255, 220, 120), k, 6)
            tick = "DRAM PRICES  +400%  ^^^   GPU  +900%  ^^^   YOUR SCORE  -10  vvv   "
            off = int(t * 220) % ui.text_width(tick, 14, True)
            ui.text(s, tick * 3, (-off, 404), 14, (120, 255, 160), bold=True)
        letterbox(s, seg(t, 0.0, 0.3), 30)


SCENES = {
    "gojo": InfiniteVoid,
    "sukuna": MalevolentKitchen,
    "mui-goku": Kamehameha,
    "trump": FiveBillion,
    "palantir-patrick": DroneStrike,
    "claude": CodeReview,
    "sam-altman": RamHeist,
}


# --- the common damage card and the player that runs the queue --------------------------------------------
def draw_end_card(s, ctx, k):
    """Who fired and who lost what; slides up at the end of a scene."""
    band = pygame.Rect(0, 0, W, 150)
    band.bottom = H - 70 + int((1 - ease_out(k)) * 260)
    pygame.draw.rect(s, (8, 10, 30), band)
    ui.hazard(s, (0, band.y, W, 10))
    ui.hazard(s, (0, band.bottom - 10, W, 10))
    who = "YOU" if ctx.mine else ctx.name.upper()
    ui.text(s, f"{who} FIRED AN ULTIMATE  -  EVERYONE ELSE -{ctx.damage}", (CX, band.y + 34), 22, ui.WARN,
            bold=True, anchor="center")
    chips = ctx.victims[:8]
    if not chips:
        ui.text(s, "...BUT NOBODY ELSE WAS HERE", (CX, band.y + 88), 18, ui.MUTED, bold=True, anchor="center")
        return
    cw = min(150, (W - 80) // len(chips))
    x0 = CX - cw * len(chips) // 2
    for i, v in enumerate(chips):
        me = v["id"] == ctx.me_id
        r = pygame.Rect(x0 + i * cw + 6, band.y + 62, cw - 12, 58)
        ui.panel(s, r, ui.PANEL_HI if me else ui.PANEL, 6, ui.BAD, 255, rivets=False)
        ui.text(s, ui.fit("YOU" if me else str(v["name"]).upper(), 12, r.w - 12, True), (r.centerx, r.y + 16), 12,
                ui.ICE, bold=True, anchor="center")
        ui.text(s, f"-{v['lost']}", (r.centerx, r.y + 40), 20, ui.BAD, bold=True, anchor="center")


class CutscenePlayer:
    """Queue of ultimates for one game screen; draws the current one over everything."""

    def __init__(self, app):
        self.app = app
        self.queue = []
        self.scene = None
        self.layer = None
        self.toasts = None

    def add(self, m, me_id, players=None, toasts=None):
        ctx = Ctx(self.app, m, me_id, players)
        cls = SCENES.get(ctx.slug)
        if cls is None:                                    # Mia, Leo (and anyone without a scene): no animation
            self.app.sfx.play("hit")
            if toasts is not None:
                who = "You" if ctx.mine else ctx.name
                lost = next((v["lost"] for v in ctx.victims if v["id"] == me_id), None)
                tail = f"  -  you lose {lost}" if lost is not None else ""
                toasts.add(f"{who} used an ultimate: everyone else -{ctx.damage}{tail}", ui.WARN, 3.5)
            return
        self.queue.append(cls(ctx))

    @property
    def active(self):
        return self.scene is not None

    def update(self, dt):
        if self.scene is None and self.queue:
            self.scene = self.queue.pop(0)
        if self.scene is not None:
            self.scene.update(dt)
            if self.scene.done:
                self.scene = None

    def draw(self, surf):
        sc = self.scene
        if sc is None:
            return
        if self.layer is None:
            self.layer = pygame.Surface((W, H)).convert()
        layer = self.layer
        sc.render(layer)
        if sc.end_card_at is not None and sc.t >= sc.end_card_at:
            draw_end_card(layer, sc.ctx, seg(sc.t, sc.end_card_at, sc.end_card_at + 0.3))
        fade = min(seg(sc.t, 0.0, 0.15), 1 - seg(sc.t, sc.duration - 0.3, sc.duration))
        ox, oy = sc.shake()
        if fade >= 1:
            if ox or oy:
                surf.fill((0, 0, 0))
            surf.blit(layer, (ox, oy))
        else:
            layer.set_alpha(int(255 * fade))
            surf.blit(layer, (ox, oy))
            layer.set_alpha(None)
