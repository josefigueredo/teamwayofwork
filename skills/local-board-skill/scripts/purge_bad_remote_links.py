#!/usr/bin/env python3
"""Delete Jira remote links whose URL still contains a .git segment."""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from board_config import load_board_config
from relations import load_document
from sync_board import load_settings, tracker_base_url
from sync_client import JiraClient


def bad_url(url: str) -> bool:
    return ".git/" in url or url.endswith(".git")


def purge_issue(
    key: str,
    base_url: str,
    email: str,
    token: str,
    throttle_seconds: float,
) -> tuple[str, int, int]:
    client = JiraClient(base_url, email, token, throttle_seconds=throttle_seconds)
    deleted = 0
    scanned = 0
    for link in client.remote_links(key):
        scanned += 1
        url = str((link.get("object") or {}).get("url") or "")
        if not bad_url(url):
            continue
        client.delete_remote_link(key, str(link["id"]))
        deleted += 1
    return key, scanned, deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge malformed .git remote links from Jira issues")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--throttle", type=float, default=None)
    args = parser.parse_args()

    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN", "")
    if not email or not token:
        print("ERROR: missing JIRA_EMAIL / JIRA_API_TOKEN", file=sys.stderr)
        return 1

    throttle = args.throttle if args.throttle is not None else float(os.environ.get("JIRA_WRITE_THROTTLE", "0.15"))
    settings = load_settings(args.board_dir)
    document = load_document(settings.relations_path)
    keys = sorted({asset.get("jira_key", "") for asset in document.get("assets", []) if asset.get("jira_key")})
    base_url = tracker_base_url()
    workers = max(1, min(args.workers, len(keys)))

    deleted_total = 0
    scanned_total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(purge_issue, key, base_url, email, token, throttle) for key in keys]
        for future in as_completed(futures):
            _, scanned, deleted = future.result()
            scanned_total += scanned
            deleted_total += deleted

    print(f"Scanned {scanned_total} remote links across {len(keys)} issues; deleted {deleted_total} bad URLs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
