"""In-game screen for players (and, via SpectatorScreen, the admin)."""
import math

import pygame

from common import config, map_data
from common import protocol as P
from client import ui
from client.assets import VIEW_ZOOM, color_of
from client.screens.base import CANVAS_H, CANVAS_W, Screen

POS_PERIOD = 1.0 / config.POS_HZ
CORRECTION_PX = 60          # snap to the server's position if we drift further than this
LETTERS = "ABCD"


class GameScreen(Screen):
    spectator = False

    def __init__(self, app, state=None, countdown=None):
        super().__init__(app)
        self.me_id = app.me["player_id"]
        self.phase = P.PHASE_COUNTDOWN
        self.countdown_left = float(countdown or config.COUNTDOWN_S)
        self.remaining = config.GAME_DURATION_S
        self.players = {}          # id -> dict(name, color, status, x, y, tx, ty, dir)
        self.terminals = {}        # id -> dict(terminal_id, x, y, state, claimed_by, ready_in)
        self.scores = []
        self.overlay = None        # TERMINAL_QUESTION being answered
        self.awaiting = False
        self.lockouts = {}         # terminal_id -> seconds left (mine)
        self.pos_timer = 0.0
        self.keepalive = 0.0
        self.last_sent = None
        self.last_snap_seq = 0
        self.mx = self.my = 0.0
        self.mdir = "down"
        self.answer_rects = []
        self.zoom = CANVAS_W / config.WORLD_W if self.spectator else VIEW_ZOOM
        self.cam = None            # top-left of the view, world units
        self._cam_px = (0, 0)      # the same, in screen px, rounded once per frame
        self.moving = False
        self.near = None
        self.place = None          # room name the player stands in
        self.place_flash = 0.0
        app.net.reset_snapshots()
        if state is not None:
            self.load_state(state)

    # --- state ------------------------------------------------------------------------
    def load_state(self, st):
        self.phase = st.get("phase", P.PHASE_PLAYING)
        if self.phase == P.PHASE_COUNTDOWN:
            self.countdown_left = st.get("countdown_ms", 0) / 1000
        self.remaining = st.get("remaining_ms", config.GAME_DURATION_S * 1000) / 1000
        self.terminals = {}
        for t in st.get("terminals", []):
            self.terminals[t["terminal_id"]] = dict(t, ready_in=t.get("ready_in_ms", 0) / 1000)
        pos = {p["id"]: p for p in st.get("positions", [])}
        self.players = {}
        for p in st.get("players", []):
            q = pos.get(p["id"], {"x": 0, "y": 0, "dir": "down"})
            self.players[p["id"]] = {"name": p["name"], "color": p["color"], "status": p["status"],
                                     "x": q["x"], "y": q["y"], "tx": q["x"], "ty": q["y"],
                                     "dir": q.get("dir", "down")}
        me = self.players.get(self.me_id)
        if me:
            self.mx, self.my, self.mdir = me["x"], me["y"], me["dir"]
        self.scores = st.get("scores", [])

    def is_me_playing(self):
        return not self.spectator and self.me_id in self.players

    def name_of(self, pid):
        p = self.players.get(pid)
        return p["name"] if p else "?"

    # --- input ------------------------------------------------------------------------
    def nearest_terminal(self):
        best, best_d = None, None
        for t in self.terminals.values():
            d = math.hypot(t["x"] - self.mx, t["y"] - self.my)
            if d <= config.INTERACT_RADIUS and (best_d is None or d < best_d):
                best, best_d = t, d
        return best

    def handle_event(self, e):
        if self.phase != P.PHASE_PLAYING or not self.is_me_playing():
            return
        if self.overlay is not None:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE and not self.awaiting:
                    self.overlay = None
                elif e.unicode in ("1", "2", "3", "4"):
                    self.answer(int(e.unicode) - 1)
                elif e.unicode and e.unicode.upper() in LETTERS:
                    self.answer(LETTERS.index(e.unicode.upper()))
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(self.answer_rects):
                    if r.collidepoint(e.pos):
                        self.answer(i)
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_e:
            t = self.nearest_terminal()
            if t is None:
                self.toasts.add("Get closer to a terminal", ui.MUTED, 1.5)
            else:
                self.app.net.send(P.msg(P.OPEN_TERMINAL, terminal_id=t["terminal_id"]))

    def answer(self, choice):
        if self.overlay is None or self.awaiting:
            return
        self.awaiting = True
        self.overlay["chosen"] = choice
        self.app.net.send(P.msg(P.ANSWER, terminal_id=self.overlay["terminal_id"],
                                question_id=self.overlay["question_id"], choice=choice))

    # --- messages -----------------------------------------------------------------------
    def handle_msg(self, m):
        t = m["type"]
        if t == P.GAME_COUNTDOWN:
            self.phase = P.PHASE_COUNTDOWN
            self.countdown_left = m["seconds"]
        elif t == P.GAME_STARTED:
            self.load_state(m)
            self.phase = P.PHASE_PLAYING
            self.app.net.reset_snapshots()
        elif t == P.TERMINAL_QUESTION:
            if self.is_me_playing():
                self.overlay = dict(m)
                self.awaiting = False
        elif t == P.ANSWER_RESULT:
            self.awaiting = False
            self.overlay = None
            st = m["status"]
            if st == P.RESULT_CORRECT:
                self.toasts.add(f"Correct! +{m['points']}", ui.GOOD)
            elif st == P.RESULT_WRONG:
                self.lockouts[m["terminal_id"]] = m.get("lockout_ms", 5000) / 1000
                self.toasts.add(f"Wrong answer {m['points']}  -  T{m['terminal_id']} locked 5 s", ui.BAD)
            elif st == P.RESULT_TOO_LATE:
                self.toasts.add("Too late - someone answered first", ui.WARN)
            elif st == P.RESULT_LOCKED:
                self.toasts.add("You are locked out of this terminal", ui.BAD)
        elif t == P.TERMINAL_STATE:
            tid = m["terminal_id"]
            self.terminals[tid] = dict(m, ready_in=m.get("ready_in_ms", 0) / 1000)
            if m["state"] == P.TERMINAL_COOLDOWN and m.get("claimed_by") != self.me_id:
                if self.overlay and self.overlay["terminal_id"] == tid and not self.awaiting:
                    self.overlay = None
                    self.toasts.add(f"{self.name_of(m['claimed_by'])} answered T{tid} first", ui.WARN)
        elif t == P.SCORE_UPDATE:
            self.scores = m["scores"]
            for s in self.scores:
                if s["id"] in self.players:
                    self.players[s["id"]]["status"] = s.get("status", "connected")
        elif t == P.TIME_SYNC:
            self.remaining = m["remaining_ms"] / 1000      # server's clock wins
        elif t == P.PLAYER_STATUS:
            p = self.players.get(m["player_id"])
            name = m.get("name") or (p and p["name"]) or "?"
            if m["status"] == P.STATUS_RECONNECTED:
                if p:
                    p["status"] = P.STATUS_CONNECTED
                self.toasts.add(f"{name} reconnected", ui.GOOD)
            else:
                if p:
                    p["status"] = m["status"]
                verb = "left the game" if m["status"] == P.STATUS_LEFT else "disconnected"
                self.toasts.add(f"{name} {verb}", ui.WARN)
        elif t == P.GAME_OVER:
            from client.screens.results import ResultsScreen
            self.app.set_screen(ResultsScreen(self.app, m))
        elif t == P.ERROR:
            if m.get("code") in (P.E_LOCKED_OUT, P.E_COOLDOWN) and m.get("remaining_ms") is not None:
                if m["code"] == P.E_LOCKED_OUT:
                    self.lockouts[m["terminal_id"]] = m["remaining_ms"] / 1000
                self.toasts.add(f"{m['message']} ({m['remaining_ms'] / 1000:.1f} s)", ui.WARN)
            else:
                super().handle_msg(m)
            self.awaiting = False

    # --- update -------------------------------------------------------------------------
    def update(self, dt):
        super().update(dt)
        if self.phase == P.PHASE_COUNTDOWN:
            self.countdown_left = max(0.0, self.countdown_left - dt)
        elif self.phase == P.PHASE_PLAYING:
            self.remaining = max(0.0, self.remaining - dt)
        for t in self.terminals.values():
            if t.get("ready_in", 0) > 0:
                t["ready_in"] = max(0.0, t["ready_in"] - dt)
        for tid in list(self.lockouts):
            self.lockouts[tid] -= dt
            if self.lockouts[tid] <= 0:
                del self.lockouts[tid]

        self._apply_snapshot()
        # others glide toward their latest snapshot position (interpolation)
        k = min(1.0, dt * 12)
        for pid, p in self.players.items():
            if pid == self.me_id and self.is_me_playing():
                p["x"], p["y"], p["dir"] = self.mx, self.my, self.mdir
            else:
                p["moving"] = math.hypot(p["tx"] - p["x"], p["ty"] - p["y"]) > 1.5
                p["x"] += (p["tx"] - p["x"]) * k
                p["y"] += (p["ty"] - p["y"]) * k

        self.moving = False
        if self.phase == P.PHASE_PLAYING and self.is_me_playing():
            self._move(dt)
        self._update_camera(dt)
        self.place_flash = max(0.0, self.place_flash - dt)
        if self.is_me_playing():
            room = map_data.room_at(self.mx, self.my)
            place = room["name"] if room else "Corridor"
            if place != self.place:
                if self.place is not None and room:
                    self.place_flash = 1.6
                self.place = place

    def _update_camera(self, dt):
        vw, vh = CANVAS_W / self.zoom, CANVAS_H / self.zoom
        if self.is_me_playing():
            fx, fy = self.mx, self.my
        elif self.spectator:
            fx, fy = config.WORLD_W / 2, config.WORLD_H / 2
        else:                                   # not spawned yet: look at the plaza
            fx, fy = map_data.TERMINALS[0]["x"], map_data.TERMINALS[0]["y"]
        tx = min(max(fx - vw / 2, 0), max(0, config.WORLD_W - vw))
        ty = min(max(fy - vh / 2, 0), max(0, config.WORLD_H - vh))
        if self.cam is None or math.hypot(tx - self.cam[0], ty - self.cam[1]) > 400:
            self.cam = [tx, ty]
        else:
            k = min(1.0, dt * 9)
            self.cam[0] += (tx - self.cam[0]) * k
            self.cam[1] += (ty - self.cam[1]) * k

    def to_screen(self, x, y):
        # same rounding as the map blit, so sprites never shimmer against the floor
        z = self.zoom
        return round(x * z) - self._cam_px[0], round(y * z) - self._cam_px[1]

    def _apply_snapshot(self):
        snap = self.app.net.latest_snapshot
        if not snap or snap["seq"] == self.last_snap_seq:
            return
        self.last_snap_seq = snap["seq"]
        for s in snap["players"]:
            p = self.players.get(s["id"])
            if p is None:
                continue
            p["tx"], p["ty"] = s["x"], s["y"]
            if s["id"] != self.me_id:
                p["dir"] = s.get("dir", p["dir"])
            elif self.is_me_playing() and math.hypot(s["x"] - self.mx, s["y"] - self.my) > CORRECTION_PX:
                self.mx, self.my = s["x"], s["y"]   # server rejected our moves: accept its position

    def _move(self, dt):
        if self.overlay is None:
            keys = pygame.key.get_pressed()
            vx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            vy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
            if vx or vy:
                self.moving = True
                norm = math.hypot(vx, vy)
                step = config.PLAYER_SPEED * min(dt, 0.05)
                self.mx, self.my = map_data.move(self.mx, self.my, vx / norm * step, vy / norm * step)
                if abs(vx) >= abs(vy):
                    self.mdir = "right" if vx > 0 else "left"
                else:
                    self.mdir = "down" if vy > 0 else "up"
        self.pos_timer += dt
        self.keepalive += dt
        if self.pos_timer >= POS_PERIOD:
            self.pos_timer = 0.0
            cur = (round(self.mx, 1), round(self.my, 1), self.mdir)
            if cur != self.last_sent or self.keepalive >= 0.5:
                self.app.net.send_pos(self.mx, self.my, self.mdir)
                self.last_sent = cur
                self.keepalive = 0.0

    # --- drawing: world -----------------------------------------------------------------
    sprite_scale = 3

    def draw(self, surf):
        if self.cam is None:
            self._update_camera(0)
        self._cam_px = (round(self.cam[0] * self.zoom), round(self.cam[1] * self.zoom))
        self._draw_world(surf)
        self._draw_hud(surf)
        if self.phase == P.PHASE_COUNTDOWN:
            self._draw_countdown(surf)
        if self.overlay is not None:
            self._draw_question(surf)
        self.draw_toasts(surf, CANVAS_W // 2, 84)

    def _draw_world(self, surf):
        assets = self.app.assets
        z = self.zoom
        world = assets.map_surface(z)
        surf.blit(world, (0, 0), (self._cam_px[0], self._cam_px[1], CANVAS_W, CANVAS_H))
        self.near = self.nearest_terminal() if self.is_me_playing() and self.phase == P.PHASE_PLAYING else None
        for t in self.terminals.values():
            sx, sy = self.to_screen(t["x"], t["y"])
            if -80 < sx < CANVAS_W + 80 and -40 < sy < CANVAS_H + 120:
                claimer = self.players.get(t.get("claimed_by"))
                assets.draw_terminal(surf, sx, sy, t, color_of(claimer["color"]) if claimer else None,
                                     self.lockouts.get(t["terminal_id"], 0), highlight=(t is self.near),
                                     scale=z / 2 + 0.25)
        order = sorted(self.players.items(), key=lambda kv: (kv[1]["y"], kv[0] == self.me_id))
        for pid, p in order:
            if p["status"] == P.STATUS_LEFT:
                continue
            sx, sy = self.to_screen(p["x"], p["y"])
            if not (-80 < sx < CANVAS_W + 80 and -40 < sy < CANVAS_H + 120):
                continue
            me = pid == self.me_id
            assets.draw_player(surf, sx, sy, p["color"], p["dir"], p["name"], me=me,
                               connected=(p["status"] == P.STATUS_CONNECTED),
                               moving=self.moving if me else p.get("moving", False), scale=self.sprite_scale)

    # --- drawing: HUD -------------------------------------------------------------------
    def _timer_plate(self, surf, cx=CANVAS_W // 2, y=10):
        playing = self.phase == P.PHASE_PLAYING
        secs = int(math.ceil(self.remaining)) if playing else config.GAME_DURATION_S
        low = playing and secs <= 20
        r = pygame.Rect(0, 0, 176, 62)
        r.midtop = (cx, y)
        blink = low and (pygame.time.get_ticks() // 400) % 2 == 0
        ui.panel(surf, r, (60, 14, 34) if blink else ui.PANEL, 10, ui.BAD if low else ui.CYAN, 240)
        ui.text(surf, "TIME LEFT", (r.centerx, r.y + 6), 12, ui.BAD if low else ui.MUTED, bold=True, anchor="midtop")
        ui.text(surf, f"{secs // 60}:{secs % 60:02d}", (r.centerx, r.y + 25), 30,
                ui.BAD if low else ui.ICE, bold=True, anchor="midtop")
        return r

    def _score_rows(self):
        if self.scores:
            return self.scores
        if self.players:
            return [{"id": pid, "name": p["name"], "score": 0, "connected": True, "color": p["color"]}
                    for pid, p in self.players.items()]
        room = self.app.room or {}              # countdown: the game state has not arrived yet
        return [{"id": p["id"], "name": p["name"], "score": 0, "connected": p["status"] == P.STATUS_CONNECTED,
                 "color": p["color"]} for p in room.get("players", [])]

    def _draw_hud(self, surf):
        self._timer_plate(surf)

        # where am I
        loc = pygame.Rect(12, 10, 286, 62)
        flash = self.place_flash > 0
        ui.panel(surf, loc, ui.PANEL_HI if flash and (pygame.time.get_ticks() // 160) % 2 else ui.PANEL, 10,
                 ui.WARN if flash else ui.CYAN, 240)
        ui.text(surf, "LOCATION", (loc.x + 18, loc.y + 9), 12, ui.MUTED, bold=True)
        ui.text(surf, (self.place or "Station").upper(), (loc.x + 18, loc.y + 26), 20,
                ui.WARN if flash else ui.ICE, bold=True)

        # scoreboard
        rows = self._score_rows()[:10]
        sb = pygame.Rect(CANVAS_W - 12 - 250, 10, 250, 46 + len(rows) * 24)
        ui.panel(surf, sb, ui.PANEL, 10, ui.CYAN, 232)
        ui.heading(surf, "SCORES", (sb.x + 16, sb.y + 10), sb.w - 34, ui.CYAN, 12)
        y = sb.y + 34
        for i, s in enumerate(rows):
            on = s.get("connected", True)
            me = s["id"] == self.me_id
            if me:
                pygame.draw.rect(surf, ui.PANEL_HI, (sb.x + 10, y - 1, sb.w - 20, 22))
            ui.text(surf, f"{i + 1}", (sb.x + 26, y + 10), 14, ui.WARN if i == 0 and s["score"] > 0 else ui.MUTED,
                    bold=True, anchor="center")
            ui.chip(surf, color_of(s.get("color")) if on else ui.GREY, (sb.x + 46, y + 10), 10)
            ui.text(surf, ui.fit(s["name"], 14, 118, True), (sb.x + 60, y + 10), 14,
                    (ui.ICE if me else ui.shade(ui.ICE, 0.8)) if on else ui.MUTED, bold=True, anchor="midleft")
            ui.text(surf, str(s["score"]), (sb.right - 16, y + 10), 14, ui.ICE if on else ui.MUTED,
                    bold=True, anchor="midright")
            y += 24

        self._draw_minimap(surf, pygame.Rect(12, CANVAS_H - 12 - 155, 260, 155))

        # controls, room code, ping
        room = self.app.room
        rtt = self.app.net.rtt_ms
        info = pygame.Rect(CANVAS_W - 12 - 384, CANVAS_H - 12 - 66, 384, 66)
        ui.plate(surf, info, ui.PANEL, 215, 6)
        x = info.x + 12
        for key, what in (("WASD", "MOVE"), ("E", "USE"), ("1-4", "ANSWER")):
            k = ui.keycap(surf, key, (x, info.y + 8), size=12)
            t = ui.text(surf, what, (k.right + 6, k.centery), 12, ui.MUTED, bold=True, anchor="midleft")
            x = t.right + 12
        ping = f"PING {rtt:.0f} MS" if rtt is not None else "PING -"
        ui.text(surf, f"ROOM {room['code']}" if room else "", (info.x + 14, info.y + 42), 12, ui.CYAN, bold=True)
        ui.text(surf, ping, (info.right - 14, info.y + 42), 12,
                ui.GOOD if rtt is not None and rtt < 120 else ui.WARN, bold=True, anchor="topright")

        # interact prompt
        if self.near is not None and self.overlay is None:
            t = self.near
            locked = self.lockouts.get(t["terminal_id"], 0)
            if t["state"] == "cooldown":
                msg, col = f"T{t['terminal_id']} IS RESETTING", ui.MUTED
            elif locked > 0:
                msg, col = f"T{t['terminal_id']} LOCKED FOR {math.ceil(locked)} S", ui.BAD
            else:
                msg, col = f"ACCESS TERMINAL T{t['terminal_id']}", ui.ICE
            w = ui.text_width(msg, 18, True) + 70          # 16 + key 26 + 12 ... text ... 16
            r = pygame.Rect(0, 0, w, 46)
            r.midbottom = (CANVAS_W // 2, CANVAS_H - 26 + int(math.sin(pygame.time.get_ticks() / 220) * 2))
            ui.panel(surf, r, ui.PANEL, 8, col if col != ui.ICE else ui.CYAN, 240, rivets=False)
            k = ui.keycap(surf, "E", (r.x + 16, r.centery), "midleft")
            ui.text(surf, msg, (k.right + 12, r.centery), 18, col, bold=True, anchor="midleft")

    def _draw_minimap(self, surf, box, dots=5):
        ui.panel(surf, box, ui.PANEL, 8, ui.CYAN, 240, rivets=False)
        inner = box.inflate(-16, -16)
        k = min(inner.w / config.WORLD_W, inner.h / config.WORLD_H)
        mini = self.app.assets.map_surface(k)
        ox, oy = inner.centerx - mini.get_width() // 2, inner.centery - mini.get_height() // 2
        surf.blit(mini, (ox, oy))
        blink = (pygame.time.get_ticks() // 300) % 2 == 0
        for t in self.terminals.values():
            x, y = int(ox + t["x"] * k), int(oy + t["y"] * k)
            claimer = self.players.get(t.get("claimed_by"))
            if t["state"] == "cooldown":
                c = color_of(claimer["color"]) if claimer else ui.MUTED
            elif self.lockouts.get(t["terminal_id"], 0) > 0:
                c = ui.BAD
            else:
                c = ui.ICE if blink else ui.CYAN
            pygame.draw.rect(surf, ui.INK, (x - 4, y - 4, 8, 8))
            pygame.draw.rect(surf, c, (x - 2, y - 2, 4, 4))
        for pid, p in self.players.items():
            if p["status"] == P.STATUS_LEFT:
                continue
            x, y = int(ox + p["x"] * k), int(oy + p["y"] * k)
            me = pid == self.me_id
            d = dots + (2 if me else 0)
            pygame.draw.rect(surf, ui.ICE if me and blink else ui.INK, (x - d // 2 - 1, y - d // 2 - 1, d + 2, d + 2))
            pygame.draw.rect(surf, color_of(p["color"]) if p["status"] == P.STATUS_CONNECTED else ui.GREY,
                             (x - d // 2, y - d // 2, d, d))
        if not self.spectator:
            view = pygame.Rect(ox + self.cam[0] * k, oy + self.cam[1] * k,
                               CANVAS_W / self.zoom * k, CANVAS_H / self.zoom * k)
            pygame.draw.rect(surf, ui.ICE, view, 1)

    # --- drawing: overlays --------------------------------------------------------------
    def _draw_countdown(self, surf):
        ui.dim(surf, 120)
        cx = CANVAS_W // 2
        n = max(1, math.ceil(self.countdown_left))
        frac = self.countdown_left - math.floor(self.countdown_left)
        band = pygame.Rect(0, 236, CANVAS_W, 250)
        pygame.draw.rect(surf, ui.INK, band)
        ui.hazard(surf, (0, band.y, CANVAS_W, 12))
        ui.hazard(surf, (0, band.bottom - 12, CANVAS_W, 12))
        ui.text(surf, "GET READY", (cx, band.y + 30), 26, ui.CYAN, bold=True, anchor="midtop")
        ui.text(surf, str(n), (cx, band.centery + int(frac * 6)), 120, ui.WARN, bold=True, anchor="center")
        tip = ("WATCHING FROM THE CONTROL DECK" if self.spectator else
               "10 TERMINALS, ONE IN EVERY ROOM  -  FIRST CORRECT ANSWER TAKES THE POINTS")
        ui.text(surf, tip, (cx, band.bottom - 44), 14, ui.MUTED, bold=True, anchor="midtop")

    def _draw_question(self, surf):
        q = self.overlay
        ui.dim(surf, 165)
        box = pygame.Rect(120, 76, 1040, 568)
        ui.panel(surf, box, ui.PANEL, 22, ui.CYAN, 250)
        room = map_data.room_by_id(q["terminal_id"])

        # title bar
        ui.hazard(surf, (box.x + 26, box.y + 22, 40, 22))
        ui.text(surf, f"TERMINAL T{q['terminal_id']}", (box.x + 78, box.y + 18), 24, ui.CYAN, bold=True)
        topic = str(q.get("topic", "")).upper()
        if topic:
            tw = ui.text_width(topic, 14, True) + 24
            tr = pygame.Rect(box.right - 28 - tw, box.y + 20, tw, 28)
            pygame.draw.rect(surf, ui.INK, tr)
            pygame.draw.rect(surf, ui.TEAL_DK, tr.inflate(-4, -4))
            ui.text(surf, topic, (tr.centerx, tr.centery), 14, ui.ICE, bold=True, anchor="center")
        ui.stitch(surf, box.x + 26, box.right - 26, box.y + 58, ui.TEAL_DK)

        # left: which room this terminal is in
        lx, lw = box.x + 28, 240
        card_box = pygame.Rect(lx, box.y + 76, lw, 236)
        ui.panel(surf, card_box, ui.FIELD, 10, ui.TEAL_DK, 255, rivets=False)
        card = self.app.assets.room_card(room["slug"], lw - 28, 208) if room else None
        if card is not None:
            surf.blit(card, card.get_rect(center=card_box.center))
        ui.text(surf, (room["name"] if room else "").upper(), (lx + lw // 2, card_box.bottom + 12), 16,
                ui.ICE, bold=True, anchor="midtop")
        y = card_box.bottom + 52
        for label, value, col in (("FIRST CORRECT", f"+{config.POINTS_CORRECT}", ui.GOOD),
                                  ("WRONG ANSWER", str(config.POINTS_WRONG), ui.BAD),
                                  ("THEN LOCKED", f"{config.WRONG_LOCKOUT_S} S", ui.WARN)):
            ui.text(surf, label, (lx + 4, y), 12, ui.MUTED, bold=True)
            ui.text(surf, value, (lx + lw - 4, y), 12, col, bold=True, anchor="topright")
            y += 24

        # right: question and answers
        rx = lx + lw + 30
        rw = box.right - 30 - rx
        y = box.y + 80
        lines = ui.wrap(q["text"], 22, rw, bold=True)[:4]
        for line in lines:
            ui.text(surf, line, (rx, y), 22, ui.ICE, bold=True)
            y += 32
        y = max(y + 14, box.y + 164)
        row_h = min(64, (box.bottom - 56 - y - 3 * 8) // 4)
        self.answer_rects = []
        for i, choice in enumerate(q["choices"]):
            r = pygame.Rect(rx, y, rw, row_h)
            chosen = q.get("chosen") == i
            hover = r.collidepoint(self.app.mouse_pos) and not self.awaiting
            ui.panel(surf, r, ui.PANEL_HI if hover or chosen else (24, 28, 76), 8,
                     ui.WARN if chosen else ui.CYAN if hover else ui.TEAL_DK, 255, rivets=False)
            ui.keycap(surf, str(i + 1), (r.x + 16, r.centery), "midleft")
            parts = ui.wrap(choice, 20, rw - 84)[:2]
            ty = r.centery - (len(parts) - 1) * 12
            for part in parts:
                ui.text(surf, part, (r.x + 58, ty), 20, ui.WARN if chosen else ui.ICE, anchor="midleft")
                ty += 24
            self.answer_rects.append(r)
            y += row_h + 8
        if self.awaiting:
            dots = "." * (1 + (pygame.time.get_ticks() // 250) % 3)
            ui.text(surf, "CHECKING" + dots, (rx + rw // 2, box.bottom - 40), 14, ui.WARN, bold=True, anchor="midtop")
        else:
            ui.text(surf, "PRESS 1-4 OR CLICK TO ANSWER   -   ESC TO STEP AWAY", (rx + rw // 2, box.bottom - 40), 12,
                    ui.MUTED, bold=True, anchor="midtop")

