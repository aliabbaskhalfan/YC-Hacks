#!/usr/bin/env python3
"""Reserve a block of free TCP ports per Superset workspace.

Superset does not pre-assign port ranges; it discovers whatever a workspace
happens to be listening on. So parallel workspaces running the same dev
servers (Vite, FastAPI, the sim WS server) all race for the same default
port. This allocator gives each workspace its own aligned block, recorded in
a shared file so sibling workspaces cannot pick it:

    ~/.superset/port-allocations.json

    {
      "/path/to/worktree": {"base": 3000, "size": 3, "workspace": "web-ui"}
    }

Usage:
    ports.py reserve <workspace-path> [--name N] [--size N] [--start N]
    ports.py release <workspace-path>
    ports.py show    <workspace-path>

`reserve` prints the base port and is idempotent: the same workspace path
always gets its existing reservation back, so re-running setup never shifts
ports out from under a running dev server.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import socket
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("SUPERSET_HOME", Path.home() / ".superset"))
STATE_FILE = STATE_DIR / "port-allocations.json"
LOCK_DIR = STATE_DIR / "port-allocations.lock"

LOCK_TIMEOUT = 30.0  # seconds to wait for a sibling workspace to finish
LOCK_STALE = 120.0  # seconds after which a held lock is assumed abandoned
MAX_PORT = 65000


# --------------------------------------------------------------------------- #
# Locking: mkdir is atomic on every POSIX filesystem, so it is the lock.
# --------------------------------------------------------------------------- #


def _lock_is_stale() -> bool:
    try:
        age = time.time() - LOCK_DIR.stat().st_mtime
    except FileNotFoundError:
        return False
    if age > LOCK_STALE:
        return True
    try:
        pid = int((LOCK_DIR / "pid").read_text().strip())
    except (OSError, ValueError):
        return False
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.ESRCH  # holder is gone
    return False


def _clear_lock() -> None:
    try:
        (LOCK_DIR / "pid").unlink()
    except OSError:
        pass
    try:
        LOCK_DIR.rmdir()
    except OSError:
        pass


def acquire_lock() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + LOCK_TIMEOUT
    while True:
        try:
            LOCK_DIR.mkdir()
            (LOCK_DIR / "pid").write_text(str(os.getpid()))
            return
        except FileExistsError:
            if _lock_is_stale():
                print(f"warn: reclaiming stale port-allocation lock {LOCK_DIR}", file=sys.stderr)
                _clear_lock()
                continue
            if time.time() > deadline:
                raise SystemExit(f"timed out after {LOCK_TIMEOUT:.0f}s waiting for {LOCK_DIR}")
            time.sleep(0.1)


def release_lock() -> None:
    _clear_lock()


# --------------------------------------------------------------------------- #
# State file
# --------------------------------------------------------------------------- #


def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        print(f"warn: ignoring unreadable {STATE_FILE}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(STATE_FILE)  # atomic, so readers never see a half-written file


def drop_vanished(state: dict) -> dict:
    """Free blocks whose worktree has been deleted.

    Teardown normally releases a block, but a workspace removed by hand (or a
    teardown that never ran) would otherwise leak its reservation forever.
    """
    return {p: e for p, e in state.items() if Path(p).is_dir()}


# --------------------------------------------------------------------------- #
# Port probing
# --------------------------------------------------------------------------- #


def port_in_use(port: int) -> bool:
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                return True
    return False


def block_is_free(base: int, size: int) -> bool:
    return all(not port_in_use(p) for p in range(base, base + size))


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_reserve(path: str, name: str, size: int, start: int) -> int:
    acquire_lock()
    try:
        state = drop_vanished(load_state())

        existing = state.get(path)
        if isinstance(existing, dict) and existing.get("size") == size:
            save_state(state)  # persist the vanished-workspace cleanup
            return int(existing["base"])

        taken = {
            int(e["base"])
            for p, e in state.items()
            if p != path and isinstance(e, dict) and "base" in e
        }

        base = start
        while base + size <= MAX_PORT:
            if base not in taken and block_is_free(base, size):
                state[path] = {"base": base, "size": size, "workspace": name}
                save_state(state)
                return base
            base += size
        raise SystemExit(f"no free {size}-port block found above {start}")
    finally:
        release_lock()


def cmd_release(path: str) -> None:
    acquire_lock()
    try:
        state = drop_vanished(load_state())
        state.pop(path, None)
        save_state(state)
    finally:
        release_lock()


def cmd_show(path: str) -> int:
    entry = load_state().get(path)
    if not isinstance(entry, dict) or "base" not in entry:
        raise SystemExit(f"no port block reserved for {path}")
    return int(entry["base"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    res = sub.add_parser("reserve", help="reserve (or re-read) this workspace's block")
    res.add_argument("path")
    res.add_argument("--name", default="", help="workspace name, for readability")
    res.add_argument("--size", type=int, default=3, help="ports per block")
    res.add_argument("--start", type=int, default=3000, help="lowest base port")

    rel = sub.add_parser("release", help="give this workspace's block back")
    rel.add_argument("path")

    shw = sub.add_parser("show", help="print this workspace's base port")
    shw.add_argument("path")

    args = parser.parse_args()
    path = str(Path(args.path).resolve())

    if args.cmd == "reserve":
        if args.size < 1:
            raise SystemExit("--size must be at least 1")
        print(cmd_reserve(path, args.name or Path(path).name, args.size, args.start))
    elif args.cmd == "release":
        cmd_release(path)
    elif args.cmd == "show":
        print(cmd_show(path))


if __name__ == "__main__":
    main()
