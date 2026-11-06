"""Client networking: TCP + UDP on background threads.

Received TCP messages go into `inbox` (a queue.Queue) that the pygame loop
drains every frame, so the window never freezes waiting on a socket. The
newest UDP SNAPSHOT is kept in `latest_snapshot`.

Local pseudo-messages pushed to the inbox (type starts with "_"):
  _CONNECTED     TCP connection established (first time or after a drop)
  _LOST          connection lost, trying to reconnect
  _GAVE_UP       could not reconnect within the resume window
"""
import queue
import socket
import threading
import time

from common import config
from common import protocol as P


class NetClient:
    def __init__(self, host, tcp_port):
        self.host = host
        self.tcp_port = tcp_port
        self.inbox = queue.Queue()
        self.sock = None
        self.alive = False
        self.token = None
        self.udp_port = None
        self.last_rx = 0.0
        self.rtt_ms = None
        self._gen = 0
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._reconnecting = False
        self._closing = False
        # UDP
        self.udp = None
        self.udp_seq = 0
        self.hello_acked = False
        self.latest_snapshot = None
        self._last_snap_seq = 0

    # --- lifecycle -------------------------------------------------------------------
    def start(self):
        threading.Thread(target=self._ping_loop, name="ping", daemon=True).start()
        self._spawn_reconnect(first=True)

    def close(self):
        self._closing = True
        self.alive = False
        for s in (self.sock, self.udp):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    def _connect(self):
        s = socket.create_connection((self.host, self.tcp_port), timeout=4)
        s.settimeout(None)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._state_lock:
            self._gen += 1
            gen = self._gen
            self.sock = s
            self.alive = True
            self.last_rx = time.monotonic()
        threading.Thread(target=self._reader, args=(s, gen), name="tcp-reader", daemon=True).start()

    def _spawn_reconnect(self, first=False):
        with self._state_lock:
            if self._reconnecting or self._closing:
                return
            self._reconnecting = True
        threading.Thread(target=self._reconnect_loop, args=(first,), name="reconnect", daemon=True).start()

    def _reconnect_loop(self, first):
        # With a token we only have the resume window; before login keep trying.
        deadline = time.monotonic() + config.RESUME_WINDOW_S if self.token else None
        delay = 0 if first else 1.0
        while not self._closing:
            if deadline is not None and time.monotonic() > deadline:
                self.token = None
                self._reconnecting = False
                self.inbox.put({"type": "_GAVE_UP"})
                self._spawn_reconnect()        # reconnect plainly so the user can log in again
                return
            time.sleep(delay)
            delay = 1.5
            try:
                self._connect()
            except OSError:
                continue
            self._reconnecting = False
            self.inbox.put({"type": "_CONNECTED"})
            if self.token:
                self.send(P.msg(P.RESUME, token=self.token))
            return

    def _lost(self, gen):
        with self._state_lock:
            if gen != self._gen or not self.alive:
                return
            self.alive = False
            sock = self.sock
        try:
            sock.close()
        except OSError:
            pass
        if self._closing:
            return
        self.hello_acked = False
        self.inbox.put({"type": "_LOST"})
        self._spawn_reconnect()

    # --- TCP ---------------------------------------------------------------------------
    def _reader(self, sock, gen):
        reader = P.LineReader()
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                self.last_rx = time.monotonic()
                for m in reader.feed(chunk):
                    if m["type"] == P.PONG:
                        t = m.get("t")
                        if isinstance(t, (int, float)):
                            self.rtt_ms = (time.monotonic() - t) * 1000
                        continue
                    self.inbox.put(m)
        except (OSError, ValueError):
            pass
        self._lost(gen)

    def send(self, obj):
        data = P.encode_line(obj)
        with self._send_lock:
            sock, gen, alive = self.sock, self._gen, self.alive
            if not alive or sock is None:
                return False
            try:
                sock.sendall(data)
                return True
            except OSError:
                pass
        self._lost(gen)
        return False

    def _ping_loop(self):
        while not self._closing:
            time.sleep(config.PING_INTERVAL_S)
            if not self.alive:
                continue
            self.send(P.msg(P.PING, t=time.monotonic()))
            # nothing at all from the server for 5 s: the link is dead (no FIN/RST will come)
            if time.monotonic() - self.last_rx > config.HEARTBEAT_TIMEOUT_S:
                self._lost(self._gen)

    def poll(self):
        try:
            return self.inbox.get_nowait()
        except queue.Empty:
            return None

    # --- UDP ---------------------------------------------------------------------------
    def start_udp(self, token, udp_port):
        """After LOGIN_OK / RESUME_OK: bind our UDP address to the session."""
        self.token = token
        self.udp_port = udp_port
        if self.udp is None:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(("", 0))
            threading.Thread(target=self._udp_reader, name="udp-reader", daemon=True).start()
        self.hello_acked = False
        threading.Thread(target=self._hello_loop, name="udp-hello", daemon=True).start()

    def stop_udp(self):
        self.token = None
        self.hello_acked = True        # stops the hello loop

    def _hello_loop(self):
        # resent every second until the first SNAPSHOT proves the path works
        while not self.hello_acked and self.token and not self._closing:
            self._udp_send(P.msg(P.UDP_HELLO, token=self.token))
            time.sleep(1.0)

    def _udp_send(self, obj):
        if self.udp is None or self.udp_port is None:
            return
        try:
            self.udp.sendto(P.encode_dgram(obj), (self.host, self.udp_port))
        except OSError:
            pass

    def send_pos(self, x, y, direction):
        if not self.token:
            return
        self.udp_seq += 1
        self._udp_send(P.msg(P.POS, token=self.token, seq=self.udp_seq,
                             x=round(x, 1), y=round(y, 1), dir=direction))

    def reset_snapshots(self):
        self._last_snap_seq = 0
        self.latest_snapshot = None

    def _udp_reader(self):
        while not self._closing:
            try:
                data, _ = self.udp.recvfrom(4096)
            except ConnectionResetError:     # Windows: ICMP unreachable from an earlier send
                continue
            except OSError:
                if self._closing:
                    return
                time.sleep(0.1)
                continue
            try:
                m = P.decode_dgram(data)
            except (ValueError, UnicodeDecodeError):
                continue
            if m["type"] != P.SNAPSHOT:
                continue
            self.hello_acked = True
            seq = m.get("seq", 0)
            if seq <= self._last_snap_seq:      # late or duplicate: a newer one already arrived
                continue
            self._last_snap_seq = seq
            self.latest_snapshot = m
