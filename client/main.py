"""Game client. Whoever creates a room hosts it as a spectator; everyone else plays.

Run from the arena/ folder:
    python -m client.main                                 # launcher: host a server here, or join one
    python -m client.main --server 192.168.1.20          # straight to the login of that server
    python -m client.main --server 100.x.y.z              # ... over Tailscale
"""
import argparse
import json
import logging
import os
import sys
import threading


def _dpi_aware():
    """Stop Windows from bitmap-stretching the window on 125 % / 150 % displays, which
    blurs every pixel. The game scales itself, crisply, instead."""
    os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_dpi_aware()

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

try:                                   # small buffer: ultimate sounds land on the frame they belong to
    pygame.mixer.pre_init(22050, -16, 2, 512)
except Exception:
    pass

from common import characters, config  # noqa: E402
from common import protocol as P  # noqa: E402
from client import ui  # noqa: E402
from client.assets import Assets  # noqa: E402
from client.net import NetClient  # noqa: E402
from client.screens.base import CANVAS_H, CANVAS_W  # noqa: E402


FADE_S = 0.28
PREFS_PATH = os.path.join(os.path.expanduser("~"), ".arena_client.json")   # last character, last server
FPS_CAP = 240
# per-backdrop options: where stars may twinkle, and a tint that keeps panels readable
BACKDROPS = {
    "login": {"stars": 26, "star_band": 0.45, "rocks": 14, "rock_band": (0.24, 0.47)},
    "space": {"stars": 40, "star_band": 1.0, "tint": (10, 6, 40, 70)},
    "scene": {"stars": 0, "tint": (6, 8, 36, 60)},
}


