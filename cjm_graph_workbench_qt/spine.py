"""Pure spine for the workbench: lens-layer view dicts -> flat row lists.

Toolkit-neutral by construction — no Qt imports (spine absorption 12f342f1,
rider 2: core-shaped seams so a future non-Qt front end lifts it whole).
Absorbed from the Textual workbench as a frozen copy-split.

A row is a plain dict: `text` (one line), optional `style` (a semantic style name
the app maps and applies to the whole line — spans-only discipline lives in the paint
path), optional `ref` + `goto` ("lead" | "node") making the row ACTIONABLE
(enter descends to it). Pure functions only — the app owns no logic beyond
painting windows of these rows (the render-projection posture, DEC 8b9804c2);
pytest covers THIS module, paint verifies by pilot probe (family craft)."""

from datetime import datetime
from typing import Any, Dict, List, Optional


def fmt_ts(ts: Any) -> str:
    """Unix seconds -> local wall-clock (minutes), or '' — humans read wall-clock."""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def build_portfolio_rows(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The front door as rows: counts header, one block per anchor (portfolio
    first), anchor-to-anchor links as a footer. Anchor rows descend to `lead`."""
    c = view.get("counts", {})
    unfiled = f" · unfiled {c['unfiled']}" if "unfiled" in c else ""
    rows: List[Dict[str, Any]] = [
        {"text": f"ready {c.get('ready', 0)} · blocked {c.get('blocked', 0)} · "
                 f"done {c.get('done', 0)} · closable {c.get('closable', 0)}{unfiled}",
         "style": "dim"},
        {"text": ""}]
    anchors = sorted(view.get("anchors", []), key=lambda a: a.get("role") != "portfolio")
    slugs = {a["id"]: a.get("slug", a["id"][:8]) for a in anchors}
    for a in anchors:
        v = a.get("vitals", {})
        bits = [f"ready {v.get('ready', 0)}", f"blocked {v.get('blocked', 0)}"]
        if v.get("closable"):
            bits.append(f"closable {v['closable']}")
        bits.append(f"findings {v.get('findings', 0)}")
        bits.append(f"pins {a.get('pins', 0)}")
        if a.get("last_touch"):
            bits.append(fmt_ts(a["last_touch"]))
        rows.append({"text": f"{a.get('slug')}  ·  " + " · ".join(bits),
                     "ref": a["id"], "goto": "lead"})
        lock = a.get("lock")
        if lock is None:
            rows.append({"text": "   ⚠ NO LOCK asserted", "style": "bold red"})
        elif lock.get("error"):
            rows.append({"text": f"   ⚠ lock unreadable: {lock['error']}", "style": "bold red"})
        else:
            rows.append({"text": "   " + str(lock.get("lead", ""))})
        rows.append({"text": ""})
    links = view.get("links", [])
    if links:
        rows.append({"text": "links:", "style": "dim"})
        for link in links:
            rows.append({"text": f"  {slugs.get(link['source'], link['source'][:8])} "
                                 f"—{link['relation']}→ "
                                 f"{slugs.get(link['target'], link['target'][:8])}",
                         "style": "dim"})
    return rows


def build_lead_rows(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One anchor's pin tree as rows: lock (row descends to the note, body lines
    follow), pins with glosses, registers expanded. Missing targets stay LOUD."""
    rows: List[Dict[str, Any]] = []
    lock = view.get("lock")
    if lock is None:
        rows.append({"text": "(no lock note asserted for this anchor)", "style": "yellow"})
    elif lock.get("error"):
        rows.append({"text": f"⚠ lock {lock['id'][:8]} unreadable: {lock['error']}",
                     "style": "bold red"})
    else:
        rows.append({"text": f"LOCK {lock['id'][:8]}", "style": "bold",
                     "ref": lock["id"], "goto": "node"})
        rows.extend({"text": line} for line in str(lock.get("body", "")).splitlines())
    rows.append({"text": ""})
    for p in view.get("pins", []):
        if p.get("missing"):
            rows.append({"text": f"[{p['role']}] ⚠ MISSING pin target {p['id'][:8]} "
                                 f"— {p.get('gloss', '')}", "style": "bold red"})
            continue
        rows.append({"text": f"[{p['role']}] {p.get('title', '')}",
                     "ref": p["id"], "goto": "node"})
        if p.get("gloss"):
            rows.append({"text": "   " + p["gloss"], "style": "dim"})
    for reg in view.get("registers", []):
        if reg.get("missing"):
            rows.append({"text": f"[register] ⚠ MISSING hub {reg['id'][:8]}",
                         "style": "bold red"})
            continue
        rows.append({"text": f"[register] {reg.get('title', '')}",
                     "ref": reg["id"], "goto": "node"})
        for m in reg.get("members", []):
            status = f"  ({m['status']})" if m.get("status") else ""
            rows.append({"text": f"   {m.get('title', '')}{status}",
                         "ref": m.get("id"), "goto": "node", "style": "dim"})
    return rows


def build_node_rows(detail: Dict[str, Any], body: Optional[str],
                    width: Optional[int] = None) -> List[Dict[str, Any]]:
    """Node-in-context as rows (DEC 47501c78): title, kind/id, ACTIVE facts,
    journal trace (the metadata roster — re-flows to one row per bit when the
    inline line exceeds `width`, so narrow windows never truncate it), a
    counts-first neighbour OVERVIEW (one row per relation, structural TOC
    relations first; enter JUMPS to the matching group below), verbatim body,
    then the full typed neighbour groups — each one keystroke away. `body` may
    be None (not every kind has a deliverable body); the statement/value
    property stands in when present."""
    n = detail.get("node") or {}
    props = detail.get("properties") or {}
    rows: List[Dict[str, Any]] = [
        {"text": str(n.get("title", "?")), "style": "bold"},
        {"text": f"{n.get('label', '?')} · {n.get('id', '')}", "style": "dim"}]
    facts = detail.get("facts") or {}
    if facts:
        rows.append({"text": " · ".join(f"{k} = {v}" for k, v in sorted(facts.items())),
                     "style": "cyan"})
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
        meta = " · ".join(bits)
        # Re-flow, never truncate: the roster stacks one bit per row when the
        # inline line cannot fit (h-scroll is the escape hatch, not the
        # reading path — drive round 2). The 3-char paint prefix is reserved.
        if width is not None and len(meta) > max(0, width - 3):
            rows.extend({"text": b, "style": "dim"} for b in bits)
        else:
            rows.append({"text": meta, "style": "dim"})
    nb = sorted(detail.get("neighbours") or [],
                key=lambda e: ((e.get("relation") or "") in ("HAS_SECTION", "CONTAINS"),
                               e.get("relation") or "", e.get("direction") or ""))
    # Counts-first OVERVIEW (drive round 2): one row per relation at the top —
    # HAS_SECTION/CONTAINS lead here (a node's own sections are its table of
    # contents) while the full groups below keep them LAST; enter on an
    # overview row jumps the cursor to the matching group header.
    if nb:
        rel_order: List[str] = []
        for e in nb:
            rel = str(e.get("relation", "?"))
            if rel not in rel_order:
                rel_order.append(rel)
        overview = sorted(rel_order,
                          key=lambda r: (r not in ("HAS_SECTION", "CONTAINS"), r))
        rows.append({"text": ""})
        for rel in overview:
            count = sum(1 for e in nb if str(e.get("relation", "?")) == rel)
            rows.append({"text": f"{rel} ({count})", "style": "dim", "jump_rel": rel})
    text = body if body else str(props.get("statement") or props.get("value") or "")
    if text:
        rows.append({"text": ""})
        rows.extend({"text": line} for line in text.splitlines())
    # Typed neighbour GROUPS (DEC 47501c78): one dim header per relation, rows
    # under it. Structural self-content relations sort LAST — a note's own
    # sections were just read in the body above, they must not bury the real
    # cross-links (the graph-authoring-craft field verdict, 2026-08-11).
    rows.append({"text": ""})
    rows.append({"text": f"neighbours ({len(nb)}):", "style": "bold"})
    seen_rel = None
    for e in nb:
        node = e.get("node") or {}
        rel = str(e.get("relation", "?"))
        if rel != seen_rel:
            count = sum(1 for x in nb if str(x.get("relation", "?")) == rel)
            rows.append({"text": f"  {rel} ({count})", "style": "dim bold", "group": rel})
            seen_rel = rel
        arrow = "→" if e.get("direction") == "out" else "←"
        rows.append({"text": f"  {arrow} {node.get('title', '?')}  ({node.get('label', '?')})",
                     "ref": node.get("id"), "goto": "node"})
    # Resolve overview rows to their group-header row indices (in-page jump).
    group_at = {r["group"]: i for i, r in enumerate(rows) if "group" in r}
    for r in rows:
        if "jump_rel" in r:
            r["jump"] = group_at.get(r.pop("jump_rel"))
    return rows
