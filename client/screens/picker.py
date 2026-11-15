"""Character select: a full-screen grid of the ten characters, opened from the room.

Mouse: hover to preview, click to pick. Keys: arrows to move, Enter to pick,
1-9 / 0 to pick directly, Esc to close. Several players may pick the same
character; coloured chips on each card show who already did.
"""
import pygame

from common import characters as CH
from client import ui
from client.assets import color_of
from client.screens.base import CANVAS_H, CANVAS_W

COLS = 5
CARD_H_SPRITE = 120          # sprite height on a card


class CharacterPicker:
    def __init__(self, app, current, on_pick, on_close):
        self.app = app
        self.current = current
        self.focus = current if CH.valid(current) else 0
        self.hover = None
        self.on_pick = on_pick
        self.on_close = on_close
        self.box = pygame.Rect(0, 0, 1180, 640)
        self.box.center = (CANVAS_W // 2, CANVAS_H // 2)
        gap, top = 14, self.box.y + 78
        cw = (self.box.w - 56 - gap * (COLS - 1)) // COLS
        ch = (self.box.bottom - 92 - top - gap) // 2
        self.cards = [pygame.Rect(self.box.x + 28 + (i % COLS) * (cw + gap), top + (i // COLS) * (ch + gap), cw, ch)
                      for i in range(CH.COUNT)]
        self.btn_done = ui.Button((self.box.right - 28 - 170, self.box.bottom - 70, 170, 48), "DONE",
                                  self.close, color=ui.BTN_GO, size=16)

    def close(self):
        self.on_close()

    def pick(self, i):
        self.current = self.focus = i
        self.on_pick(i)
        self.on_close()

    def _card_at(self, pos):
        return next((i for i, r in enumerate(self.cards) if r.collidepoint(pos)), None)

    def handle(self, e):
        """Takes every event while open (the room behind does not react)."""
        if self.btn_done.handle(e):
            return
        if e.type == pygame.MOUSEMOTION:
            self.hover = self._card_at(e.pos)
            if self.hover is not None:
                self.focus = self.hover
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            i = self._card_at(e.pos)
            if i is not None:
                self.pick(i)
            elif not self.box.collidepoint(e.pos):
                self.close()
        elif e.type == pygame.KEYDOWN:
            k = e.key
            if k in (pygame.K_ESCAPE, pygame.K_c):
                self.close()
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.pick(self.focus)
            elif k in (pygame.K_LEFT, pygame.K_a):
                self.focus = (self.focus - 1) % CH.COUNT
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.focus = (self.focus + 1) % CH.COUNT
            elif k in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                self.focus = (self.focus + COLS) % CH.COUNT
            elif e.unicode and e.unicode.isdigit():
                i = (int(e.unicode) - 1) % 10
                if i < CH.COUNT:
                    self.pick(i)

    def draw(self, surf, roster, me_id):
        assets = self.app.assets
        ui.dim(surf, 170)
        box = self.box
        ui.panel(surf, box, ui.PANEL, 18, ui.CYAN, 248)
        ui.text(surf, "CHOOSE YOUR CHARACTER", (box.x + 28, box.y + 22), 26, ui.ICE, bold=True)
        ui.text(surf, "SAME PICK AS SOMEONE ELSE? FINE - YOUR NAME FLOATS ABOVE YOU",
                (box.right - 28, box.y + 32), 12, ui.MUTED, bold=True, anchor="topright")

        who = {}                                       # character -> colours of players on it
        for p in roster:
            if p.get("status") == "connected" and CH.valid(p.get("character")):
                who.setdefault(p["character"], []).append((p["id"] == me_id, p["color"]))

        t = pygame.time.get_ticks()
        for i, r in enumerate(self.cards):
            sel = i == self.current
            foc = i == self.focus
            ui.panel(surf, r, ui.PANEL_HI if foc else ui.HULL, 10,
                     ui.WARN if sel else ui.CYAN if foc else ui.TEAL_DK, 255, rivets=False)
            # stage light
            feet = (r.centerx, r.bottom - 50)
            ring = pygame.Rect(0, 0, 96, 22)
            ring.center = feet
            pygame.draw.ellipse(surf, ui.INK, ring)
            pygame.draw.ellipse(surf, ui.WARN if sel else ui.CYAN if foc else ui.TEAL_DK, ring, 2)
            # focused card walks across, the others idle
            if foc:
                d = ("right", "down", "left", "down")[(t // 1400) % 4]
                assets.draw_character(surf, *feet, i, CARD_H_SPRITE, d, True, phase_ms=i * 97)
            else:
                assets.draw_character(surf, *feet, i, CARD_H_SPRITE, "down", False, phase_ms=i * 97)
            name = ui.fit(CH.CHARACTERS[i]["name"].upper(), 14, r.w - 16, True)
            ui.text(surf, name, (r.centerx, r.bottom - 22), 14, ui.WARN if sel else ui.ICE, bold=True,
                    anchor="center")
            ui.keycap(surf, str((i + 1) % 10), (r.x + 8, r.y + 8), size=12)
            if sel:
                tag = pygame.Rect(0, 0, 76, 22)
                tag.topright = (r.right - 8, r.y + 8)
                ui.plate(surf, tag, ui.WARN, 255, 3)
                ui.text(surf, "YOURS", tag.center, 12, ui.INK, bold=True, anchor="center", shadow=False)
            # who else plays it
            x = r.x + 12
            for mine, col in sorted(who.get(i, []))[:8]:
                if not mine:
                    ui.chip(surf, color_of(col), (x + 6, r.bottom - 40), 10)
                    x += 16

        hint = "CLICK OR 1-0 TO PICK    ARROWS + ENTER    ESC TO CLOSE"
        ui.text(surf, hint, (box.x + 28, self.btn_done.rect.centery), 12, ui.MUTED, bold=True, anchor="midleft")
        self.btn_done.draw(surf)
