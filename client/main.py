"""Game client (players and admin).

Run from the arena/ folder:
    python -m client.main --server 192.168.1.20          # player
    python -m client.main --server 100.x.y.z              # player over Tailscale
    python -m client.main --admin                         # admin spectator (on the server PC)
"""
import argparse
import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

from common import config  # noqa: E402
from common import protocol as P  # noqa: E402
from client import ui  # noqa: E402
from client.assets import Assets  # noqa: E402
from client.net import NetClient  # noqa: E402
from client.screens.base import CANVAS_H, CANVAS_W  # noqa: E402


class App:
    def __init__(self, args):
        pygame.init()
        pygame.display.set_caption("Multiplayer Game Arena" + (" - Admin" if args.admin else ""))
        info = pygame.display.Info()
        scale = min(1.0, info.current_w * 0.95 / CANVAS_W, info.current_h * 0.85 / CANVAS_H)
        self.window = pygame.display.set_mode((int(CANVAS_W * scale), int(CANVAS_H * scale)), pygame.RESIZABLE)
        self.canvas = pygame.Surface((CANVAS_W, CANVAS_H))
        self.clock = pygame.time.Clock()
        self.assets = Assets()
        self.admin_mode = args.admin
        self.me = None              # LOGIN_OK fields
        self.room = None            # latest ROOM_UPDATE
        self.connected = False
        self.banner = None
        self.mouse_pos = (0, 0)
        self.running = True
        self.net = NetClient(args.server, args.tcp_port)
        self.net.start()
        from client.screens.login import LoginScreen
        self.screen = LoginScreen(self)

    @property
    def is_admin(self):
        return bool(self.me and self.me.get("role") == "admin")

    def set_screen(self, screen):
        self.screen = screen

    def make_game_screen(self, state=None, countdown=None):
        from client.screens.game import GameScreen
        from client.screens.spectator import SpectatorScreen
        cls = SpectatorScreen if self.is_admin else GameScreen
        return cls(self, state=state, countdown=countdown)

    def on_login(self, m):
        self.me = dict(m)
        self.net.start_udp(m["token"], m["udp_port"])

    # --- scaling between the window and the fixed-size canvas ---------------------------
    def _transform(self):
        ww, wh = self.window.get_size()
        s = min(ww / CANVAS_W, wh / CANVAS_H)
        return s, (ww - CANVAS_W * s) / 2, (wh - CANVAS_H * s) / 2

    def _to_canvas(self, pos):
        s, ox, oy = self._transform()
        return int((pos[0] - ox) / s), int((pos[1] - oy) / s)

    def _map_event(self, e):
        if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            d = dict(e.dict)
            d["pos"] = self._to_canvas(e.pos)
            return pygame.event.Event(e.type, d)
        return e

    # --- messages that matter whatever the current screen is ---------------------------
    def dispatch(self, m):
        from client.screens.lobby import LobbyScreen
        from client.screens.login import LoginScreen
        t = m["type"]
        if t == "_CONNECTED":
            self.connected = True
            self.banner = "Reconnected - resuming session..." if self.net.token else None
        elif t == "_LOST":
            self.connected = False
            self.banner = "Connection lost - reconnecting..."
        elif t == "_GAVE_UP":
            self.banner = None
            self.me = self.room = None
            self.set_screen(LoginScreen(self, "Could not reconnect within 30 s - please log in again"))
        elif t == P.RESUME_OK:
            self.banner = None
            self.on_login(m)
            self.room = m.get("room")
            if m.get("game"):
                self.set_screen(self.make_game_screen(state=m["game"]))
            elif self.room:
                from client.screens.room import RoomScreen
                self.set_screen(RoomScreen(self))
            else:
                self.set_screen(LobbyScreen(self))
        elif t == P.ERROR and m.get("code") == P.E_RESUME_FAILED:
            self.banner = None
            self.me = self.room = None
            self.net.stop_udp()
            self.set_screen(LoginScreen(self, m.get("message")))
        elif t == P.ROOM_UPDATE:
            self.room = m
            self.screen.handle_msg(m)
        elif t == P.ROOM_CLOSED:
            self.room = None
            self.set_screen(LobbyScreen(self, f"Room closed: {m.get('reason', '')}"))
        elif t == P.LOGOUT_OK:
            self.me = self.room = None
            self.net.stop_udp()
            self.set_screen(LoginScreen(self, "Logged out"))
        else:
            self.screen.handle_msg(m)

    # --- main loop -----------------------------------------------------------------------
    def frame(self):
        """One iteration of the main loop: input, network, update, draw."""
        dt = self.clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
                return
            e = self._map_event(e)
            if e.type == pygame.MOUSEMOTION:
                self.mouse_pos = e.pos
            self.screen.handle_event(e)
        while True:
            m = self.net.poll()
            if m is None:
                break
            self.dispatch(m)
        self.screen.update(dt)
        self.canvas.fill(ui.BG)
        self.screen.draw(self.canvas)
        if self.banner:
            r = pygame.Rect(0, 0, CANVAS_W, 40)
            pygame.draw.rect(self.canvas, (120, 40, 40), r)
            ui.text(self.canvas, self.banner, r.center, 22, ui.TEXT, bold=True, anchor="center")
        s, ox, oy = self._transform()
        self.window.fill((0, 0, 0))
        size = (int(CANVAS_W * s), int(CANVAS_H * s))
        frame = self.canvas if size == (CANVAS_W, CANVAS_H) else pygame.transform.smoothscale(self.canvas, size)
        self.window.blit(frame, (int(ox), int(oy)))
        pygame.display.flip()

    def run(self):
        while self.running:
            self.frame()
        self.net.close()
        pygame.quit()


def main():
    ap = argparse.ArgumentParser(description="Multiplayer Game Arena client")
    ap.add_argument("--server", default=config.SERVER_HOST,
                    help="server address: LAN IP (192.168.x.y) or Tailscale IP (100.x.y.z)")
    ap.add_argument("--tcp-port", type=int, default=config.TCP_PORT)
    ap.add_argument("--admin", action="store_true", help="admin spectator mode (prefills the admin user)")
    args = ap.parse_args()
    App(args).run()


if __name__ == "__main__":
    sys.exit(main())
