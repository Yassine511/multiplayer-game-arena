import pygame

from common import characters as CH
from common import config
from common import protocol as P
from client import ui
from client.qr import make_qr_surface
from client.screens.base import CANVAS_W, Screen
from client.screens.picker import CARD_H_SPRITE, CharacterPicker

SHOW_H = 150                 # showcase sprite height
ROSTER_H = 30                # roster sprite height
# the showcase turns the character around: (direction, walking, seconds)
SHOWCASE = [("down", False, 2.2), ("right", True, 1.6), ("left", True, 1.6), ("down", True, 1.4)]


class RoomScreen(Screen):
    backdrop = "scene"

    def __init__(self, app):
        super().__init__(app)
        self.left = pygame.Rect(36, 32, 430, 656)
        self.right = pygame.Rect(CANVAS_W - 36 - 330, 32, 330, 408)
        self.brief = pygame.Rect(490, 458, 452, 230)
        self.pick = pygame.Rect(490, 32, 400, 408)
        bx, by, bw = self.left.x + 28, self.left.bottom - 76, self.left.w - 56
        self.btn_start = ui.Button((bx, by, bw - 142, 52), "START GAME", self.start, color=ui.BTN_GO, size=18)
        self.btn_leave = ui.Button((bx + bw - 130, by, 130, 52), "LEAVE", self.leave, color=ui.BTN_DANGER, size=16)
        pk = self.pick
        self.btn_prev = ui.Button((pk.x + 24, pk.y + 150, 48, 56), "<", lambda: self.step(-1), color=ui.BTN_QUIET, size=20)
        self.btn_next = ui.Button((pk.right - 72, pk.y + 150, 48, 56), ">", lambda: self.step(1), color=ui.BTN_QUIET, size=20)
        self.btn_all = ui.Button((pk.x + 24, pk.bottom - 72, pk.w - 48, 50), "ALL CHARACTERS  (C)", self.open_picker,
                                 size=16)
        self.picker = None
        self._qr_for = None
        self._qr = None
        # scale every frame used on this screen now, behind the screen fade, not mid-animation
        chars = app.assets.chars
        for h in (SHOW_H, CARD_H_SPRITE, ROSTER_H):
            chars.prewarm(h)
        if self._is_player() and not app.character_saved and not getattr(app, "character_prompted", False):
            app.character_prompted = True
            self.open_picker()            # first room ever: start on the character select

    # --- character ------------------------------------------------------------------------
    def _is_player(self):
        room, me = self.app.room, self.app.me
        if me is None or me.get("role") == "admin":
            return False
        return room is None or any(p["id"] == me["player_id"] for p in room.get("players", []))

    def my_character(self):
        room, me = self.app.room, self.app.me
        if room and me:
            for p in room.get("players", []):
                if p["id"] == me["player_id"] and CH.valid(p.get("character")):
                    return p["character"]
        return self.app.character

    def step(self, d):
        self.app.set_character((self.my_character() + d) % CH.COUNT)
        self.show_t0 = pygame.time.get_ticks()

    def open_picker(self):
        self.picker = CharacterPicker(self.app, self.my_character(), self.app.set_character, self.close_picker)

    def close_picker(self):
        self.picker = None

    def start(self):
        self.app.net.send(P.msg(P.START_GAME))

    def leave(self):
        from client.screens.lobby import LobbyScreen
        self.app.net.send(P.msg(P.LEAVE_ROOM))
        self.app.room = None
        self.app.set_screen(LobbyScreen(self.app))

    def _is_host(self):
        room, me = self.app.room, self.app.me
        return bool(room and me and room["host"] == me["player_id"])

    def handle_event(self, e):
        if self.picker is not None:
            self.picker.handle(e)
            return
        if self._is_host():
            self.btn_start.handle(e)
        self.btn_leave.handle(e)
        if self._is_player():
            for b in (self.btn_prev, self.btn_next, self.btn_all):
                b.handle(e)
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_c:
                    self.open_picker()
                elif e.key == pygame.K_LEFT:
                    self.step(-1)
                elif e.key == pygame.K_RIGHT:
                    self.step(1)

    def handle_msg(self, m):
        t = m["type"]
        if t == P.GAME_COUNTDOWN:
            self.app.set_screen(self.app.make_game_screen(countdown=m["seconds"]))
        elif t == P.GAME_STARTED:
            self.app.set_screen(self.app.make_game_screen(state=m))
        else:
            super().handle_msg(m)

    def qr_surface(self, data):
        if data != self._qr_for:
            self._qr_for = data
            self._qr = make_qr_surface(data, 222)
        return self._qr

    def draw(self, surf):
        room = self.app.room
        if room is None:
            ui.text(surf, "DOCKING...", (CANVAS_W // 2, 340), 30, ui.ICE, bold=True, anchor="center")
            return
        assets = self.app.assets
        left = self.left
        ui.panel(surf, left, ui.PANEL, 18, ui.CYAN, 236)
        x = left.x + 28

        # code
        ui.text(surf, "ROOM CODE", (x, left.y + 20), 14, ui.MUTED, bold=True)
        ui.text(surf, room["code"], (x - 3, left.y + 38), 68, ui.WARN, bold=True)
        n = len([p for p in room["players"] if p["status"] == "connected"])
        need = room.get("min", 3)
        ready = n >= need
        ui.text(surf, f"HOST  {ui.fit(room['host_name'], 14, 150, True).upper()}", (x, left.y + 128), 14, ui.ICE, bold=True)
        ui.text(surf, f"{n} / {room['max']} CREW", (left.right - 28, left.y + 128), 14,
                ui.GOOD if ready else ui.WARN, bold=True, anchor="topright")
        # seats
        for i in range(room["max"]):
            c = ui.GOOD if i < n and ready else ui.WARN if i < n else ui.shade(ui.MUTED, 0.45)
            pygame.draw.rect(surf, ui.INK, (x + i * 38, left.y + 154, 32, 10))
            pygame.draw.rect(surf, c, (x + i * 38 + 2, left.y + 156, 28, 6))

        # roster
        ui.heading(surf, "CREW", (x, left.y + 182), left.w - 56, ui.CYAN, 14)
        y = left.y + 210
        roster = room["players"][:10]
        bottom = self.btn_start.rect.y - (34 if room.get("spectators") else 10)
        row_h = min(36, (bottom - y) // max(1, len(roster)))
        for p in roster:
            on = p["status"] == "connected"
            me = self.app.me and p["id"] == self.app.me["player_id"]
            if me:
                pygame.draw.rect(surf, ui.PANEL_HI, (x - 8, y - 1, left.w - 40, row_h - 2))
            mid = y + row_h // 2 - 2
            assets.draw_character(surf, x + 16, y + row_h - 3, p.get("character"), min(ROSTER_H, row_h - 4),
                                  "down", False, on, p["color"] * 137, p["color"])
            name = ui.fit(p["name"], 20, 200)
            r = ui.text(surf, name, (x + 46, mid), 20, ui.ICE if on else ui.MUTED, anchor="midleft")
            tx = r.right + 10
            flags = [("YOU", ui.CYAN)] if me else []
            if p["id"] == room["host"]:
                flags.append(("HOST", ui.WARN))
            if not on:
                flags.append(("OFFLINE", ui.BAD))
            for flag, col in flags:
                tx = ui.text(surf, flag, (tx, mid + 1), 12, col, bold=True, anchor="midleft").right + 8
            y += row_h
        if room.get("spectators"):
            ui.text(surf, f"{room['spectators']} SPECTATOR(S) WATCHING", (x, self.btn_start.rect.y - 26), 12,
                    ui.MUTED, bold=True)

        if self._is_host():
            self.btn_start.enabled = ready
            self.btn_start.label = "START GAME" if ready else f"NEED {need} CREW"
            self.btn_start.draw(surf)
        else:
            dots = "." * (1 + (pygame.time.get_ticks() // 400) % 3)
            ui.text(surf, "WAITING FOR HOST" + dots, (x, self.btn_leave.rect.centery), 14, ui.MUTED,
                    bold=True, anchor="midleft")
        self.btn_leave.draw(surf)

        if self._is_player():
            self._draw_showcase(surf)

        # join info + QR (the QR encodes the same join info as the code)
        right = self.right
        ui.panel(surf, right, ui.PANEL, 18, ui.CYAN, 236)
        ui.heading(surf, "SCAN TO JOIN", (right.x + 28, right.y + 20), right.w - 56, ui.CYAN, 14)
        qr = self.qr_surface(room["join_string"])
        if qr is not None:
            qr_rect = qr.get_rect(midtop=(right.centerx, right.y + 62))
            pygame.draw.rect(surf, ui.INK, qr_rect.inflate(20, 20))
            pygame.draw.rect(surf, (255, 255, 255), qr_rect.inflate(12, 12))
            surf.blit(qr, qr_rect)
            ty = qr_rect.bottom + 26
        else:
            ui.text(surf, "PIP INSTALL QRCODE", (right.centerx, right.y + 140), 14, ui.MUTED, bold=True, anchor="midtop")
            ui.text(surf, "TO SHOW A QR CODE", (right.centerx, right.y + 164), 14, ui.MUTED, bold=True, anchor="midtop")
            ty = right.y + 300
        ui.text(surf, "JOIN INFO", (right.centerx, ty), 12, ui.MUTED, bold=True, anchor="midtop")
        for i, line in enumerate(ui.wrap(room["join_string"], 12, right.w - 64, True)[:3]):
            ui.text(surf, line, (right.centerx, ty + 22 + i * 22), 12, ui.ICE, bold=True, anchor="midtop")

        # briefing
        brief = self.brief
        ui.panel(surf, brief, ui.PANEL, 14, ui.TEAL, 232)
        ui.heading(surf, "MISSION BRIEFING", (brief.x + 24, brief.y + 16), brief.w - 48, ui.CYAN, 14)
        secs = config.GAME_DURATION_S
        length = f"{secs // 60} MIN" if secs % 60 == 0 else f"{secs} S"
        steps = [("WASD", "WALK THE STATION"), ("E", "OPEN A TERMINAL NEXT TO YOU"),
                 ("1-4", f"ANSWER: FIRST CORRECT +{config.POINTS_CORRECT}"),
                 ("!", f"WRONG: {config.POINTS_WRONG} AND {config.WRONG_LOCKOUT_S} S LOCKOUT")]
        y = brief.y + 50
        for key, what in steps:
            k = ui.keycap(surf, key, (brief.x + 24, y), size=12)
            ui.text(surf, ui.fit(what, 12, brief.right - 28 - (brief.x + 100), True),
                    (brief.x + 100, k.centery), 12, ui.ICE, bold=True, anchor="midleft")
            y += 32
        ui.text(surf, f"HIGHEST SCORE AFTER {length} WINS", (brief.right - 28, brief.bottom - 22), 12,
                ui.WARN, bold=True, anchor="bottomright")
        if self.picker is not None:
            self.picker.draw(surf, room["players"], self.app.me and self.app.me["player_id"])
        self.draw_toasts(surf)

    def _draw_showcase(self, surf):
        """Your character on a stage, turning around; arrows cycle, C opens the grid."""
        pk = self.pick
        ui.panel(surf, pk, ui.PANEL, 18, ui.CYAN, 236)
        ui.heading(surf, "YOUR CHARACTER", (pk.x + 24, pk.y + 20), pk.w - 48, ui.CYAN, 14)
        c = self.my_character()
        feet = (pk.centerx, pk.y + 246)
        ring = pygame.Rect(0, 0, 150, 34)
        ring.center = feet
        pygame.draw.ellipse(surf, ui.INK, ring.inflate(8, 6))
        pygame.draw.ellipse(surf, ui.TEAL_DK, ring)
        pygame.draw.ellipse(surf, ui.CYAN, ring, 2)
        total = sum(s for _, _, s in SHOWCASE)
        t = (pygame.time.get_ticks() - getattr(self, "show_t0", 0)) / 1000 % total
        for d, walking, secs in SHOWCASE:
            if t < secs:
                break
            t -= secs
        self.app.assets.draw_character(surf, *feet, c, SHOW_H, d, walking)
        ui.text(surf, CH.name_of(c).upper(), (pk.centerx, pk.y + 276), 22, ui.WARN, bold=True, anchor="midtop")
        ui.text(surf, f"{c + 1} / {CH.COUNT}", (pk.centerx, pk.y + 306), 12, ui.MUTED, bold=True,
                anchor="midtop")
        for b in (self.btn_prev, self.btn_next, self.btn_all):
            b.draw(surf)
