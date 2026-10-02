# cjm-graph-workbench-qt

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

_No purpose recorded on-graph yet — author it with_ `assert 64eca3b7-45b2-550b-b70a-39b76aefaf32 purpose "…"` _(or by the repo's entity key)._

## Modules

- **`cjm_graph_workbench_qt.__init__`** — Qt workbench over a cjm context graph — the PySide6 lane slab-1 pilot (d2a6d8e1).
- **`cjm_graph_workbench_qt.app`** — The Qt workbench: the FIRST SHELL INSTANCE (ruling 2bae2cc1, item a9ba662e).
- **`cjm_graph_workbench_qt.cli`** — CLI entry for the Qt graph workbench (console script `cjm-graph-workbench-qt`).
- **`cjm_graph_workbench_qt.data`** — One open graph behind a private asyncio loop thread — the workbench's
- **`cjm_graph_workbench_qt.feed`** — The session feed as MARKDOWN — slab 2's seat page (DEC ee9e9be6).
- **`cjm_graph_workbench_qt.mdspine`** — Node-in-context as MARKDOWN — the Qt absorption surface (item d2a6d8e1).
- **`cjm_graph_workbench_qt.spine`** — Pure spine for the workbench: lens-layer view dicts -> flat row lists.

## API

### `cjm_graph_workbench_qt.app`

- `WorkbenchWindow` _class_ — Portfolio front door -> anchor pin tree -> node-in-context detail.
- `picker_rows` _function_ — Spine row dicts -> PickerList rows: every row is a cursor stop (j/k

### `cjm_graph_workbench_qt.cli`

- `build_parser` _function_
- `main` _function_ — Resolve the launch, open the graph session, run the window; teardown is unconditional.
- `resolve` _function_ — The precedence walk over the launch keys; the graph db is required

### `cjm_graph_workbench_qt.data`

- `GraphSession` _class_ — The workbench's session: start() opens the graph on the loop, the
- `read_session_pointer` _function_
- `session_pointer_path` _function_
- `write_session_pointer` _function_

### `cjm_graph_workbench_qt.feed`

- `build_feed_markdown` _function_ — The whole feed page for one zoom level: header (session/window vitals,
- `build_session_rows` _function_ — The sessions picker as rows (newest first): key · started · title —
- `fmt_ts_s` _function_ — Unix seconds -> local wall-clock WITH seconds — feed ops land seconds

### `cjm_graph_workbench_qt.mdspine`

- `build_node_markdown` _function_ — One node's whole context as a markdown document (DEC 47501c78 order:
- `build_search_markdown` _function_ — Literal search results as one page of graph:// links (the slab-2 half
- `escape_inline_html` _function_ — Neutralize markdown hazards in PROSE — raw `<` and bare `~` — while
- `link_text` _function_ — Escape the markdown-active characters in link/inline TEXT (titles and

### `cjm_graph_workbench_qt.spine`

- `build_lead_rows` _function_ — One anchor's pin tree as rows: lock (row descends to the note, body lines
- `build_node_rows` _function_ — Node-in-context as rows (DEC 47501c78): title, kind/id, ACTIVE facts,
- `build_portfolio_rows` _function_ — The front door as rows: counts header, one block per anchor (portfolio
- `fmt_ts` _function_ — Unix seconds -> local wall-clock (minutes), or '' — humans read wall-clock.

## Dependencies

**Depends on:** `PySide6`, `cjm-context-graph-projection`, `cjm-substrate-qt-kit`
