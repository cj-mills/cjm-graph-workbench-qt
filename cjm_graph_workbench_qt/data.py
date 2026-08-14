"""One open graph behind a private asyncio loop thread — sync reads for the Qt shell.

The projection layer is async (open_graph + the lens views); Qt's event loop is
not. A GraphSession owns a daemon loop thread, opens the graph ONCE (the cold
capability load is a per-open cost, never a per-read one), and exposes blocking
fetches the widgets call directly. Read-only, like the slab it serves."""

import asyncio
import os
import threading
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_primitives.journal import append_write
from cjm_context_graph_projection import write as write_verbs
from cjm_context_graph_projection.authoring import read_node
from cjm_context_graph_projection.factlayer import load_label
from cjm_context_graph_projection.projection import grep, locate, show
from cjm_context_graph_projection.runtime import DEFAULT_MANIFESTS, open_graph
from cjm_context_graph_projection.workbench import anchor_lead_view, portfolio_view, session_feed


class GraphSession:
    """Sync facade over the async lens layer: start() opens the graph, the
    fetch methods block the caller (the Qt thread) until the loop thread
    delivers, close() tears both down. One instance per window; concurrent
    instances stay legal (no current-session singletons — DEC ee9e9be6)."""

    def __init__(self, graph_db_path: str, manifests_dir: Optional[str] = None,
                 journal_paths: Optional[List[str]] = None, timeout: float = 60.0):
        self.graph_db_path = graph_db_path
        self.manifests_dir = manifests_dir or DEFAULT_MANIFESTS
        self.journal_paths = list(journal_paths or [])
        self.timeout = timeout
        self.gx = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stack: Optional[AsyncExitStack] = None

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout)

    async def _open(self):
        self._stack = AsyncExitStack()
        return await self._stack.enter_async_context(
            open_graph(self.graph_db_path, self.manifests_dir))

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name="graph-session", daemon=True)
        self._thread.start()
        self.gx = self._call(self._open())

    def portfolio(self) -> Dict[str, Any]:
        return self._call(portfolio_view(self.gx, journal_paths=self.journal_paths))

    def lead(self, ref: str) -> Dict[str, Any]:
        return self._call(anchor_lead_view(self.gx, ref))

    def node(self, ref: str) -> Tuple[Dict[str, Any], Optional[str]]:
        detail = self._call(show(self.gx, ref, journal_paths=self.journal_paths))
        if detail.get("error"):
            return detail, None
        body_res = self._call(read_node(self.gx, ref))
        body = None if body_res.get("error") else str(body_res.get("text", ""))
        return detail, body

    def feed(self, session_key: Optional[str] = None, since: Optional[float] = None,
             limit: int = 200) -> Dict[str, Any]:
        """The two-zoom session feed (DEC ee9e9be6) — declarative and cheap, so
        live mode is plain re-evaluation (the Qt shell polls this)."""
        return self._call(session_feed(self.gx, self.journal_paths,
                                       session=session_key, since=since, limit=limit))

    def body(self, ref: str) -> Optional[str]:
        """A node's verbatim body alone (feed-card expansion — no `show` join)."""
        res = self._call(read_node(self.gx, ref))
        return None if res.get("error") else str(res.get("text", ""))

    # ---- journaled writes (slab 2) -------------------------------------

    def _journal(self, verb: str, args: Dict[str, Any]) -> None:
        """Mirror a LANDED write into the writes journal (journal_paths[0]) with
        the exact arg shape cg-write's CLI records — replay/rebuild must treat
        workbench writes and cg-writes identically (the db is a projection;
        an unjournaled write is lost on the next rebuild)."""
        if self.journal_paths:
            append_write(self.journal_paths[0], verb, args)

    def register_session(self, key: str, *, started_at: Optional[float] = None,
                         title: Optional[str] = None,
                         actor: str = "user:workbench") -> Dict[str, Any]:
        res = self._call(write_verbs.register_session(
            self.gx, key, started_at=started_at, title=title, actor=actor))
        if res.get("written"):
            self._journal("session", {"key": key, "started_at": started_at,
                                      "title": title, "actor": actor})
        return res

    def decide(self, statement: str, *, title: Optional[str] = None,
               state: Optional[str] = None, session: Optional[str] = None,
               actor: str = "user:workbench") -> Dict[str, Any]:
        """Mint a Decision (optionally with task_state, mirroring `decide --state`:
        a fresh work item is invisible to readiness until task_state lands)."""
        res = self._call(write_verbs.decide(self.gx, statement, actor=actor,
                                            session=session, title=title))
        if res.get("error"):
            return res
        self._journal("decide", {"statement": statement, "actor": actor,
                                 "supports": None, "supersedes": None,
                                 "session": session, "title": title})
        if state:
            st = self._call(write_verbs.assert_value(
                self.gx, res["decision_id"], "task_state", state, actor=actor))
            if not st.get("error"):
                self._journal("assert", {"subject": res["decision_id"],
                                         "predicate": "task_state", "value": state,
                                         "actor": actor, "evidence": None,
                                         "supersede": False})
        return res

    def link(self, source_id: str, target_id: str, relation: str, *,
             actor: str = "user:workbench") -> Dict[str, Any]:
        res = self._call(write_verbs.link(self.gx, source_id, target_id, relation,
                                          actor=actor))
        if res.get("written"):
            self._journal("link", {"source_id": res["source_id"],
                                   "target_id": res["target_id"],
                                   "relation": relation, "actor": actor,
                                   "source_label": res.get("source_label"),
                                   "target_label": res.get("target_label")})
        return res

    def feed_async(self, session_key: Optional[str] = None,
                   since: Optional[float] = None, limit: int = 200):
        """Non-blocking feed read: a concurrent Future resolving on the loop
        thread — the Qt shell must never block its paint thread on a journal
        parse (drive find 2026-08-14: the sync 2s poll hitched scrolling)."""
        return asyncio.run_coroutine_threadsafe(
            session_feed(self.gx, self.journal_paths, session=session_key,
                         since=since, limit=limit), self._loop)

    def sessions(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Registered Session spine nodes (one server-side label pull), newest
        first: {id, key, title, started_at}."""
        nodes = self._call(load_label(self.gx, "Session", limit=limit))
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

    def search(self, term: str, limit: int = 25) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """The literal pair (slab-2 half of the search seat): locate over
        identifying properties + grep over exhaustive content."""
        return (self._call(locate(self.gx, term, limit=limit)),
                self._call(grep(self.gx, term, limit=limit)))

    def close(self) -> None:
        if self._loop is None:
            return
        if self._stack is not None:
            self._call(self._stack.aclose())
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)


def session_pointer_path(journal_paths: List[str]) -> Optional[str]:
    """The `.cjm/current-session` pointer next to the WRITES journal — the
    default for untagged writers (env-first everywhere: CJM_SESSION overrides;
    long-term shape is writer-scoped binding, item 4972bac7)."""
    if not journal_paths:
        return None
    return os.path.join(os.path.dirname(journal_paths[0]), "current-session")


def read_session_pointer(journal_paths: List[str]) -> Optional[str]:
    """The pointed session key, or None (missing/empty file is not an error)."""
    path = session_pointer_path(journal_paths)
    try:
        with open(path) as f:  # type: ignore[arg-type]
            key = f.readline().strip()
        return key or None
    except (TypeError, OSError):
        return None


def write_session_pointer(journal_paths: List[str], key: str) -> Optional[str]:
    """Point `.cjm/current-session` at `key` (the seat's S verb); returns the
    path written, or None when there is no journal to sit next to."""
    path = session_pointer_path(journal_paths)
    if not path:
        return None
    with open(path, "w") as f:
        f.write(key)
    return path
