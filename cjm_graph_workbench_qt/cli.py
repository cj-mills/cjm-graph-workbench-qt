"""CLI entry for the Qt graph workbench (console script `cjm-graph-workbench-qt`)."""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .app import WorkbenchWindow
from .data import GraphSession


def build_parser() -> argparse.ArgumentParser:
    """The same argument surface as the Textual shell — db + journal paths stay
    EXPLICIT (guardrail 027bbe56: dev `.cjm/` locations are scaffolding, never
    baked-in defaults; wrappers bake them per graph)."""
    p = argparse.ArgumentParser(
        prog="cjm-graph-workbench-qt",
        description="Qt workbench over a cjm context graph (slab-1 pilot): portfolio "
                    "front door -> per-anchor pin trees -> node-in-context markdown.")
    p.add_argument("--graph-db-path", required=True,
                   help="Explicit sqlite db path (always explicit — no default repoint)")
    p.add_argument("--journal-path", default=None,
                   help="The graph's writes journal (last-touch column + metadata traces)")
    p.add_argument("--source-journal-path", default=None,
                   help="The graph's source journal (code touches live there)")
    p.add_argument("--manifests-dir", default=None,
                   help="Capability manifests dir (default: the projection lib's)")
    p.add_argument("--anchor", default=None,
                   help="Open directly at this anchor's lead (slug or id)")
    return p


def main() -> int:
    """Open the graph session, run the window; teardown is unconditional."""
    args = build_parser().parse_args()
    session = GraphSession(args.graph_db_path, manifests_dir=args.manifests_dir,
                           journal_paths=[p for p in (args.journal_path,
                                                      args.source_journal_path) if p])
    session.start()
    app = QApplication(sys.argv[:1])
    window = WorkbenchWindow(session, anchor=args.anchor)
    window.show()
    try:
        return app.exec()
    finally:
        session.close()


if __name__ == "__main__":  # runtime-order: must trail every def (python -m executes in slot order)
    sys.exit(main())
