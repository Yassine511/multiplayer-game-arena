"""In-game screen for players (and, via SpectatorScreen, the admin)."""
import math

import pygame

from common import config, map_data
from common import protocol as P
from client import ui
from client.assets import color_of
from client.screens.base import CANVAS_H, CANVAS_W, Screen

SIDEBAR_X = config.WORLD_W
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
                self.toasts.add("Get closer to a terminal (within 60 px)", ui.MUTED, 1.5)
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
                p["x"] += (p["tx"] - p["x"]) * k
                p["y"] += (p["ty"] - p["y"]) * k

        if self.phase == P.PHASE_PLAYING and self.is_me_playing():
            self._move(dt)

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

    # --- drawing ------------------------------------------------------------------------
    def draw(self, surf):
        world = surf.subsurface(pygame.Rect(0, 0, config.WORLD_W, config.WORLD_H))
        assets = self.app.assets
        assets.draw_map(world)
        near = self.nearest_terminal() if self.is_me_playing() and self.phase == P.PHASE_PLAYING else None
        for t in self.terminals.values():
            claimer = self.players.get(t.get("claimed_by"))
            assets.draw_terminal(world, t, color_of(claimer["color"]) if claimer else None,
                                 self.lockouts.get(t["terminal_id"], 0), highlight=(t is near))
        order = sorted(self.players.items(), key=lambda kv: (kv[0] == self.me_id, kv[1]["y"]))
        for pid, p in order:
            assets.draw_player(world, p["x"], p["y"], p["color"], p["dir"], p["name"],
                               me=(pid == self.me_id), connected=(p["status"] == P.STATUS_CONNECTED))
        if near is not None and self.overlay is None:
            ui.text(world, f"Press E to open T{near['terminal_id']}", (config.WORLD_W // 2, config.WORLD_H - 40),
                    22, ui.TEXT, bold=True, anchor="center")
        if self.phase == P.PHASE_COUNTDOWN:
            shade = pygame.Surface((config.WORLD_W, config.WORLD_H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 140))
            world.blit(shade, (0, 0))
            ui.text(world, "Get ready", (config.WORLD_W // 2, 250), 36, ui.MUTED, anchor="center")
            ui.text(world, str(max(1, math.ceil(self.countdown_left))), (config.WORLD_W // 2, 340), 120,
                    ui.WARN, bold=True, anchor="center")
        if self.overlay is not None:
            self._draw_question(world)
        self._draw_sidebar(surf)
        self.draw_toasts(surf, config.WORLD_W // 2, 20)

    def _draw_question(self, surf):
        q = self.overlay
        shade = pygame.Surface((config.WORLD_W, config.WORLD_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        surf.blit(shade, (0, 0))
        box = pygame.Rect(0, 0, 820, 470)
        box.center = (config.WORLD_W // 2, config.WORLD_H // 2)
        ui.panel(surf, box, (26, 31, 42), 14, ui.ACCENT)
        ui.text(surf, f"Terminal T{q['terminal_id']}  -  {q.get('topic', '')}", (box.x + 30, box.y + 22), 20, ui.ACCENT)
        y = box.y + 60
        for line in ui.wrap(q["text"], 28, box.width - 60, bold=True):
            ui.text(surf, line, (box.x + 30, y), 28, bold=True)
            y += 36
        y += 14
        self.answer_rects = []
        for i, choice in enumerate(q["choices"]):
            r = pygame.Rect(box.x + 30, y, box.width - 60, 54)
            chosen = q.get("chosen") == i
            hover = r.collidepoint(self.app.mouse_pos) and not self.awaiting
            ui.panel(surf, r, ui.PANEL_HI if hover or chosen else ui.PANEL, 8, ui.ACCENT if chosen else ui.BORDER)
            ui.text(surf, f"{i + 1}", (r.x + 22, r.centery), 22, ui.ACCENT, bold=True, anchor="center")
            ui.text(surf, choice, (r.x + 48, r.centery), 22, anchor="midleft")
            self.answer_rects.append(r)
            y += 62
        hint = "Checking..." if self.awaiting else "Press 1-4 or click to answer  -  Esc to close"
        ui.text(surf, hint, (box.centerx, box.bottom - 22), 18, ui.MUTED, anchor="center")

    def _draw_sidebar(self, surf):
        x0 = SIDEBAR_X
        pygame.draw.rect(surf, (22, 26, 34), (x0, 0, CANVAS_W - x0, CANVAS_H))
        pygame.draw.line(surf, ui.BORDER, (x0, 0), (x0, CANVAS_H))
        cx = x0 + (CANVAS_W - x0) // 2
        secs = int(math.ceil(self.remaining)) if self.phase == P.PHASE_PLAYING else config.GAME_DURATION_S
        col = ui.BAD if self.phase == P.PHASE_PLAYING and secs <= 20 else ui.TEXT
        ui.text(surf, "TIME LEFT", (cx, 18), 16, ui.MUTED, anchor="midtop")
        ui.text(surf, f"{secs // 60}:{secs % 60:02d}", (cx, 38), 48, col, bold=True, anchor="midtop")
        ui.text(surf, "SCOREBOARD", (x0 + 16, 112), 16, ui.MUTED)
        y = 138
        rows = self.scores or [{"id": pid, "name": p["name"], "score": 0, "connected": True, "color": p["color"]}
                               for pid, p in self.players.items()]
        for i, s in enumerate(rows[:10]):
            on = s.get("connected", True)
            pygame.draw.circle(surf, color_of(s.get("color")) if on else (90, 94, 104), (x0 + 24, y + 12), 7)
            me = s["id"] == self.me_id
            name = s["name"] if len(s["name"]) <= 11 else s["name"][:10] + "."
            ui.text(surf, f"{i + 1}. {name}", (x0 + 38, y + 12), 19, ui.TEXT if on else ui.MUTED,
                    bold=me, anchor="midleft")
            ui.text(surf, str(s["score"]), (CANVAS_W - 16, y + 12), 20, ui.TEXT if on else ui.MUTED,
                    bold=True, anchor="midright")
            y += 30
        self._draw_sidebar_footer(surf, x0, cx)

    def _draw_sidebar_footer(self, surf, x0, cx):
        room = self.app.room
        y = CANVAS_H - 150
        if room:
            ui.text(surf, f"Room {room['code']}", (x0 + 16, y), 18, ui.MUTED)
        rtt = self.app.net.rtt_ms
        ui.text(surf, f"ping {rtt:.0f} ms" if rtt is not None else "ping -", (CANVAS_W - 16, y), 18,
                ui.MUTED, anchor="topright")
        for i, line in enumerate(["WASD / arrows: move", "E: open terminal", "1-4: answer, Esc: close"]):
            ui.text(surf, line, (x0 + 16, y + 34 + i * 24), 17, ui.MUTED)
