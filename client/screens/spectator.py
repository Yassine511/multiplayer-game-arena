"""Admin view: the whole station and live scores, no movement and no answering."""
import pygame

from common import protocol as P
from client import ui
from client.assets import color_of
from client.qr import make_qr_surface
from client.screens.base import CANVAS_H, CANVAS_W
from client.screens.game import GameScreen


class SpectatorScreen(GameScreen):
    spectator = True
    sprite_scale = 2

    CONFIRM_S = 3.0

    def __init__(self, app, state=None, countdown=None):
        super().__init__(app, state=state, countdown=countdown)
        self._qr_for = None
        self._qr = None
        self.btn_stop = ui.Button((12, 74, 250, 46), "STOP GAME", self.stop, color=ui.BTN_DANGER, size=16)
        self.confirm_left = 0.0          # a first click arms the button; a second one within 3 s stops

    def stop(self):
        if self.confirm_left > 0:
            self.confirm_left = 0.0
            self.app.net.send(P.msg(P.STOP_GAME))
            self.toasts.add("Stopping the game...", ui.WARN, 2)
        else:
            self.confirm_left = self.CONFIRM_S

    def handle_event(self, e):
        if not self.app.is_host or self.cutscenes.active:
            return
        self.btn_stop.handle(e)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and self.confirm_left > 0:
            self.confirm_left = 0.0

    def update(self, dt):
        super().update(dt)
        self.confirm_left = max(0.0, self.confirm_left - dt)

    def _draw_stop(self, surf):
        if not self.app.is_host:
            return
        armed = self.confirm_left > 0
        self.btn_stop.label = "CLICK AGAIN TO STOP" if armed else "STOP GAME"
        self.btn_stop.size = 14 if armed else 16
        self.btn_stop.draw(surf)

    def _draw_hud(self, surf):
        """Everything sits in the strip of space around the hull, so no room is covered."""
        room = self.app.room
        self._timer_plate(surf, y=4)

        live = len([s for s in self.scores if s.get("connected", True)]) if self.scores else len(self.players)
        tag = pygame.Rect(12, 4, 250, 62)
        ui.panel(surf, tag, ui.PANEL, 10, ui.WARN, 240)
        ui.text(surf, "SPECTATING", (tag.x + 18, tag.y + 9), 16, ui.WARN, bold=True)
        ui.text(surf, f"{live} CONNECTED", (tag.x + 18, tag.y + 31), 12, ui.MUTED, bold=True)
        self._draw_stop(surf)

        # room code and QR in the top-right corner of space
        if room:
            code = pygame.Rect(CANVAS_W - 12 - 150, 4, 150, 62)
            ui.panel(surf, code, ui.PANEL, 10, ui.CYAN, 240)
            ui.text(surf, "ROOM CODE", (code.centerx, code.y + 9), 12, ui.MUTED, bold=True, anchor="midtop")
            ui.text(surf, room["code"], (code.centerx, code.y + 27), 20, ui.WARN, bold=True, anchor="midtop")
            if room["join_string"] != self._qr_for:
                self._qr_for = room["join_string"]
                self._qr = make_qr_surface(room["join_string"], 92)
            if self._qr is not None:
                r = self._qr.get_rect(topright=(CANVAS_W - 14, code.bottom + 10))
                pygame.draw.rect(surf, ui.INK, r.inflate(12, 12))
                pygame.draw.rect(surf, (255, 255, 255), r.inflate(6, 6))
                surf.blit(self._qr, r)

        # scoreboard along the bottom, 5 x 2
        rows = self._score_rows()[:10]
        cols, cw, ch, gap = 5, 240, 36, 8
        x0 = (CANVAS_W - (cols * cw + (cols - 1) * gap)) // 2
        y0 = CANVAS_H - 10 - 2 * ch - gap
        for i, s in enumerate(rows):
            r = pygame.Rect(x0 + (i % cols) * (cw + gap), y0 + (i // cols) * (ch + gap), cw, ch)
            on = s.get("connected", True)
            lead = i == 0 and s["score"] > 0
            ui.panel(surf, r, ui.PANEL, 6, ui.WARN if lead else ui.TEAL_DK, 236, rivets=False)
            ui.text(surf, str(i + 1), (r.x + 20, r.centery), 14, ui.WARN if lead else ui.MUTED,
                    bold=True, anchor="center")
            ui.chip(surf, color_of(s.get("color")) if on else ui.GREY, (r.x + 42, r.centery), 10)
            ui.text(surf, ui.fit(s["name"], 14, 112, True), (r.x + 56, r.centery), 14,
                    ui.ICE if on else ui.MUTED, bold=True, anchor="midleft")
            ui.text(surf, str(s["score"]), (r.right - 14, r.centery), 14, ui.ICE if on else ui.MUTED,
                    bold=True, anchor="midright")
