"""Node-in-context as MARKDOWN — the Qt absorption surface (item d2a6d8e1).

The Textual shell flattens a node into fixed-width rows; the Qt shell hands
QTextDocument real markdown instead: proportional type, native word-wrap,
rendered headings/emphasis/code inside note bodies. Neighbour references
become `graph://<id>` links, so 'enter descends' survives the medium change
as link activation. Pure functions -> pytest covers this module; painting
verifies by grab() probe (family craft)."""

from typing import Any, Dict, List, Optional

from cjm_graph_workbench_tui.spine import fmt_ts

CODE_KINDS = ("CodeSymbol", "CodeModule", "CodeText", "Cell")


def link_text(title: Any) -> str:
    """Escape the markdown-active characters in link/inline TEXT (titles and
    summaries are data): brackets, and raw `<` — QTextDocument's markdown
    parser reads `<word>` as an inline-HTML element and SWALLOWS the rest of
    the document (drive find 2026-08-14: a statement containing a literal
    `expand:` link example ate the neighbours section)."""
    return (str(title).replace("[", "\\[").replace("]", "\\]")
            .replace("<", "&lt;"))


def escape_inline_html(text: str) -> str:
    """Neutralize raw `<` in PROSE so it cannot open an inline-HTML element
    (same hazard as link_text; fenced code protects itself, so never apply
    this inside a fence)."""
    return text.replace("<", "&lt;")


def build_node_markdown(detail: Dict[str, Any], body: Optional[str]) -> str:
    """One node's whole context as a markdown document (DEC 47501c78 order:
    head matter, ACTIVE facts, journal trace, counts-first neighbour overview
    (each relation a jump: link descending in-page to its group),
    verbatim body — code kinds fenced, notes rendered — then the typed
    neighbour groups as `graph://<id>` links)."""
    n = detail.get("node") or {}
    props = detail.get("properties") or {}
    lines: List[str] = [f"# {n.get('title', '?')}", "",
                        f"`{n.get('label', '?')}` · `{n.get('id', '')}`"]
    facts = detail.get("facts") or {}
    if facts:
        lines += ["", "**" + " · ".join(f"{k} = {v}" for k, v in sorted(facts.items())) + "**"]
    j = detail.get("journal") or {}
    bits = []
    if j.get("first_ts"):
        bits.append("created " + fmt_ts(j["first_ts"]))
    if j.get("last_ts"):
        bits.append("updated " + fmt_ts(j["last_ts"]))
    if j.get("sessions"):
        bits.append("sessions " + ", ".join(list(j["sessions"])[-3:]))
    if j.get("actors"):
        bits.append("actors " + ", ".join(j["actors"]))
    if bits:
        lines += ["", "*" + " · ".join(bits) + "*"]
    nb = sorted(detail.get("neighbours") or [],
                key=lambda e: ((e.get("relation") or "") in ("HAS_SECTION", "CONTAINS"),
                               e.get("relation") or "", e.get("direction") or ""))
    if nb:  # counts-first overview, each entry a jump: link (round-2 parity)
        counts: Dict[str, int] = {}
        for e in nb:
            rel = str(e.get("relation", "?"))
            counts[rel] = counts.get(rel, 0) + 1
        overview = sorted(counts, key=lambda r: (r not in ("HAS_SECTION", "CONTAINS"), r))
        # `jump:` scheme WITHOUT `//`: an authority component would get
        # host-normalized (lowercased) by QUrl, breaking the block match.
        lines += ["", " · ".join(f"[{rel} ({counts[rel]})](jump:{rel})"
                                 for rel in overview)]
    text = body if body else str(props.get("statement") or props.get("value") or "")
    if text:
        lines += ["", "---", ""]
        if n.get("label") in CODE_KINDS:
            lines += ["```python", text.rstrip("\n"), "```"]
        else:
            lines.append(_defuse_frontmatter(text))
    lines += ["", "---", "", f"## neighbours ({len(nb)})"]
    seen_rel = None
    for e in nb:
        node = e.get("node") or {}
        rel = str(e.get("relation", "?"))
        if rel != seen_rel:
            lines += ["", f"**{rel}**", ""]
            seen_rel = rel
        arrow = "→" if e.get("direction") == "out" else "←"
        lines.append(f"- {arrow} [{link_text(node.get('title', '?'))}](graph://{node.get('id', '')}) "
                     f"*{node.get('label', '?')}*")
    return "\n".join(lines)


def _defuse_frontmatter(text: str) -> str:
    """Prose body -> safe markdown: leading `---` frontmatter fenced as yaml
    (it renders as setext-heading noise otherwise), and raw inline HTML
    neutralized in the prose remainder (the fence protects its own)."""
    if not text.startswith("---\n"):
        return escape_inline_html(text)
    end = text.find("\n---", 4)
    if end < 0:
        return escape_inline_html(text)
    head = text[4:end].rstrip("\n")
    rest = text[end + 4:].lstrip("\n")
    return "```yaml\n" + head + "\n```\n\n" + escape_inline_html(rest)


def build_search_markdown(term: str, locate_res: Dict[str, Any],
                          grep_res: Dict[str, Any]) -> str:
    """Literal search results as one page of graph:// links (the slab-2 half
    of the 18cd3e8d search seat): `locate` over identifying properties, `grep`
    over exhaustive content with judgeable snippets. Concept-level existence
    stays slab 3."""
    lines: List[str] = [f"# search — {link_text(term)}", ""]
    loc = locate_res.get("matches") or []
    hits = grep_res.get("matches") or []
    lines.append(f"*locate {locate_res.get('count', len(loc))}"
                 f"{' (truncated)' if locate_res.get('truncated') else ''}"
                 f" · grep {grep_res.get('count', len(hits))}"
                 f"{' (truncated)' if grep_res.get('truncated') else ''}*")
    lines += ["", "## locate — names · slugs · paths", ""]
    for m in loc:
        path = f" — `{m['path']}`" if m.get("path") else ""
        lines.append(f"- [{link_text(m.get('title') or str(m.get('id', ''))[:8])}]"
                     f"(graph://{m.get('id', '')}) `{m.get('label', '?')}`{path}")
    if not loc:
        lines.append("*(no matches)*")
    lines += ["", "## grep — exact content", ""]
    for m in hits:
        lines.append(f"- [{link_text(m.get('title') or str(m.get('id', ''))[:8])}]"
                     f"(graph://{m.get('id', '')}) `{m.get('label', '?')}`"
                     f" · {m.get('field', '?')}")
        if m.get("snippet"):
            lines.append(f"  …{link_text(m['snippet'])}…")
    if not hits:
        lines.append("*(no matches)*")
    return "\n".join(lines)
