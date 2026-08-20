"""The workbench spine, pure half: view dicts -> row lists (paint-path strings
verify by pilot probe, per the standing TUI craft)."""

from cjm_graph_workbench_qt.spine import (build_lead_rows, build_node_rows,
                                           build_portfolio_rows, fmt_ts)


def test_portfolio_rows_order_and_descend_refs():
    view = {"counts": {"ready": 2, "blocked": 0, "done": 1, "closable": 0},
            "anchors": [
                {"id": "p" * 36, "role": "program", "slug": "prog-a", "title": "A",
                 "lock": {"id": "l" * 36, "lead": "the lead"}, "pins": 1,
                 "vitals": {"ready": 1, "blocked": 0, "closable": 0, "findings": 0},
                 "last_touch": None},
                {"id": "q" * 36, "role": "portfolio", "slug": "portfolio", "title": "P",
                 "lock": None, "pins": 6,
                 "vitals": {"ready": 0, "blocked": 0, "closable": 0, "findings": 0},
                 "last_touch": None}],
            "links": [{"source": "q" * 36, "target": "p" * 36, "relation": "REFERENCES"}]}
    rows = build_portfolio_rows(view)
    actionable = [r for r in rows if r.get("ref")]
    # Portfolio sorts first; anchor rows descend to LEAD; a lockless anchor is loud.
    assert [r["ref"] for r in actionable] == ["q" * 36, "p" * 36]
    assert all(r["goto"] == "lead" for r in actionable)
    assert any("⚠ NO LOCK" in r["text"] for r in rows)
    assert any("portfolio —REFERENCES→ prog-a" in r["text"] for r in rows)


def test_lead_rows_lock_pins_registers():
    view = {"anchor": {"id": "a" * 36, "role": "program", "slug": "prog-a", "title": "A"},
            "lock": {"id": "l" * 36, "body": "line one\nline two"},
            "pins": [{"role": "design", "id": "d" * 36, "gloss": "spec", "title": "DEC"},
                     {"role": "rule", "id": "e" * 36, "gloss": "gone", "missing": True}],
            "registers": [{"id": "r" * 36, "slug": "model-register", "title": "Models",
                           "members": [{"id": "m" * 36, "title": "v1.6",
                                        "status": "candidate"}]}]}
    rows = build_lead_rows(view)
    assert rows[0]["ref"] == "l" * 36 and rows[0]["goto"] == "node"  # lock row opens the note
    assert any(r.get("text") == "line two" for r in rows)            # body lines verbatim
    assert any(r.get("ref") == "d" * 36 for r in rows)               # pin descends
    assert any("⚠ MISSING pin target" in r["text"] for r in rows)    # never dropped
    member = [r for r in rows if r.get("ref") == "m" * 36]
    assert member and "(candidate)" in member[0]["text"]             # status rides the row


def test_node_rows_metadata_roster_and_neighbours():
    detail = {"node": {"id": "n" * 36, "label": "Decision", "title": "the DEC"},
              "properties": {"statement": "the statement body"},
              "facts": {"task_state": "open", "priority": "early"},
              "journal": {"first_ts": 1786400000.0, "last_ts": 1786400001.0,
                          "sessions": ["2026-01-01_00-00-00"], "actors": ["agent:session"]},
              "neighbours": [
                  {"node": {"id": "b" * 36, "label": "Note", "title": "a note"},
                   "relation": "REFERENCES", "direction": "out"},
                  {"node": {"id": "c" * 36, "label": "Check", "title": "a check"},
                   "relation": "CHECKS", "direction": "in"},
                  {"node": {"id": "s" * 36, "label": "Section", "title": "a section"},
                   "relation": "HAS_SECTION", "direction": "out"}]}
    rows = build_node_rows(detail, None)
    text = "\n".join(r["text"] for r in rows)
    assert "task_state = open" in text and "priority = early" in text
    assert "sessions 2026-01-01_00-00-00" in text
    assert "the statement body" in text        # property stands in for a missing body
    nb = [r for r in rows if r.get("ref")]
    # neighbours group by relation, structural self-content (HAS_SECTION) LAST
    assert [r["ref"] for r in nb] == ["c" * 36, "b" * 36, "s" * 36]
    text_all = [r["text"] for r in rows]
    assert "  CHECKS (1)" in text_all and "  REFERENCES (1)" in text_all  # typed headers
    assert text_all.index("  HAS_SECTION (1)") > text_all.index("  REFERENCES (1)")


def test_fmt_ts_handles_junk():
    assert fmt_ts(None) == "" and fmt_ts("nope") == ""
    assert fmt_ts(1786400000.0)  # some local wall-clock string


def test_node_rows_overview_counts_first_and_jump():
    detail = {"node": {"id": "n" * 36, "label": "Note", "title": "a note"},
              "properties": {},
              "neighbours": [
                  {"node": {"id": "b" * 36, "label": "Note", "title": "a ref"},
                   "relation": "REFERENCES", "direction": "out"},
                  {"node": {"id": "s" * 36, "label": "Section", "title": "sec"},
                   "relation": "HAS_SECTION", "direction": "out"}]}
    rows = build_node_rows(detail, "body text")
    texts = [r["text"] for r in rows]
    # Overview: one row per relation, structural TOC relations FIRST, all
    # BEFORE the body; the full groups below the body keep structural LAST.
    assert texts.index("HAS_SECTION (1)") < texts.index("REFERENCES (1)")
    assert texts.index("REFERENCES (1)") < texts.index("body text")
    assert texts.index("  REFERENCES (1)") < texts.index("  HAS_SECTION (1)")
    # Each overview row carries an in-page jump to its group header.
    for rel in ("HAS_SECTION", "REFERENCES"):
        over = rows[texts.index(f"{rel} (1)")]
        assert rows[over["jump"]]["text"] == f"  {rel} (1)"
        assert not over.get("ref")  # jump rows never descend


def test_node_rows_metadata_reflow_at_narrow_width():
    detail = {"node": {"id": "n" * 36, "label": "Decision", "title": "the DEC"},
              "properties": {"statement": "s"},
              "journal": {"first_ts": 1786400000.0, "last_ts": 1786400001.0,
                          "sessions": ["2026-01-01_00-00-00", "2026-01-02_00-00-00"],
                          "actors": ["agent:session", "reconcile:absorb"]}}
    wide = build_node_rows(detail, None, width=500)
    narrow = build_node_rows(detail, None, width=40)
    unbounded = build_node_rows(detail, None)
    inline = [r["text"] for r in wide if r["text"].startswith("created ")]
    # Wide (and width-less) keep the inline roster; narrow stacks one bit per
    # row instead of truncating into h-scroll (drive round 2).
    assert inline and " · updated " in inline[0]
    assert [r["text"] for r in unbounded if r["text"].startswith("created ")] == inline
    ntexts = [r["text"] for r in narrow]
    assert inline[0] not in ntexts
    assert any(t.startswith("created ") for t in ntexts)
    assert any(t.startswith("updated ") for t in ntexts)
    assert any(t.startswith("sessions ") for t in ntexts)
    assert any(t.startswith("actors ") for t in ntexts)
