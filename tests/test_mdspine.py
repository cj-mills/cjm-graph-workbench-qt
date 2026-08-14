"""The node markdown builder: head matter, fencing, links, fallbacks (no Qt, no graph)."""

from cjm_graph_workbench_qt.mdspine import build_node_markdown, link_text

A = "11111111-2222-3333-4444-555555555555"
B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _detail(label="Decision", body_neighbours=True):
    nb = ([{"relation": "REFERENCES", "direction": "out",
            "node": {"id": B, "title": "a [bracketed] title", "label": "Note"}},
           {"relation": "HAS_SECTION", "direction": "out",
            "node": {"id": A, "title": "sec", "label": "Section"}}]
          if body_neighbours else [])
    return {"node": {"id": A, "title": "the node", "label": label},
            "properties": {"statement": "the statement"},
            "facts": {"task_state": "open"},
            "journal": {"first_ts": 1786600000.0, "last_ts": 1786650000.0,
                        "sessions": ["s1", "s2"]},
            "neighbours": nb}


def test_head_matter_facts_and_meta():
    md = build_node_markdown(_detail(), "the body")
    assert md.startswith("# the node")
    assert "`Decision` · `" + A + "`" in md
    assert "**task_state = open**" in md
    assert "sessions s1, s2" in md


def test_neighbour_links_and_toc_relations_lead_overview():
    md = build_node_markdown(_detail(), "the body")
    assert f"[a \\[bracketed\\] title](graph://{B})" in md
    # counts-first overview: HAS_SECTION (a TOC relation) leads REFERENCES
    assert md.index("HAS_SECTION (1)") < md.index("REFERENCES (1)")
    # ...while the full groups keep TOC relations LAST (they must not bury cross-links)
    assert md.index("**REFERENCES**") < md.index("**HAS_SECTION**")


def test_code_kinds_fence_notes_render():
    md = build_node_markdown(_detail(label="CodeSymbol"), "def f():\n    return 1\n")
    assert "```python\ndef f():\n    return 1\n```" in md
    assert "```" not in build_node_markdown(_detail(), "## a heading")


def test_statement_stands_in_for_missing_body():
    md = build_node_markdown(_detail(), None)
    assert "the statement" in md


def test_link_text_escapes_brackets():
    assert link_text("[x] y") == "\\[x\\] y"


def test_frontmatter_fenced_not_headed():
    md = build_node_markdown(_detail(), "---\nname: x\ntype: t\n---\n\nthe prose")
    assert "```yaml\nname: x\ntype: t\n```" in md
    assert "the prose" in md


def test_overview_entries_are_jump_links():
    md = build_node_markdown(_detail(), "the body")
    assert "[HAS_SECTION (1)](jump:HAS_SECTION)" in md
    assert "[REFERENCES (1)](jump:REFERENCES)" in md


def test_raw_inline_html_in_prose_cannot_swallow_the_document():
    # A statement/body containing a literal `<id>` must not open an inline-HTML
    # element (QTextDocument's parser ate the neighbours section — drive find
    # 2026-08-14): the `<` is neutralized in prose AND in link/summary text.
    md = build_node_markdown(_detail(), "toggle via expand:<id> links, then more")
    assert "expand:&lt;id> links" in md
    assert "**REFERENCES**" in md and "**HAS_SECTION**" in md
    detail = _detail()
    detail["neighbours"][0]["node"]["title"] = "uses Dict<str> maps"
    md = build_node_markdown(detail, None)
    assert "Dict&lt;str>" in md
