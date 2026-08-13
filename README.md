# cjm-graph-workbench-qt

Qt workbench over a cjm context graph — the slab-1 **pilot** for the PySide6
application lane (DEC `1e5b9a76`). Re-paints the Textual workbench's stages
(portfolio front door → per-anchor pin trees → node-in-context) over the same
projection lens layer and the same spine row dicts, with the absorption wins Qt
gives for free: proportional typography, native word-wrap, and
markdown-rendered note bodies (`QTextDocument.setMarkdown`).

Read-only spike. Keyboard vocabulary matches the Textual shell: `j/k` move,
`tab` next actionable, `enter` open, `b` back, `p` portfolio, `r` reload,
`q` quit; on the node stage `tab` cycles neighbour links and `enter` follows.

```
cjm-graph-workbench-qt --graph-db-path <db> [--journal-path <jsonl>] [--anchor <slug>]
```

Born on-graph: the modules are graph-sourced (`cjm-substrate` dev graph); the
`.py` files are generated committed artifacts.
