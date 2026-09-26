"""Offscreen stage-walk probe: the window paints all three stages and the seat
verbs navigate them, against a FAKE session (no graph). grab() proves the
agent-readable screenshot path (family craft: paint verifies by probe). The
window is a SHELL INSTANCE: reads arrive through the shell's bridge (the
fake's futures are already resolved, so delivery is synchronous), the
prompts are the shell's, the mint is the shell's."""

import os
from concurrent.futures import Future

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cjm_graph_workbench_qt.app import WorkbenchWindow

ANCHOR = "11111111-2222-3333-4444-555555555555"
LOCK = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CJM_KIT_PREFS", str(tmp_path / "theme.json"))
    monkeypatch.delenv("CJM_THEME", raising=False)
    monkeypatch.delenv("CJM_DECORATIONS", raising=False)
    monkeypatch.delenv("CJM_SESSION", raising=False)
    yield


def resolved(value) -> Future:
    fut = Future()
    fut.set_result(value)
    return fut


class FakeSession:
    """Canned lens views + write capture: one anchor, one lock note, one node
    detail, an empty feed; journaled writes append to `.writes` for asserting.
    The *_async variants return already-resolved futures (the shell's bridge
    delivers them synchronously)."""

    journal_paths: list = []

    def __init__(self):
        self.writes = []

    def feed(self, session_key=None, since=None, limit=200):
        return {"window": {"session": session_key, "since": since, "cursor": 1786700000.0,
                           "total_ops": 1, "shown": 1},
                "ops": [{"ts": 1786700000.0, "verb": "decide", "actor": "user:workbench",
                         "session": session_key, "summary": "a canned op",
                         "refs": [{"ref": LOCK[:8], "id": LOCK, "label": "Decision",
                                   "title": "the stub"}]}],
                "cards": [{"ref": LOCK[:8], "id": LOCK, "label": "Decision",
                           "title": "the stub", "verbs": {"decide": 1}, "touches": 1,
                           "first_ts": 1786700000.0, "last_ts": 1786700000.0}],
                "missing": 0}

    def feed_async(self, session_key=None, since=None, limit=200):
        return resolved(self.feed(session_key, since, limit))

    def body(self, ref):
        return "the stub body"

    def body_async(self, ref):
        return resolved(self.body(ref))

    def sessions(self, limit=500):
        return [{"id": LOCK, "key": "2026-08-13_00-00-00", "title": "older one",
                 "started_at": 1786600000.0},
                {"id": LOCK, "key": "2026-08-14_00-00-00", "title": "",
                 "started_at": 1786690000.0}]

    def sessions_async(self, limit=500):
        return resolved(self.sessions(limit))

    def search(self, term, limit=25):
        return ({"matches": [{"id": ANCHOR, "label": "Note", "title": "a name hit",
                              "path": "pkg/mod.py"}], "count": 1},
                {"matches": [{"id": LOCK, "label": "Decision", "title": "a content hit",
                              "field": "statement", "snippet": f"around {term} here"}],
                 "count": 1})

    def search_async(self, term, limit=25):
        return resolved(self.search(term, limit))

    def register_session(self, key, **kw):
        kw["env_at_write"] = os.environ.get("CJM_SESSION")  # stamp-order probe
        self.writes.append(("session", key, kw))
        return {"written": True, "key": key}

    def retract_session(self, key, **kw):
        self.writes.append(("retract-session", key, kw))
        return {"written": True}

    def decide(self, statement, **kw):
        self.writes.append(("decide", statement, kw))
        return {"decision_id": LOCK, "statement": statement}

    def link(self, source_id, target_id, relation, **kw):
        self.writes.append(("link", source_id, target_id, relation))
        return {"written": True, "source_id": source_id, "target_id": target_id}

    def portfolio(self):
        return {"counts": {"ready": 2, "blocked": 1, "done": 3, "closable": 1},
                "anchors": [{"id": ANCHOR, "slug": "program-x", "role": "program",
                             "vitals": {"ready": 2, "blocked": 1, "findings": 1},
                             "pins": 2, "lock": {"lead": "the lock lead line"}}],
                "links": []}

    def portfolio_async(self):
        return resolved(self.portfolio())

    def lead(self, ref):
        assert ref == ANCHOR
        return {"lock": {"id": LOCK, "body": "line one\nline two"},
                "pins": [{"id": LOCK, "role": "design", "title": "a pin", "gloss": "why"}],
                "registers": []}

    def lead_async(self, ref):
        return resolved(self.lead(ref))

    def node(self, ref):
        return ({"node": {"id": ref, "title": "the node", "label": "Note"},
                 "properties": {}, "facts": {}, "journal": {},
                 "neighbours": [{"relation": "REFERENCES", "direction": "out",
                                 "node": {"id": ANCHOR, "title": "back", "label": "Note"}}]},
                "## rendered heading\n\nbody prose")

    def node_async(self, ref):
        return resolved(self.node(ref))


