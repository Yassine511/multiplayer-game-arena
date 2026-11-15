"""Art for the station: map, backdrops, room cards, players and terminals.

Files live in client/assets/ (tools/import_art.py fills it from Map_and_rooms/):

  map.png                       the whole station; world 1280x720 stretched over it
  bg_login.jpg / bg_space.jpg / bg_scene.jpg      screen backdrops
  rooms/<slug>.png              one card per room, shown on its terminal

  characters/<slug>.png + characters/characters.json
                                the ten playable characters (tools/import_characters.py)

If a character's art is missing, that player is drawn as a small astronaut in
their colour instead.
"""
import json
import math
import os

import pygame

from common import characters, config, map_data
from client import ui

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

PALETTE = [
    (72, 148, 250), (240, 92, 92), (84, 208, 128), (250, 196, 64), (176, 112, 240),
    (48, 212, 222), (248, 138, 56), (242, 110, 190), (164, 214, 76), (214, 218, 232),
]
GREY = (110, 114, 140)

# screen px per world unit in the player's camera view: the art's own density, so the
# map is shown pixel for pixel (no resampling blur)
VIEW_ZOOM = map_data.ART_W / config.WORLD_W
SPRITE_W, SPRITE_H = 16, 20
CHAR_H_PER_SCALE = 24        # character height in screen px per sprite "scale" (3 in game -> 72 px)


def color_of(idx):
    return PALETTE[idx % len(PALETTE)] if idx is not None else GREY


