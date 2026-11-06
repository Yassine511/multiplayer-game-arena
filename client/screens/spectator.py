"""Admin view: the whole map and live scores, no movement and no answering."""
from client import ui
from client.qr import make_qr_surface
from client.screens.base import CANVAS_H, CANVAS_W
from client.screens.game import GameScreen


class SpectatorScreen(GameScreen):
    spectator = True

    def __init__(self, app, state=None, countdown=None):
        super().__init__(app, state=state, countdown=countdown)
        self._qr_for = None
        self._qr = None

    def _draw_sidebar_footer(self, surf, x0, cx):
        room = self.app.room
        ui.text(surf, "SPECTATING", (cx, CANVAS_H - 250), 16, ui.WARN, bold=True, anchor="midtop")
        if not room:
            return
        ui.text(surf, room["code"], (cx, CANVAS_H - 226), 34, ui.ACCENT, bold=True, anchor="midtop")
        if room["join_string"] != self._qr_for:
            self._qr_for = room["join_string"]
            self._qr = make_qr_surface(room["join_string"], 160)
        if self._qr is not None:
            r = self._qr.get_rect(midtop=(cx, CANVAS_H - 175))
            ui.panel(surf, r.inflate(10, 10), (255, 255, 255), 6, None)
            surf.blit(self._qr, r)
        live = len([s for s in self.scores if s.get("connected", True)])
        ui.text(surf, f"{live} connected", (CANVAS_W - 16, 112), 16, ui.MUTED, anchor="topright")
