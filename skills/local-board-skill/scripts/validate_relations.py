#!/usr/bin/env python3
"""Validate the board relationship graph without contacting Jira."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from board_config import load_board_config
from relations import RelationValidationError, load_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local board relationship graph")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument(
        "--relations",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    try:
        config = load_board_config(args.board_dir)
        document = load_document(args.relations or config.relations_file)
    except RelationValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "OK relations: "
        f"assets={len(document['assets'])} specs={len(document['specs'])} "
        f"commits={len(document['commits'])} relations={len(document['relations'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
