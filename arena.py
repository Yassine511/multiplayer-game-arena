"""Single entry point: this is what the one-file executable runs.

    ultimate-slop-showdown                         launcher window: HOST ON THIS PC, or JOIN a server by IP
    ultimate-slop-showdown --server 192.168.1.20   straight to that server's login
    ultimate-slop-showdown server [--public-host X]   headless server only (no window), logs to the terminal

From source the same works with `python arena.py ...`.

The Windows build is a windowed app (no black console flashing up behind the game).
Its log lines go to arena_data/arena.log next to the exe; `ultimate-slop-showdown server` started from
a terminal attaches to that terminal (or opens a console) so the headless server
still prints its log.
"""
import multiprocessing
import os
import sys


def _log_file():
    folder = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "arena_data")
    try:
        os.makedirs(folder, exist_ok=True)
        return open(os.path.join(folder, "arena.log"), "a", buffering=1, encoding="utf-8", errors="replace")
    except OSError:
        return open(os.devnull, "w")


def _console_for_server():
    """Windowed exe started as `... server`: write to the terminal it came from, or a new one."""
    if sys.platform != "win32":
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    if not (k32.AttachConsole(-1) or k32.AllocConsole()):      # -1: the parent process's console
        return False
    try:
        sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stderr = sys.stdout
        sys.stdin = open("CONIN$", "r")
    except OSError:
        return False
    return True


def _fix_stdio(server_mode):
    """A windowed (console=False) PyInstaller exe starts with sys.stdout/stderr = None."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    if server_mode and _console_for_server():
        return
    log = _log_file()
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main():
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    server_mode = bool(args) and args[0] == "server"
    _fix_stdio(server_mode)
    if server_mode:
        sys.argv = [sys.argv[0]] + args[1:]
        from server.main import main as server_main
        return server_main()
    if args and args[0] == "client":
        sys.argv = [sys.argv[0]] + args[1:]
    from client.main import main as client_main
    return client_main()


if __name__ == "__main__":
    sys.exit(main())
