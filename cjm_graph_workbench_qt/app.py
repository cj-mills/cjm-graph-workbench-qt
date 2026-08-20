"""The Qt workbench shell: the same seat verbs, real typography (item d2a6d8e1).

Slab-1 parity with the Textual shell: portfolio -> lead -> node, one stage
visible at a time, keyboard-first (j/k, tab, enter, b, p, r, q). Portfolio and
lead stay ROW lists — the tui spine's own row dicts painted as list items with
native word-wrap — while the node stage is a QTextBrowser over
build_node_markdown: the typography/absorption hypothesis under test.
Slab 2 adds the SESSION SEAT + LIVE FEED page (s/S, two zooms of one page via
z, 2s live re-evaluation) and the capture verbs: t titles the seated session,
f flags the focused link into a journaled correction stub — render-projection
+ capture-verbs, zero state/logic (DEC 8b9804c2); every write is a journaled
graph verb. Failures paint into the status bar and the seat stays up (family
posture: never crash the seat). No current-session singletons — every window
owns its GraphSession."""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cjm_substrate_qt_kit.keys import bind
from cjm_substrate_qt_kit.style import apply_row_style as _kit_apply_row_style
from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QInputDialog, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QStackedWidget, QTextBrowser)

from .data import read_session_pointer, write_session_pointer
from .feed import build_feed_markdown, build_session_rows
from .mdspine import build_node_markdown, build_search_markdown
from .spine import build_lead_rows, build_portfolio_rows

# Style words paint via the kit's shared palette (STYLE_COLORS /
# apply_row_style imported above — kit-owned since the transcription
# migration's duplication, DEC dcf8a712).

HINTS = ("j/k move · tab next • · enter open · s feed · b back · p portfolio · "
         "r reload · q quit")


def apply_row_style(item: QListWidgetItem, style: Optional[str]) -> None:
    """Map a spine row's style string onto a list item — delegates to the kit
    (cjm_substrate_qt_kit.style), kit-owned since the transcription migration's
    duplication (DEC dcf8a712)."""
    _kit_apply_row_style(item, style)


