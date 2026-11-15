"""Single entry point: this is what the one-file executable runs.

    arena                         launcher window: HOST ON THIS PC, or JOIN a server by IP
    arena --server 192.168.1.20   straight to that server's login
    arena server [--public-host X]   headless server only (no window), logs to the terminal

From source the same works with `python arena.py ...`.
"""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    if args and args[0] == "server":
        sys.argv = [sys.argv[0]] + args[1:]
        from server.main import main as server_main
        return server_main()
    if args and args[0] == "client":
        sys.argv = [sys.argv[0]] + args[1:]
    from client.main import main as client_main
    return client_main()


if __name__ == "__main__":
    sys.exit(main())
