"""The Qt workbench: the FIRST SHELL INSTANCE (ruling 2bae2cc1, item a9ba662e).

Slab-1 parity with the Textual shell: portfolio -> lead -> node, one stage
visible at a time, keyboard-first (j/k, tab, enter, b, p, r, q). Portfolio and
lead stay ROW lists — the tui spine's own row dicts painted through the kit
PickerList — while the node stage is a kit ReadingPane over
build_node_markdown. Slab 2 adds the SESSION SEAT + LIVE FEED page (s/S, two
zooms of one page via z, 2s live re-evaluation) and the capture verbs: t
titles the seated session, f flags the focused link into a journaled
correction stub — render-projection + capture-verbs, zero state/logic (DEC
8b9804c2); every write is a journaled graph verb. Failures paint into the
strip and the seat stays up (family posture: never crash the seat).

What the shell owns now (and this file no longer carries): the window frame
+ title bar, the menus derived from the keymap, the status strip, the find
bar, the keyboard-hints overlay, the job seat, the Future -> Signal bridge,
session-key adoption at launch, the ONE mint (Shift+S: confirm, register,
point, adopt, boot prompt), title (t) and retract (x) as shell verbs, the kit
prompt / confirm dialogs, and the reading pane's link cycling + seat. Every
graph read goes through `read_async` — the paint thread never blocks."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cjm_substrate_qt_kit.keys import bind
from cjm_substrate_qt_kit.pickerlist import PickerList
from cjm_substrate_qt_kit.readingpane import ReadingPane
from cjm_substrate_qt_kit.shell import AppShell
from PySide6.QtCore import Qt, QTimer, QUrl

from .feed import build_feed_markdown, build_session_rows
from .mdspine import build_node_markdown, build_search_markdown
from .spine import build_lead_rows, build_portfolio_rows

HINTS = ("j/k move · tab next • · enter open · s feed · b back · p portfolio · "
         "r reload · q quit")

ROW_STAGES = ("portfolio", "lead", "sessions")
READING_STAGES = ("node", "feed", "search")


def picker_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Spine row dicts -> PickerList rows: every row is a cursor stop (j/k
    walk prose too, as the Textual shell did; tab hops the actionable ones),
    the ref marker leads, the style words paint through the state channel."""
    out = []
    for i, r in enumerate(rows):
        marker = "• " if r.get("ref") else "  "
        out.append({"kind": "item", "spans": [(marker + str(r.get("text", "")), r.get("style") or "")],
                    "key": i})
    return out


