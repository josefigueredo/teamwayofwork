#!/usr/bin/env python3
"""Attach verified web URLs to commit nodes using repository remotes from an inventory."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from board_config import load_board_config
from relations import load_document, save_document


def _strip_git_suffix(path: str) -> str:
    return path[:-4] if path.endswith(".git") else path


def web_base(remote: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"git@([^:]+):(.+)", remote)
    if match:
        host = match.group(1)
        return f"https://{host}/{_strip_git_suffix(match.group(2))}", host
    match = re.fullmatch(r"https?://([^/]+)/(.+)", remote)
    if match:
        host = match.group(1)
        return f"https://{host}/{_strip_git_suffix(match.group(2))}", host
    return None


def commit_url(base: str, host: str, commit_hash: str) -> str:
    normalized_host = host.lower()
    if "bitbucket" in normalized_host:
        return f"{base}/commits/{commit_hash}"
    if "gitlab" in normalized_host:
        return f"{base}/-/commit/{commit_hash}"
    return f"{base}/commit/{commit_hash}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich graph commit nodes with URLs from verified Git remotes")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    config = load_board_config(args.board_dir)
    remotes = {
        repository["path"]: web_base(repository.get("remotes", {}).get("origin", ""))
        for repository in json.loads(args.inventory.read_text(encoding="utf-8")).get("repositories", [])
    }
    document = load_document(config.relations_file)
    updated = 0
    for node in document["commits"]:
        remote_info = remotes.get(node.get("repository", ""))
        if remote_info and node.get("hash"):
            base, host = remote_info
            node["url"] = commit_url(base, host, node["hash"])
            updated += 1
    save_document(config.relations_file, document)
    print(f"Enriched commit URLs={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
