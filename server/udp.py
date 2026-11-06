"""UDP: POS intake and SNAPSHOT broadcast.

UDP is connectionless, so every datagram carries the session token and the
server drops anything with an unknown token. Datagrams can arrive late or out
of order, so each carries a per-sender seq and stale ones are dropped.
"""
import itertools
import logging
import math
import socket
import sys
import time

from common import config, map_data
from common import protocol as P

log = logging.getLogger("arena.udp")


class UdpService:
    def __init__(self, server, host, port):
        self.server = server
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if sys.platform == "win32":
            # Windows reports ICMP "port unreachable" from an earlier sendto as an
            # error on the next recvfrom; turn that off so one gone client can't
            # disturb the loop.
            try:
                self.sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (AttributeError, OSError):
                pass
        self.sock.bind((host, port))
        self._seq = itertools.count(1)       # global, so it only ever grows

    def loop(self):
        while self.server.running:
            try:
                data, addr = self.sock.recvfrom(2048)
            except ConnectionResetError:
                continue
            except OSError:
                if not self.server.running:
                    return
                continue
            try:
                m = P.decode_dgram(data)
            except (ValueError, UnicodeDecodeError):
                continue
            try:
                if m["type"] == P.POS:
                    self._on_pos(m, addr)
                elif m["type"] == P.UDP_HELLO:
                    self._on_hello(m, addr)
            except Exception:
                log.exception("bad datagram from %s", addr)

    def _session(self, token):
        if not isinstance(token, str):
            return None
        with self.server.lock:
            return self.server.sessions.by_token.get(token)

    def _on_hello(self, m, addr):
        s = self._session(m.get("token"))
        if s is None:
            return                            # unknown token: drop silently
        s.udp_addr = addr                     # client sent first, so this works through NAT
        # acknowledge with an empty snapshot so the client stops resending HELLO
        self.sendto(P.msg(P.SNAPSHOT, seq=0, players=[]), [addr])

    def _on_pos(self, m, addr):
        s = self._session(m.get("token"))
        if s is None:
            return
        if s.udp_addr != addr:
            s.udp_addr = addr                 # NAT rebinding: follow the latest source address
        room = s.room
        if room is None:
            return
        try:
            seq = int(m["seq"])
            x = float(m["x"])
            y = float(m["y"])
        except (KeyError, TypeError, ValueError):
            return
        d = m.get("dir") if m.get("dir") in P.DIRECTIONS else None
        now = time.monotonic()
        with room.lock:
            p = room.players.get(s.player_id)
            if p is None or not p.connected or room.phase != P.PHASE_PLAYING:
                return
            if seq <= p.last_seq:             # late / duplicate datagram
                return
            p.last_seq = seq
            if d:
                p.dir = d
            # don't trust the client: reject moves faster than max speed or into walls
            elapsed = min(now - p.last_pos_time, 1.0)
            allowed = config.PLAYER_SPEED * elapsed * 1.35 + 24
            if math.hypot(x - p.x, y - p.y) > allowed:
                return
            if map_data.blocked(x, y, config.PLAYER_RADIUS - 2):
                return
            p.x, p.y = x, y
            p.last_pos_time = now

    # --- snapshots ---------------------------------------------------------------
    def build_snapshot(self, room):
        """room.lock held. Returns (message, [addresses])."""
        players = [
            {"id": p.id, "x": round(p.x, 1), "y": round(p.y, 1), "dir": p.dir}
            for p in room.players.values() if p.status != P.STATUS_LEFT
        ]
        addrs = [s.udp_addr for s in room.member_sessions() if s.udp_addr and s.conn is not None]
        return P.msg(P.SNAPSHOT, seq=next(self._seq), players=players), addrs

    def sendto(self, obj, addrs):
        try:
            data = P.encode_dgram(obj)
        except ValueError as e:
            log.error("snapshot not sent: %s", e)
            return
        for a in addrs:
            try:
                self.sock.sendto(data, a)
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
