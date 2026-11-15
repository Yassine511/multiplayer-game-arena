import pygame

from common import characters as CH
from common import config
from common import protocol as P
from client import ui
from client.qr import make_qr_surface
from client.screens.base import CANVAS_W, Screen
from client.screens.picker import CARD_H_SPRITE, CharacterPicker
from client.screens.qeditor import CsvImport, QuestionEditor, import_csv

BANK_ROW_H = 34

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
        self.modal = None             # host: QuestionEditor or CsvImport
        self._qr_for = None
        self._qr = None
        # host: the question bank panel takes the middle column
        self.bank = pygame.Rect(490, 32, 400, 656)
        bk, half = self.bank, (self.bank.w - 48 - 12) // 2
        self.btn_write = ui.Button((bk.x + 24, bk.y + 120, half, 48), "WRITE", self.open_editor, color=ui.BTN_GO, size=16)
        self.btn_csv = ui.Button((bk.x + 36 + half, bk.y + 120, half, 48), "IMPORT CSV", self.open_csv, size=16)
        self.btn_default = ui.Button((bk.x + 24, bk.y + 176, half, 48), "BUILT-IN SET", self.use_default,
                                     color=ui.BTN_QUIET, size=16)
        self.btn_clear = ui.Button((bk.x + 36 + half, bk.y + 176, half, 48), "CLEAR ALL", self.clear_bank,
                                   color=ui.BTN_DANGER, size=16)
        self.list_rect = pygame.Rect(bk.x + 16, bk.y + 262, bk.w - 32, bk.h - 262 - 44)
        self.scroll = 0
        self.row_hits = []            # (delete-rect, index) drawn last frame
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
        if me is None or room is None:
            return False
        return any(p["id"] == me["player_id"] for p in room.get("players", []))

    # --- host: question bank ---------------------------------------------------------------
    def open_editor(self):
        self.modal = QuestionEditor(self.app, self.close_modal, self.toasts)

    def open_csv(self):
        self.modal = CsvImport(self.app, self.close_modal, self.toasts)

    def close_modal(self):
        self.modal = None

    def use_default(self):
        self.app.net.send(P.msg(P.SET_QUESTIONS, action="default"))

    def clear_bank(self):
        self.app.net.send(P.msg(P.SET_QUESTIONS, action="clear"))

    def remove_question(self, i):
        self.app.net.send(P.msg(P.SET_QUESTIONS, action="remove", index=i))

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
        return self.app.is_host

    def handle_event(self, e):
        if e.type == pygame.DROPFILE and self._is_host():
            if isinstance(self.modal, CsvImport):
                self.modal.drop(e.file)
            else:
                msg, col = import_csv(self.app, e.file)
                self.toasts.add(msg, col, 5)
            return
        if self.modal is not None:
            self.modal.handle(e)
            return
        if self.picker is not None:
            self.picker.handle(e)
            return
        if self._is_host():
            self.btn_start.handle(e)
            for b in (self.btn_write, self.btn_csv, self.btn_default, self.btn_clear):
                b.handle(e)
            if e.type == pygame.MOUSEWHEEL:
                self.scroll = max(0, self.scroll - e.y)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for rect, i in self.row_hits:
                    if rect.collidepoint(e.pos):
                        self.remove_question(i)
                        break
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
        watchers = max(0, room.get("spectators", 0) - 1)          # the host is always one of them
        bottom = self.btn_start.rect.y - (34 if watchers else 10)
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
        if watchers:
            ui.text(surf, f"{watchers} MORE WATCHING WITH THE HOST", (x, self.btn_start.rect.y - 26), 12,
                    ui.MUTED, bold=True)

        if self._is_host():
            has_q = room.get("questions", 0) > 0
            self.btn_start.enabled = ready and has_q
            self.btn_start.label = ("START GAME" if ready and has_q else
                                    f"NEED {need} CREW" if not ready else "ADD QUESTIONS")
            self.btn_start.draw(surf)
        else:
            dots = "." * (1 + (pygame.time.get_ticks() // 400) % 3)
            ui.text(surf, "WAITING FOR HOST" + dots, (x, self.btn_leave.rect.centery), 14, ui.MUTED,
                    bold=True, anchor="midleft")
        self.btn_leave.draw(surf)

        if self._is_player():
            self._draw_showcase(surf)
        elif self._is_host():
            self._draw_bank(surf)

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
        if not self._is_host():
            self._draw_brief(surf, room)
        if self.picker is not None:
            self.picker.draw(surf, room["players"], self.app.me and self.app.me["player_id"])
        if self.modal is not None:
            self.modal.draw(surf)
        self.draw_toasts(surf)

    def _draw_brief(self, surf, room):
        brief = self.brief
        ui.panel(surf, brief, ui.PANEL, 14, ui.TEAL, 232)
        ui.heading(surf, "MISSION BRIEFING", (brief.x + 24, brief.y + 16), brief.w - 48, ui.CYAN, 14)
        secs = config.GAME_DURATION_S
        length = f"{secs // 60} MIN" if secs % 60 == 0 else f"{secs} S"
        steps = [("ARROWS", "WALK THE STATION"), ("E", "OPEN A TERMINAL NEXT TO YOU"),
                 ("1-4", f"FIRST CORRECT +{config.POINTS_CORRECT}, WRONG {config.POINTS_WRONG}"),
                 ("x" + str(config.TERMINAL_MAX_USES), f"EACH TERMINAL: {config.TERMINAL_MAX_USES} CREW, ONCE EACH"),
                 ("SPACE", f"{config.ULT_STREAK} IN A ROW = ULTIMATE: -{config.ULT_DAMAGE} TO ALL")]
        y = brief.y + 46
        for key, what in steps:
            k = ui.keycap(surf, key, (brief.x + 24, y), size=12)
            ui.text(surf, ui.fit(what, 12, brief.right - 28 - (brief.x + 112), True),
                    (brief.x + 112, k.centery), 12, ui.ICE, bold=True, anchor="midleft")
            y += 30
        n = room.get("questions", 0)
        ui.text(surf, f"{n} QUESTIONS LOADED" if n else "HOST IS CHOOSING QUESTIONS", (brief.x + 24, brief.bottom - 22),
                12, ui.GOOD if n else ui.MUTED, bold=True, anchor="bottomleft")
        ui.text(surf, f"BEST AFTER {length} WINS", (brief.right - 28, brief.bottom - 22), 12,
                ui.WARN, bold=True, anchor="bottomright")

    def _draw_bank(self, surf):
        """Host: what the crew will be asked. Write, import, built-in set, delete rows."""
        bk = self.bank
        ui.panel(surf, bk, ui.PANEL, 18, ui.WARN, 236)
        ui.heading(surf, "QUESTION BANK", (bk.x + 24, bk.y + 20), bk.w - 48, ui.WARN, 14)
        qs = (self.app.questions or {}).get("questions", [])
        n = len(qs)
        ui.text(surf, f"{n} QUESTION{'S' if n != 1 else ''}", (bk.x + 24, bk.y + 50), 30,
                ui.GOOD if n else ui.BAD, bold=True)
        src = (self.app.questions or {}).get("source") or ("YOU DECIDE: WRITE, IMPORT OR BUILT-IN" if not n else "")
        ui.text(surf, ui.fit(str(src).upper(), 12, bk.w - 48, True), (bk.x + 24, bk.y + 92), 12, ui.MUTED, bold=True)
        for b in (self.btn_write, self.btn_csv, self.btn_default, self.btn_clear):
            b.enabled = not (b is self.btn_clear and n == 0)
            b.draw(surf)
        ui.stitch(surf, bk.x + 24, bk.right - 24, bk.y + 244, ui.TEAL_DK)
        lr = self.list_rect
        rows = max(1, lr.h // BANK_ROW_H)
        self.scroll = max(0, min(self.scroll, n - rows))
        self.row_hits = []
        mouse = self.app.mouse_pos
        if not qs:
            for i, line in enumerate(("NO QUESTIONS YET", "THE GAME CANNOT START", "UNTIL YOU ADD SOME")):
                ui.text(surf, line, (lr.centerx, lr.y + 60 + i * 26), 14, ui.MUTED, bold=True, anchor="midtop")
        for k, q in enumerate(qs[self.scroll:self.scroll + rows]):
            i = self.scroll + k
            r = pygame.Rect(lr.x, lr.y + k * BANK_ROW_H, lr.w, BANK_ROW_H - 4)
            hover = r.collidepoint(mouse)
            ui.panel(surf, r, ui.PANEL_HI if hover else (24, 28, 76), 4, ui.CYAN if hover else ui.TEAL_DK, 255,
                     rivets=False)
            ui.text(surf, str(i + 1), (r.x + 22, r.centery), 12, ui.MUTED, bold=True, anchor="center")
            ui.text(surf, ui.fit(q["text"], 14, r.w - 120), (r.x + 42, r.centery), 14, ui.ICE, anchor="midleft")
            ui.text(surf, "ABCD"[q["answer"]], (r.right - 50, r.centery), 14, ui.GOOD, bold=True, anchor="center")
            x = pygame.Rect(r.right - 30, r.y + 4, 24, r.h - 8)
            if hover:
                pygame.draw.rect(surf, ui.BTN_DANGER if x.collidepoint(mouse) else ui.shade(ui.BTN_DANGER, 0.6), x)
                ui.text(surf, "X", x.center, 12, ui.ICE, bold=True, anchor="center")
            self.row_hits.append((x, i))
        if n > rows:
            ui.text(surf, f"{self.scroll + 1}-{min(n, self.scroll + rows)} OF {n}  -  WHEEL SCROLLS",
                    (bk.right - 24, bk.bottom - 22), 12, ui.MUTED, bold=True, anchor="bottomright")
        else:
            ui.text(surf, "TIP: DRAG A .CSV ONTO THE WINDOW", (bk.x + 24, bk.bottom - 22), 12, ui.MUTED, bold=True,
                    anchor="bottomleft")

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
