"""The feed markdown builders: ledger rows, cards, expansion, missing refs (no Qt)."""

from cjm_graph_workbench_qt.feed import build_feed_markdown


def _view(session="2026-08-14_12-00-00"):
    nid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    return {"window": {"session": session, "since": None, "cursor": 1786700000.0,
                       "total_ops": 3, "shown": 2},
            "ops": [{"ts": 1786690000.0, "verb": "decide", "actor": "user:workbench",
                     "session": session, "summary": "minted [a] stub",
                     "refs": [{"ref": nid[:8], "id": nid, "label": "Decision",
                               "title": "the [stub] title"}]},
                    {"ts": 1786700000.0, "verb": "link", "actor": "agent:session",
                     "session": session, "summary": "linked things",
                     "refs": [{"ref": "deadbeef", "missing": True}]}],
            "cards": [{"ref": nid[:8], "id": nid, "label": "Decision",
                       "title": "the [stub] title", "verbs": {"decide": 1, "link": 2},
                       "touches": 3, "first_ts": 1786690000.0,
                       "last_ts": 1786700000.0}],
            "missing": 1}


def test_ledger_zoom_rows_link_refs_and_keep_missing_visible():
    md = build_feed_markdown(_view(), zoom="ops")
    assert md.startswith("# feed — session 2026-08-14_12-00-00")
    assert "`decide` `user:workbench` — minted \\[a\\] stub" in md
    assert "[the \\[stub\\] title](graph://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee)" in md
    assert "~~deadbeef~~" in md          # missing ref struck, never dropped
    assert "ops 2/3" in md and "missing 1" in md


def test_cards_zoom_expands_bodies_per_card():
    nid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    md = build_feed_markdown(_view(), zoom="cards")
    assert f"[+ expand](expand:{nid})" in md
    assert "decide×1 · link×2 · touches 3" in md
    # expanded, non-code label: body renders plain
    md = build_feed_markdown(_view(), zoom="cards", expanded={nid},
                             bodies={nid: "the body prose"})
    assert f"[− collapse](expand:{nid})" in md and "the body prose" in md
    # code kinds fence
    view = _view()
    view["cards"][0]["label"] = "CodeSymbol"
    md = build_feed_markdown(view, zoom="cards", expanded={nid},
                             bodies={nid: "def f():\n    return 1\n"})
    assert "```python\ndef f():\n    return 1\n```" in md


def test_live_window_header_and_empty_states():
    empty = {"window": {"session": None, "since": None, "cursor": None,
                        "total_ops": 0, "shown": 0}, "ops": [], "cards": [],
             "missing": 0}
    md = build_feed_markdown(empty, zoom="ops")
    assert md.startswith("# feed — live window")
    assert "(no ops in this window yet)" in md
    assert "(no nodes touched in this window yet)" in build_feed_markdown(
        empty, zoom="cards")