def _window(qtbot, **kw):
    win = WorkbenchWindow(FakeSession(), **kw)
    qtbot.addWidget(win)
    return win


def row_texts(win):
    return win.picker.plain_text().splitlines()


def test_portfolio_paints_and_descends_to_lead(qtbot):
    win = _window(qtbot)
    assert win.stage == "portfolio" and win.current_stage() == "rows"
    assert any("program-x" in t for t in row_texts(win))
    win.jump_actionable(1)
    assert win.rows[win.picker.cursor].get("ref") == ANCHOR
    win.descend()
    assert win.stage == "lead" and win.ref == ANCHOR
    assert any("line one" in t for t in row_texts(win))


def test_lead_descends_to_node_markdown_and_back_restores_seat(qtbot):
    win = _window(qtbot, anchor=ANCHOR)
    assert win.stage == "lead"
    win.jump_actionable(1)
    seat = win.picker.cursor
    win.descend()
    assert win.stage == "node" and win.current_stage() == "reading"
    assert "the node" in win.browser.toPlainText()
    win.back()
    assert win.stage == "lead" and win.picker.cursor == seat


def test_node_link_descends_and_portfolio_clears_trail(qtbot):
    win = _window(qtbot, anchor=ANCHOR)
    win.jump_actionable(1)
    win.descend()
    from PySide6.QtCore import QUrl
    win._on_link(QUrl(f"graph://{ANCHOR}"))
    assert win.stage == "node" and win.ref == ANCHOR and len(win.trail) == 2
    win.portfolio()
    assert win.stage == "portfolio" and not win.trail


def test_grab_yields_agent_readable_pixels(qtbot, tmp_path):
    win = _window(qtbot)
    win.resize(900, 600)
    image = win.grab().toImage()
    assert not image.isNull() and image.width() > 0
    out = tmp_path / "probe.png"
    assert win.grab().save(str(out)) and out.stat().st_size > 0


def test_shell_frame_and_derived_menus(qtbot):
    """The first shell instance: the frame + title bar are the shell's, the
    menus derive from the keymap groups in declaration order + Theme."""
    from PySide6.QtCore import Qt
    win = _window(qtbot)
    assert win.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert win.titlebar.title.text() == "cjm graph workbench (qt)"
    assert [a.text() for a in win.menubar.actions()] == ["Navigate", "File", "Session", "View", "Theme"]
    session_menu = win.menus["Session"]
    labels = [a.text() for a in session_menu.actions()]
    assert labels == ["Open session feed", "Mint new session (start ritual)",
                      "Title seated session (end ritual)", "Retract an empty session",
                      "Open sessions list"]
    verbs = {e["verb"] for e in win.hints_overlay._entries}
    assert {"back", "mint-session", "keys", "find", "rows-move"} <= verbs
    # Return verbs answer the numpad Enter too (the keyboard contract)
    assert [s.toString() for s in win.keymap.action("find").shortcuts()] == ["Ctrl+F"]


def test_back_restores_browser_scroll_after_link_follow(qtbot):
    from PySide6.QtCore import QUrl

    class LongSession(FakeSession):
        def node(self, ref):
            detail, _body = super().node(ref)
            return detail, "\n\n".join(f"paragraph {i}" for i in range(300))

    win = WorkbenchWindow(LongSession(), anchor=ANCHOR)
    qtbot.addWidget(win)
    win.resize(900, 400)
    win.show()
    win.jump_actionable(1)
    win.descend()
    bar = win.browser.verticalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 200)
    bar.setValue(150)
    win._on_link(QUrl(f"graph://{LOCK}"))
    win.back()
    # the restore is DEFERRED past the next layout pass (drive-round-1 fix)
    qtbot.waitUntil(lambda: bar.value() == 150)


