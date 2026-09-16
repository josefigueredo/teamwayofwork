#!/usr/bin/env python3
"""Render a human-readable commit inventory from the generated sync JSON."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from board_config import load_board_config


def short_date(timestamp: str) -> str:
    return timestamp[:10] if timestamp else "unknown"


def markdown(document: dict[str, Any], board_name: str) -> str:
    generated_at = datetime.now(timezone.utc).date().isoformat()
    since = document.get("since") or "all history"
    lines = [
        f"# Commit Inventory - {board_name}",
        "",
        f"Period: `{since}` onward. Generated: `{generated_at}`.",
        "",
        "Generated from `sync/git-inventory.json`. Refresh using the skill scripts; "
        "do not edit commit rows manually.",
    ]
    for repository in document.get("repositories", []):
        commits = repository.get("commits", [])
        lines.extend(["", f"## {repository.get('path', 'unknown')}", "", f"- Commits: **{len(commits)}**"])
        if not commits:
            continue
        lines.extend(
            [
                f"- First commit: `{short_date(commits[0].get('committed_at', ''))}`",
                f"- Last commit: `{short_date(commits[-1].get('committed_at', ''))}`",
                "",
                "### Authors",
                "",
                "| Author | Commits |",
                "| --- | ---: |",
            ]
        )
        authors = Counter(commit.get("author", "unknown") for commit in commits)
        lines.extend(f"| {author} | {count} |" for author, count in authors.most_common())
        lines.extend(["", "### Commits", "", "| Date | Hash | Author | Subject |", "| --- | --- | --- | --- |"])
        for commit in commits:
            subject = str(commit.get("subject", "")).replace("|", "\\|")
            lines.append(
                f"| {short_date(commit.get('committed_at', ''))} | `{str(commit.get('hash', ''))[:12]}` | "
                f"{commit.get('author', 'unknown')} | {subject} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Markdown commit inventory from sync JSON")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    config = load_board_config(args.board_dir)
    input_path = args.input or config.sync_dir / "git-inventory.json"
    output_path = args.output or config.board_dir / "_meta" / "inventario-commits.md"
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        parser.error(f"no existe el inventario JSON: {input_path}")
    except json.JSONDecodeError as exc:
        parser.error(f"inventario JSON inválido: {exc}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown(document, config.name), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
