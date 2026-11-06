"""Wire protocol shared by server and clients.

Every message is a JSON object with a "type" field.
  * TCP: one object per line, terminated by "\\n" (TCP is a byte stream, so the
    reader buffers and splits on newlines).
  * UDP: one object per datagram, at most config.MAX_DATAGRAM bytes.
"""
import json

from common import config

# --- TCP: account and lobby ----------------------------------------------------
REGISTER = "REGISTER"
REGISTER_OK = "REGISTER_OK"
LOGIN = "LOGIN"
LOGIN_OK = "LOGIN_OK"
LOGOUT = "LOGOUT"
LOGOUT_OK = "LOGOUT_OK"
LIST_ROOMS = "LIST_ROOMS"
ROOM_LIST = "ROOM_LIST"
CREATE_ROOM = "CREATE_ROOM"
ROOM_CREATED = "ROOM_CREATED"
JOIN_ROOM = "JOIN_ROOM"
ROOM_JOINED = "ROOM_JOINED"
SPECTATE_ROOM = "SPECTATE_ROOM"
LEAVE_ROOM = "LEAVE_ROOM"
ROOM_UPDATE = "ROOM_UPDATE"
ROOM_CLOSED = "ROOM_CLOSED"

# --- TCP: game -----------------------------------------------------------------
START_GAME = "START_GAME"
GAME_COUNTDOWN = "GAME_COUNTDOWN"
GAME_STARTED = "GAME_STARTED"
OPEN_TERMINAL = "OPEN_TERMINAL"
TERMINAL_QUESTION = "TERMINAL_QUESTION"
ANSWER = "ANSWER"
ANSWER_RESULT = "ANSWER_RESULT"
TERMINAL_STATE = "TERMINAL_STATE"
SCORE_UPDATE = "SCORE_UPDATE"
TIME_SYNC = "TIME_SYNC"
PLAYER_STATUS = "PLAYER_STATUS"
GAME_OVER = "GAME_OVER"

# --- TCP: connection -----------------------------------------------------------
PING = "PING"
PONG = "PONG"
RESUME = "RESUME"
RESUME_OK = "RESUME_OK"
ERROR = "ERROR"

# --- UDP -----------------------------------------------------------------------
UDP_HELLO = "UDP_HELLO"
POS = "POS"
SNAPSHOT = "SNAPSHOT"

# --- Enumerations ----------------------------------------------------------------
PHASE_WAITING = "waiting"
PHASE_COUNTDOWN = "countdown"
PHASE_PLAYING = "playing"

TERMINAL_ACTIVE = "active"
TERMINAL_COOLDOWN = "cooldown"

RESULT_CORRECT = "correct"
RESULT_WRONG = "wrong"
RESULT_TOO_LATE = "too_late"
RESULT_LOCKED = "locked"

STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
STATUS_RECONNECTED = "reconnected"
STATUS_LEFT = "left"

DIRECTIONS = ("up", "down", "left", "right")

# Error codes carried in ERROR.code
E_BAD_REQUEST = "bad_request"
E_NOT_LOGGED_IN = "not_logged_in"
E_ALREADY_LOGGED_IN = "already_logged_in"
E_AUTH_FAILED = "auth_failed"
E_USER_EXISTS = "user_exists"
E_INVALID = "invalid"
E_RESUME_FAILED = "resume_failed"
E_ALREADY_IN_ROOM = "already_in_room"
E_NOT_IN_ROOM = "not_in_room"
E_BAD_CODE = "bad_code"
E_ROOM_FULL = "room_full"
E_ROOM_STARTED = "room_started"
E_FORBIDDEN = "forbidden"
E_NOT_HOST = "not_host"
E_NOT_ENOUGH_PLAYERS = "not_enough_players"
E_NOT_PLAYING = "not_playing"
E_BAD_TERMINAL = "bad_terminal"
E_TOO_FAR = "too_far"
E_LOCKED_OUT = "locked_out"
E_COOLDOWN = "cooldown"
E_INTERNAL = "internal"


def msg(type_, **fields):
    """Build a message dict: msg(LOGIN, username='a', password='b')."""
    out = {"type": type_}
    out.update(fields)
    return out


def error(code, message, **extra):
    return msg(ERROR, code=code, message=message, **extra)


# --- TCP framing -------------------------------------------------------------------
def encode_line(obj):
    """Serialize one message as a single newline-terminated UTF-8 line."""
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")


def send_line(sock, obj):
    sock.sendall(encode_line(obj))


class LineReader:
    """Reassembles newline-delimited JSON from an arbitrary chunked byte stream.

    Two send() calls can arrive in one recv(), and one send() can be split
    across two recv() calls; feed() handles both by buffering.
    """

    def __init__(self, max_line=config.MAX_LINE):
        self.buf = b""
        self.max_line = max_line

    def feed(self, chunk):
        """Add raw bytes; return the list of complete messages now available.

        A malformed line is returned as {"type": "_BAD"} so the caller can
        answer with an ERROR instead of losing the rest of the stream.
        """
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
                if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
                    raise ValueError("not a message object")
                out.append(obj)
            except (ValueError, UnicodeDecodeError):
                out.append({"type": "_BAD"})
        if len(self.buf) > self.max_line:
            raise ValueError("line too long")
        return out


def read_lines(sock, bufsize=4096):
    """Generator yielding messages from a TCP socket until the peer closes."""
    reader = LineReader()
    while True:
        chunk = sock.recv(bufsize)
        if not chunk:                       # peer closed the connection (FIN)
            raise ConnectionError("peer closed the connection")
        for obj in reader.feed(chunk):
            yield obj


# --- UDP framing -------------------------------------------------------------------
def encode_dgram(obj):
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(data) > config.MAX_DATAGRAM:
        raise ValueError(f"datagram too large ({len(data)} bytes)")
    return data


def decode_dgram(data):
    obj = json.loads(data.decode("utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
        raise ValueError("not a message object")
    return obj