def test_back_serves_cache_and_r_refreshes(qtbot):
    class CountingSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.lead_calls = 0

        def lead(self, ref):
            self.lead_calls += 1
            return super().lead(ref)

    session = CountingSession()
    win = WorkbenchWindow(session, anchor=ANCHOR)
    qtbot.addWidget(win)
    assert session.lead_calls == 1
    win.jump_actionable(1)
    win.descend()                      # lead -> node
    win.back()                         # node -> lead: served from cache
    assert session.lead_calls == 1
    win.reload()                       # `r`: explicit fresh pull
    assert session.lead_calls == 2


def test_reload_keeps_the_seat(qtbot):
    win = _window(qtbot, anchor=ANCHOR)
    win.jump_actionable(1)
    seat = win.picker.cursor
    assert seat > 0
    win.reload()
    assert win.picker.cursor == seat


def test_load_failure_paints_and_the_seat_stays_up(qtbot):
    class BrokenSession(FakeSession):
        def lead_async(self, ref):
            fut = Future()
            fut.set_exception(RuntimeError("graph down"))
            return fut

    win = WorkbenchWindow(BrokenSession(), anchor=ANCHOR)
    qtbot.addWidget(win)
    assert win.stage == "lead" and win.rows == []
    assert "graph down" in win.strip.readout.text()
    assert win.strip.readout.property("role") == "warn"
    win.portfolio()                    # the seat is still driveable
    assert any("program-x" in t for t in row_texts(win))


def test_overview_jump_scrolls_and_b_unwinds_in_page(qtbot):
    from PySide6.QtCore import QUrl

    class GroupSession(FakeSession):
        def node(self, ref):
            detail, _body = super().node(ref)
            detail["neighbours"] = (
                [{"relation": "REFERENCES", "direction": "out",
                  "node": {"id": LOCK, "title": f"ref {i}", "label": "Note"}}
                 for i in range(40)]
                + [{"relation": "SHAPES", "direction": "out",
                    "node": {"id": LOCK, "title": "shaped", "label": "Note"}}])
            return detail, "\n\n".join(f"para {i}" for i in range(50))

    win = WorkbenchWindow(GroupSession(), anchor=ANCHOR)
    qtbot.addWidget(win)
    win.resize(900, 400)
    win.show()
    win.jump_actionable(1)
    win.descend()
    bar = win.browser.verticalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0)
    assert bar.value() == 0
    cursor_before = win.browser.textCursor().position()
    win._on_link(QUrl("jump:SHAPES"))
    # in-page jump: same stage/ref, the trail grew, the view scrolled down,
    # and the KEYBOARD cursor moved so tab cycles the jumped-to group's links
    assert win.stage == "node" and len(win.trail) == 2 and bar.value() > 0
    assert win.browser.textCursor().position() > cursor_before
    win.back()
    # in-page pop: the seat (scroll AND cursor) restored immediately, no reload
    assert win.stage == "node" and len(win.trail) == 1 and bar.value() == 0
    assert win.browser.textCursor().position() == cursor_before


def test_tab_link_cycling_follows_the_jump(qtbot):
    from PySide6.QtCore import Qt

    class GroupSession(FakeSession):
        def node(self, ref):
            detail, _body = super().node(ref)
            detail["neighbours"] = (
                [{"relation": "REFERENCES", "direction": "out",
                  "node": {"id": LOCK, "title": f"ref {i}", "label": "Note"}}
                 for i in range(3)]
                + [{"relation": "SHAPES", "direction": "out",
                    "node": {"id": LOCK, "title": "shaped", "label": "Note"}}])
            return detail, "short body"

    win = WorkbenchWindow(GroupSession(), anchor=ANCHOR)
    qtbot.addWidget(win)
    win.resize(1000, 700)
    win.show()
    win.jump_actionable(1)
    win.descend()
    # tab (through the reading pane's own key handling) selects the FIRST overview link
    qtbot.keyClick(win.browser, Qt.Key_Tab)
    assert win.browser.textCursor().selectedText() == "REFERENCES (3)"
    # enter-jump: the cursor lands on the group header, so the NEXT tab selects
    # that group's first link — not the document's first (drive find 2026-08-14)
    qtbot.keyClick(win.browser, Qt.Key_Return)
    assert len(win.trail) == 2
    qtbot.keyClick(win.browser, Qt.Key_Tab)
    assert win.browser.textCursor().selectedText() == "ref 0"
    # shift+tab walks backward across the group header to the previous link
    win.browser.cycle_link(-1)
    assert win.browser.textCursor().selectedText() == "SHAPES (1)"
    win.browser.cycle_link(1)
    # b unwinds the jump AND re-lights the overview link it started from
    win.back()
    assert win.browser.textCursor().selectedText() == "REFERENCES (3)"
    # the same enter path activates graph:// links: jump, tab in, descend —
    # the numpad Enter included
    qtbot.keyClick(win.browser, Qt.Key_Return)
    qtbot.keyClick(win.browser, Qt.Key_Tab)
    qtbot.keyClick(win.browser, Qt.Key_Enter)
    assert win.stage == "node" and win.ref == LOCK and len(win.trail) == 3


