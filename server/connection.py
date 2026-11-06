"""One TCP client: a reader thread, a writer thread and an outbound queue.

Every other thread (tick loop, other clients' readers) only enqueues bytes and
returns, so two threads never call sendall() on the same socket at once and a
slow client can never block anyone but its own writer.
"""
import logging
import queue
import socket
import threading
import time
import traceback

from common import protocol as P

log = logging.getLogger("arena.conn")


class Connection:
    def __init__(self, server, sock, addr):
        self.server = server
        self.sock = sock
        self.addr = addr
        self.outbox = queue.Queue()
        self.session = None
        self.last_seen = time.monotonic()     # updated on every received chunk (heartbeat)
        self.closed = False
        self._close_lock = threading.Lock()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # no Nagle delay

    def start(self):
        threading.Thread(target=self._reader, name=f"reader-{self.addr}", daemon=True).start()
        threading.Thread(target=self._writer, name=f"writer-{self.addr}", daemon=True).start()

    def send(self, obj):
        if not self.closed:
            self.outbox.put(P.encode_line(obj))

    def close(self):
        with self._close_lock:
            if self.closed:
                return
            self.closed = True
        self.outbox.put(None)                 # wake the writer so it exits
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            # On Windows shutdown() alone does not wake a thread blocked in recv();
            # closing the socket does.
            self.sock.close()
        except OSError:
            pass

    def _reader(self):
        reader = P.LineReader()
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:                 # FIN: app closed normally
                    break
                self.last_seen = time.monotonic()
                for m in reader.feed(chunk):
                    if m["type"] == "_BAD":
                        self.send(P.error(P.E_BAD_REQUEST, "Malformed JSON line"))
                        continue
                    try:
                        self.server.handle(self, m)
                    except Exception:         # a bug in one handler must not kill the server
                        log.error("handler error for %s: %s", m.get("type"), traceback.format_exc())
                        self.send(P.error(P.E_INTERNAL, "Server error"))
        except (OSError, ValueError) as e:    # RST, timeout, line too long...
            log.info("connection %s error: %s", self.addr, e)
        except Exception:
            log.error("reader crashed: %s", traceback.format_exc())
        finally:
            self.close()
            try:
                self.server.on_disconnect(self)
            finally:
                try:
                    self.sock.close()
                except OSError:
                    pass

    def _writer(self):
        while True:
            data = self.outbox.get()
            if data is None:
                return
            try:
                self.sock.sendall(data)
            except OSError:
                self.close()
                return
