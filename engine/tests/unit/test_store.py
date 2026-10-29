"""T012: the per-session store (research R13, data-model "Session folder")."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from mcp_privacy_guard.errors import BadInput, Refused, StoreUnavailable
from mcp_privacy_guard.store import Store


def mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def sess(home: Path, sid: str) -> Path:
    return home / "store" / "sessions" / sid


def test_begin_creates_owner_only_files(home: Path) -> None:
    store = Store.begin(home, "s1")
    folder = sess(home, "s1")
    assert mode(folder) == 0o700
    assert mode(folder / "secret.key") == 0o600
    assert len((folder / "secret.key").read_bytes()) == 32
    assert mode(folder / "mapping.sqlite") == 0o600
    assert store.key == (folder / "secret.key").read_bytes()


def test_begin_on_live_session_is_refused(home: Path) -> None:
    Store.begin(home, "s1")
    with pytest.raises(Refused) as err:
        Store.begin(home, "s1")
    assert err.value.code == "session-live"


def test_open_missing_session_creates_nothing(home: Path) -> None:
    with pytest.raises(StoreUnavailable) as err:
        Store.open(home, "nope")
    assert err.value.code == "session-missing"
    assert not (home / "store").exists()


@pytest.mark.parametrize("sid", ["", "../x", "a/b", "a" * 129, "a b", "é"])
def test_bad_session_id(home: Path, sid: str) -> None:
    for call in (Store.begin, Store.open, Store.end):
        with pytest.raises(BadInput):
            call(home, sid)


def test_permissive_secret_refused(home: Path) -> None:
    Store.begin(home, "s1")
    os.chmod(sess(home, "s1") / "secret.key", 0o644)
    with pytest.raises(StoreUnavailable) as err:
        Store.open(home, "s1")
    assert err.value.code == "too-permissive"


def test_unreadable_secret_refused(home: Path) -> None:
    Store.begin(home, "s1")
    os.chmod(sess(home, "s1") / "secret.key", 0o000)
    try:
        with pytest.raises(StoreUnavailable) as err:
            Store.open(home, "s1")
        assert err.value.code == "unreadable"
    finally:
        os.chmod(sess(home, "s1") / "secret.key", 0o600)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_store_in_unignored_git_tree_refused(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S607
    inside = tmp_path / "guard"
    with pytest.raises(StoreUnavailable) as err:
        Store.begin(inside, "s1")
    assert err.value.code == "in-git-tree"
    (tmp_path / ".gitignore").write_text("guard/\n")
    Store.begin(inside, "s1")


def test_end_deletes_everything_and_is_idempotent(home: Path) -> None:
    store = Store.begin(home, "s1")
    store.issue("IP", "10.1.1.1", "10.9.9.9")
    store.close()
    Store.end(home, "s1")
    assert not sess(home, "s1").exists()
    Store.end(home, "s1")  # already gone: not an error


def test_sweep_deletes_only_old_other_sessions(home: Path) -> None:
    for sid in ("old", "new", "mine"):
        Store.begin(home, sid).close()
    long_ago = time.time() - 25 * 3600
    for sid in ("old", "mine"):
        folder = sess(home, sid)
        for path in [*folder.iterdir(), folder]:
            os.utime(path, (long_ago, long_ago))
    assert Store.sweep(home, "mine") == 1
    assert not sess(home, "old").exists()
    assert sess(home, "new").exists()
    assert sess(home, "mine").exists()


def test_issue_is_idempotent_and_rev_increases(home: Path) -> None:
    store = Store.begin(home, "s1")
    assert store.rev() == 0
    assert store.issue("IP", "10.1.1.1", "10.9.9.9") == "10.9.9.9"
    assert store.rev() == 1
    assert store.issue("IP", "10.1.1.1", "10.7.7.7") == "10.9.9.9"
    assert store.rev() == 1
    store.issue("NAME", "fw-1", "n-aaaaaa", token="aaaaaa")
    assert store.rev() == 2
    row = store.lookup_standin("n-aaaaaa")
    assert row is not None
    assert (row["kind"], row["real"], row["token"]) == ("NAME", "fw-1", "aaaaaa")
    assert store.lookup_token("aaaaaa") is not None
    assert store.lookup_standin("n-zzzzzz") is None


def test_table_since(home: Path) -> None:
    store = Store.begin(home, "s1")
    store.issue("IP", "10.1.1.1", "10.9.9.9")
    store.issue("IP", "10.1.1.2", "10.9.9.8")
    rev, entries = store.table(1)
    assert rev == 2
    assert entries == [{"standin": "10.9.9.8", "real": "10.1.1.2", "kind": "IP"}]
    assert store.table(2) == (2, [])


def test_sessions_are_independent(home: Path) -> None:
    a = Store.begin(home, "a")
    b = Store.begin(home, "b")
    assert a.key != b.key
    a.issue("IP", "10.1.1.1", "10.9.9.9")
    assert b.lookup_standin("10.9.9.9") is None
    assert b.table(0) == (0, [])


def test_ephemeral_store_with_fixed_key() -> None:
    store = Store.ephemeral(b"k" * 32)
    assert store.key == b"k" * 32
    assert store.issue("IP", "10.1.1.1", "10.9.9.9") == "10.9.9.9"
    assert store.lookup_standin("10.9.9.9") is not None
    assert store.table(0)[0] == 1
