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


# --- Gojo: Domain Expansion - Infinite Void (Muryokusho) ------------------------------------------------
class InfiniteVoid(Scene):
    """The beats of the anime: the hand seal (middle finger crossed over the index), the
    blindfold coming off on the Six Eyes, the barrier closing everything in black, then the
    void itself - an endless cosmos round a blinding ring of light - where every target
    stands frozen while infinite information pours into them. Gojo alone moves."""
    duration = 4.9
    end_card_at = 3.9
    cues = ((0.0, "whoosh"), (0.55, "blip"), (1.0, "void"), (1.45, "hit"), (2.9, "whoosh"))
    SKIN, LINE = (250, 222, 200), (40, 26, 40)
    RING = (CX, 175)
    UNIFORM = (22, 24, 44)
    INFO = ["SEE", "HEAR", "FEEL", "KNOW", "EVERYTHING", "FOREVER", "1011010", "SYN", "ACK", "TTL=INF",
            "0xFFFF", "ALL AT ONCE", "NEVER ENDS", "WHY", "MURYOKUSHO", "INFINITY"]

    def setup(self):
        r = self.rng
        self.stars = [(r.uniform(0, math.tau), r.uniform(0.15, 1.0), r.uniform(0, 1), r.choice(
            [(255, 255, 255), (160, 220, 255), (190, 140, 255), (120, 160, 255)])) for _ in range(240)]
        self.dust = [(r.uniform(0, W), r.uniform(0, H), r.uniform(1, 3), r.uniform(0, 6)) for _ in range(120)]
        n = max(1, min(6, len(self.ctx.victims)))
        left = (n + 1) // 2                                 # either side of Gojo, who stands in the middle
        xs = [lerp(130, CX - 230, (i + 0.5) / left) for i in range(left)]
        xs += [lerp(CX + 230, W - 130, (i + 0.5) / (n - left)) for i in range(n - left)]
        self.spots = [(int(x), H - 70 - (40 if i % 2 else 0)) for i, x in enumerate(xs)]
        self.streams = [[(r.uniform(0, math.tau), r.uniform(0, 1), r.choice(self.INFO)) for _ in range(9)]
                        for _ in range(n)]

    def shake(self):
        amp = 10 * (seg(self.t, 1.45, 1.5) - seg(self.t, 1.5, 1.9))
        if amp <= 0:
            return 0, 0
        return int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp))

    # -- beat 1: the hand seal --------------------------------------------------------------
    PX_HAND = 4                         # the hand is drawn at 1/4 size and blown up: chunky pixels

    @classmethod
    def _seal_sprite(cls):
        """Right hand, palm to the camera: middle finger crossed over the index, ring and
        pinky folded down, thumb holding them. Built once at low resolution."""
        if getattr(cls, "_seal_img", None) is not None:
            return cls._seal_img
        skin, shade, line, nail = (252, 214, 186), (222, 168, 144), (70, 36, 44), (255, 236, 228)
        img = pygame.Surface((72, 112), pygame.SRCALPHA)
        pygame.draw.rect(img, line, (8, 92, 56, 20))                             # sleeve
        pygame.draw.rect(img, cls.UNIFORM, (9, 93, 54, 19))
        pygame.draw.line(img, (60, 66, 110), (9, 95), (62, 95))
        pygame.draw.rect(img, line, (19, 80, 34, 16))                            # wrist
        pygame.draw.rect(img, skin, (20, 80, 32, 14))
        palm = pygame.Rect(12, 50, 48, 42)
        pygame.draw.rect(img, line, palm.inflate(2, 2), border_radius=11)
        pygame.draw.rect(img, skin, palm, border_radius=10)

        def finger(base, tip, wb, wt):
            dx, dy = tip[0] - base[0], tip[1] - base[1]
            ln = math.hypot(dx, dy)
            nx, ny = -dy / ln, dx / ln
            for col, grow in ((line, 1), (skin, 0)):
                b2, t2 = wb / 2 + grow, wt / 2 + grow
                pygame.draw.polygon(img, col, [(base[0] + nx * b2, base[1] + ny * b2),
                                               (tip[0] + nx * t2, tip[1] + ny * t2),
                                               (tip[0] - nx * t2, tip[1] - ny * t2),
                                               (base[0] - nx * b2, base[1] - ny * b2)])
                pygame.draw.circle(img, col, (round(tip[0]), round(tip[1])), round(t2))
            for f in (0.35, 0.65):                                               # knuckle creases
                cx, cy = base[0] + dx * f, base[1] + dy * f
                pygame.draw.line(img, shade, (cx - nx * wt * 0.3, cy - ny * wt * 0.3),
                                 (cx + nx * wt * 0.3, cy + ny * wt * 0.3))
            ux, uy = dx / ln, dy / ln                                            # nail near the tip
            pygame.draw.circle(img, nail, (round(tip[0] - ux * 2), round(tip[1] - uy * 2)), max(1, round(wt / 4)))

        finger((19, 60), (31, 12), 12, 10)                                       # index, leaning right
        finger((32, 60), (19, 4), 12, 10)                                        # middle, crossed over it
        pygame.draw.rect(img, skin, palm.inflate(-4, -10).move(0, 4))            # hide the finger roots
        for x in (38, 49):                                                       # ring + pinky folded down
            r = pygame.Rect(x, 44, 11, 20)
            pygame.draw.rect(img, line, r.inflate(2, 2), border_radius=5)
            pygame.draw.rect(img, skin, r, border_radius=5)
            pygame.draw.line(img, shade, (x + 2, 52), (x + 8, 52))
            pygame.draw.rect(img, nail, (x + 3, 58, 5, 4))
        finger((12, 84), (46, 66), 12, 10)                                       # thumb across them
        pygame.draw.line(img, shade, (20, 76), (36, 72))                         # palm crease
        pygame.draw.line(img, shade, (14, 58), (14, 74))                         # palm edge shading
        cls._seal_img = pygame.transform.scale(img, (72 * cls.PX_HAND, 112 * cls.PX_HAND))
        return cls._seal_img

    def _hand_seal(self, s, t):
        k = ease_out(seg(t, 0.0, 0.35))
        img = self._seal_sprite()
        r = img.get_rect(midbottom=(CX + 190, H + int((1 - k) * 420)))
        if t > 0.3:
            r.x += int(math.sin(t * 40) * 2)                                     # cursed energy trembles
        glow(s, (90, 170, 255), (r.centerx, r.y + 140), 260, 80)
        s.blit(img, r)

    # -- beat 2: the Six Eyes ---------------------------------------------------------------
    def _six_eyes(self, s, t):
        band = pygame.Rect(0, CY - 120, W, 240)
        pygame.draw.rect(s, self.SKIN, band)
        lift = ease_out(seg(t, 0.5, 0.7))                                                # blindfold slides up
        open_k = ease_out(seg(t, 0.62, 0.82))
        for ex in (CX - 230, CX + 230):
            eye = pygame.Rect(0, 0, 300, max(4, int(130 * open_k)))
            eye.center = (ex, CY + 10)
            pygame.draw.ellipse(s, self.LINE, eye.inflate(10, 10))
            pygame.draw.ellipse(s, (245, 250, 255), eye)
            clip = s.get_clip()
            s.set_clip(eye)
            ix = ex + int(math.sin(t * 3) * 6)
            for rr, col in ((62, (20, 90, 220)), (54, (40, 150, 255)), (40, (120, 220, 255)), (24, (200, 245, 255))):
                pygame.draw.circle(s, col, (ix, CY + 10), rr)
            for a in range(0, 360, 20):                                                  # the crystalline iris
                rad = math.radians(a + t * 40)
                pygame.draw.line(s, (230, 250, 255), (ix + math.cos(rad) * 18, CY + 10 + math.sin(rad) * 18),
                                 (ix + math.cos(rad) * 52, CY + 10 + math.sin(rad) * 52), 1)
            pygame.draw.circle(s, (10, 20, 60), (ix, CY + 10), 12)
            pygame.draw.circle(s, (255, 255, 255), (ix - 18, CY - 8), 8)
            s.set_clip(clip)
            for i in range(9):                                                           # white lashes
                x = eye.x + 20 + i * 32
                pygame.draw.line(s, (255, 255, 255), (x, eye.y + 4), (x - 6 + i, eye.y - 22), 4)
            glow(s, (110, 200, 255), (ex, CY + 10), 170, int(110 * open_k))
        for i in range(-3, 18):                                                          # white hair falling over
            x = i * 80 + int(math.sin(t * 2 + i) * 6)
            pygame.draw.polygon(s, (236, 240, 250), [(x - 40, band.y), (x + 40, band.y), (x + 10, band.y + 70)])
            pygame.draw.polygon(s, (200, 206, 226), [(x + 10, band.y), (x + 40, band.y), (x + 10, band.y + 70)])
        if lift < 1:                                                                     # the blindfold
            by = int(band.y + 30 - lift * 190)
            pygame.draw.rect(s, (12, 12, 20), (0, by, W, 150))
            pygame.draw.line(s, (40, 40, 60), (0, by + 6), (W, by + 6), 3)
        ui.text(s, "THE SIX EYES", (CX, band.bottom + 30), 16, (180, 220, 255), bold=True, anchor="center",
                alpha=255 * open_k)

    # -- beat 4: the void -------------------------------------------------------------------
    def _void(self, s, t):
        s.fill((3, 2, 10))
        for x, y, sz, ph in self.dust:
            a = 0.5 + 0.5 * math.sin(t * 2 + ph)
            pygame.draw.rect(s, ui.mix((3, 2, 10), (150, 170, 255), a * 0.6), (x, y, sz, sz))
        hx, hy = self.RING                                                               # the ring of light
        speed = 0.35 + 1.4 * seg(t, 1.45, 2.2)
        for ang, sp, off, col in self.stars:                                             # pouring out of it
            d = (off + t * sp * speed) % 1.0
            r0 = 100 + d * d * 760
            r1 = r0 + 6 + 80 * d * sp * speed
            x0, y0 = hx + math.cos(ang) * r0, hy + math.sin(ang) * r0 * 0.7
            x1, y1 = hx + math.cos(ang) * r1, hy + math.sin(ang) * r1 * 0.7
            pygame.draw.line(s, ui.mix((3, 2, 10), col, clamp(d * 1.6)), (x0, y0), (x1, y1), 2 if d > 0.5 else 1)
        pulse = 6 * math.sin(t * 4)
        glow(s, (140, 180, 255), (hx, hy), 270 + pulse, 120, 6)
        disk = pygame.Rect(0, 0, 540, 46)
        disk.center = (hx, hy)
        pygame.draw.ellipse(s, (170, 200, 255), disk.inflate(26, 14))                    # far side of the disc
        pygame.draw.ellipse(s, (250, 252, 255), disk)
        pygame.draw.circle(s, (240, 246, 255), (hx, hy), 96 + int(pulse))               # light bent round the hole
        pygame.draw.circle(s, (0, 0, 0), (hx, hy), 80)
        clip = s.get_clip()                                                              # near side crosses in front
        s.set_clip(pygame.Rect(0, hy, W, 50))
        pygame.draw.ellipse(s, (250, 252, 255), disk)
        s.set_clip(clip)
        pygame.draw.ellipse(s, (120, 160, 255), disk, 2)

    def _victims(self, s, t):
        ctx = self.ctx
        hx, hy = self.RING
        for i, v in enumerate(ctx.victims[:len(self.spots)]):
            x, y = self.spots[i]
            y += int(math.sin(t * 1.3 + i) * 6)                                          # drifting, weightless
            for ang, ph, word in self.streams[i]:                                        # information pouring in
                k = (t * 1.6 + ph) % 1.0
                src = (hx + math.cos(ang) * 270, hy + math.sin(ang) * 23)
                head = (x, y - 100)
                px, py = lerp(src[0], head[0], k), lerp(src[1], head[1], k)
                pygame.draw.line(s, ui.mix((3, 2, 10), (120, 190, 255), 0.35), src, head, 1)
                pygame.draw.rect(s, (220, 240, 255), (px - 2, py - 2, 4, 4))
                if k > 0.7:
                    ui.text(s, word, (px, py - 12), 12, (150, 210, 255), bold=True, anchor="center", shadow=False,
                            alpha=255 * (1 - k) * 3)
            ctx.assets.draw_character(s, x, y, ctx.victim_character(v), 104, "down", False, False, 0,
                                      v.get("color"))                                    # frozen: greyed, still
            pygame.draw.ellipse(s, (180, 220, 255), (x - 40, y - 4, 80, 12), 1)
            name = "YOU" if v["id"] == ctx.me_id else str(v["name"]).upper()
            ui.text(s, ui.fit(name, 12, 140, True), (x, y - 124), 12, (200, 220, 255), bold=True, anchor="center")
            if int(t * 3 + i) % 2:
                ui.text(s, "...", (x + 30, y - 108), 12, (200, 220, 255), bold=True, anchor="center")

    def render(self, s):
        t = self.t
        if t < 0.5:
            s.fill((8, 10, 30))
            self.caster(s, 330, H - 30, 300, "right")
            self._hand_seal(s, t)
            ui.text(s, "RYOIKI TENKAI", (CX, 70), 22, (170, 200, 255), bold=True, anchor="center",
                    alpha=255 * seg(t, 0.1, 0.3))
        elif t < 1.0:
            s.fill((8, 10, 30))
            self._six_eyes(s, t)
        elif t < 1.45:                                                                    # the barrier closes
            s.fill((8, 10, 30))
            self.caster(s, CX, H - 40, 260)
            k = ease_in(seg(t, 1.0, 1.42))
            rad = int(40 + k * 900)
            pygame.draw.circle(s, (0, 0, 0), (CX, CY), rad)
            for j in range(18):                                                          # ink edge
                a = j / 18 * math.tau + t * 2
                pygame.draw.circle(s, (0, 0, 0), (int(CX + math.cos(a) * rad), int(CY + math.sin(a) * rad)),
                                   26 + (j * 7) % 20)
            pygame.draw.circle(s, (120, 150, 255), (CX, CY), rad, 3)
            big_text(s, "DOMAIN EXPANSION", (CX, 90), 34, (220, 230, 255), alpha=255 * seg(t, 1.05, 1.2))
        else:
            self._void(s, t)
            self._victims(s, t)
            glow(s, (110, 200, 255), (CX, H - 140), 120, 60)
            self.caster(s, CX, H - 40, 200)                                              # the only one who moves
            k = pop(t, 1.5)
            if k:
                ab = 4 if int(t * 20) % 3 else 7
                stamp_text(s, "INFINITE VOID", (CX - ab, 318), 64, (255, 40, 120), k)
                stamp_text(s, "INFINITE VOID", (CX + ab, 318), 64, (40, 220, 255), k)
                stamp_text(s, "INFINITE VOID", (CX, 318), 64, (255, 255, 255), k)
            if t > 1.75:
                ui.text(s, "MURYOKUSHO", (CX, 366), 16, (170, 200, 255), bold=True, anchor="center",
                        alpha=255 * seg(t, 1.75, 2.0))
            if t > 2.1:
                ui.text(s, "INFINITE INFORMATION. NONE OF THEM CAN MOVE.", (CX, 400), 14, (200, 220, 255),
                        bold=True, anchor="center", alpha=255 * seg(t, 2.1, 2.4))
            if t > 2.8:
                ui.text(s, f"0.2 SECONDS INSIDE  -  {self.ctx.damage} POINTS GONE", (CX, 424), 14, (150, 200, 255),
                        bold=True, anchor="center", alpha=255 * seg(t, 2.8, 3.1))
        letterbox(s, seg(t, 0.0, 0.3), 40)
        if 1.42 < t < 1.6:
            wash(s, (255, 255, 255), 230 * (1 - seg(t, 1.42, 1.6)))


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

    SKIN, BAND, LINE = (250, 206, 168), (40, 70, 170), (50, 24, 30)

    def _arms(self, s, shoulder, hands):
        """Both arms from the shoulder to the cupped hands; drawn at half size, doubled."""
        k = 2
        ox, oy = int(min(shoulder[0], hands[0]) - 60), int(min(shoulder[1], hands[1]) - 60)
        w = int(abs(shoulder[0] - hands[0]) + 120) // k + 2
        h = int(abs(shoulder[1] - hands[1]) + 120) // k + 2
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        sx, sy = (shoulder[0] - ox) / k, (shoulder[1] - oy) / k
        hx, hy = (hands[0] - ox) / k, (hands[1] - oy) / k
        for dy in (-4, 4):                                                       # two arms, slightly apart
            a, b = (sx, sy + dy * 0.5), (hx - 6, hy + dy)
            pygame.draw.line(img, self.LINE, a, b, 12)
            pygame.draw.line(img, self.SKIN, a, b, 9)
            wx, wy = lerp(a[0], b[0], 0.78), lerp(a[1], b[1], 0.78)            # blue wristbands
            pygame.draw.circle(img, self.BAND, (round(wx), round(wy)), 4)
        for sign in (-1, 1):                                                     # cupped palms, heels together
            palm = pygame.Rect(0, 0, 11, 10)
            palm.center = (round(hx - 2), round(hy + sign * 5))
            pygame.draw.rect(img, self.LINE, palm.inflate(2, 2), border_radius=3)
            pygame.draw.rect(img, self.SKIN, palm, border_radius=3)
            for f in range(4):                                                   # fingers curled round the orb
                ang = math.radians(sign * (25 + f * 13))
                base = (palm.right - 2, palm.centery + sign * (f - 1.5) * 1.6)
                tip = (base[0] + math.cos(ang) * 8, base[1] + math.sin(ang) * 8)
                pygame.draw.line(img, self.LINE, base, tip, 4)
                pygame.draw.line(img, self.SKIN, base, tip, 2)
        s.blit(pygame.transform.scale(img, (w * k, h * k)), (ox, oy))

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
        charge = ease_out(seg(t, 0.0, 1.9))
        glow(s, (150, 210, 255), (230, 480), 150 + 20 * math.sin(t * 20), 70)       # aura
        body = self.caster(pygame.Surface((1, 1)), 230, H - 100, 250, "right")    # where the sprite lands
        shoulder = (body.centerx + body.w * 0.02, body.top + body.h * 0.60)       # chibi: big head, low shoulders
        hip = (body.centerx - body.w * 0.34, body.top + body.h * 0.74)            # cupped at his side
        front = (body.centerx + body.w * 0.66, body.top + body.h * 0.60)          # arms thrust forward
        start = (body.centerx + body.w * 0.22, body.top + body.h * 0.72)
        wind = ease_out(seg(t, 0.0, 0.25))                                         # hands pulled back
        thrust = ease_out(seg(t, 1.82, 1.95))                                      # ... then pushed out
        hx = lerp(lerp(start[0], hip[0], wind), front[0], thrust)
        hy = lerp(lerp(start[1], hip[1], wind), front[1], thrust)
        if t < 1.9:
            hx += math.sin(t * 50) * 2 * seg(t, 0.6, 1.8)                          # straining
        hx, hy = int(hx), int(hy)
        self.caster(s, 230, H - 100, 250, "right")
        self._arms(s, shoulder, (hx, hy))
        # particles converging on the hands
        if t < 1.95:
            for ang, dist, ph in self.parts:
                k = (t * 1.4 + ph) % 1.0
                d = dist * (1 - k)
                x, y = hx + math.cos(ang) * d, hy + math.sin(ang) * d
                pygame.draw.rect(s, (200, 240, 255), (x, y, 3, 3))
        # the orb
        rad = 8 + 22 * charge if t < 1.85 else 70        # a ball in his hands, then the blast
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
            self._arms(s, shoulder, (hx, hy))                                    # hands stay over the beam
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


