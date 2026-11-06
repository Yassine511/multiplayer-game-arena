"""Accounts (users.json with salted PBKDF2 hashes) and login sessions."""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading

from common import config

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
MIN_PASSWORD = 4


class UserStore:
    """users.json: {username: {id, role, salt, hash}}. Passwords never stored in clear."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()      # guards the dict and the file; never held while hashing
        self.users = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.users = json.load(f)

    @staticmethod
    def _hash(password, salt_hex):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), config.PBKDF2_ITERATIONS
        ).hex()

    def _save_locked(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.users, f, indent=2)
        os.replace(tmp, self.path)

    def create(self, username, password, role="player"):
        """Return (True, None) or (False, (error_code, message))."""
        if not isinstance(username, str) or not USERNAME_RE.match(username):
            return False, ("invalid", "Username must be 3-16 letters, digits or _")
        if not isinstance(password, str) or len(password) < MIN_PASSWORD:
            return False, ("invalid", f"Password must be at least {MIN_PASSWORD} characters")
        salt = secrets.token_hex(16)
        digest = self._hash(password, salt)           # slow on purpose: outside the lock
        with self.lock:
            if username.lower() in (u.lower() for u in self.users):
                return False, ("user_exists", "Username already taken")
            next_id = max((u["id"] for u in self.users.values()), default=0) + 1
            self.users[username] = {"id": next_id, "role": role, "salt": salt, "hash": digest}
            self._save_locked()
        return True, None

    def verify(self, username, password):
        """Return {"id", "username", "role"} if the credentials are right, else None."""
        if not isinstance(username, str) or not isinstance(password, str):
            return None
        with self.lock:
            rec = self.users.get(username)
            rec = dict(rec) if rec else None
        if rec is None:
            return None
        if not hmac.compare_digest(self._hash(password, rec["salt"]), rec["hash"]):
            return None
        return {"id": rec["id"], "username": username, "role": rec["role"]}

    def ensure_admin(self, username, password):
        with self.lock:
            exists = username in self.users
        if not exists:
            ok, err = self.create(username, password, role="admin")
            if not ok:
                raise RuntimeError(f"cannot create admin account: {err}")
            return True
        return False


class Session:
    """One logged-in user. Survives a dropped TCP connection for RESUME_WINDOW_S."""

    def __init__(self, player_id, username, role):
        self.player_id = player_id
        self.username = username
        self.role = role
        self.token = secrets.token_hex(16)
        self.conn = None              # current Connection, None while disconnected
        self.udp_addr = None          # (ip, port) learned from UDP_HELLO
        self.room = None              # Room the user is in (player or spectator)
        self.disconnected_at = None   # monotonic time of the drop

    @property
    def is_admin(self):
        return self.role == "admin"

    def send(self, obj):
        conn = self.conn
        if conn is not None:
            conn.send(obj)


class SessionTable:
    """Online sessions by token and by player id. Guarded by server_lock."""

    def __init__(self):
        self.by_token = {}
        self.by_player = {}

    def add(self, session):
        self.by_token[session.token] = session
        self.by_player[session.player_id] = session

    def remove(self, session):
        self.by_token.pop(session.token, None)
        if self.by_player.get(session.player_id) is session:
            del self.by_player[session.player_id]

    def expired(self, now):
        return [
            s for s in self.by_token.values()
            if s.conn is None and s.disconnected_at is not None
            and now - s.disconnected_at > config.RESUME_WINDOW_S
        ]