class WorkbenchWindow(QMainWindow):
    """Portfolio front door -> anchor pin tree -> node-in-context detail.

    The trail keeps (stage, ref, seat) per hop — `b` restores the exact seat
    (list row, or browser scroll position on the node stage)."""

    feed_ready = Signal(object)  # loop-thread Future -> Qt thread (queued)

    def __init__(self, session, anchor: Optional[str] = None):
        super().__init__()
        self.session = session
        self.setWindowTitle("cjm graph workbench (qt)")
        self.resize(1080, 780)
        self.stage = "lead" if anchor else "portfolio"
        self.ref: Optional[str] = anchor
        self.trail: List[Tuple[str, Optional[str], int]] = []
        self.rows: List[Dict[str, Any]] = []
        self._view_cache: Dict[Tuple[str, str], Any] = {}
        self.rowlist = QListWidget()
        self.rowlist.setWordWrap(True)  # re-flow, never truncate (drive round 2)
        self.rowlist.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rowlist.itemDoubleClicked.connect(lambda _item: self.descend())
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setTabChangesFocus(False)  # tab stays ours: links, not widgets
        self.browser.installEventFilter(self)   # tab/enter link nav lives in eventFilter
        self.browser.anchorClicked.connect(self._on_link)
        self.browser.document().setDocumentMargin(16)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.rowlist)
        self.stack.addWidget(self.browser)
        self.setCentralWidget(self.stack)
        self.feed_zoom = "ops"                 # "ops" (ledger) | "cards"
        self.feed_expanded: set = set()        # card ids with bodies shown
        self._feed_bodies: Dict[str, Optional[str]] = {}
        self._feed_view: Optional[Dict[str, Any]] = None
        self._feed_view_ref: Optional[str] = None  # which session the held view is for
        self._feed_inflight = False
        self.feed_ready.connect(self._on_feed_ready)
        self.feed_timer = QTimer(self)
        self.feed_timer.setInterval(2000)      # live mode = re-evaluate + repaint on change
        self.feed_timer.timeout.connect(self._poll_feed)
        if not os.environ.get("CJM_SESSION"):
            pointed = read_session_pointer(self.session.journal_paths)
            if pointed:  # env-first, pointer-fallback — cg-write's resolution order
                os.environ["CJM_SESSION"] = pointed
        self._bind_keys()
        self.reload()

    def _bind_keys(self) -> None:
        # Kit bind (cjm_substrate_qt_kit.keys) since the transcription
        # migration's duplication — same helper, owner-first signature.
        for key, fn in (("B", self.back), ("Escape", self.back),
                        ("P", self.portfolio), ("R", self.reload),
                        ("Q", self.close), ("S", self.open_feed),
                        ("Shift+S", self.new_session), ("Z", self.toggle_zoom),
                        ("T", self.title_session), ("F", self.flag_focused),
                        ("O", self.open_sessions), ("/", self.search_prompt),
                        ("X", self.retract_session_row)):
            bind(self, key, fn)
        bind(self, "J", lambda: self.move_cursor(1), self.rowlist, Qt.WidgetShortcut)
        bind(self, "K", lambda: self.move_cursor(-1), self.rowlist, Qt.WidgetShortcut)
        bind(self, "Tab", lambda: self.jump_actionable(1), self.rowlist, Qt.WidgetShortcut)
        bind(self, "Shift+Tab", lambda: self.jump_actionable(-1), self.rowlist, Qt.WidgetShortcut)
        bind(self, "Return", self.descend, self.rowlist, Qt.WidgetShortcut)
        bind(self, "J", lambda: self.scroll_browser(3), self.browser, Qt.WidgetShortcut)
        bind(self, "K", lambda: self.scroll_browser(-3), self.browser, Qt.WidgetShortcut)

    # ---- stage loading -------------------------------------------------

    def reload(self) -> None:
        """Explicit refresh (`r`): drop every cached stage view, then re-pull —
        the seat survives the refresh (Textual parity: `r` never loses the row)."""
        seat = self._seat()
        self._view_cache.clear()
        self._load()
        self._restore_seat(seat)

    def _load(self) -> None:
        """Paint the current stage — CACHED when already seen (b/back re-paints
        without a graph read, f4701770; errors never cache); `r` refreshes."""
        self.statusBar().showMessage(f"{self._where()} · loading…")
        if self.stage != "feed":
            self.feed_timer.stop()
        error = None
        key = (self.stage, str(self.ref))
        try:
            if self.stage == "portfolio":
                if key not in self._view_cache:
                    self._view_cache[key] = self.session.portfolio()
                self.rows = build_portfolio_rows(self._view_cache[key])
                self._paint_rows()
            elif self.stage == "lead":
                if key in self._view_cache:
                    view = self._view_cache[key]
                else:
                    view = self.session.lead(str(self.ref))
                    if not view.get("error"):
                        self._view_cache[key] = view
                if view.get("error"):
                    error, self.rows = str(view["error"]), []
                    self._paint_rows()
                else:
                    self.rows = build_lead_rows(view)
                    self._paint_rows()
            elif self.stage == "feed":
                # LIVE, ASYNC — the journal parse runs on the loop thread and
                # lands via feed_ready (the paint thread never blocks on it);
                # a held view (b-back) paints instantly, the poll freshens it.
                if (self._feed_view is not None
                        and self._feed_view_ref == (self.ref or None)):
                    self._paint_feed()
                else:
                    self._feed_view = None
                    self.browser.setMarkdown("*loading feed…*")
                    self.stack.setCurrentWidget(self.browser)
                    self.browser.setFocus()
                self._request_feed()
                self.feed_timer.start()
            elif self.stage == "sessions":
                if key not in self._view_cache:
                    self._view_cache[key] = self.session.sessions()
                self.rows = build_session_rows(self._view_cache[key])
                self._paint_rows()
            elif self.stage == "search":
                if key not in self._view_cache:
                    self._view_cache[key] = self.session.search(str(self.ref))
                loc, hits = self._view_cache[key]
                self.browser.setMarkdown(
                    build_search_markdown(str(self.ref), loc, hits))
                self.stack.setCurrentWidget(self.browser)
                self.browser.setFocus()
            else:
                if key in self._view_cache:
                    detail, body = self._view_cache[key]
                else:
                    detail, body = self.session.node(str(self.ref))
                    if not detail.get("error"):
                        self._view_cache[key] = (detail, body)
                if detail.get("error"):
                    error = str(detail["error"])
                    self.browser.setMarkdown(f"*{error}*")
                else:
                    self.browser.setMarkdown(build_node_markdown(detail, body))
                self.stack.setCurrentWidget(self.browser)
                self.browser.setFocus()
        except Exception as e:  # never crash the seat — paint and stay up
            error, self.rows = f"load failed: {e}", []
        self.statusBar().showMessage(
            f"{self._where()} · ⚠ {error}" if error
            else f"{self._where()} · {self._hints()}")

    def _paint_rows(self) -> None:
        self.rowlist.clear()
        for r in self.rows:
            marker = "• " if r.get("ref") else "  "
            item = QListWidgetItem(marker + str(r.get("text", "")))
            apply_row_style(item, r.get("style"))
            self.rowlist.addItem(item)
        if self.rows:
            self.rowlist.setCurrentRow(0)
        self.stack.setCurrentWidget(self.rowlist)
        self.rowlist.setFocus()

    def _where(self) -> str:
        return {"portfolio": "portfolio",
                "lead": f"lead {str(self.ref)[:28]}",
                "node": f"node {str(self.ref)[:12]}",
                "feed": f"feed {self.ref or 'live'}",
                "sessions": "sessions",
                "search": f"search {str(self.ref)[:24]}"}[self.stage]

    def _hints(self) -> str:
        """Stage-contextual keybar (the ba8a423b gap-4 stage half)."""
        if self.stage == "feed":
            return ("z zoom · tab links · enter open/expand · f flag · t title · "
                    "o sessions · shift+s new session · b back · r reload · q quit")
        if self.stage == "node":
            return ("j/k scroll · tab links · enter open/jump · f flag · / search · "
                    "b back · p portfolio · r reload · q quit")
        if self.stage == "search":
            return ("j/k scroll · tab links · enter open · f flag · / new search · "
                    "b back · p portfolio · q quit")
        if self.stage == "sessions":
            return ("j/k move · enter open feed · x retract empty · b back · "
                    "p portfolio · r reload · q quit")
        return HINTS

    # ---- seat verbs ----------------------------------------------------

    def move_cursor(self, delta: int) -> None:
        row = self.rowlist.currentRow() + delta
        self.rowlist.setCurrentRow(max(0, min(self.rowlist.count() - 1, row)))

    def jump_actionable(self, delta: int) -> None:
        """tab / shift+tab: hop between ACTIONABLE rows, never hunt through prose."""
        i = self.rowlist.currentRow() + delta
        while 0 <= i < len(self.rows):
            if self.rows[i].get("ref"):
                self.rowlist.setCurrentRow(i)
                return
            i += delta

    def scroll_browser(self, lines: int) -> None:
        bar = self.browser.verticalScrollBar()
        bar.setValue(bar.value() + lines * bar.singleStep())

    def _restore_seat(self, seat) -> None:
        """Put the seat back after a repaint. The browser restore is DEFERRED:
        setMarkdown's layout lands on the NEXT event-loop pass, and the
        not-yet-grown scroll range would clamp the value to the top (drive
        round 1: b lost the jump point after a link follow)."""
        if self.stage in ("node", "feed", "search"):
            QTimer.singleShot(0, lambda: self._restore_browser_seat(seat))
        elif self.rowlist.count():
            self.rowlist.setCurrentRow(min(seat, self.rowlist.count() - 1))

    def _restore_browser_seat(self, seat) -> None:
        """Node-stage seat restore: keyboard cursor/selection first (its
        implicit scroll is then overridden), stored scroll last so the
        viewport wins. Restoring the SELECTION re-lights the focused link."""
        if isinstance(seat, tuple):
            scroll, anchor, pos = seat
            limit = self.browser.document().characterCount() - 1
            cursor = self.browser.textCursor()
            cursor.setPosition(min(anchor, limit))
            cursor.setPosition(min(pos, limit), QTextCursor.KeepAnchor)
            self.browser.setTextCursor(cursor)
        else:
            scroll = seat
        self.browser.verticalScrollBar().setValue(scroll)

    def _scroll_to_group(self, rel: str) -> None:
        """Scroll the node stage so `rel`'s neighbour-group header sits at the
        viewport top. Matched block-exact below the neighbours heading — group
        headers are whole paragraphs, so titles that merely CONTAIN a relation
        word (and the overview line itself) can never false-match."""
        doc = self.browser.document()
        block = doc.begin()
        seen_head = False
        while block.isValid():
            if not seen_head:
                seen_head = block.text().startswith("neighbours (")
            elif block.text() == rel:
                # The keyboard cursor travels WITH the jump: tab now cycles the
                # jumped-to group's links, not the overview's (drive find
                # 2026-08-14). Cursor first — its implicit ensure-visible
                # scroll is then corrected to put the header at the top.
                self.browser.setTextCursor(QTextCursor(block))
                bar = self.browser.verticalScrollBar()
                bar.setValue(bar.value()
                             + self.browser.cursorRect(QTextCursor(block)).top())
                return
            block = block.next()

    def eventFilter(self, obj, event) -> bool:
        """Browser link nav owned HERE: QTextBrowser's native tab cycling keeps
        a PRIVATE focus cursor that cannot be seeded, so a counts-first jump
        could never carry it (drive find 2026-08-14: post-jump tab reset to
        the document's first link). Tab/shift+tab select the next/previous
        anchor from the TEXT cursor — which jumps, b, and reload all steer —
        and enter activates the selected one."""
        if obj is self.browser and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self._cycle_link(1)
                return True
            if event.key() == Qt.Key_Backtab:
                self._cycle_link(-1)
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._activate_link():
                return True
        return super().eventFilter(obj, event)

    def _anchor_spans(self) -> List[Tuple[int, int, str]]:
        """(start, end, href) for every link in document order; contiguous
        fragments of one anchor merge into a single span."""
        spans: List[Tuple[int, int, str]] = []
        block = self.browser.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                href = fmt.anchorHref() if fmt.isAnchor() else ""
                if href:
                    start, end = frag.position(), frag.position() + frag.length()
                    if spans and spans[-1][2] == href and spans[-1][1] == start:
                        spans[-1] = (spans[-1][0], end, href)
                    else:
                        spans.append((start, end, href))
                it += 1
            block = block.next()
        return spans

    def _cycle_link(self, delta: int) -> None:
        """Select the next/previous link from the text cursor (wrapping); the
        SELECTION is the visible focus indicator, and the seat follows it."""
        spans = self._anchor_spans()
        if not spans:
            return
        cur = self.browser.textCursor()
        lo = min(cur.anchor(), cur.position())
        hi = max(cur.anchor(), cur.position())
        if delta > 0:
            nxt = next((s for s in spans
                        if s[0] >= hi and (s[0], s[1]) != (lo, hi)), spans[0])
        else:
            nxt = next((s for s in reversed(spans)
                        if s[1] <= lo and (s[0], s[1]) != (lo, hi)), spans[-1])
        cur.setPosition(nxt[0])
        cur.setPosition(nxt[1], QTextCursor.KeepAnchor)
        self.browser.setTextCursor(cur)
        self.browser.ensureCursorVisible()

    def _activate_link(self) -> bool:
        """Open the tab-selected link (enter); False when none is selected."""
        cur = self.browser.textCursor()
        if not cur.hasSelection():
            return False
        probe = self.browser.textCursor()
        probe.setPosition(cur.selectionStart() + 1)  # format of the char AT start
        fmt = probe.charFormat()
        if fmt.isAnchor() and fmt.anchorHref():
            self._on_link(QUrl(fmt.anchorHref()))
            return True
        return False

    def _seat(self):
        if self.stage in ("node", "feed", "search"):
            # (scroll, cursor anchor, cursor position): tab link-cycling runs
            # off the text cursor (see eventFilter), so the whole selection
            # state is part of the seat — b re-focuses the exact link you left
            # (user drive finds 2026-08-14: nav position must travel).
            cur = self.browser.textCursor()
            return (self.browser.verticalScrollBar().value(),
                    cur.anchor(), cur.position())
        return max(0, self.rowlist.currentRow())

    def descend(self) -> None:
        i = self.rowlist.currentRow()
        row = self.rows[i] if 0 <= i < len(self.rows) else None
        if not row or not row.get("ref"):
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage = row.get("goto", "node")
        self.ref = row["ref"]
        self._load()

    def _on_link(self, url: QUrl) -> None:
        target = url.toString()
        if target.startswith("expand:"):
            # Feed-card body toggle: fetch the body once, repaint in place —
            # the seat (scroll + focused link) survives the re-render.
            nid = target[len("expand:"):]
            if nid in self.feed_expanded:
                self.feed_expanded.discard(nid)
            else:
                self.feed_expanded.add(nid)
                if nid not in self._feed_bodies:
                    try:
                        self._feed_bodies[nid] = self.session.body(nid)
                    except Exception as e:  # keep the seat up; card shows no body
                        self._feed_bodies[nid] = None
                        self.statusBar().showMessage(
                            f"{self._where()} · ⚠ body fetch failed: {e}")
            seat = self._seat()
            self._paint_feed()
            self._restore_seat(seat)
            return
        if target.startswith("jump:"):
            # Counts-first overview link: hop IN-PAGE to that relation's
            # neighbour group; the trail records the seat so `b` unwinds the
            # jump (drive-round-2 parity with the Textual overview rows).
            # `jump:` carries the relation as its PATH — an authority (`//`)
            # form would arrive host-lowercased through QUrl.
            self.trail.append((self.stage, self.ref, self._seat()))
            self._scroll_to_group(target[len("jump:"):])
            return
        if not target.startswith("graph://"):
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "node", target[len("graph://"):]
        self._load()

    def back(self) -> None:
        if not self.trail:
            return
        stage, ref, seat = self.trail.pop()
        if (stage, ref) == (self.stage, self.ref):
            # In-page pop (undoing an overview jump): the document is unchanged,
            # so the seat goes straight back — no reload, no deferred pass.
            if stage in ("node", "feed", "search"):
                self._restore_browser_seat(seat)
            elif self.rowlist.count():
                self.rowlist.setCurrentRow(min(seat, self.rowlist.count() - 1))
            return
        self.stage, self.ref = stage, ref
        self._load()
        self._restore_seat(seat)

    def portfolio(self) -> None:
        self.trail.clear()
        self.stage, self.ref = "portfolio", None
        self._load()

    # ---- session seat + live feed (slab 2, DEC ee9e9be6) ---------------

    def _paint_feed(self) -> None:
        """Render the held feed view at the current zoom; expansion bodies ride."""
        if self._feed_view is None:
            return
        self.browser.setMarkdown(build_feed_markdown(
            self._feed_view, zoom=self.feed_zoom,
            expanded=self.feed_expanded, bodies=self._feed_bodies))
        self.stack.setCurrentWidget(self.browser)
        self.browser.setFocus()

    def _poll_feed(self) -> None:
        """Live mode tick: request a fresh evaluation (async, in-flight-guarded)."""
        if self.stage != "feed":
            self.feed_timer.stop()
            return
        self._request_feed()

    def _request_feed(self) -> None:
        """Submit one async feed evaluation; the Future lands on the Qt thread
        through the queued feed_ready signal."""
        if self._feed_inflight:
            return
        self._feed_inflight = True
        self.session.feed_async(self.ref).add_done_callback(self.feed_ready.emit)

    def _on_feed_ready(self, fut) -> None:
        """Fresh feed view arrived: repaint only when the cursor advanced (or
        this is the first paint for the target session), seat preserved."""
        self._feed_inflight = False
        if self.stage != "feed":
            return
        try:
            view = fut.result()
        except Exception as e:  # transient read failure must not kill the loop
            self.statusBar().showMessage(f"{self._where()} · ⚠ feed read failed: {e}")
            return
        if ((view.get("window") or {}).get("session") or None) != (self.ref or None):
            return  # stale result for a session we already navigated away from
        first = (self._feed_view is None
                 or self._feed_view_ref != (self.ref or None))
        old = ((self._feed_view or {}).get("window") or {}).get("cursor")
        if not first and ((view.get("window") or {}).get("cursor")) == old:
            return
        self._feed_view = view
        self._feed_view_ref = self.ref or None
        if first:
            self._paint_feed()
            self.statusBar().showMessage(f"{self._where()} · {self._hints()}")
        else:
            seat = self._seat()
            self._paint_feed()
            self._restore_seat(seat)

    def open_feed(self) -> None:
        """`s`: the seat page for the ACTIVE session (env-first, pointer
        fallback), or the whole-journal live window when none is active."""
        if self.stage == "feed":
            return
        key = (os.environ.get("CJM_SESSION")
               or read_session_pointer(self.session.journal_paths))
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "feed", key
        self._load()

    def new_session(self) -> None:
        """`S`: mint + register a session spine node, point .cjm/current-session
        at it, adopt it in-process, open its feed — the start ritual as one key."""
        # Key-repeat debounce (field find 2026-08-20): a held/bouncing Shift+S
        # minted TWO spine nodes one second apart. A just-adopted timestamp key
        # means this press is a repeat, not a new sitting — ignore it.
        active = (os.environ.get("CJM_SESSION")
                  or read_session_pointer(self.session.journal_paths))
        if active:
            try:
                age = time.time() - datetime.strptime(
                    active, "%Y-%m-%d_%H-%M-%S").timestamp()
                if 0 <= age < 10.0:
                    self.statusBar().showMessage(
                        f"{self._where()} · session {active} just minted — "
                        f"repeat Shift+S ignored")
                    return
            except ValueError:
                pass  # non-timestamp key (manual/legacy) — no debounce basis
        key = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Adopt the key BEFORE the journaled write: a registration op stamps
        # with its OWN session (the manual boot ritual's convention — pointer
        # first, register second), never the outgoing one (S-test find
        # 2026-08-14: the op landed tagged to the PREVIOUS session, so it
        # appeared in both feeds).
        prev = os.environ.get("CJM_SESSION")
        os.environ["CJM_SESSION"] = key
        try:
            res = self.session.register_session(key, started_at=time.time())
        except Exception as e:
            res = {"error": str(e)}
        if res.get("error"):
            if prev is None:
                os.environ.pop("CJM_SESSION", None)
            else:
                os.environ["CJM_SESSION"] = prev
            self.statusBar().showMessage(f"{self._where()} · ⚠ session write failed: "
                                         f"{res['error']}")
            return
        write_session_pointer(self.session.journal_paths, key)
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "feed", key
        self._load()
        self.statusBar().showMessage(f"{self._where()} · session {key} registered · "
                                     f"{self._hints()}")

    def toggle_zoom(self) -> None:
        """`z`: op ledger <-> node cards (two zooms of ONE page)."""
        if self.stage != "feed":
            return
        self.feed_zoom = "cards" if self.feed_zoom == "ops" else "ops"
        self._paint_feed()

    def open_sessions(self) -> None:
        """`o`: the sessions picker — every registered spine session, newest
        first; enter opens that session's feed (past sessions included)."""
        if self.stage == "sessions":
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "sessions", None
        self._load()

    def retract_session_row(self) -> None:
        """`x` (sessions picker): retract an EMPTY double-minted session row.

        The key-repeat cleanup gesture (field find 2026-08-20), not history
        editing: the active key refuses here, and the data layer refuses any
        session with journaled ops attributed to it — only true empty mints
        pass both guards. Confirm dialog before the journaled retraction."""
        if self.stage != "sessions":
            return
        row = self.rowlist.currentRow()
        if not (0 <= row < len(self.rows)):
            return
        key = self.rows[row].get("ref")
        if not key:
            return
        active = (os.environ.get("CJM_SESSION")
                  or read_session_pointer(self.session.journal_paths))
        if key == active:
            self.statusBar().showMessage(
                f"{self._where()} · ⚠ {key} is the ACTIVE session — not retracting")
            return
        if QMessageBox.question(self, "retract session",
                                f"Retract empty session {key}?") != QMessageBox.StandardButton.Yes:
            return
        try:
            res = self.session.retract_session(str(key))
        except Exception as e:  # keep the seat up — surface, never crash
            res = {"error": str(e)}
        if res.get("error"):
            self.statusBar().showMessage(f"{self._where()} · ⚠ {res['error']}")
            return
        self._view_cache.clear()
        self._load()
        self.statusBar().showMessage(f"{self._where()} · session {key} retracted · "
                                     f"{self._hints()}")

    def search_prompt(self) -> None:
        """`/`: literal search (the slab-2 half of the 18cd3e8d seat) — locate
        over names/slugs/paths + grep over exhaustive content, one results page."""
        term, ok = QInputDialog.getText(self, "search", "literal term:")
        if not ok or not term.strip():
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "search", term.strip()
        self._load()

    def title_session(self) -> None:
        """`t`: name the seated session (the END ritual — an ordinary
        re-register; a later title never clobbers started_at)."""
        if self.stage != "feed" or not self.ref:
            return
        text, ok = QInputDialog.getText(self, "session title",
                                        f"title for {self.ref}:")
        if not ok or not text.strip():
            return
        try:
            res = self.session.register_session(str(self.ref), title=text.strip())
        except Exception as e:
            self.statusBar().showMessage(f"{self._where()} · ⚠ title write failed: {e}")
            return
        msg = res.get("error") or f"titled: {text.strip()}"
        self.statusBar().showMessage(f"{self._where()} · {msg}")

    # ---- correction flag (the capture verb) ----------------------------

    def _focused_graph_id(self) -> Optional[str]:
        """The tab-focused link's graph node id, if the browser is up and a
        graph:// anchor is selected."""
        if self.stack.currentWidget() is not self.browser:
            return None
        cur = self.browser.textCursor()
        if not cur.hasSelection():
            return None
        probe = self.browser.textCursor()
        probe.setPosition(cur.selectionStart() + 1)
        fmt = probe.charFormat()
        href = fmt.anchorHref() if fmt.isAnchor() else ""
        return href[len("graph://"):] if href.startswith("graph://") else None

    def flag_focused(self) -> None:
        """`f`: mint a correction stub for the focused link (or the open node) —
        a Decision with task_state=open, stub -REFERENCES-> target, all
        journaled (the acdb1c04 doorbell: content flows on-graph; chat stays
        the turn-advance signal)."""
        target = self._focused_graph_id()
        if target is None and self.stage == "node" and self.ref:
            target = str(self.ref)
        if not target:
            self.statusBar().showMessage(
                f"{self._where()} · flag: focus a graph link first (tab)")
            return
        note, ok = QInputDialog.getText(self, "correction flag",
                                        f"note for {target[:8]} (optional):")
        if not ok:
            return
        note = note.strip()
        session_key = (str(self.ref) if self.stage == "feed" and self.ref
                       else os.environ.get("CJM_SESSION") or None)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        statement = (f"CORRECTION FLAG (user:workbench, {stamp}): "
                     f"{note or 'flagged for attention'} — target {target}")
        try:
            res = self.session.decide(statement, state="open", session=session_key,
                                      title=f"flag: {note[:44] if note else target[:8]}")
            if res.get("error"):
                self.statusBar().showMessage(f"{self._where()} · ⚠ {res['error']}")
                return
            stub = res["decision_id"]
            lk = self.session.link(stub, target, "REFERENCES")
        except Exception as e:
            self.statusBar().showMessage(f"{self._where()} · ⚠ flag write failed: {e}")
            return
        tail = f" (link: {lk['error']})" if lk.get("error") else ""
        self.statusBar().showMessage(
            f"{self._where()} · flagged {target[:8]} → stub {stub[:8]}{tail}")
