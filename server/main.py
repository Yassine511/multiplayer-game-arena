"""Central authoritative game server.

Threads: accept loop (TCP), one reader + one writer per client, UDP loop,
tick loop (20 Hz: snapshots, timers, heartbeats).

Run from the arena/ folder:   python -m server.main
"""
import argparse
import logging
import os
import socket
import threading
import time

from common import config
from common import protocol as P
from server import game
from server.auth import Session, SessionTable, UserStore
from server.connection import Connection
from server.rooms import RoomRegistry
from server.udp import UdpService

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def detect_addresses():
    """LAN IP (via the routing table, no packet sent) and any Tailscale 100.x IPs."""
    lan = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    tailscale = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            first, second = (int(v) for v in ip.split(".")[:2])
            if first == 100 and 64 <= second <= 127 and ip not in tailscale:   # CGNAT range Tailscale uses
                tailscale.append(ip)
    except (OSError, ValueError):
        pass
    return lan, tailscale


class Server:
    def __init__(self, bind_host, tcp_port, udp_port, public_host=None):
        self.log = logging.getLogger("arena.server")
        self.lock = threading.RLock()          # server_lock: users, sessions, room registry
        self.running = True
        self.users = UserStore(os.environ.get("ARENA_USERS_FILE") or os.path.join(DATA_DIR, "users.json"))
        if self.users.ensure_admin(config.ADMIN_USERNAME, config.ADMIN_PASSWORD):
            self.log.info("created admin account '%s'", config.ADMIN_USERNAME)
        n = game.load_questions(game.default_bank_path())
        self.log.info("loaded %d questions", n)
        self.sessions = SessionTable()
        self.rooms = RoomRegistry(self)
        self.conns = set()
        lan, ts = detect_addresses()
        self.public_host = public_host or config.PUBLIC_HOST or (ts[0] if ts else lan)
        self.addresses = (lan, ts)
        self.bind_host, self.tcp_port, self.udp_port = bind_host, tcp_port, udp_port
        self.udp = UdpService(self, bind_host, udp_port)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind((bind_host, tcp_port))
        self.listener.listen(32)
        self.listener.settimeout(1.0)

    # --- threads -------------------------------------------------------------------
    def serve_forever(self):
        threading.Thread(target=self.udp.loop, name="udp", daemon=True).start()
        threading.Thread(target=self._tick_loop, name="tick", daemon=True).start()
        lan, ts = self.addresses
        self.log.info("TCP %s:%d  UDP %s:%d", self.bind_host, self.tcp_port, self.bind_host, self.udp_port)
        self.log.info("LAN address: %s   Tailscale: %s", lan, ", ".join(ts) or "(not detected)")
        self.log.info("join strings use host %s", self.public_host)
        try:
            while self.running:
                try:
                    sock, addr = self.listener.accept()
                    sock.settimeout(None)
                except socket.timeout:
                    continue                    # wake up regularly so Ctrl+C works on Windows
                except OSError:
                    if not self.running:
                        break
                    continue
                conn = Connection(self, sock, addr)
                with self.lock:
                    self.conns.add(conn)
                self.log.info("connect %s:%d", *addr)
                conn.start()
        finally:
            self.shutdown()

    def shutdown(self):
        if not self.running:
            return
        self.running = False
        with self.lock:
            for room in list(self.rooms.rooms.values()):
                with room.lock:
                    self.rooms.close_room_locked(room, "Server shutting down")
            conns = list(self.conns)
        time.sleep(0.2)                         # let writers flush ROOM_CLOSED
        for c in conns:
            c.close()
        try:
            self.listener.close()
        except OSError:
            pass
        self.udp.close()

    def _tick_loop(self):
        period = 1.0 / config.TICK_HZ
        next_tick = time.monotonic()
        next_sweep = next_tick
        while self.running:
            now = time.monotonic()
            with self.lock:
                rooms = list(self.rooms.rooms.values())
            for room in rooms:
                snap = None
                with room.lock:
                    if room.closed:
                        continue
                    game.tick(room, now)
                    if room.phase == P.PHASE_PLAYING:
                        snap = self.udp.build_snapshot(room)
                    cleanup = room.needs_cleanup
                if snap:
                    self.udp.sendto(*snap)          # never send while holding a lock
                if cleanup:
                    self.rooms.post_game_cleanup(room)
            if now >= next_sweep:
                next_sweep = now + 0.5
                self._sweep(now)
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()

    def _sweep(self, now):
        """Heartbeats (no data for 5 s => dead link) and expired resume tokens."""
        with self.lock:
            conns = list(self.conns)
        for c in conns:
            if not c.closed and now - c.last_seen > config.HEARTBEAT_TIMEOUT_S:
                self.log.info("heartbeat timeout %s:%d", *c.addr)
                c.close()
                self.on_disconnect(c)           # idempotent; the reader may also call it
        with self.lock:
            for s in self.sessions.expired(now):
                self.log.info("session of %s expired", s.username)
                self.rooms.expire_session(s)
                self.sessions.remove(s)

    # --- dispatch --------------------------------------------------------------------
    def handle(self, conn, m):
        t = m["type"]
        if t == P.PING:
            conn.send(P.msg(P.PONG, t=m.get("t")))
            return
        if t == P.REGISTER:
            return self._on_register(conn, m)
        if t == P.LOGIN:
            return self._on_login(conn, m)
        if t == P.RESUME:
            return self._on_resume(conn, m)
        s = conn.session
        if s is None:
            conn.send(P.error(P.E_NOT_LOGGED_IN, "Log in first"))
            return
        if t == P.LOGOUT:
            return self._on_logout(conn, s)
        if t == P.LIST_ROOMS:
            return self.rooms.list_rooms(s)
        if t == P.CREATE_ROOM:
            return self.rooms.create_room(s)
        if t == P.JOIN_ROOM:
            return self.rooms.join_room(s, m.get("code"))
        if t == P.SPECTATE_ROOM:
            return self.rooms.spectate_room(s, m.get("code"))
        if t == P.LEAVE_ROOM:
            if s.room is None:
                s.send(P.error(P.E_NOT_IN_ROOM, "You are not in a room"))
            return self.rooms.leave_room(s)
        if t in (P.START_GAME, P.OPEN_TERMINAL, P.ANSWER):
            return self._on_game_msg(s, m)
        conn.send(P.error(P.E_BAD_REQUEST, f"Unknown message type {t}"))

    def _on_game_msg(self, s, m):
        room = s.room
        if room is None:
            s.send(P.error(P.E_NOT_IN_ROOM, "You are not in a room"))
            return
        now = time.monotonic()
        with room.lock:
            if m["type"] == P.START_GAME:
                game.start_game(room, s)
                return
            p = room.players.get(s.player_id)
            if p is None or not p.connected:
                s.send(P.error(P.E_FORBIDDEN, "Spectators cannot answer"))
                return
            try:
                tid = int(m.get("terminal_id"))
            except (TypeError, ValueError):
                s.send(P.error(P.E_BAD_REQUEST, "terminal_id required"))
                return
            if m["type"] == P.OPEN_TERMINAL:
                game.open_terminal(room, p, tid, now)
            else:
                game.answer(room, p, tid, m.get("question_id"), m.get("choice"), now)

    # --- accounts --------------------------------------------------------------------
    def _on_register(self, conn, m):
        ok, err = self.users.create(m.get("username"), m.get("password"))
        if ok:
            conn.send(P.msg(P.REGISTER_OK, username=m.get("username")))
            self.log.info("registered %s", m.get("username"))
        else:
            conn.send(P.error(err[0], err[1]))

    def _login_ok(self, s):
        return P.msg(P.LOGIN_OK, player_id=s.player_id, username=s.username, token=s.token,
                     role=s.role, udp_port=self.udp_port)

    def _on_login(self, conn, m):
        if conn.session is not None:
            conn.send(P.error(P.E_ALREADY_LOGGED_IN, "Already logged in"))
            return
        user = self.users.verify(m.get("username"), m.get("password"))   # slow hash, no lock held
        if user is None:
            conn.send(P.error(P.E_AUTH_FAILED, "Wrong username or password"))
            return
        with self.lock:
            s = self.sessions.by_player.get(user["id"])
            if s is not None and s.conn is not None and not s.conn.closed:
                conn.send(P.error(P.E_ALREADY_LOGGED_IN, "This account is already logged in elsewhere"))
                return
            resumed = s is not None
            if s is None:
                s = Session(user["id"], user["username"], user["role"])
                self.sessions.add(s)
            self._attach(s, conn)
            conn.send(self._login_ok(s))
        self.log.info("login %s (%s)%s", s.username, s.role, " [resumed]" if resumed else "")
        if resumed:
            self._restore(s)

    def _on_resume(self, conn, m):
        token = m.get("token")
        with self.lock:
            s = self.sessions.by_token.get(token) if isinstance(token, str) else None
            if s is None or conn.session is not None:
                conn.send(P.error(P.E_RESUME_FAILED, "Session expired, please log in again"))
                return
            self._attach(s, conn)
        self.log.info("resume %s", s.username)
        self._restore(s)

    def _attach(self, s, conn):
        """server.lock held. Bind a session to a (new) connection."""
        old = s.conn
        s.conn = conn
        s.disconnected_at = None
        s.udp_addr = None                       # client sends UDP_HELLO again
        conn.session = s
        if old is not None and old is not conn:
            old.close()                         # its on_disconnect sees s.conn is not old -> ignored

    def _restore(self, s):
        """Send the current room/game state after a RESUME or a re-login."""
        with self.lock:
            room = s.room
            if room is None:
                s.send(P.msg(P.RESUME_OK, player_id=s.player_id, username=s.username, token=s.token,
                             role=s.role, udp_port=self.udp_port, room=None, game=None, spectator=False))
                return
            with room.lock:
                spectator = s.player_id in room.spectators
                in_game = room.phase != P.PHASE_WAITING
                s.send(P.msg(P.RESUME_OK, player_id=s.player_id, username=s.username, token=s.token,
                             role=s.role, udp_port=self.udp_port, room=room.roster(),
                             game=game.started_message(room) if in_game else None,
                             spectator=spectator))
                p = room.players.get(s.player_id)
                if p is not None and in_game and p.status == P.STATUS_DISCONNECTED:
                    game.on_player_back(room, p)
                elif not in_game:
                    room.broadcast(room.roster())

    def _on_logout(self, conn, s):
        self.rooms.leave_room(s)
        with self.lock:
            self.sessions.remove(s)
            s.conn = None
            conn.session = None
        conn.send(P.msg(P.LOGOUT_OK))
        self.log.info("logout %s", s.username)

    # --- disconnects -------------------------------------------------------------------
    def on_disconnect(self, conn):
        with self.lock:
            self.conns.discard(conn)
            s = conn.session
            if s is None or s.conn is not conn:
                return                          # never logged in, or already replaced by a RESUME
            s.conn = None
            s.udp_addr = None
            s.disconnected_at = time.monotonic()
            self.log.info("disconnect %s", s.username)
            room = s.room
            if room is None:
                return
            with room.lock:
                if room.phase == P.PHASE_WAITING:
                    self.rooms._remove_member_locked(room, s, "disconnected")
                else:
                    p = room.players.get(s.player_id)
                    if p is not None:
                        game.on_player_gone(room, p, P.STATUS_DISCONNECTED)
                    # a spectator just stops receiving; the game goes on


def main():
    ap = argparse.ArgumentParser(description="Multiplayer Game Arena server")
    ap.add_argument("--host", default=config.BIND_HOST, help="bind address (default 0.0.0.0)")
    ap.add_argument("--tcp-port", type=int, default=config.TCP_PORT)
    ap.add_argument("--udp-port", type=int, default=config.UDP_PORT)
    ap.add_argument("--public-host", default=None, help="address shown in the join string / QR")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    server = Server(args.host, args.tcp_port, args.udp_port, args.public_host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.log.info("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
