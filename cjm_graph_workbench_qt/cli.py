"""CLI entry for the Qt graph workbench (console script `cjm-graph-workbench-qt`).

Launch resolution is the shell's (ruling 2bae2cc1 (4), kit `launch`): the
workspace's launch record and the persisted in-app config outrank a CLI
flag, which outranks the default — and nothing is ever resolved from the
current directory (guardrail 027bbe56: dev `.cjm/` locations are
scaffolding, never baked-in defaults). A workspace is named by --workspace
or CJM_WORKSPACE; the graph db must come from SOME rung — the launch names
the three when none supplies it."""

import argparse
import sys

from cjm_substrate_qt_kit import launch
from cjm_substrate_qt_kit.theme import apply_theme
from PySide6.QtWidgets import QApplication

from .app import WorkbenchWindow
from .data import GraphSession

APP_ID = "cjm-graph-workbench-qt"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=APP_ID,
        description="Qt workbench over a cjm context graph: portfolio front door -> "
                    "per-anchor pin trees -> node-in-context markdown.")
    p.add_argument("--workspace", default=None,
                   help="Workspace root carrying cjm-workspace.yaml (else CJM_WORKSPACE); "
                        "its .cjm/launch/%s.json record outranks the flags below" % APP_ID)
    p.add_argument("--graph-db-path", default=None,
                   help="Explicit sqlite db path (never resolved from cwd)")
    p.add_argument("--journal-path", default=None,
                   help="The graph's writes journal (last-touch column + metadata traces)")
    p.add_argument("--source-journal-path", default=None,
                   help="The graph's source journal (code touches live there)")
    p.add_argument("--manifests-dir", default=None,
                   help="Capability manifests dir (default: the projection lib's)")
    p.add_argument("--anchor", default=None,
                   help="Open directly at this anchor's lead (slug or id)")
    p.add_argument("--theme", default=None, metavar="SYSTEM[:MODE]",
                   help="Design system and mode for this launch (e.g. netrunner:blue, "
                        "classical:auto); default: CJM_THEME, then the persisted choice")
    p.add_argument("--decorations", default=None, choices=("client", "system"),
                   help="The shell's frame (client, default) or the window manager's (system)")
    return p


def resolve(args) -> launch.LaunchConfig:
    """The precedence walk over the launch keys; the graph db is required
    from some rung."""
    cfg = launch.resolve(APP_ID, workspace=args.workspace,
                         cli={"graph_db_path": args.graph_db_path,
                              "journal_path": args.journal_path,
                              "source_journal_path": args.source_journal_path,
                              "manifests_dir": args.manifests_dir,
                              "anchor": args.anchor, "theme": args.theme,
                              "decorations": args.decorations},
                         defaults={"anchor": None, "theme": None, "decorations": None,
                                   "manifests_dir": None, "journal_path": None,
                                   "source_journal_path": None})
    return cfg


def main() -> int:
    """Resolve the launch, open the graph session, run the window; teardown is unconditional."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        cfg = resolve(args)
    except launch.LaunchError as e:
        parser.error(str(e))
    if not cfg.get("graph_db_path"):
        parser.error("no graph db: pass --graph-db-path, record it in the workspace's "
                     f".cjm/launch/{APP_ID}.json, or persist it in the in-app config")
    print(cfg.describe(), file=sys.stderr)
    session = GraphSession(cfg["graph_db_path"], manifests_dir=cfg.get("manifests_dir"),
                           journal_paths=[p for p in (cfg.get("journal_path"),
                                                      cfg.get("source_journal_path")) if p])
    session.start()
    app = QApplication(sys.argv[:1])
    system, _, mode = (cfg.get("theme") or "").partition(":")
    apply_theme(app, system or None, mode or None)
    window = WorkbenchWindow(session, anchor=cfg.get("anchor"), decorations=cfg.get("decorations"))
    window.show()
    try:
        return app.exec()
    finally:
        session.close()


if __name__ == "__main__":  # runtime-order: must trail every def (python -m executes in slot order)
    sys.exit(main())
