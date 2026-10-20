"""The per-session store: secret, mapping, names and warm-up state (research R13).

One folder per Claude Code session, `<home>/store/sessions/<sid>/`, created by `begin` and
deleted by `end`. Only `begin` ever creates a secret: every other entry point raises
`StoreUnavailable("session-missing")` when the folder is gone, so a stand-in is never read
with another key.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp_privacy_guard.errors import BadInput, Refused, StoreUnavailable

SID = re.compile(r"[A-Za-z0-9_-]{1,128}")
STALE_SECONDS = 24 * 3600
SCHEMA_VERSION = "1"
AMBIGUOUS = "ambiguous:"

SCHEMA = """
CREATE TABLE standin (
    standin TEXT NOT NULL UNIQUE,
    token TEXT,
    kind TEXT NOT NULL,
    real TEXT NOT NULL,
    rev INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    fixed INTEGER NOT NULL DEFAULT 0,
    UNIQUE (kind, real)
);
CREATE UNIQUE INDEX standin_token ON standin (token) WHERE token IS NOT NULL;
CREATE INDEX standin_rev ON standin (rev);
CREATE TABLE names (
    real TEXT NOT NULL,
    kind TEXT NOT NULL,
    server TEXT NOT NULL,
    common_word INTEGER NOT NULL DEFAULT 0,
    UNIQUE (real, kind)
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

Row = dict[str, Any]


def check_sid(sid: str) -> str:
    if not SID.fullmatch(sid):
        raise BadInput("bad-session", "the session id is malformed", "use [A-Za-z0-9_-]{1,128}")
    return sid


def _sessions(home: Path) -> Path:
    return home / "store" / "sessions"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_unignored_git_tree(path: Path) -> bool:
    repo = next((p for p in [path, *path.parents] if (p / ".git").exists()), None)
    if repo is None:
        return False
    try:
        done = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", str(path)],  # noqa: S607
            cwd=repo,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return True  # cannot tell: fail closed
    return done.returncode != 0


def _check_store_location(home: Path) -> None:
    if _in_unignored_git_tree(home / "store"):
        raise StoreUnavailable(
            "in-git-tree",
            "the store lies inside a git work tree that does not ignore it",
            "add the folder to .gitignore or set MCP_PRIVACY_GUARD_HOME elsewhere",
        )


def _make_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


class Store:
    """An open session store. Use `begin`, `open` or `ephemeral`; never the constructor."""

    def __init__(self, key: bytes, db: sqlite3.Connection, folder: Path | None) -> None:
        self.key = key
        self._db = db
        self.folder = folder

    # -- lifecycle ---------------------------------------------------------------------

    @classmethod
    def begin(cls, home: Path, sid: str) -> Store:
        check_sid(sid)
        folder = _sessions(home) / sid
        if folder.exists():
            raise Refused("session-live", "this session already has a store")
        _make_private_dir(home)
        _make_private_dir(home / "store")
        _make_private_dir(_sessions(home))
        _check_store_location(home)
        try:
            folder.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise Refused("session-live", "this session already has a store") from exc
        os.chmod(folder, 0o700)
        key = secrets.token_bytes(32)
        fd = os.open(folder / "secret.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
        db_path = folder / "mapping.sqlite"
        os.close(os.open(db_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        db = cls._connect(db_path)
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [("schema_version", SCHEMA_VERSION), ("session_id", sid), ("created_at", _now())],
        )
        return cls(key, db, folder)

    @classmethod
    def open(cls, home: Path, sid: str) -> Store:
        check_sid(sid)
        folder = _sessions(home) / sid
        if not folder.is_dir():
            raise StoreUnavailable(
                "session-missing",
                "the session has expired or was never started",
                "start a new conversation (/clear)",
            )
        _check_store_location(home)
        db_path = folder / "mapping.sqlite"
        for path in (folder, folder / "secret.key", db_path):
            try:
                loose = _mode(path) & 0o077
            except OSError as exc:
                raise StoreUnavailable("unreadable", "the session store is unreadable") from exc
            if loose:
                raise StoreUnavailable(
                    "too-permissive",
                    "the session store is readable by others",
                    "start a new conversation (/clear)",
                )
        try:
            key = (folder / "secret.key").read_bytes()
        except OSError as exc:
            raise StoreUnavailable("unreadable", "the session secret is unreadable") from exc
        if len(key) != 32:
            raise StoreUnavailable("unreadable", "the session secret is damaged")
        try:
            db = cls._connect(db_path)
            db.execute("SELECT 1 FROM meta LIMIT 1")
        except sqlite3.Error as exc:
            raise StoreUnavailable("unreadable", "the session mapping is unreadable") from exc
        return cls(key, db, folder)

    @classmethod
    def ephemeral(cls, key: bytes) -> Store:
        db = cls._connect(":memory:")
        db.executescript(SCHEMA)
        return cls(key, db, None)

    @staticmethod
    def _connect(path: Path | str) -> sqlite3.Connection:
        db = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 5000")
        if str(path) != ":memory:":
            db.execute("PRAGMA journal_mode = WAL")
        return db

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def end(home: Path, sid: str) -> bool:
        """Delete the session folder, WAL files included. True when something was deleted."""
        check_sid(sid)
        folder = _sessions(home) / sid
        existed = folder.exists()
        shutil.rmtree(folder, ignore_errors=True)
        return existed and not folder.exists()

    @staticmethod
    def sweep(home: Path, except_sid: str | None = None) -> int:
        """Delete other sessions' folders untouched for over 24 hours."""
        root = _sessions(home)
        if not root.is_dir():
            return 0
        cutoff = time.time() - STALE_SECONDS
        swept = 0
        for folder in root.iterdir():
            if folder.name == except_sid or not folder.is_dir():
                continue
            try:
                touched = max(p.stat().st_mtime for p in [folder, *folder.iterdir()])
            except OSError:
                continue
            if touched < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
                swept += 1
        return swept

    @staticmethod
    def state(home: Path) -> str:
        """The condition of `<home>/store` itself: ready, in-git-tree or too-permissive."""
        store = home / "store"
        if not store.exists():
            return "ready"
        if _in_unignored_git_tree(store):
            return "in-git-tree"
        try:
            return "too-permissive" if _mode(store) & 0o077 else "ready"
        except OSError:
            return "unreadable"

    @staticmethod
    def live(home: Path) -> list[str]:
        """Ids of the sessions whose folder exists."""
        root = _sessions(home)
        if not root.is_dir():
            return []
        return sorted(f.name for f in root.iterdir() if f.is_dir() and SID.fullmatch(f.name))

    @staticmethod
    def exists(home: Path, sid: str) -> bool:
        return (_sessions(home) / check_sid(sid)).is_dir()

    # -- mapping -----------------------------------------------------------------------

    def rev(self) -> int:
        row = self._db.execute("SELECT COALESCE(MAX(rev), 0) AS r FROM standin").fetchone()
        return int(row["r"])

    def issue(
        self,
        kind: str,
        real: str,
        standin: str,
        token: str | None = None,
        fixed: bool = False,
    ) -> str:
        """Record a stand-in. The same (kind, real) always returns the first stand-in issued."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT standin FROM standin WHERE kind = ? AND real = ?", (kind, real)
            ).fetchone()
            if row is not None:
                self._db.execute("COMMIT")
                return str(row["standin"])
            clash = self._db.execute(
                "SELECT 1 FROM standin WHERE standin = ? OR (token IS NOT NULL AND token = ?)",
                (standin, token),
            ).fetchone()
            if clash is not None:
                raise Refused("standin-collision", "a stand-in is already used by another value")
            self._db.execute(
                "INSERT INTO standin (standin, token, kind, real, rev, first_seen, fixed)"
                " VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(rev), 0) + 1 FROM standin), ?, ?)",
                (standin, token, kind, real, _now(), int(fixed)),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return standin

    def fix(self, value: str) -> bool:
        """Record `value` as a fixed entry (`standin = real`): a value the model saw unchanged.

        Returns False and flags the value ambiguous when it is already another value's issued
        stand-in (research R15): `args` then refuses it and `reveal` marks it.
        """
        row = self.lookup_standin(value)
        if row is None:
            self.issue("FIXED", value, value, fixed=True)
            return True
        if not row["fixed"]:
            self.meta_set(AMBIGUOUS + value, "1")
            return False
        return True

    def is_ambiguous(self, value: str) -> bool:
        return self.meta_get(AMBIGUOUS + value) is not None

    def lookup_standin(self, standin: str) -> Row | None:
        return self._row("SELECT * FROM standin WHERE standin = ?", (standin,))

    def lookup_token(self, token: str) -> Row | None:
        return self._row("SELECT * FROM standin WHERE token = ?", (token,))

    def lookup_real(self, kind: str, real: str) -> Row | None:
        return self._row("SELECT * FROM standin WHERE kind = ? AND real = ?", (kind, real))

    def token_taken(self, token: str) -> bool:
        return self.lookup_token(token) is not None

    def table(self, since: int) -> tuple[int, list[Row]]:
        rows = self._db.execute(
            "SELECT standin, real, kind FROM standin WHERE rev > ? ORDER BY rev", (since,)
        ).fetchall()
        return self.rev(), [dict(r) for r in rows]

    # -- names and meta ----------------------------------------------------------------

    def add_name(self, real: str, kind: str, server: str, common_word: bool) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO names (real, kind, server, common_word) VALUES (?, ?, ?, ?)",
            (real, kind, server, int(common_word)),
        )

    def names(self) -> list[Row]:
        return [dict(r) for r in self._db.execute("SELECT * FROM names").fetchall()]

    def names_for(self, real: str) -> list[Row]:
        rows = self._db.execute("SELECT * FROM names WHERE real = ?", (real,)).fetchall()
        return [dict(r) for r in rows]

    def meta_get(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def meta_set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def meta_items(self, prefix: str) -> dict[str, str]:
        rows = self._db.execute(
            "SELECT key, value FROM meta WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
        return {str(r["key"]): str(r["value"]) for r in rows}

    def _row(self, sql: str, args: tuple[object, ...]) -> Row | None:
        row = self._db.execute(sql, args).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["fixed"] = bool(data["fixed"])
        return data