class Assets:
    def __init__(self, canvas_size):
        self.canvas_size = canvas_size
        self._files = {}
        self._maps = {}
        self._cards = {}
        self._sprites = {}
        self._backdrops = {}
        self._cones = {}
        self.chars = CharacterArt()
        self._map_src = self._load("map.png", alpha=False)
        if self._map_src is None:
            self._map_src = self._fallback_map()

    # --- loading ------------------------------------------------------------------------
    def _load(self, name, alpha=True):
        if name in self._files:
            return self._files[name]
        path = os.path.join(ASSET_DIR, *name.split("/"))
        img = None
        if os.path.exists(path):
            try:
                img = pygame.image.load(path)
                img = img.convert_alpha() if alpha else img.convert()
            except pygame.error as e:
                print(f"[assets] cannot load {name}: {e}")
        self._files[name] = img
        return img

    def _fallback_map(self):
        """No map.png: paint the floor grid so the game is still playable."""
        s = pygame.Surface((map_data.COLS, map_data.ROWS))
        s.fill(ui.HULL)
        for cy in range(map_data.ROWS):
            for cx in range(map_data.COLS):
                if map_data.walkable_cell(cx, cy):
                    s.set_at((cx, cy), ui.TEAL)
        return s.convert()

    def map_surface(self, zoom):
        """The map scaled to `zoom` screen px per world unit (cached)."""
        key = round(zoom, 3)
        if key not in self._maps:
            size = (int(config.WORLD_W * zoom), int(config.WORLD_H * zoom))
            sw, sh = self._map_src.get_size()
            if abs(size[0] - sw) <= 4 and abs(size[1] - sh) <= 4:
                self._maps[key] = self._map_src            # native size: blit the art untouched
            elif size[0] > sw:
                self._maps[key] = pygame.transform.scale(self._map_src, size).convert()
            else:                                          # shrinking (minimap): smooth is sharper
                self._maps[key] = pygame.transform.smoothscale(self._map_src, size).convert()
        return self._maps[key]

    def backdrop(self, name, **kw):
        if name not in self._backdrops:
            self._backdrops[name] = ui.Backdrop(self._load(f"bg_{name}.jpg", alpha=False), self.canvas_size, **kw)
        return self._backdrops[name]

    def room_card(self, slug, max_w, max_h):
        """Room illustration fitted into max_w x max_h, or None."""
        key = (slug, max_w, max_h)
        if key not in self._cards:
            img = self._load(f"rooms/{slug}.png")
            if img is not None:
                w, h = img.get_size()
                k = min(max_w / w, max_h / h)
                img = pygame.transform.smoothscale(img, (max(1, int(w * k)), max(1, int(h * k)))).convert_alpha()
            self._cards[key] = img
        return self._cards[key]

    # --- players ------------------------------------------------------------------------
    def player_sprite(self, color_idx, direction="down", frame=0, scale=3, connected=True):
        """Astronaut in the player's colour (fallback art). frame: 0 standing, 1 / 2 walking."""
        key = (color_idx, direction, frame, scale, connected)
        img = self._sprites.get(key)
        if img is None:
            img = _draw_astronaut(color_of(color_idx) if connected else GREY, direction, frame)
            img = pygame.transform.scale(img, (img.get_width() * scale, img.get_height() * scale)).convert_alpha()
            if not connected:
                img = img.copy()
                img.fill((150, 150, 170, 150), special_flags=pygame.BLEND_RGBA_MULT)
            self._sprites[key] = img
        return img

    def draw_character(self, surf, sx, sy, character, height, direction="down", moving=False,
                       connected=True, phase_ms=0, color_idx=None):
        """Draw a character with its feet on (sx, sy) and return its rect. Without its art,
        the player's astronaut is drawn instead."""
        img, anchor, lift = self.chars.frame(character, direction, moving, height, connected, phase_ms)
        if img is None:
            scale = max(1, round(height / CHAR_H_PER_SCALE))
            t = pygame.time.get_ticks()
            frame = (1 + (t // 140) % 2) if moving else 0
            img = self.player_sprite(color_idx, direction, frame, scale, connected)
            rect = img.get_rect(midbottom=(int(sx), int(sy) + scale))
        else:
            rect = img.get_rect(topleft=(int(sx) - anchor[0], int(sy) - anchor[1] - lift))
        surf.blit(img, rect)
        return rect

    def draw_player(self, surf, sx, sy, color_idx, direction, name, me=False, connected=True,
                    moving=False, scale=3, label=True, character=None):
        """(sx, sy) is where the feet stand, in screen px."""
        t = pygame.time.get_ticks()
        sx, sy = int(sx), int(sy)
        sh = pygame.Rect(0, 0, 9 * scale, 3 * scale)
        sh.center = (sx, sy)
        pygame.draw.ellipse(surf, (10, 12, 40), sh)
        height = CHAR_H_PER_SCALE * scale
        rect = self.draw_character(surf, sx, sy, character, height, direction, moving, connected,
                                   (color_idx or 0) * 137, color_idx)
        if not label:
            return rect
        size = 14 if scale >= 3 else 12
        tag = ui.fit(name, size, 150, True) + ("" if connected else " (off)")
        tw = ui.text_width(tag, size, True)
        bg = pygame.Rect(0, 0, tw + 10, size + 8)
        bg.midbottom = (sx, sy - height - 4)        # fixed height: the plate never jitters with the frames
        ui.plate(surf, bg, ui.INK, 170, 2)
        ui.text(surf, tag, (bg.centerx, bg.centery), size,
                (ui.ICE if me else color_of(color_idx)) if connected else ui.MUTED, bold=True, anchor="center")
        if me:
            ay = bg.top - 8 + int(math.sin(t / 200) * 3)
            pygame.draw.polygon(surf, ui.INK, [(sx - 9, ay - 8), (sx + 9, ay - 8), (sx, ay + 4)])
            pygame.draw.polygon(surf, ui.CYAN, [(sx - 6, ay - 6), (sx + 6, ay - 6), (sx, ay + 1)])
        return rect

    # --- terminals ----------------------------------------------------------------------
    def draw_terminal(self, surf, sx, sy, t, claimer_color=None, locked_s=0.0, highlight=False, scale=1.0):
        """Holographic beacon floating over the console at screen (sx, sy)."""
        sx, sy = int(sx), int(sy)
        now = pygame.time.get_ticks() / 1000
        cooldown = t["state"] == "cooldown"
        locked = locked_s > 0 and not cooldown
        color = (claimer_color or ui.MUTED) if cooldown else ui.BAD if locked else ui.CYAN
        pulse = 0.5 + 0.5 * math.sin(now * 3.2 + t["terminal_id"])
        u = max(1, int(round(2 * scale)))                      # beacon pixel size

        # ring on the floor
        rw, rh = int((30 + (10 if highlight else 4) * pulse) * scale), int((11 + 3 * pulse) * scale)
        ring = pygame.Rect(0, 0, rw * 2, rh * 2)
        ring.center = (sx, sy)
        pygame.draw.ellipse(surf, ui.INK, ring.inflate(u * 2, u * 2), u * 3)
        pygame.draw.ellipse(surf, color if not cooldown else ui.shade(color, 0.7), ring, u)

        # light cone and floating screen
        bob = int(math.sin(now * 2.1 + t["terminal_id"] * 1.7) * 2 * scale) if not cooldown else 0
        w, h = 11 * u, 8 * u
        scr = pygame.Rect(0, 0, w, h)
        scr.midbottom = (sx, sy - int(13 * scale) + bob)
        cw, chh = w + 8 * u, sy - scr.bottom + 2
        if chh > 2:
            key = (cw, chh, u, color)
            cone = self._cones.get(key)
            if cone is None:
                cone = pygame.Surface((cw, chh), pygame.SRCALPHA)
                pygame.draw.polygon(cone, (*color, 54),
                                    [(0 + 2 * u, 0), (cw - 2 * u, 0), (cw // 2 + u, chh), (cw // 2 - u, chh)])
                if len(self._cones) > 400:
                    self._cones.clear()
                self._cones[key] = cone = cone.convert_alpha()
            surf.blit(cone, (sx - cw // 2, scr.bottom))
        pygame.draw.rect(surf, ui.INK, scr.inflate(u * 2, u * 2))
        pygame.draw.rect(surf, color, scr)
        inner = scr.inflate(-u * 2, -u * 2)
        pygame.draw.rect(surf, (10, 22, 52) if not cooldown else (26, 28, 50), inner)
        if cooldown:                                            # claimed: drain bar
            frac = max(0.0, min(1.0, t.get("ready_in", 0) / config.TERMINAL_COOLDOWN_S))
            pygame.draw.rect(surf, color, (inner.x + u, inner.centery - u // 2, int((inner.w - 2 * u) * frac), u))
        elif locked:                                            # locked for me: X
            for i in range(4):
                pygame.draw.rect(surf, ui.BAD, (inner.x + u + i * u, inner.y + i * u, u, u))
                pygame.draw.rect(surf, ui.BAD, (inner.right - 2 * u - i * u, inner.y + i * u, u, u))
        else:                                                   # ready: prompt  >_
            pygame.draw.rect(surf, color, (inner.x + u, inner.y + u, u, u))
            pygame.draw.rect(surf, color, (inner.x + 2 * u, inner.y + 2 * u, u, u))
            pygame.draw.rect(surf, color, (inner.x + u, inner.y + 3 * u, u, u))
            if int(now * 2.5 + t["terminal_id"]) % 2:
                pygame.draw.rect(surf, ui.ICE, (inner.x + 4 * u, inner.y + 3 * u, 3 * u, u))

        size = 14 if scale >= 1.5 else 12
        label = f"T{t['terminal_id']}"
        if cooldown and t.get("ready_in", 0) > 0:
            label += f"  {math.ceil(t['ready_in'])}s"
        elif locked:
            label += f"  LOCK {math.ceil(locked_s)}s"
        tw = ui.text_width(label, size, True)
        bg = pygame.Rect(0, 0, tw + 12, size + 8)
        bg.midbottom = (sx, scr.top - 3 * u)
        ui.plate(surf, bg, ui.INK, 215, 2)
        ui.text(surf, label, (bg.centerx, bg.centery), size, color, bold=True, anchor="center")


# --- characters ---------------------------------------------------------------------------------
class CharacterArt:
    """The ten baked character atlases. Each frame is scaled once per height and cached,
    so drawing a character is a single blit. prewarm() fills the cache for a size ahead
    of time, keeping the scaling out of animated frames."""

    def __init__(self):
        self.target_h = 160
        self.meta = {}
        self.atlas = {}
        self._cache = {}
        folder = os.path.join(ASSET_DIR, "characters")
        try:
            with open(os.path.join(folder, "characters.json")) as f:
                data = json.load(f)
            self.target_h = data["target_h"]
            for ch in characters.CHARACTERS:
                slug = ch["slug"]
                if slug not in data["characters"]:
                    continue
                img = pygame.image.load(os.path.join(folder, f"{slug}.png")).convert_alpha()
                self.atlas[slug] = img
                self.meta[slug] = data["characters"][slug]
        except (OSError, KeyError, ValueError, pygame.error) as e:
            print(f"[assets] character art unavailable ({e}); drawing astronauts")

    def has(self, character):
        return characters.valid(character) and characters.CHARACTERS[character]["slug"] in self.atlas

    def anim(self, character, direction, moving):
        """(atlas row, frame count, ms per frame, hop) for a pose."""
        m = self.meta[characters.CHARACTERS[character]["slug"]]
        d = direction if direction in ("up", "down", "left", "right") else "down"
        row, ms, hop = m["anims"][f"{'walk' if moving else 'idle'}_{d}"]
        return row, m["frames"][row], ms, hop

    def scaled(self, character, row, i, height, connected=True):
        """(surface, feet anchor) of one frame, scaled so the idle pose is `height` px."""
        key = (character, row, i, height, connected)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        slug = characters.CHARACTERS[character]["slug"]
        m = self.meta[slug]
        cw, ch = m["cell"]
        img = self.atlas[slug].subsurface((i * cw, row * ch, cw, ch))
        k = height / self.target_h
        if abs(k - 1) > 1e-3:
            img = pygame.transform.smoothscale(img, (max(1, round(cw * k)), max(1, round(ch * k))))
        else:
            img = img.copy()
        if not connected:
            if hasattr(pygame.transform, "grayscale"):
                img = pygame.transform.grayscale(img)
            img.fill((150, 150, 170, 150), special_flags=pygame.BLEND_RGBA_MULT)
        hit = (img.convert_alpha(), (round(m["anchor"][0] * k), round(m["anchor"][1] * k)))
        self._cache[key] = hit
        return hit

    def frame(self, character, direction, moving, height, connected=True, phase_ms=0):
        """(surface, anchor, lift px) for this instant, or (None, None, 0) without art."""
        if not self.has(character):
            return None, None, 0
        row, n, ms, hop = self.anim(character, direction, moving)
        t = pygame.time.get_ticks() + phase_ms
        img, anchor = self.scaled(character, row, (t // ms) % n, height, connected)
        lift = 0
        if hop:                                     # single-pose art: a light hop while walking
            lift = int(abs(math.sin(t / (ms * 1.3))) * height * 0.06)
        return img, anchor, lift

    def prewarm(self, height, chars=None):
        for c in (range(characters.COUNT) if chars is None else chars):
            if self.has(c):
                m = self.meta[characters.CHARACTERS[c]["slug"]]
                for row, n in enumerate(m["frames"]):
                    for i in range(n):
                        self.scaled(c, row, i, height)


# --- the placeholder astronaut -----------------------------------------------------------------
_HELM = (238, 243, 250)
_HELM_SH = (176, 190, 222)
_VISOR = (22, 30, 78)
_GLINT = (130, 226, 244)
_BOOT = (38, 42, 84)


def _draw_astronaut(color, direction, frame):
    """16x20 pixel astronaut with a one-pixel ink outline (18x22 surface)."""
    s = pygame.Surface((SPRITE_W, SPRITE_H), pygame.SRCALPHA)
    dark = ui.shade(color, 0.68)
    light = ui.shade(color, 1.25)

    def px(c, x, y, w=1, h=1):
        s.fill(c, (x, y, w, h))

    side = direction in ("left", "right")
    # helmet
    px(_HELM, 5, 1, 6, 1)
    px(_HELM, 4, 2, 8, 1)
    px(_HELM, 3, 3, 10, 5)
    px(_HELM, 4, 8, 8, 1)
    px(_HELM_SH, 4, 8, 8, 1)
    px(_HELM_SH, 12, 4, 1, 4)
    px(color, 6, 1, 4, 1)                       # colour band on top
    if direction == "down":
        px(_VISOR, 5, 4, 6, 3)
        px(_GLINT, 6, 4, 2, 1)
        px(_GLINT, 5, 5, 1, 1)
    elif side:
        px(_VISOR, 3, 4, 5, 3)
        px(_GLINT, 4, 4, 2, 1)
    else:
        px(_HELM_SH, 5, 6, 6, 1)
    # body
    if side:
        px(dark, 10, 9, 3, 6)                   # backpack behind
        px(_HELM_SH, 11, 10, 1, 1)
        px(color, 5, 9, 6, 6)
        px(dark, 5, 14, 6, 1)
        px(light, 7, 10, 2, 4)                  # arm
        px(_HELM, 7, 13, 2, 1)
        legs = [(6, 2), (9, 2)]
    else:
        px(color, 4, 9, 8, 6)
        px(dark, 4, 14, 8, 1)
        px(dark, 3, 9, 1, 5)
        px(dark, 12, 9, 1, 5)
        px(_HELM, 3, 13, 1, 1)
        px(_HELM, 12, 13, 1, 1)
        if direction == "down":
            px(light, 6, 10, 4, 3)              # chest panel
            px(_GLINT, 7, 11, 1, 1)
            px(ui.WARN, 8, 11, 1, 1)
        else:
            px(dark, 5, 9, 6, 5)                # backpack
            px(_HELM_SH, 6, 10, 4, 1)
            px(_GLINT, 7, 12, 2, 1)
        legs = [(5, 2), (9, 2)]
    for i, (lx, lw) in enumerate(legs):
        lift = 1 if frame and (frame - 1) == i else 0
        px(dark, lx, 15, lw, 3 - lift)
        px(_BOOT, lx - (0 if side else (1 if i == 0 else 0)), 18 - lift, lw + (0 if side else 1), 1)
    if direction == "right":
        s = pygame.transform.flip(s, True, False)

    out = pygame.Surface((SPRITE_W + 2, SPRITE_H + 2), pygame.SRCALPHA)
    ink = pygame.mask.from_surface(s).to_surface(setcolor=(*ui.INK, 255), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(ink, (dx, dy))
    out.blit(s, (1, 1))
    return out
