"""The Qt workbench shell: the same seat verbs, real typography (item d2a6d8e1).

Slab-1 parity with the Textual shell: portfolio -> lead -> node, one stage
visible at a time, keyboard-first (j/k, tab, enter, b, p, r, q). Portfolio and
lead stay ROW lists — the tui spine's own row dicts painted as list items with
native word-wrap — while the node stage is a QTextBrowser over
build_node_markdown: the typography/absorption hypothesis under test.
Read-only; failures paint into the status bar and the seat stays up (family
posture: never crash the seat). No current-session singletons — every window
owns its GraphSession."""

from typing import Any, Dict, List, Optional, Tuple

from cjm_graph_workbench_tui.spine import build_lead_rows, build_portfolio_rows
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QMainWindow, QStackedWidget,
                               QTextBrowser)

from .mdspine import build_node_markdown

# Spine rows carry Rich-ish style words; the Qt paint maps the palette words to
# colors and `bold` to weight (theme-neutral hexes readable on light and dark).
STYLE_COLORS = {"red": "#c74a3c", "yellow": "#b9770e", "cyan": "#2b8a9d",
                "magenta": "#9b59b6", "dim": "#8a9299"}

HINTS = "j/k move · tab next • · enter open · b back · p portfolio · r reload · q quit"


def apply_row_style(item: QListWidgetItem, style: Optional[str]) -> None:
    """Map a spine row's style string onto a list item (color words + bold)."""
    parts = str(style or "").split()
    for word in parts:
        if word in STYLE_COLORS:
            item.setForeground(QColor(STYLE_COLORS[word]))
    if "bold" in parts:
        font = item.font()
        font.setBold(True)
        item.setFont(font)


class WorkbenchWindow(QMainWindow):
    """Portfolio front door -> anchor pin tree -> node-in-context detail.

    The trail keeps (stage, ref, seat) per hop — `b` restores the exact seat
    (list row, or browser scroll position on the node stage)."""

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
        self.browser.setTabChangesFocus(False)  # tab cycles LINKS, not widgets
        self.browser.anchorClicked.connect(self._on_link)
        self.browser.document().setDocumentMargin(16)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.rowlist)
        self.stack.addWidget(self.browser)
        self.setCentralWidget(self.stack)
        self._bind_keys()
        self.reload()

    def _bind_keys(self) -> None:
        def bind(key: str, fn, parent=None, context=Qt.WindowShortcut):
            shortcut = QShortcut(QKeySequence(key), parent or self)
            shortcut.setContext(context)
            shortcut.activated.connect(fn)
        bind("B", self.back)
        bind("Escape", self.back)
        bind("P", self.portfolio)
        bind("R", self.reload)
        bind("Q", self.close)
        bind("J", lambda: self.move_cursor(1), self.rowlist, Qt.WidgetShortcut)
        bind("K", lambda: self.move_cursor(-1), self.rowlist, Qt.WidgetShortcut)
        bind("Tab", lambda: self.jump_actionable(1), self.rowlist, Qt.WidgetShortcut)
        bind("Shift+Tab", lambda: self.jump_actionable(-1), self.rowlist, Qt.WidgetShortcut)
        bind("Return", self.descend, self.rowlist, Qt.WidgetShortcut)
        bind("J", lambda: self.scroll_browser(3), self.browser, Qt.WidgetShortcut)
        bind("K", lambda: self.scroll_browser(-3), self.browser, Qt.WidgetShortcut)

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
            f"{self._where()} · ⚠ {error}" if error else f"{self._where()} · {HINTS}")

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
                "node": f"node {str(self.ref)[:12]}"}[self.stage]

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
        if self.stage == "node":
            QTimer.singleShot(0, lambda: self._restore_browser_seat(seat))
        elif self.rowlist.count():
            self.rowlist.setCurrentRow(min(seat, self.rowlist.count() - 1))

    def _restore_browser_seat(self, seat) -> None:
        """Node-stage seat restore: keyboard cursor first (its implicit scroll
        is then overridden), stored scroll last so the viewport wins."""
        scroll, pos = seat if isinstance(seat, tuple) else (seat, None)
        if pos is not None:
            cursor = self.browser.textCursor()
            cursor.setPosition(min(pos, self.browser.document().characterCount() - 1))
            self.browser.setTextCursor(cursor)
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

    def _seat(self):
        if self.stage == "node":
            # (scroll, keyboard cursor): tab cycles links FROM the text cursor,
            # so the nav position is part of the seat, not just the viewport
            # (user drive find 2026-08-14: tab stayed at the overview after a
            # counts-first jump).
            return (self.browser.verticalScrollBar().value(),
                    self.browser.textCursor().position())
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
            if stage == "node":
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
