"""Offscreen stage-walk probe: the window paints all three stages and the seat
verbs navigate them, against a FAKE session (no graph). grab() proves the
agent-readable screenshot path (family craft: paint verifies by probe)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cjm_graph_workbench_qt.app import WorkbenchWindow

ANCHOR = "11111111-2222-3333-4444-555555555555"
LOCK = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class FakeSession:
    """Canned lens views: one anchor, one lock note, one node detail."""

    def portfolio(self):
        return {"counts": {"ready": 2, "blocked": 1, "done": 3, "closable": 1},
                "anchors": [{"id": ANCHOR, "slug": "program-x", "role": "program",
                             "vitals": {"ready": 2, "blocked": 1, "findings": 1},
                             "pins": 2, "lock": {"lead": "the lock lead line"}}],
                "links": []}

    def lead(self, ref):
        assert ref == ANCHOR
        return {"lock": {"id": LOCK, "body": "line one\nline two"},
                "pins": [{"id": LOCK, "role": "design", "title": "a pin", "gloss": "why"}],
                "registers": []}

    def node(self, ref):
        return ({"node": {"id": ref, "title": "the node", "label": "Note"},
                 "properties": {}, "facts": {}, "journal": {},
                 "neighbours": [{"relation": "REFERENCES", "direction": "out",
                                 "node": {"id": ANCHOR, "title": "back", "label": "Note"}}]},
                "## rendered heading\n\nbody prose")


def _window(qtbot, **kw):
    win = WorkbenchWindow(FakeSession(), **kw)
    qtbot.addWidget(win)
    return win


def test_portfolio_paints_and_descends_to_lead(qtbot):
    win = _window(qtbot)
    assert win.stage == "portfolio"
    texts = [win.rowlist.item(i).text() for i in range(win.rowlist.count())]
    assert any("program-x" in t for t in texts)
    win.jump_actionable(1)
    assert win.rows[win.rowlist.currentRow()].get("ref") == ANCHOR
    win.descend()
    assert win.stage == "lead" and win.ref == ANCHOR
    assert any("line one" in win.rowlist.item(i).text()
               for i in range(win.rowlist.count()))


def test_lead_descends_to_node_markdown_and_back_restores_seat(qtbot):
    win = _window(qtbot, anchor=ANCHOR)
    assert win.stage == "lead"
    win.jump_actionable(1)
    seat = win.rowlist.currentRow()
    win.descend()
    assert win.stage == "node"
    assert "the node" in win.browser.toPlainText()
    win.back()
    assert win.stage == "lead" and win.rowlist.currentRow() == seat


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