def test_feed_stage_paints_zooms_and_expands(qtbot):
    from PySide6.QtCore import QUrl
    win = _window(qtbot)
    win.open_feed()
    assert win.stage == "feed" and win.ref is None
    text = win.browser.toPlainText()
    assert "feed — live window" in text and "a canned op" in text
    win.toggle_zoom()  # cards zoom: the canned card with its expand toggle
    text = win.browser.toPlainText()
    assert "the stub" in text and "+ expand" in text
    win._on_link(QUrl(f"expand:{LOCK}"))
    assert "the stub body" in win.browser.toPlainText()
    win._on_link(QUrl(f"expand:{LOCK}"))  # toggle off
    assert "the stub body" not in win.browser.toPlainText()
    win.back()
    assert win.stage == "portfolio"


def test_mint_session_registers_points_and_opens_feed(qtbot, tmp_path):
    session = FakeSession()
    session.journal_paths = [str(tmp_path / "g.writes.jsonl")]
    win = WorkbenchWindow(session)
    qtbot.addWidget(win)
    key = win.mint_session(confirm=False)
    verb, wkey, kw = session.writes[0]
    assert verb == "session" and wkey == key and kw.get("started_at")
    # the registration op stamps with its OWN session, never the outgoing one
    # (S-test find 2026-08-14): the env is adopted BEFORE the journaled write
    assert kw.get("env_at_write") == key
    assert win.stage == "feed" and win.ref == key
    assert (tmp_path / "current-session").read_text() == key
    assert os.environ["CJM_SESSION"] == key
    assert "boot prompt on clipboard" in win.strip.readout.text()


def test_flag_mints_open_stub_linked_to_target(qtbot, monkeypatch):
    session = FakeSession()
    win = WorkbenchWindow(session, anchor=ANCHOR)
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "prompt_text", lambda *a, **k: "the flag note")
    win.jump_actionable(1)
    win.descend()                      # node stage; no link focused -> flag self.ref
    win.flag_focused()
    decides = [w for w in session.writes if w[0] == "decide"]
    links = [w for w in session.writes if w[0] == "link"]
    assert len(decides) == 1 and len(links) == 1
    _verb, statement, kw = decides[0]
    assert "CORRECTION FLAG (user:workbench" in statement
    assert "the flag note" in statement and str(win.ref) in statement
    assert kw.get("state") == "open"   # flags land on the readiness frontier
    _verb, src, tgt, rel = links[0]
    assert src == LOCK and tgt == str(win.ref) and rel == "REFERENCES"


def test_sessions_picker_search_stage_and_title_verb(qtbot, monkeypatch):
    win = _window(qtbot)
    win.open_sessions()
    assert win.stage == "sessions"
    texts = row_texts(win)
    # newest first, titles ride along
    assert any("2026-08-14_00-00-00" in t for t in texts)
    assert texts.index(next(t for t in texts if "2026-08-14" in t)) < \
        texts.index(next(t for t in texts if "older one" in t))
    win.jump_actionable(1)
    assert win.retract_target() == "2026-08-14_00-00-00"     # the focused row is the x target
    win.descend()                       # a session row opens that session's FEED
    assert win.stage == "feed" and win.ref == "2026-08-14_00-00-00"
    # t titles the VIEWED session through the shell's prompt
    monkeypatch.setattr(win, "prompt_text", lambda *a, **k: "the older sitting")
    assert win.title_session() == "the older sitting"
    assert win.session.writes[-1][:2] == ("session", "2026-08-14_00-00-00")
    # literal search: locate + grep on one page, back pops to the feed
    monkeypatch.setattr(win, "prompt_text", lambda *a, **k: "needle")
    win.search_prompt()
    assert win.stage == "search" and win.ref == "needle"
    text = win.browser.toPlainText()
    assert "a name hit" in text and "pkg/mod.py" in text
    assert "a content hit" in text and "around needle here" in text
    win.back()
    assert win.stage == "feed"