class WorkbenchWindow(AppShell):
    """Portfolio front door -> anchor pin tree -> node-in-context detail.

    The trail keeps (stage, ref, seat) per hop — `b` restores the exact seat
    (list cursor, or the reading pane's scroll + selection)."""

    def __init__(self, session, anchor: Optional[str] = None,
                 decorations: Optional[str] = None):
        super().__init__("cjm graph workbench (qt)", session=session, seat="workbench",
                         decorations=decorations)
        self.resize(1080, 780)
        self.stage = "lead" if anchor else "portfolio"
        self.ref: Optional[str] = anchor
        self.trail: List[Tuple[str, Optional[str], Any]] = []
        self.rows: List[Dict[str, Any]] = []
        self._view_cache: Dict[Tuple[str, str], Any] = {}
        self._load_seq = 0
        self.picker = PickerList(self.frame, on_activate=lambda _key: self.descend())
        self.picker.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # the container takes the keys
        self.browser = ReadingPane(self.frame)
        self.browser.activated.connect(self._on_link)
        self.add_stage("rows", self.picker)
        self.add_stage("reading", self.browser)
        self.feed_zoom = "ops"                 # "ops" (ledger) | "cards"
        self.feed_expanded: set = set()        # card ids with bodies shown
        self._feed_bodies: Dict[str, Optional[str]] = {}
        self._feed_view: Optional[Dict[str, Any]] = None
        self._feed_view_ref: Optional[str] = None  # which session the held view is for
        self._feed_inflight = False
        self.feed_timer = QTimer(self)
        self.feed_timer.setInterval(2000)      # live mode = re-evaluate + repaint on change
        self.feed_timer.timeout.connect(self._poll_feed)
        self.session_minted.connect(self._on_minted)
        self._bind_keys()
        self._load()

    def _bind_keys(self) -> None:
        # Window verbs on the kit KeymapRegistry: the declarative table is the
        # discovery surface — the shell derives the menus and the ?-overlay
        # from it and gates bare-letter verbs off while a field has focus.
        add = self.keymap.add
        add("back", "Back (unwind trail)", "B", self.back, group="Navigate")
        add("back-esc", "Back (Escape)", "Escape", self.back, group="Navigate")
        add("portfolio", "Portfolio front door", "P", self.portfolio, group="Navigate")
        add("search", "Graph search (locate + grep)", "/", self.search_prompt, group="Navigate")
        add("reload", "Reload stage (seat survives)", "R", self.reload, group="File")
        add("quit", "Quit", "Q", self.close, group="File")
        add("feed", "Open session feed", "S", self.open_feed, group="Session")
        self.add_session_verbs(mint="Shift+S", title="T", retract="X")
        add("open-sessions", "Open sessions list", "O", self.open_sessions, group="Session")
        add("zoom", "Toggle feed zoom (ops/cards)", "Z", self.toggle_zoom, group="View")
        add("flag", "Flag focused row", "F", self.flag_focused, group="View")
        # Widget-scoped rows binds live on kit `bind` (the picker container
        # holds focus on row stages; the reading pane owns tab/enter/j/k
        # itself) and are declared to the overlay as data.
        bind(self, "J", lambda: self.move_cursor(1), self.picker, Qt.ShortcutContext.WidgetShortcut)
        bind(self, "K", lambda: self.move_cursor(-1), self.picker, Qt.ShortcutContext.WidgetShortcut)
        bind(self, "Tab", lambda: self.jump_actionable(1), self.picker, Qt.ShortcutContext.WidgetShortcut)
        bind(self, "Shift+Tab", lambda: self.jump_actionable(-1), self.picker,
             Qt.ShortcutContext.WidgetShortcut)
        bind(self, "Return", self.descend, self.picker, Qt.ShortcutContext.WidgetShortcut)
        self.finish_keys([
            {"verb": "rows-move", "label": "move row / scroll", "key": "J/K", "group": "Rows & Reading"},
            {"verb": "rows-actionable", "label": "jump actionable", "key": "Tab", "group": "Rows & Reading"},
            {"verb": "rows-open", "label": "open/descend", "key": "Return", "group": "Rows & Reading"}])

    # ---- stage loading (async: the paint thread never blocks) ------------

    def reload(self) -> None:
        """Explicit refresh (`r`): drop every cached stage view, then re-pull —
        the seat survives the refresh (Textual parity: `r` never loses the row)."""
        seat = self._seat()
        self._view_cache.clear()
        self._load(then=lambda: self._restore_seat(seat))

    def _fetch(self, stage: str, ref: Optional[str]):
        """The stage's read as a Future on the session's loop thread."""
        s = self.session
        if stage == "portfolio":
            return s.portfolio_async()
        if stage == "lead":
            return s.lead_async(str(ref))
        if stage == "sessions":
            return s.sessions_async()
        if stage == "search":
            return s.search_async(str(ref))
        return s.node_async(str(ref))

    def _load(self, then=None) -> None:
        """Paint the current stage — CACHED when already seen (b/back re-paints
        without a graph read, f4701770; errors never cache); `r` refreshes.
        Reads land through the shell's bridge; a stale result (the stage
        moved on) is dropped by sequence."""
        self._load_seq += 1
        seq = self._load_seq
        if self.stage != "feed":
            self.feed_timer.stop()
        key = (self.stage, str(self.ref))
        if self.stage == "feed":
            # LIVE, ASYNC — the journal parse runs on the loop thread and
            # lands through the bridge; a held view (b-back) paints
            # instantly, the poll freshens it.
            if self._feed_view is not None and self._feed_view_ref == (self.ref or None):
                self._paint_feed()
            else:
                self._feed_view = None
                self.browser.setMarkdown("*loading feed…*")
                self.show_stage("reading")
            self._request_feed()
            self.feed_timer.start()
            self._paint_frame()
            if then:
                then()
            return
        if key in self._view_cache:
            self._paint_stage(key, self._view_cache[key])
            if then:
                then()
            return
        self.read_async(self._fetch(self.stage, self.ref),
                        lambda res: self._on_loaded(seq, key, res, then),
                        on_error=lambda e: self._on_load_failed(seq, e))

    def _on_load_failed(self, seq: int, e: BaseException) -> None:
        if seq != self._load_seq:
            return
        self.rows = []
        if self.stage in ROW_STAGES:
            self._paint_rows()
        self._paint_result(f"⚠ load failed: {e}", role="warn")

    def _on_loaded(self, seq: int, key: Tuple[str, str], res: Any, then) -> None:
        if seq != self._load_seq:
            return   # the stage moved on while this read was in flight
        stage = key[0]
        error = None
        if stage == "lead":
            error = res.get("error")
        elif stage == "node":
            error = res[0].get("error")
        if not error:
            self._view_cache[key] = res
        self._paint_stage(key, res)
        if then:
            then()

    def _paint_stage(self, key: Tuple[str, str], res: Any) -> None:
        stage = key[0]
        error = None
        if stage == "portfolio":
            self.rows = build_portfolio_rows(res)
            self._paint_rows()
        elif stage == "lead":
            if res.get("error"):
                error, self.rows = str(res["error"]), []
            else:
                self.rows = build_lead_rows(res)
            self._paint_rows()
        elif stage == "sessions":
            self.rows = build_session_rows(res)
            self._paint_rows()
        elif stage == "search":
            loc, hits = res
            self.browser.setMarkdown(build_search_markdown(str(self.ref), loc, hits))
            self.show_stage("reading")
        else:
            detail, body = res
            if detail.get("error"):
                error = str(detail["error"])
                self.browser.setMarkdown(f"*{error}*")
            else:
                self.browser.setMarkdown(build_node_markdown(detail, body))
            self.show_stage("reading")
        if error:
            self._paint_result(f"⚠ {error}", role="warn")
        else:
            self._paint_frame()

    def _paint_rows(self) -> None:
        self.picker.set_rows(picker_rows(self.rows), cursor=0)
        self.show_stage("rows")

    def _where(self) -> str:
        return {"portfolio": "portfolio",
                "lead": f"lead {str(self.ref)[:28]}",
                "node": f"node {str(self.ref)[:12]}",
                "feed": f"feed {self.ref or 'live'}",
                "sessions": "sessions",
                "search": f"search {str(self.ref)[:24]}"}[self.stage]

    def _paint_frame(self) -> None:
        """Footer decomposition (DEC 2a42c028): where-chip + stage hints on
        the strip."""
        self.strip.set_chips([("where", self._where())])
        self.strip.set_hints(self._hints() + " · ? keys")

    def _paint_result(self, text: str, role: str = "") -> None:
        """Action results ride the persistent readout (⚠ paints warn)."""
        self._paint_frame()
        self.strip.set_readout(text, role=role or None)

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
        self.picker.move(delta)

    def jump_actionable(self, delta: int) -> None:
        """tab / shift+tab: hop between ACTIONABLE rows, never hunt through prose."""
        i = self.picker.cursor + delta
        while 0 <= i < len(self.rows):
            if self.rows[i].get("ref"):
                self.picker.set_cursor(i)
                return
            i += delta

    def _seat(self):
        if self.stage in READING_STAGES:
            return self.browser.seat()
        return max(0, self.picker.cursor)

    def _restore_seat(self, seat) -> None:
        """Put the seat back after a repaint (the reading pane defers past
        the next layout pass; the row cursor is immediate)."""
        if self.stage in READING_STAGES:
            self.browser.restore_seat(seat)
        elif self.picker.count():
            self.picker.set_rows_cursor(min(int(seat), self.picker.count() - 1))

    def descend(self) -> None:
        i = self.picker.cursor
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
                seat = self._seat()
                self._paint_feed()
                self._restore_seat(seat)
                return
            self.feed_expanded.add(nid)
            if nid in self._feed_bodies:
                seat = self._seat()
                self._paint_feed()
                self._restore_seat(seat)
                return
            seat = self._seat()

            def landed(body) -> None:
                self._feed_bodies[nid] = body
                self._paint_feed()
                self._restore_seat(seat)

            def failed(e) -> None:   # keep the seat up; card shows no body
                self._feed_bodies[nid] = None
                self._paint_feed()
                self._restore_seat(seat)
                self._paint_result(f"⚠ body fetch failed: {e}", role="warn")

            self.read_async(self.session.body_async(nid), landed, on_error=failed, busy=None)
            return
        if target.startswith("jump:"):
            # Counts-first overview link: hop IN-PAGE to that relation's
            # neighbour group; the trail records the seat so `b` unwinds the
            # jump. `jump:` carries the relation as its PATH — an authority
            # (`//`) form would arrive host-lowercased through QUrl.
            self.trail.append((self.stage, self.ref, self._seat()))
            self.browser.scroll_to_block(target[len("jump:"):], after_prefix="neighbours (")
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
            if stage in READING_STAGES:
                self.browser.restore_seat(seat, deferred=False)
            elif self.picker.count():
                self.picker.set_rows_cursor(min(int(seat), self.picker.count() - 1))
            return
        self.stage, self.ref = stage, ref
        self._load(then=lambda: self._restore_seat(seat))

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
        self.show_stage("reading")

    def _poll_feed(self) -> None:
        """Live mode tick: request a fresh evaluation (async, in-flight-guarded)."""
        if self.stage != "feed":
            self.feed_timer.stop()
            return
        self._request_feed()

    def _request_feed(self) -> None:
        """Submit one async feed evaluation; the result lands on the Qt thread
        through the shell's bridge (no busy readout — the poll is silent)."""
        if self._feed_inflight:
            return
        self._feed_inflight = True
        self.read_async(self.session.feed_async(self.ref), self._on_feed_ready,
                        on_error=self._on_feed_failed, busy=None)

    def _on_feed_failed(self, e: BaseException) -> None:
        self._feed_inflight = False
        self._paint_result(f"⚠ feed read failed: {e}", role="warn")

    def _on_feed_ready(self, view) -> None:
        """Fresh feed view arrived: repaint only when the cursor advanced (or
        this is the first paint for the target session), seat preserved."""
        self._feed_inflight = False
        if self.stage != "feed":
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
            self._paint_frame()
        else:
            seat = self._seat()
            self._paint_feed()
            self._restore_seat(seat)

    def open_feed(self) -> None:
        """`s`: the seat page for the ACTIVE session (env-first, pointer
        fallback), or the whole-journal live window when none is active."""
        if self.stage == "feed":
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "feed", self.active_session_key()
        self._load()

    def _on_minted(self, key: str) -> None:
        """The shell minted + adopted a session (Shift+S): open its feed."""
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "feed", key
        self._load()

    def title_session(self, key: Optional[str] = None) -> Optional[str]:
        """`t`: name the VIEWED session on the feed stage (the end ritual)."""
        if self.stage != "feed" or not self.ref:
            self._paint_result("title: open a session feed first (s)")
            return None
        return super().title_session(str(self.ref))

    def retract_target(self) -> Optional[str]:
        """`x` (sessions picker): the focused session row's key."""
        if self.stage != "sessions":
            return None
        i = self.picker.cursor
        return self.rows[i].get("ref") if 0 <= i < len(self.rows) else None

    def retract_session(self, key: Optional[str], confirm: bool = True) -> bool:
        ok = super().retract_session(key, confirm)
        if ok:
            self._view_cache.clear()
            self._load()
        return ok

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

    def search_prompt(self) -> None:
        """`/`: literal search (the slab-2 half of the 18cd3e8d seat) — locate
        over names/slugs/paths + grep over exhaustive content, one results page."""
        term = self.prompt_text("Search", "literal term:")
        if not term or not term.strip():
            return
        self.trail.append((self.stage, self.ref, self._seat()))
        self.stage, self.ref = "search", term.strip()
        self._load()

    # ---- correction flag (the capture verb) ----------------------------

    def _focused_graph_id(self) -> Optional[str]:
        """The tab-focused link's graph node id, if the reading pane is up
        and a graph:// anchor is selected."""
        if self.current_stage() != "reading":
            return None
        href = self.browser.focused_href() or ""
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
            self._paint_result("flag: focus a graph link first (tab)")
            return
        note = self.prompt_text("Correction flag", f"note for {target[:8]} (optional):")
        if note is None:
            return
        note = note.strip()
        session_key = (str(self.ref) if self.stage == "feed" and self.ref
                       else self.active_session_key())
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        statement = (f"CORRECTION FLAG (user:workbench, {stamp}): "
                     f"{note or 'flagged for attention'} — target {target}")
        try:
            res = self.session.decide(statement, state="open", session=session_key,
                                      title=f"flag: {note[:44] if note else target[:8]}")
            if res.get("error"):
                self._paint_result(f"⚠ {res['error']}", role="warn")
                return
            stub = res["decision_id"]
            lk = self.session.link(stub, target, "REFERENCES")
        except Exception as e:
            self._paint_result(f"⚠ flag write failed: {e}", role="warn")
            return
        tail = f" (link: {lk['error']})" if lk.get("error") else ""
        self._paint_result(f"flagged {target[:8]} → stub {stub[:8]}{tail}")
