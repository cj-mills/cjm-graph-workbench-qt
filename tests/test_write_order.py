"""THE SEAT'S WRITE ORDER (ruling d2d05e78 (4), work item eeda5977 leg L4): the workbench's write
gestures run the CLI's own landing functions inside its unit of work, held to the CLI's proof --
- every gesture's ops land in the writes journal, a gesture that changes nothing journals nothing,
  and the db's applied cursor stands at the journal's end (finding F1: an app write once left it
  behind, so the next cg-write re-applied the app's ops as a crashed tail);
- the live db equals the replay of its journal ELEMENT FOR ELEMENT (`rebuild-diff`, ruling f8b9c728);
- a gesture killed between an append and its apply (CJM_JOURNAL_FAULT, exit 86) heals at the next
  gesture's writer, which completes the chain, so the journal equals the uncrashed run's;
- a gesture waits for the family's lock without blocking the session's loop.
Drives the real projection CLI (replay, rebuild-diff, journal-cursor) beside the session."""

import fcntl
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import psutil
import pytest
from cjm_context_graph_primitives.journal import lock_path, read_journal
from cjm_context_graph_primitives.writer import FAULT_EXIT, JOURNAL_FAULT_ENV
from cjm_context_graph_projection.runtime import DEFAULT_GRAPH_ID, DEFAULT_MANIFESTS
from cjm_dev_graph_schema.nodes import DecisionNode
from cjm_graph_workbench_qt.data import GraphSession

pytestmark = pytest.mark.skipif(
    not (Path(DEFAULT_MANIFESTS) / f"{DEFAULT_GRAPH_ID}.json").exists(),
    reason=f"graph capability {DEFAULT_GRAPH_ID!r} not installed at {DEFAULT_MANIFESTS}",
)

KEY, EMPTY = "2026-01-01_00-00-00", "2026-01-01_00-00-30"
ITEM, OTHER = "WORK ITEM: the seat's subject", "FINDING: the seat's other end"
ITEM_ID, OTHER_ID = DecisionNode(statement=ITEM).id, DecisionNode(statement=OTHER).id


def _cli(db: Path, jp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "cjm_context_graph_projection.cli",
                           "--graph-db-path", str(db), "--journal-path", str(jp), *args],
                          capture_output=True, text=True)


def _graph(run: Path) -> tuple:  # (db, writes journal): a graph seeded through the CLI
    run.mkdir(parents=True, exist_ok=True)
    (run / "graph.config.json").write_text(json.dumps({"memory_journal_path": str(run / "memory.jsonl")}))
    db, jp = run / "live.db", run / "writes.jsonl"
    r = _cli(db, jp, "decide", OTHER)
    assert r.returncode == 0, r.stderr
    return db, jp


def _ops(jp: Path) -> list:  # The journal as (verb, args): the clock abstracted
    return [(o["verb"], o["args"]) for o in read_journal(str(jp))]


def _held(db: Path, jp: Path) -> None:  # The cursor at the journal's end, the live db its replay
    r = _cli(db, jp, "journal-cursor")
    assert r.returncode == 0, f"the db's cursor is behind its journal: {r.stdout}{r.stderr}"
    rebuilt = db.parent / "rebuilt.db"
    r = _cli(rebuilt, jp, "replay")
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "cjm_context_graph_projection.cli", "--graph-db-path", str(db),
                        "rebuild-diff", "--against", str(rebuilt)], capture_output=True, text=True)
    assert r.returncode == 0, f"live != its replay:\n{r.stdout}{r.stderr}"


def _session(db: Path, jp: Path) -> GraphSession:
    s = GraphSession(str(db), journal_paths=[str(jp)])
    s.start()
    return s


