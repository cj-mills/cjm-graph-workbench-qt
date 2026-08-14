"""The session feed as MARKDOWN — slab 2's seat page (DEC ee9e9be6).

Two zoom levels of ONE page: the op ledger (journal ops with refs joined to
live nodes — the verify-it-landed read) and the touched-node cards (per-node
aggregation, bodies expandable per card). Pure builders over `session_feed`
view dicts; refs render as `graph://<id>` links and card expansion as
`expand:<id>` toggle links, so the shell's owned link-cycling drives the whole
page. Painting verifies by grab() probe (family craft)."""

from typing import Any, Dict, List, Optional, Set

from cjm_graph_workbench_tui.spine import fmt_ts

from .mdspine import _defuse_frontmatter, CODE_KINDS, link_text


def _ref_links(refs: List[Dict[str, Any]]) -> str:
    """Joined refs as ` · `-separated graph:// links; missing refs stay VISIBLE
    (struck through) — the feed is an audit surface, never silently thinner."""
    parts: List[str] = []
    for r in refs:
        if r.get("missing"):
            parts.append(f"~~{str(r.get('ref', ''))[:8]}~~")
        else:
            title = r.get("title") or str(r.get("id", ""))[:8]
            parts.append(f"[{link_text(title)}](graph://{r.get('id', '')})")
    return " · ".join(parts)


def _card_markdown(card: Dict[str, Any], expanded: Set[str],
                   bodies: Dict[str, Optional[str]]) -> List[str]:
    """One touched-node card: title link, label, per-verb touch counts, window
    span, and an `expand:<id>` toggle; the body renders inline when expanded
    (code kinds fenced, note frontmatter defused — the mdspine rules)."""
    if card.get("missing"):
        return ["", f"### ~~{str(card.get('ref', ''))[:8]}~~ *(missing)*"]
    nid = str(card.get("id", ""))
    title = link_text(card.get("title") or nid[:8])
    lines = ["", f"### [{title}](graph://{nid})  `{card.get('label', '?')}`"]
    verbs = card.get("verbs") or {}
    bits = [f"{v}×{n}" for v, n in sorted(verbs.items())]
    bits.append(f"touches {card.get('touches', 0)}")
    if card.get("last_ts"):
        bits.append("last " + fmt_ts(card["last_ts"]))
    toggle = "− collapse" if nid in expanded else "+ expand"
    lines.append("*" + " · ".join(bits) + f"* — [{toggle}](expand:{nid})")
    if nid in expanded:
        body = bodies.get(nid)
        if not body:
            lines += ["", "*(no verbatim body)*"]
        elif card.get("label") in CODE_KINDS:
            lines += ["", "```python", body.rstrip("\n"), "```"]
        else:
            lines += ["", _defuse_frontmatter(body)]
    return lines


def build_feed_markdown(view: Dict[str, Any], *, zoom: str = "ops",
                        expanded: Optional[Set[str]] = None,
                        bodies: Optional[Dict[str, Optional[str]]] = None) -> str:
    """The whole feed page for one zoom level: header (session/window vitals,
    zoom indicator), then the op LEDGER (`zoom="ops"`, chronological — the
    verify-it-landed read) or the touched-node CARDS (`zoom="cards"`,
    most-recent first)."""
    expanded = expanded or set()
    bodies = bodies or {}
    w = view.get("window") or {}
    key = w.get("session")
    lines: List[str] = [f"# feed — {'session ' + key if key else 'live window'}", ""]
    bits = [f"ops {w.get('shown', 0)}/{w.get('total_ops', 0)}"]
    if w.get("cursor"):
        bits.append("last " + fmt_ts(w["cursor"]))
    if view.get("missing"):
        bits.append(f"missing {view['missing']}")
    bits.append("zoom: " + ("op ledger" if zoom == "ops" else "node cards"))
    lines += ["*" + " · ".join(bits) + "*", "", "---"]
    if zoom == "ops":
        lines.append("")
        for op in view.get("ops", []):
            actor = f" `{op['actor']}`" if op.get("actor") else ""
            row = (f"- **{fmt_ts(op.get('ts'))}** `{op.get('verb', '?')}`{actor}"
                   f" — {link_text(str(op.get('summary') or ''))}")
            refs = _ref_links(op.get("refs") or [])
            lines.append(row + (f" → {refs}" if refs else ""))
        if not view.get("ops"):
            lines.append("*(no ops in this window yet)*")
    else:
        cards = sorted(view.get("cards", []),
                       key=lambda c: -(c.get("last_ts") or 0.0))
        for card in cards:
            lines += _card_markdown(card, expanded, bodies)
        if not cards:
            lines += ["", "*(no nodes touched in this window yet)*"]
    return "\n".join(lines)


def build_session_rows(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The sessions picker as rows (newest first): key · started · title —
    each row descends to that session's FEED (a past session's feed is simply
    one whose cursor never advances; no live/dead mode split)."""
    rows: List[Dict[str, Any]] = [
        {"text": f"sessions ({len(sessions)}) — enter opens a session's feed",
         "style": "dim"},
        {"text": ""}]
    ordered = sorted(sessions, key=lambda s: (s.get("started_at") or 0.0, s["key"]),
                     reverse=True)
    for s in ordered:
        bits = [s["key"]]
        if s.get("started_at"):
            bits.append(fmt_ts(s["started_at"]))
        title = f"  — {s['title']}" if s.get("title") else ""
        rows.append({"text": " · ".join(bits) + title,
                     "ref": s["key"], "goto": "feed"})
    if not sessions:
        rows.append({"text": "(no sessions registered)", "style": "dim"})
    return rows
