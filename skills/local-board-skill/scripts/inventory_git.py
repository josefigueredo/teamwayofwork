#!/usr/bin/env python3
"""Collect reproducible Git evidence for board traceability without mutations."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IGNORED_DIRECTORIES = {".git", "node_modules", "vendor", "dist", "build", ".terraform"}


def run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def discover_repositories(workspace: Path) -> list[Path]:
    """Find Git worktrees while pruning generated directories during traversal."""
    repositories: set[Path] = set()
    for root, dirs, _files in os.walk(workspace):
        has_git_dir = ".git" in dirs or ".git" in _files
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRECTORIES]
        if not has_git_dir:
            continue
        repository = Path(root)
        try:
            run_git(repository, "rev-parse", "--is-inside-work-tree")
        except subprocess.CalledProcessError:
            continue
        repositories.add(repository)
    return sorted(repositories)


def repository_inventory(workspace: Path, repository: Path, since: str | None) -> dict[str, Any]:
    relative = repository.relative_to(workspace).as_posix()
    remote_lines = run_git(repository, "remote", "-v").splitlines()
    remotes: dict[str, str] = {}
    for line in remote_lines:
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(fetch)":
            remotes[parts[0]] = parts[1]

    log_args = [
        "log",
        "--reverse",
        "--date=iso-strict",
        "--format=%H%x1f%cI%x1f%an%x1f%ae%x1f%P%x1f%s",
        "--name-only",
    ]
    if since:
        log_args.append(f"--since={since}")
    raw_log = run_git(repository, *log_args)
    commits: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in raw_log.splitlines():
        if "\x1f" in line:
            if current:
                commits.append(current)
            commit_hash, committed_at, author, email, parents, subject = line.split("\x1f", 5)
            current = {
                "id": f"commit:{relative}:{commit_hash}",
                "hash": commit_hash,
                "committed_at": committed_at,
                "author": author,
                "author_email": email,
                "parents": [parent for parent in parents.split() if parent],
                "subject": subject,
                "paths": [],
            }
        elif current and line:
            current["paths"].append(line)
    if current:
        commits.append(current)

    return {
        "id": f"repository:{relative}",
        "path": relative,
        "head": run_git(repository, "rev-parse", "HEAD").strip(),
        "branch": run_git(repository, "branch", "--show-current").strip(),
        "status": run_git(repository, "status", "--short").splitlines(),
        "remotes": remotes,
        "commits": commits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Git repositories for board traceability")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace containing board/ and Git repositories.",
    )
    parser.add_argument("--since", help="Git-compatible inclusive timestamp for commits.")
    parser.add_argument(
        "--board-dir",
        type=Path,
        default=Path.cwd() / "board",
        help="Board instance used only to resolve the generated-cache directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Generated cache path; it is not the relationship source of truth.",
    )
    args = parser.parse_args()
    from board_config import load_board_config

    workspace = args.workspace.resolve()
    output = args.output or load_board_config(args.board_dir).sync_dir / "git-inventory.json"
    repositories = [repository_inventory(workspace, repo, args.since) for repo in discover_repositories(workspace)]
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "since": args.since,
        "repositories": repositories,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    commit_count = sum(len(repository["commits"]) for repository in repositories)
    print(f"Wrote {output}: repositories={len(repositories)} commits={commit_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or str(exc), file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
