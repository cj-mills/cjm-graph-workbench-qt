"""One open graph behind a private asyncio loop thread — the workbench's
session over the projection layer.

The projection layer is async (open_graph + the lens views); Qt's event loop
is not. A GraphSession owns a daemon loop thread (the kit LoopThreadSession's
OPEN / JOURNAL / CLOSE pattern, ruling 2bae2cc1), opens the graph ONCE on it
(the cold capability load is a per-open cost, never a per-read one), and
exposes every read twice: the `*_async` form — a Future the shell's bridge
lands on the Qt thread (the paint thread never blocks) — and the blocking
form for probes, scripts and teardown. Writes go through the CLI's own landing
functions inside its unit of work (ruling d2d05e78): journaled before they apply."""

from concurrent.futures import Future
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_primitives.query import OrderBy
from cjm_context_graph_projection import perf, write as write_verbs
from cjm_context_graph_projection.authoring import read_node
from cjm_context_graph_projection.factlayer import load_label_where
from cjm_context_graph_projection.projection import grep, locate, show
from cjm_context_graph_projection.runtime import DEFAULT_MANIFESTS, open_graph
from cjm_context_graph_projection.workbench import anchor_lead_view, portfolio_view, session_feed
from cjm_context_graph_projection.writes import write_window
from cjm_substrate_qt_kit import sessionkey
from cjm_substrate_qt_kit.gesturebench import ladder
from cjm_substrate_qt_kit.loopthread import LoopThreadSession, op_write


