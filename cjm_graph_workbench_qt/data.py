"""One open graph behind a private asyncio loop thread — the workbench's
session over the projection layer.

The projection layer is async (open_graph + the lens views); Qt's event loop
is not. A GraphSession owns a daemon loop thread (the kit LoopThreadSession's
OPEN / JOURNAL / CLOSE pattern, ruling 2bae2cc1), opens the graph ONCE on it
(the cold capability load is a per-open cost, never a per-read one), and
exposes every read twice: the `*_async` form — a Future the shell's bridge
lands on the Qt thread (the paint thread never blocks) — and the blocking
form for probes, scripts and teardown. Writes are journal-mirrored in
cg-write's exact arg shape through the base's journal()."""

from concurrent.futures import Future
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_primitives.journal import read_journal
from cjm_context_graph_projection import write as write_verbs
from cjm_context_graph_projection.authoring import read_node
from cjm_context_graph_projection.factlayer import load_label
from cjm_context_graph_projection.projection import grep, locate, show
from cjm_context_graph_projection.runtime import DEFAULT_MANIFESTS, open_graph
from cjm_context_graph_projection.workbench import anchor_lead_view, portfolio_view, session_feed
from cjm_substrate_qt_kit import sessionkey
from cjm_substrate_qt_kit.loopthread import LoopThreadSession, op_write


class GraphSession(LoopThreadSession):
    """The workbench's session: start() opens the graph on the loop, the
    `*_async` reads return Futures for the shell's bridge, the plain reads
    block (probes, scripts), close() tears both down. One instance per
    window; concurrent instances stay legal (no current-session singletons —
    DEC ee9e9be6)."""

    thread_name = "graph-session"

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
        nodes = await load_label(self.gx, "Session", limit=limit)
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
        return self.call(self._portfolio())

    def portfolio_async(self) -> Future:
        return self.submit(self._portfolio())

    def lead(self, ref: str) -> Dict[str, Any]:
        return self.call(self._lead(ref))

    def lead_async(self, ref: str) -> Future:
        return self.submit(self._lead(ref))

    def node(self, ref: str) -> Tuple[Dict[str, Any], Optional[str]]:
        return self.call(self._node(ref))

    def node_async(self, ref: str) -> Future:
        return self.submit(self._node(ref))

    def body(self, ref: str) -> Optional[str]:
        """A node's verbatim body alone (feed-card expansion — no `show` join)."""
        return self.call(self._body(ref))

    def body_async(self, ref: str) -> Future:
        return self.submit(self._body(ref))

    def feed(self, session_key: Optional[str] = None, since: Optional[float] = None,
             limit: int = 200) -> Dict[str, Any]:
        """The two-zoom session feed (DEC ee9e9be6) — declarative and cheap, so
        live mode is plain re-evaluation (the Qt shell polls this)."""
        return self.call(self._feed(session_key, since, limit))

    def feed_async(self, session_key: Optional[str] = None,
                   since: Optional[float] = None, limit: int = 200) -> Future:
        """Non-blocking feed read: the Qt shell must never block its paint
        thread on a journal parse (drive find 2026-08-14: the sync 2s poll
        hitched scrolling)."""
        return self.submit(self._feed(session_key, since, limit))

    def sessions(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Registered Session spine nodes (one server-side label pull), newest
        first: {id, key, title, started_at}."""
        return self.call(self._sessions(limit))

    def sessions_async(self, limit: int = 500) -> Future:
        return self.submit(self._sessions(limit))

    def search(self, term: str, limit: int = 25) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """The literal pair (slab-2 half of the search seat): locate over
        identifying properties + grep over exhaustive content."""
        return self.call(self._search(term, limit))

    def search_async(self, term: str, limit: int = 25) -> Future:
        return self.submit(self._search(term, limit))

    # ---- journaled writes (slab 2) -------------------------------------

    @op_write
    def register_session(self, key: str, *, started_at: Optional[float] = None,
                         title: Optional[str] = None,
                         actor: str = "user:workbench") -> Dict[str, Any]:
        res = self.call(write_verbs.register_session(
            self.gx, key, started_at=started_at, title=title, actor=actor))
        if res.get("written"):
            self.journal("session", {"key": key, "started_at": started_at,
                                     "title": title, "actor": actor})
        return res

    @op_write
    def retract_session(self, key: str, *, force: bool = False,
                        actor: str = "user:workbench") -> Dict[str, Any]:
        """RETRACT an empty-minted Session spine node (key-repeat Shift+S dups).

        Mirrors the CLI guard: any journaled op attributed to the key besides
        its own registrations means real history — refuse unless force. The
        landed retraction is journaled so a rebuild converges (the db is a
        projection; an unjournaled delete resurrects on the next replay)."""
        foreign = [
            op for p in self.journal_paths for op in read_journal(p)
            if (op.get("session") or (op.get("args") or {}).get("session")) == key
            and not (op.get("verb") == "session"
                     and (op.get("args") or {}).get("key") == key)]
        if foreign and not force:
            return {"error": f"session '{key}' has {len(foreign)} journaled op(s) "
                             f"attributed to it — not an empty mint",
                    "written": False}
        res = self.call(write_verbs.retract_session(self.gx, key, actor=actor))
        if res.get("written"):
            self.journal("retract-session", {"key": key, "actor": actor})
        return res

    @op_write
    def decide(self, statement: str, *, title: Optional[str] = None,
               state: Optional[str] = None, session: Optional[str] = None,
               actor: str = "user:workbench") -> Dict[str, Any]:
        """Mint a Decision (optionally with task_state, mirroring `decide --state`:
        a fresh work item is invisible to readiness until task_state lands)."""
        res = self.call(write_verbs.decide(self.gx, statement, actor=actor,
                                           session=session, title=title))
        if res.get("error"):
            return res
        self.journal("decide", {"statement": statement, "actor": actor,
                                "supports": None, "supersedes": None,
                                "session": session, "title": title})
        if state:
            st = self.call(write_verbs.assert_value(
                self.gx, res["decision_id"], "task_state", state, actor=actor))
            if not st.get("error"):
                self.journal("assert", {"subject": res["decision_id"],
                                        "predicate": "task_state", "value": state,
                                        "actor": actor, "evidence": None,
                                        "supersede": False})
        return res

    @op_write
    def link(self, source_id: str, target_id: str, relation: str, *,
             actor: str = "user:workbench") -> Dict[str, Any]:
        res = self.call(write_verbs.link(self.gx, source_id, target_id, relation,
                                         actor=actor))
        if res.get("written"):
            self.journal("link", {"source_id": res["source_id"],
                                  "target_id": res["target_id"],
                                  "relation": relation, "actor": actor,
                                  "source_label": res.get("source_label"),
                                  "target_label": res.get("target_label")})
        return res


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