# --- Epstein: summons his island ------------------------------------------------------------------------------
class IslandSummon(Scene):
    """The sea boils, the island rises - palms, the striped temple with its gold dome - a private
    jet circles in, the wave it throws up swamps everyone else, and the case file gets redacted."""
    duration = 4.6
    end_card_at = 3.6
    cues = ((0.0, "charge"), (0.7, "boom"), (1.75, "whoosh"), (2.2, "hit"), (2.9, "slash"))
    SEA_Y = 430

    def setup(self):
        r = self.rng
        n = max(1, min(6, len(self.ctx.victims)))
        self.rafts = [int(330 + (W - 420) * (i + 0.5) / n) for i in range(n)]
        self.spray = [(r.uniform(-1, 1), r.uniform(-1.6, -0.6), r.uniform(120, 420)) for _ in range(70)]
        self.waves = [(r.uniform(0, W), r.uniform(self.SEA_Y + 8, H), r.uniform(20, 60)) for _ in range(40)]
        self.redact = [r.uniform(0.45, 0.95) for _ in range(7)]

    def shake(self):
        amp = 5 * seg(self.t, 0.6, 0.8) * (1 - seg(self.t, 1.5, 1.8)) + 9 * (seg(self.t, 2.2, 2.25) - seg(self.t, 2.25, 2.6))
        if amp <= 0:
            return 0, 0
        return int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp))

    def _sky(self, s, t):
        dusk = seg(t, 0.4, 1.4)                         # the light turns as the island arrives
        for i in range(14):
            c0 = ui.mix((255, 170, 90), (250, 120, 120), i / 13)
            c1 = ui.mix((40, 20, 70), (140, 50, 90), i / 13)
            pygame.draw.rect(s, ui.mix(c0, c1, dusk), (0, i * self.SEA_Y // 14, W, self.SEA_Y // 14 + 1))
        pygame.draw.circle(s, ui.mix((255, 230, 140), (255, 120, 90), dusk), (W - 230, self.SEA_Y - 40), 80)

    def _palm(self, s, x, y, h, lean, t):
        top = (x + lean, y - h)
        pts = [(x + lean * (i / 6) ** 2, y - h * i / 6) for i in range(7)]
        pygame.draw.lines(s, (60, 36, 20), False, pts, 12)
        pygame.draw.lines(s, (130, 86, 46), False, pts, 8)
        sway = math.sin(t * 2 + x) * 6
        for a in (-150, -110, -60, -20, 20, 60):
            rad = math.radians(a)
            tip = (top[0] + math.cos(rad) * 70 + sway, top[1] + math.sin(rad) * 34 + 26)
            mid = ((top[0] + tip[0]) / 2, (top[1] + tip[1]) / 2 - 16)
            pygame.draw.polygon(s, (24, 110, 50), [top, mid, tip, (mid[0], mid[1] + 14)])
        pygame.draw.circle(s, (90, 60, 30), (int(top[0]), int(top[1]) + 6), 8)

    def _island(self, s, t):
        k = ease_out(seg(t, 0.6, 1.6))
        if k <= 0:
            return
        base = self.SEA_Y + 20 + int((1 - k) * 260)
        cx = CX + 120
        pygame.draw.ellipse(s, (232, 210, 150), (cx - 380, base - 70, 760, 150))          # sand
        pygame.draw.polygon(s, (40, 120, 60), [(cx - 300, base - 30), (cx - 180, base - 130), (cx - 20, base - 170),
                                               (cx + 150, base - 140), (cx + 300, base - 40)])   # hill
        pygame.draw.polygon(s, (30, 96, 50), [(cx + 20, base - 168), (cx + 150, base - 140), (cx + 300, base - 40),
                                              (cx + 120, base - 60)])
        tx, ty = cx - 40, base - 168                                                       # the temple
        body = pygame.Rect(tx - 70, ty - 90, 140, 90)
        pygame.draw.rect(s, (245, 245, 250), body)
        for i in range(0, 140, 20):
            pygame.draw.rect(s, (60, 110, 200), (body.x + i, body.y, 10, body.h))
        pygame.draw.rect(s, (30, 30, 50), body, 3)
        pygame.draw.rect(s, (30, 30, 60), (tx - 18, ty - 46, 36, 46))                      # door
        dome = pygame.Rect(tx - 60, ty - 150, 120, 120)
        clip = s.get_clip()
        s.set_clip(pygame.Rect(0, dome.y, W, dome.h // 2))                                 # top half only
        pygame.draw.ellipse(s, (240, 190, 60), dome)
        pygame.draw.ellipse(s, (180, 130, 30), dome, 3)
        s.set_clip(clip)
        pygame.draw.rect(s, (245, 245, 250), (body.x, body.y - 4, body.w, 6))
        pygame.draw.line(s, (240, 190, 60), (tx, ty - 150), (tx, ty - 176), 3)
        for px, h, lean in ((cx - 250, 150, -30), (cx - 170, 190, 20), (cx + 120, 170, 34), (cx + 230, 140, -16)):
            self._palm(s, px, base - 40, h, lean, t)
        if k < 1:                                                                          # water pouring off it
            for vx, vy, sp in self.spray:
                d = sp * seg(t, 0.6, 1.8)
                pygame.draw.rect(s, (220, 240, 255), (cx + vx * 360 + vx * d * 0.6, base - 80 + vy * d + 400 * d * d / 1e5,
                                                      4, 4))

    def _sea(self, s, t):
        pygame.draw.rect(s, (30, 90, 140), (0, self.SEA_Y, W, H - self.SEA_Y))
        for x, y, ln in self.waves:
            xx = (x + t * 40) % (W + 80) - 40
            pygame.draw.line(s, (90, 170, 210), (xx, y), (xx + ln, y), 2)

    def _jet(self, s, t):
        if not 1.6 < t < 3.2:
            return
        k = seg(t, 1.6, 3.2)
        x, y = lerp(-160, W + 160, k), 150 - math.sin(k * math.pi) * 40
        pygame.draw.line(s, (255, 255, 255), (x - 520, y + 6), (x - 60, y + 4), 3)        # contrail
        body = pygame.Rect(x - 70, y - 9, 140, 18)
        pygame.draw.ellipse(s, (235, 238, 245), body)
        pygame.draw.polygon(s, (200, 205, 220), [(x - 10, y), (x - 50, y + 34), (x - 30, y + 34), (x + 20, y)])
        pygame.draw.polygon(s, (200, 205, 220), [(x - 60, y - 4), (x - 78, y - 28), (x - 64, y - 28), (x - 44, y - 4)])
        for i in range(5):
            pygame.draw.rect(s, (40, 60, 100), (x - 28 + i * 14, y - 4, 7, 5))

    def _file(self, s, t):
        if t < 2.7:
            return
        k = ease_out(seg(t, 2.7, 2.95))
        doc = pygame.Rect(0, 0, 300, 250)
        doc.topright = (W - 30, 170 - int((1 - k) * 420))
        pygame.draw.rect(s, (0, 0, 0), doc.move(6, 8))
        pygame.draw.rect(s, (238, 232, 214), doc)
        ui.text(s, "CASE FILE", (doc.x + 20, doc.y + 18), 16, (40, 30, 30), bold=True, shadow=False)
        ui.text(s, "P. 1 / 3000", (doc.right - 20, doc.y + 22), 12, (90, 80, 70), bold=True, anchor="topright",
                shadow=False)
        for i, ln in enumerate(self.redact):
            y = doc.y + 56 + i * 24
            pygame.draw.rect(s, (150, 140, 120), (doc.x + 20, y + 6, doc.w - 40, 3))
            bar = seg(t, 2.95 + i * 0.05, 3.1 + i * 0.05)
            pygame.draw.rect(s, (10, 10, 10), (doc.x + 20, y, int((doc.w - 40) * ln * bar), 14))
        if t > 3.2:
            stamp_text(s, "REDACTED", (doc.centerx, doc.centery + 20), 40, (200, 30, 40), pop(t, 3.2, 0.12), 14)

    def render(self, s):
        t = self.t
        ctx = self.ctx
        self._sky(s, t)
        self._jet(s, t)
        self._sea(s, t)
        self._island(s, t)
        # the caster on his dock, arms up
        pygame.draw.rect(s, (90, 60, 36), (0, self.SEA_Y + 80, 260, 22))
        for x in (30, 120, 210):
            pygame.draw.rect(s, (70, 46, 28), (x, self.SEA_Y + 100, 14, 60))
        glow(s, (255, 200, 120), (140, self.SEA_Y), 120 + 20 * math.sin(t * 8), 60 * (1 - seg(t, 1.6, 2.0)))
        self.caster(s, 140, self.SEA_Y + 84, 220, "right")
        # everyone else bobbing on rafts in the foreground; the wave swamps them
        wave_k = seg(t, 2.05, 2.45)
        for i, v in enumerate(ctx.victims[:len(self.rafts)]):
            x = self.rafts[i]
            y = H - 70 + int(math.sin(t * 3 + i) * 5)
            sink = int(70 * ease_in(seg(t, 2.25 + i * 0.04, 2.7 + i * 0.04)))
            pygame.draw.rect(s, (120, 80, 40), (x - 50, y - 6 + sink, 100, 14))
            ctx.assets.draw_character(s, x, y + sink, ctx.victim_character(v), 92, "up", False, True, i * 97,
                                      v.get("color"))
            pygame.draw.rect(s, (30, 90, 140), (x - 70, y + 6, 140, H - y))                # water in front
            if sink > 10:
                ui.text(s, f"-{v['lost']}", (x, y - 120 - sink), 18, ui.BAD, bold=True, anchor="center")
            name = "YOU" if v["id"] == ctx.me_id else str(v["name"]).upper()
            ui.text(s, ui.fit(name, 12, 140, True), (x, y - 106 + sink // 2), 12, (255, 240, 220), bold=True,
                    anchor="center")
        if 0 < wave_k < 1:                                                                 # the wave rolls in
            wx = lerp(W + 100, -300, ease_in(wave_k))
            pygame.draw.polygon(s, (60, 140, 190), [(wx, H), (wx + 60, H - 160), (wx + 160, H - 190),
                                                    (wx + 260, H - 120), (wx + 300, H), ])
            pygame.draw.lines(s, (230, 245, 255), False, [(wx + 60, H - 160), (wx + 160, H - 190),
                                                          (wx + 260, H - 120)], 6)
        if t > 0.15:
            ui.text(s, "SUMMONING...", (CX, 52), 22, (255, 240, 220), bold=True, anchor="center",
                    alpha=255 * seg(t, 0.15, 0.35) * (1 - seg(t, 0.9, 1.1)))
        if t > 1.15:
            k = pop(t, 1.15)
            stamp_text(s, "THE ISLAND RISES", (CX + 4, 82), 54, (0, 0, 0), k)
            stamp_text(s, "THE ISLAND RISES", (CX, 78), 54, (255, 236, 200), k)
        if t > 1.5:
            ui.text(s, "LITTLE ST. JAMES  -  PRIVATE. NO GUESTS. NO QUESTIONS.", (CX, 128), 14, (255, 230, 200),
                    bold=True, anchor="center", alpha=255 * seg(t, 1.5, 1.8))
        self._file(s, t)
        letterbox(s, seg(t, 0.0, 0.3), 30)


# --- Sam Altman: steals their RAM ------------------------------------------------------------------------------
class RamHeist(Scene):
    """Sam walks down the row, pulls the sticks out of everyone's PC with his own hands,
    bags them and runs them into the data centre. Their PCs go OUT OF MEMORY."""
    duration = 4.8
    end_card_at = 3.85
    FLOOR = H - 150
    START, END = 0.45, 2.85            # the round of visits
    cues = ((0.0, "blip"), (3.0, "whoosh"), (3.35, "cash"))

    def setup(self):
        r = self.rng
        n = max(1, min(6, len(self.ctx.victims)))
        span = W - 520
        self.cols = [int(250 + span * (i + 0.5) / n) for i in range(n)]
        self.gb = [r.choice((16, 32, 64)) for _ in range(n)]
        self.slot = (self.END - self.START) / n
        self.dc = pygame.Rect(W - 190, self.FLOOR - 300, 170, 300)
        self.cues = self.cues + tuple((self._grab_at(i) + 0.05 * j, "blip") for i in range(n) for j in range(2))

    def _arrive_at(self, i):
        return self.START + i * self.slot + self.slot * 0.45

    def _grab_at(self, i):
        return self._arrive_at(i) + 0.02

    def _sam_x(self, t):
        stops = [x - 80 for x in self.cols]
        if t < self.START:
            return lerp(-120, stops[0], 0), False
        for i, sx in enumerate(stops):
            t0 = self.START + i * self.slot
            arrive = self._arrive_at(i)
            prev = -120 if i == 0 else stops[i - 1]
            if t < arrive:
                return lerp(prev, sx, seg(t, t0, arrive)), True
            if t < t0 + self.slot:
                return sx, False
        k = ease_in(seg(t, self.END, self.END + 0.5))
        return lerp(stops[-1], self.dc.centerx, k), k < 1

    def _stick(self, s, center, scale=1.0, angle=0.0):
        w, h = max(4, int(90 * scale)), max(3, int(22 * scale))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        img.fill((30, 120, 60))
        for i in range(5):
            pygame.draw.rect(img, (20, 20, 24), (5 * scale + i * 16 * scale, 4 * scale, 11 * scale, 10 * scale))
        for i in range(0, w, max(2, int(4 * scale))):
            pygame.draw.rect(img, (230, 190, 60), (i, h - 5 * scale, max(1, 2 * scale), 5 * scale))
        pygame.draw.rect(img, (16, 70, 34), img.get_rect(), max(1, int(2 * scale)))
        if angle:
            img = pygame.transform.rotate(img, angle)
        s.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))

    def _pc(self, s, x, k, gb, i):
        """Tower with its side panel off: two sticks in their slots until Sam takes them."""
        tower = pygame.Rect(x - 40, self.FLOOR - 120, 80, 120)
        pygame.draw.rect(s, (20, 22, 30), tower.inflate(6, 6))
        pygame.draw.rect(s, (60, 64, 80), tower)
        board = tower.inflate(-16, -20)
        pygame.draw.rect(s, (24, 80, 50), board)
        for j in range(2):
            slot = pygame.Rect(board.x + 10 + j * 16, board.y + 8, 8, 64)
            pygame.draw.rect(s, (12, 30, 20), slot)
            if k < 0.5 + j * 0.25:
                pygame.draw.rect(s, (40, 150, 70), slot.inflate(-2, 0))
                pygame.draw.rect(s, (230, 190, 60), (slot.x + 1, slot.bottom - 6, 6, 6))
        mon = pygame.Rect(x - 50, self.FLOOR - 220, 100, 70)                       # the screen on top
        pygame.draw.rect(s, (20, 22, 30), mon.inflate(8, 8))
        dead = k >= 1
        pygame.draw.rect(s, (20, 60, 200) if dead else (30, 40, 60), mon)
        if dead:
            ui.text(s, ":(", (mon.x + 10, mon.y + 6), 16, (255, 255, 255), bold=True, shadow=False)
            ui.text(s, "OUT OF", (mon.centerx, mon.y + 38), 12, (255, 255, 255), bold=True, anchor="center",
                    shadow=False)
            ui.text(s, "MEMORY", (mon.centerx, mon.y + 54), 12, (255, 255, 255), bold=True, anchor="center",
                    shadow=False)
        else:
            for j in range(4):
                pygame.draw.rect(s, (90, 255, 140), (mon.x + 10, mon.y + 10 + j * 14, 30 + ((j * 23 + i * 7) % 50), 6))
        pygame.draw.rect(s, (20, 22, 30), (x - 6, self.FLOOR - 150, 12, 30))
        left = int(round(gb * (1 - k)))
        ui.text(s, f"{left} GB", (x, self.FLOOR + 14), 14, (255, 110, 110) if dead else (160, 240, 190), bold=True,
                anchor="midtop")

    def render(self, s):
        t = self.t
        ctx = self.ctx
        for i in range(10):
            pygame.draw.rect(s, ui.mix((10, 18, 34), (26, 50, 70), i / 9), (0, i * H // 10, W, H // 10 + 1))
        pygame.draw.rect(s, (22, 26, 36), (0, self.FLOOR, W, H - self.FLOOR))
        pygame.draw.line(s, (70, 80, 110), (0, self.FLOOR), (W, self.FLOOR), 3)
        # the data centre on the right
        dc = self.dc
        pygame.draw.rect(s, (24, 28, 36), dc)
        pygame.draw.rect(s, (90, 100, 120), dc, 4)
        for row in range(7):
            for col in range(2):
                on = (row * 2 + col + int(t * 12)) % 5
                pygame.draw.rect(s, (90, 255, 140) if on else (30, 60, 40), (dc.x + 22 + col * 70, dc.y + 50 + row * 26,
                                                                              56, 8))
        ui.text(s, "STARGATE", (dc.centerx, dc.y + 18), 16, (220, 230, 255), bold=True, anchor="center")
        door = pygame.Rect(dc.centerx - 30, dc.bottom - 64, 60, 64)
        pygame.draw.rect(s, (255, 240, 180) if 3.2 < t < 3.5 else (10, 12, 18), door)
        # the victims and their PCs
        sam_x, walking = self._sam_x(t)
        carried = 0
        for i, v in enumerate(ctx.victims[:len(self.cols)]):
            x = self.cols[i]
            g = self._grab_at(i)
            k = seg(t, g, g + self.slot * 0.4)
            if k >= 0.5:
                carried += 1
            self._pc(s, x, k, self.gb[i], i)
            ctx.assets.draw_character(s, x + 70, self.FLOOR + 4, ctx.victim_character(v), 110,
                                      "left" if t < g + 0.4 else "down", False, True, i * 131, v.get("color"))
            name = "YOU" if v["id"] == ctx.me_id else str(v["name"]).upper()
            ui.text(s, ui.fit(name, 12, 130, True), (x + 70, self.FLOOR - 128), 12,
                    (255, 220, 120) if v["id"] == ctx.me_id else (220, 240, 255), bold=True, anchor="center")
            if 0 < k < 1:                                                       # sticks pulled into the bag
                for j in range(2):
                    kj = seg(k, j * 0.3, 0.6 + j * 0.3)
                    if 0 < kj < 1:
                        p0 = (x - 14 + j * 16, self.FLOOR - 80)
                        p1 = (sam_x + 30, self.FLOOR - 70)
                        bx = lerp(p0[0], p1[0], kj)
                        by = lerp(p0[1], p1[1], kj) - math.sin(kj * math.pi) * 70
                        self._stick(s, (bx, by), 0.7, kj * 360)
            if k >= 1 and t < g + self.slot * 0.4 + 0.5:
                ui.text(s, "HEY!", (x + 70, self.FLOOR - 150), 14, ui.BAD, bold=True, anchor="center")
        # Sam and his growing sack
        if t < self.END + 0.5:
            self.caster(s, sam_x, self.FLOOR + 4, 170, "right", moving=walking)
            size = 14 + 4 * carried
            sack = (int(sam_x - 46), int(self.FLOOR - 14 - size))
            pygame.draw.circle(s, (60, 40, 20), sack, size + 3)
            pygame.draw.circle(s, (170, 130, 80), sack, size)
            pygame.draw.line(s, (90, 60, 30), (sack[0] - 6, sack[1] - size), (sack[0] + 6, sack[1] - size - 10), 4)
            if carried:
                ui.text(s, "RAM", sack, 12, (60, 40, 20), bold=True, anchor="center", shadow=False)
        stolen = sum(self.gb[i] for i in range(len(self.cols)) if t >= self._grab_at(i) + self.slot * 0.4)
        ui.text(s, f"STOLEN: {stolen} GB", (40, 104), 16, (120, 200, 255), bold=True)
        title = "SAM ALTMAN IS STEALING YOUR RAM"
        big_text(s, title[:int(t * 40) + 1], (CX, 56), 30, (255, 255, 255))
        if t > 3.3:
            stamp_text(s, "THANKS FOR THE COMPUTE", (CX - 120, 210), 40, (255, 220, 120), pop(t, 3.3), 6)
        if t > 3.1:
            tick = "DRAM PRICES  +400%  ^^^   GPU  +900%  ^^^   YOUR SCORE  -10  vvv   "
            off = int(t * 220) % ui.text_width(tick, 14, True)
            ui.text(s, tick * 3, (-off, 140), 14, (120, 255, 160), bold=True)
        letterbox(s, seg(t, 0.0, 0.3), 30)


SCENES = {
    "gojo": InfiniteVoid,
    "sukuna": MalevolentKitchen,
    "mui-goku": Kamehameha,
    "trump": FiveBillion,
    "palantir-patrick": DroneStrike,
    "claude": CodeReview,
    "sam-altman": RamHeist,
    "epstein": IslandSummon,
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
        if cls is None:                                    # Mia, Leo: no scene of their own, a toast instead
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