class GraphSession(LoopThreadSession):
    """The workbench's session: start() opens the graph on the loop, the
    `*_async` reads return Futures for the shell's bridge, the plain reads
    block (probes, scripts), close() tears both down. One instance per
    window; concurrent instances stay legal (no current-session singletons —
    DEC ee9e9be6). Every read and write is a measured gesture (the kit's seam,
    design detail 4389a579) in the graph's timings ledger; the feed is a poll."""

    thread_name = "graph-session"
    app = "workbench"
    polls = frozenset({"feed"})

    def __init__(self, graph_db_path: str, manifests_dir: Optional[str] = None,
                 journal_paths: Optional[List[str]] = None, timeout: float = 60.0):
        super().__init__(timeout=timeout, journal_paths=journal_paths)
        self.graph_db_path = graph_db_path
        self.manifests_dir = manifests_dir or DEFAULT_MANIFESTS
        self.gx = None
        self._stack: Optional[AsyncExitStack] = None

    async def on_open(self) -> None:
        self._stack = AsyncExitStack()
        self.gx = await self._stack.enter_async_context(
            open_graph(self.graph_db_path, self.manifests_dir))
        await self.measure_into(self.graph_db_path)

    async def measure_covariates(self) -> Optional[Dict[str, Any]]:
        """The growth covariates beside the gestures (design detail 4389a579): the
        projection's measure -- the store, the repos, the journal families this
        session reads (journal_paths: the writes journal, then the source journal)."""
        return await perf.measure_covariates(self.gx, dict(zip(("writes", "source"),
                                                               self.journal_paths)))

    async def on_close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()

    # ---- reads: coroutines, then the async + blocking doors ---------------

    def _portfolio(self):
        return portfolio_view(self.gx, journal_paths=self.journal_paths)

    def _lead(self, ref: str):
        return anchor_lead_view(self.gx, ref)

    async def _node(self, ref: str) -> Tuple[Dict[str, Any], Optional[str]]:
        detail = await show(self.gx, ref, journal_paths=self.journal_paths)
        if detail.get("error"):
            return detail, None
        body_res = await read_node(self.gx, ref)
        body = None if body_res.get("error") else str(body_res.get("text", ""))
        return detail, body

    async def _body(self, ref: str) -> Optional[str]:
        res = await read_node(self.gx, ref)
        return None if res.get("error") else str(res.get("text", ""))

    def _feed(self, session_key: Optional[str], since: Optional[float], limit: int):
        return session_feed(self.gx, self.journal_paths, session=session_key,
                            since=since, limit=limit)

    async def _sessions(self, limit: int) -> List[Dict[str, Any]]:
        # The newest `limit` sessions, ordered in SQL before the cut (finding a107e2f3: a
        # capped load sorted afterwards dropped the NEWEST once the class outgrew the cap).
        nodes = await load_label_where(self.gx, "Session", [], limit=limit,
                                       order_by=OrderBy("started_at", descending=True))
        out: List[Dict[str, Any]] = []
        for n in nodes:
            props = (n.get("properties") if isinstance(n, dict)
                     else getattr(n, "properties", None)) or {}
            nid = n.get("id") if isinstance(n, dict) else getattr(n, "id", None)
            key = props.get("key") or props.get("name")
            if not key:
                continue
            out.append({"id": nid, "key": str(key),
                        "title": str(props.get("display_title") or ""),
                        "started_at": props.get("started_at")})
        out.sort(key=lambda s: (s.get("started_at") or 0.0, s["key"]), reverse=True)
        return out

    async def _search(self, term: str, limit: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return (await locate(self.gx, term, limit=limit),
                await grep(self.gx, term, limit=limit))

    def portfolio(self) -> Dict[str, Any]:
        return self.call(self._portfolio(), gesture="portfolio")

    def portfolio_async(self) -> Future:
        return self.submit(self._portfolio(), gesture="portfolio")

    def lead(self, ref: str) -> Dict[str, Any]:
        return self.call(self._lead(ref), gesture="lead")

    def lead_async(self, ref: str) -> Future:
        return self.submit(self._lead(ref), gesture="lead")

    def node(self, ref: str) -> Tuple[Dict[str, Any], Optional[str]]:
        return self.call(self._node(ref), gesture="node")

    def node_async(self, ref: str) -> Future:
        return self.submit(self._node(ref), gesture="node")

    def body(self, ref: str) -> Optional[str]:
        """A node's verbatim body alone (feed-card expansion — no `show` join)."""
        return self.call(self._body(ref), gesture="body")

    def body_async(self, ref: str) -> Future:
        return self.submit(self._body(ref), gesture="body")

    def feed(self, session_key: Optional[str] = None, since: Optional[float] = None,
             limit: int = 200) -> Dict[str, Any]:
        """The two-zoom session feed (DEC ee9e9be6) — declarative and cheap, so
        live mode is plain re-evaluation (the Qt shell polls this)."""
        return self.call(self._feed(session_key, since, limit), gesture="feed")

    def feed_async(self, session_key: Optional[str] = None,
                   since: Optional[float] = None, limit: int = 200) -> Future:
        """Non-blocking feed read: the Qt shell must never block its paint
        thread on a journal parse (drive find 2026-08-14: the sync 2s poll
        hitched scrolling)."""
        return self.submit(self._feed(session_key, since, limit), gesture="feed")

    def sessions(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Registered Session spine nodes (one server-side label pull), newest
        first: {id, key, title, started_at}."""
        return self.call(self._sessions(limit), gesture="sessions")

    def sessions_async(self, limit: int = 500) -> Future:
        return self.submit(self._sessions(limit), gesture="sessions")

    def search(self, term: str, limit: int = 25) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """The literal pair (slab-2 half of the search seat): locate over
        identifying properties + grep over exhaustive content."""
        return self.call(self._search(term, limit), gesture="search")

    def search_async(self, term: str, limit: int = 25) -> Future:
        return self.submit(self._search(term, limit), gesture="search")

    # ---- journaled writes (slab 2) -------------------------------------
    # Each write gesture is ONE coroutine inside the unit of work (ruling d2d05e78): the writes
    # journal's lock and heal, the verb's landing function -- the same one the CLI's branch
    # calls -- planning each op, appending it, applying it through the replay's applier, and the
    # live write window's site-link step before the lock is released.

    def _writes(self):
        return write_window(self.gx, self.journal_paths[0] if self.journal_paths else None)

    def register_session(self, key: str, *, started_at: Optional[float] = None,
                         title: Optional[str] = None,
                         actor: str = "user:workbench") -> Dict[str, Any]:
        return self.call(self._register_session(key, started_at, title, actor),
                         gesture="register_session")

    @op_write
    async def _register_session(self, key: str, started_at: Optional[float],
                                title: Optional[str], actor: str) -> Dict[str, Any]:
        async with self._writes() as writes:
            return await write_verbs.land_session(self.gx, writes, key, started_at=started_at,
                                                  title=title, actor=actor)

    def retract_session(self, key: str, *, force: bool = False,
                        actor: str = "user:workbench") -> Dict[str, Any]:
        """RETRACT an empty-minted Session spine node (key-repeat Shift+S dups): the landing
        function's emptiness guard refuses a key with journaled history unless force."""
        return self.call(self._retract_session(key, force, actor), gesture="retract_session")

    @op_write
    async def _retract_session(self, key: str, force: bool, actor: str) -> Dict[str, Any]:
        async with self._writes() as writes:
            return await write_verbs.land_retract_session(
                self.gx, writes, key, journal_paths=self.journal_paths, force=force, actor=actor)

    def decide(self, statement: str, *, title: Optional[str] = None,
               state: Optional[str] = None, session: Optional[str] = None,
               actor: str = "user:workbench") -> Dict[str, Any]:
        """Mint a Decision (optionally with task_state, `decide --state`'s chain: a fresh work
        item is invisible to readiness until task_state lands)."""
        return self.call(self._decide(statement, title, state, session, actor), gesture="decide")

    @op_write
    async def _decide(self, statement: str, title: Optional[str], state: Optional[str],
                      session: Optional[str], actor: str) -> Dict[str, Any]:
        async with self._writes() as writes:
            return await write_verbs.land_decide(
                self.gx, writes, statement, actor=actor, session=session, title=title,
                facts=[("task_state", state)] if state else [])

    def link(self, source_id: str, target_id: str, relation: str, *,
             actor: str = "user:workbench") -> Dict[str, Any]:
        return self.call(self._link(source_id, target_id, relation, actor), gesture="link")

    @op_write
    async def _link(self, source_id: str, target_id: str, relation: str,
                    actor: str) -> Dict[str, Any]:
        async with self._writes() as writes:
            return await write_verbs.land_link(self.gx, writes, source_id, target_id, relation,
                                               actor=actor, manifests_dir=self.manifests_dir)


def bench_gestures(
    params: Dict[str, Any],  # db, manifests_dir, journals; the lane's anchor / hub / session / term
) -> List[str]:  # The gestures run, in order
    """The workbench's canonical gestures for the scale harness (design detail 4389a579): its
    read ladder on one graph -- the portfolio, an anchor's lead, a node, one feed tick, the
    sessions list, a search -- each measured by the session's own seam."""
    journals = params.get("journals") or {}
    s = GraphSession(params["db"], manifests_dir=params.get("manifests_dir"),
                     journal_paths=[p for p in (journals.get("writes"), journals.get("source")) if p],
                     timeout=float(params.get("timeout_s", 3600)))
    s.start()
    try:
        return ladder([("portfolio", s.portfolio),
                       ("lead", lambda: s.lead(params["anchor"])),
                       ("node", lambda: s.node(params["hub"])),
                       ("feed", lambda: s.feed(params.get("session"))),
                       ("sessions", s.sessions),
                       ("search", lambda: s.search(params["term"]))])
    finally:
        s.close()


# The session-pointer helpers moved to the kit (sessionkey — the ONE
# implementation the shell and every app share); these names stay for
# callers that import them from here.

def session_pointer_path(journal_paths: List[str]) -> Optional[str]:
    p = sessionkey.pointer_path(journal_paths)
    return str(p) if p is not None else None


def read_session_pointer(journal_paths: List[str]) -> Optional[str]:
    return sessionkey.read_pointer(sessionkey.pointer_path(journal_paths))


def write_session_pointer(journal_paths: List[str], key: str) -> Optional[str]:
    p = sessionkey.pointer_path(journal_paths)
    return str(sessionkey.write_pointer(p, key)) if p is not None else None