class App:
    def __init__(self, args):
        pygame.init()
        pygame.display.set_caption("Ultimate Slop Showdown - Mediterranean University Station")
        self.window, self.vsync, scaled = self._open_window()
        # SCALED: draw straight to the display and let the GPU scale it to the window
        self.canvas = self.window if scaled else pygame.Surface((CANVAS_W, CANVAS_H)).convert()
        self.clock = pygame.time.Clock()
        self.assets = Assets((CANVAS_W, CANVAS_H))
        pygame.display.set_icon(self.assets.player_sprite(5, "down", 0, 2))
        self.fade = 0.0             # seconds left of the fade-in after a screen change
        self.prefs = self._load_prefs()
        self.character, self.character_saved = self._load_character()
        self.me = None              # LOGIN_OK fields
        self.room = None            # latest ROOM_UPDATE
        self.questions = None       # latest QUESTIONS (only the host of a room gets one)
        self.connected = False
        self.banner = None
        self.mouse_pos = (0, 0)
        self.running = True
        self.net = None
        self.server = None          # the embedded server, when this PC hosts
        self.tcp_port = args.tcp_port
        from client import sfx
        self.sfx = sfx.Sfx()
        if args.server:
            self.connect(args.server)
            from client.screens.login import LoginScreen
            self.screen = LoginScreen(self)
        else:
            from client.screens.launch import LaunchScreen
            self.screen = LaunchScreen(self)
        self.fade = FADE_S

    # --- server link --------------------------------------------------------------------------
    def connect(self, host):
        """Start talking to the server at `host` (TCP connects in the background)."""
        if self.net is not None:
            self.net.close()
        self.net = NetClient(host, self.tcp_port)
        self.net.start()
        self.connected = False
        self.save_prefs(server=host)

    def disconnect(self):
        """Drop the link to a (non-embedded) server, e.g. to fix a mistyped address."""
        if self.net is not None:
            self.net.close()
        self.net = None
        self.connected = False
        self.banner = None
        self.me = self.room = self.questions = None

    def host_server(self):
        """Run the game server inside this app, then connect to it. Returns a notice or None."""
        notice = None
        if self.server is None:
            from server.main import Server
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                                datefmt="%H:%M:%S")
            try:
                self.server = Server(config.BIND_HOST, self.tcp_port, config.UDP_PORT)
            except OSError:
                notice = f"Port {self.tcp_port} is busy - joining the server already running on this PC"
            else:
                threading.Thread(target=self.server.serve_forever, name="server", daemon=True).start()
        self.connect("127.0.0.1")
        return notice

    def server_addresses(self):
        """(lan_ip, [tailscale ips]) of the embedded server, or None when not hosting."""
        return self.server.addresses if self.server is not None else None

    @property
    def is_spectator(self):
        """True when I watch the current room instead of playing in it (the host always does)."""
        room, me = self.room, self.me
        if not room or not me:
            return False
        return not any(p["id"] == me["player_id"] for p in room.get("players", []))

    @property
    def is_host(self):
        room, me = self.room, self.me
        return bool(room and me and room.get("host") == me["player_id"])

    def set_screen(self, screen):
        if type(screen) is not type(self.screen):
            self.fade = FADE_S
        self.screen = screen

    def make_game_screen(self, state=None, countdown=None):
        from client.screens.game import GameScreen
        from client.screens.spectator import SpectatorScreen
        cls = SpectatorScreen if self.is_spectator else GameScreen
        return cls(self, state=state, countdown=countdown)

    def on_login(self, m):
        self.me = dict(m)
        self.net.start_udp(m["token"], m["udp_port"])
        # never picked: the server deals one out by seat; TCP is ordered, so this lands before any join
        if self.character_saved:
            self.net.send(P.msg(P.SET_CHARACTER, character=self.character))

    # --- preferences (remembered between runs) -------------------------------------------------
    @staticmethod
    def _load_prefs():
        try:
            with open(PREFS_PATH) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_prefs(self, **kw):
        self.prefs.update(kw)
        try:
            with open(PREFS_PATH, "w") as f:
                json.dump(self.prefs, f)
        except OSError:
            pass

    def _load_character(self):
        c = self.prefs.get("character")
        if characters.valid(c):
            return c, True
        return 0, False

    def set_character(self, c):
        """Pick a character: shown at once locally, then confirmed by the server's roster."""
        if not characters.valid(c):
            return
        self.character, self.character_saved = c, True
        self.save_prefs(character=c)
        if self.me is not None:
            self.net.send(P.msg(P.SET_CHARACTER, character=c))
            if self.room:
                for p in self.room.get("players", []):
                    if p["id"] == self.me["player_id"]:
                        p["character"] = c

    # --- window ---------------------------------------------------------------------------
    @staticmethod
    def _open_window():
        """A 1280x720 logical canvas that SDL scales on the GPU to any window size.

        With SCALED the display surface *is* the canvas: no per-frame CPU rescale, mouse
        positions arrive in canvas coordinates, and vsync gives even frame pacing.
        """
        os.environ["SDL_RENDER_SCALE_QUALITY"] = "0"     # nearest neighbour: hard pixel edges
        flags = pygame.SCALED | pygame.RESIZABLE
        for vsync in (1, 0):
            try:
                return pygame.display.set_mode((CANVAS_W, CANVAS_H), flags, vsync=vsync), bool(vsync), True
            except pygame.error:
                continue
        return pygame.display.set_mode((CANVAS_W, CANVAS_H), pygame.RESIZABLE), False, False

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
        elif t == P.RESUME_OK and m.get("version") != P.VERSION:
            from client.screens.login import OLD_SERVER
            self.banner = None
            self.net.send(P.msg(P.LOGOUT))
            self.me = self.room = self.questions = None
            self.set_screen(LoginScreen(self, OLD_SERVER))
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
        elif t == P.ERROR and m.get("code") == P.E_VERSION and not isinstance(self.screen, LoginScreen):
            self.banner = None
            self.me = self.room = self.questions = None
            self.net.stop_udp()
            self.set_screen(LoginScreen(self, m.get("message")))
        elif t == P.ERROR and m.get("code") == P.E_RESUME_FAILED:
            self.banner = None
            self.me = self.room = None
            self.net.stop_udp()
            self.set_screen(LoginScreen(self, m.get("message")))
        elif t == P.ROOM_UPDATE:
            self.room = m
            self.screen.handle_msg(m)
        elif t == P.QUESTIONS:
            self.questions = m
            self.screen.handle_msg(m)
        elif t == P.ROOM_CLOSED:
            self.room = self.questions = None
            self.set_screen(LobbyScreen(self, f"Room closed: {m.get('reason', '')}"))
        elif t == P.LOGOUT_OK:
            self.me = self.room = self.questions = None
            self.net.stop_udp()
            self.set_screen(LoginScreen(self, "Logged out"))
        else:
            self.screen.handle_msg(m)

    # --- main loop -----------------------------------------------------------------------
    def frame(self):
        """One iteration of the main loop: input, network, update, draw."""
        # vsync paces the loop; the cap only guards drivers that ignore it
        dt = self.clock.tick(FPS_CAP if self.vsync else 60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
                return
            if e.type == pygame.KEYDOWN and (e.key == pygame.K_F11 or
                                             (e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT)):
                pygame.display.toggle_fullscreen()
                continue
            e = self._map_event(e)
            if e.type == pygame.MOUSEMOTION:
                self.mouse_pos = e.pos
            self.screen.handle_event(e)
        while self.net is not None:
            m = self.net.poll()
            if m is None:
                break
            self.dispatch(m)
        self.screen.update(dt)
        if self.screen.backdrop:
            self.assets.backdrop(self.screen.backdrop, **BACKDROPS.get(self.screen.backdrop, {})).draw(self.canvas)
        else:
            self.canvas.fill(ui.BG)
        self.screen.draw(self.canvas)
        if self.fade > 0:
            self.fade = max(0.0, self.fade - dt)
            ui.dim(self.canvas, int(255 * self.fade / FADE_S) // 16 * 16, ui.INK)
        if self.banner:
            r = pygame.Rect(0, 0, CANVAS_W, 44)
            pygame.draw.rect(self.canvas, ui.INK, r)
            ui.hazard(self.canvas, (0, 0, CANVAS_W, 8), ui.BAD)
            ui.hazard(self.canvas, (0, 36, CANVAS_W, 8), ui.BAD)
            ui.text(self.canvas, self.banner.upper(), (r.centerx, r.centery), 16, ui.ICE, bold=True, anchor="center")
        if self.canvas is not self.window:              # fallback window without SCALED
            s, ox, oy = self._transform()
            self.window.fill((0, 0, 0))
            size = (int(CANVAS_W * s), int(CANVAS_H * s))
            frame = self.canvas if size == (CANVAS_W, CANVAS_H) else pygame.transform.smoothscale(self.canvas, size)
            self.window.blit(frame, (int(ox), int(oy)))
        pygame.display.flip()

    def run(self):
        while self.running:
            self.frame()
        if self.net is not None:
            self.net.close()
        if self.server is not None:
            self.server.shutdown()
        pygame.quit()


def main():
    ap = argparse.ArgumentParser(description="Ultimate Slop Showdown client")
    ap.add_argument("--server", default=os.environ.get("ARENA_SERVER") or None,
                    help="server address: LAN IP (192.168.x.y) or Tailscale IP (100.x.y.z); "
                         "leave it out to get the host / join launcher")
    ap.add_argument("--tcp-port", type=int, default=config.TCP_PORT)
    args = ap.parse_args()
    App(args).run()


if __name__ == "__main__":
    sys.exit(main())
