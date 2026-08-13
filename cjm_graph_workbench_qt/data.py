"""One open graph behind a private asyncio loop thread — sync reads for the Qt shell.

The projection layer is async (open_graph + the lens views); Qt's event loop is
not. A GraphSession owns a daemon loop thread, opens the graph ONCE (the cold
capability load is a per-open cost, never a per-read one), and exposes blocking
fetches the widgets call directly. Read-only, like the slab it serves."""

import asyncio
import threading
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_projection.authoring import read_node
from cjm_context_graph_projection.projection import show
from cjm_context_graph_projection.runtime import DEFAULT_MANIFESTS, open_graph
from cjm_context_graph_projection.workbench import anchor_lead_view, portfolio_view


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

    def close(self) -> None:
        if self._loop is None:
            return
        if self._stack is not None:
            self._call(self._stack.aclose())
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