def _flag(db: Path, jp: Path, crash: int = 0) -> subprocess.CompletedProcess:
    """The flag gesture's chain (a decide, its task_state) in a process of its own -- armed, it dies
    between the crash-th op's append and its apply."""
    code = textwrap.dedent(f"""
        from cjm_graph_workbench_qt.data import GraphSession
        s = GraphSession({str(db)!r}, journal_paths=[{str(jp)!r}])
        s.start()
        res = s.decide({ITEM!r}, state="open", session={KEY!r})
        assert not res.get("error"), res
        s.close()
    """)
    env = {**os.environ, **({JOURNAL_FAULT_ENV: f"after_append@{crash}"} if crash else {})}
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    out, err = proc.communicate()
    if crash:  # the crashed host's capability worker outlives it (finding f1734c73)
        for p in psutil.process_iter(["cmdline"]):
            cmd = p.info["cmdline"] or []
            if "--ppid" in cmd and cmd[cmd.index("--ppid") + 1:cmd.index("--ppid") + 2] == [str(proc.pid)]:
                p.terminate()
                p.wait(10)
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def test_every_write_gesture_lands_journaled_and_live_is_its_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("CJM_SESSION", KEY)  # the sitting the writes are stamped with (the guard reads the stamp first)
    db, jp = _graph(tmp_path)
    s = _session(db, jp)
    try:
        def step(fn, *verbs):
            before = len(_ops(jp))
            res = fn()
            assert [v for v, _ in _ops(jp)[before:]] == list(verbs), (verbs, res)
            return res

        step(lambda: s.register_session(KEY, started_at=1.0), "session")
        step(lambda: s.register_session(KEY, started_at=1.0))                       # no change
        res = step(lambda: s.decide(ITEM, state="open", session=KEY), "decide", "assert")
        assert res["decision_id"] == ITEM_ID and [f.get("error") for f in res["facts"]] == [None]
        step(lambda: s.decide(ITEM, state="open", session=KEY))                     # no change
        step(lambda: s.link(ITEM_ID[:8], OTHER_ID[:8], "REFERENCES"), "link")
        step(lambda: s.link(ITEM_ID, OTHER_ID, "REFERENCES"))                       # no change
        step(lambda: s.register_session(EMPTY, started_at=2.0), "session")
        step(lambda: s.retract_session(EMPTY), "retract-session")
        refused = step(lambda: s.retract_session(KEY))       # the decide is attributed to it
        assert "not an empty mint" in refused["error"]
    finally:
        s.close()
    _held(db, jp)


@pytest.mark.parametrize("k", [1, 2])
def test_a_crashed_gesture_heals_at_the_next_writer(tmp_path, k):
    uncrashed_db, uncrashed_jp = _graph(tmp_path / "a")
    assert _flag(uncrashed_db, uncrashed_jp).returncode == 0
    db, jp = _graph(tmp_path / "b")
    r = _flag(db, jp, crash=k)
    assert r.returncode == FAULT_EXIT, f"no crash ({r.returncode}): {r.stderr}"
    assert [v for v, _ in _ops(jp)][-k:] == ["decide", "assert"][:k]
    r = _cli(db, jp, "journal-cursor")
    assert "1 record(s) past it" in r.stdout, r.stdout     # the crashed op: appended, never applied
    assert _flag(db, jp).returncode == 0                   # the retry heals it, then plans the rest
    assert _ops(jp) == _ops(uncrashed_jp)
    _held(db, jp)


def test_a_gesture_waits_for_the_family_lock_without_blocking_the_loop(tmp_path):
    db, jp = _graph(tmp_path)
    s = _session(db, jp)
    s.decide(ITEM)
    fd = os.open(lock_path(str(jp)), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)          # another writer holds the family
        done = threading.Event()
        threading.Thread(target=lambda: (s.link(ITEM_ID, OTHER_ID, "REFERENCES"), done.set()),
                         daemon=True).start()
        time.sleep(0.5)
        assert not done.is_set(), "the write landed while another writer held the family's lock"
        assert s.sessions() is not None          # a read gesture runs while the write waits
        fcntl.flock(fd, fcntl.LOCK_UN)
        assert done.wait(30), "the write never landed once the lock was released"
        assert [v for v, _ in _ops(jp)][-1] == "link"
    finally:
        os.close(fd)
        s.close()
    _held(db, jp)
