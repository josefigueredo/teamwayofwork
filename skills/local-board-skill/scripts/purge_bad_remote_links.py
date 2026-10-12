#!/usr/bin/env python3
"""Delete Jira remote links whose URL still contains a .git segment.

Read-only by default: it prints the links it would delete. Pass --apply to delete them.
"""
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
    apply: bool = False,
) -> tuple[str, int, list[tuple[str, str]]]:
    """Return (key, scanned, bad links as (link id, url)); delete them only when apply is set."""
    client = JiraClient(base_url, email, token, throttle_seconds=throttle_seconds)
    bad: list[tuple[str, str]] = []
    scanned = 0
    for link in client.remote_links(key):
        scanned += 1
        url = str((link.get("object") or {}).get("url") or "")
        if not bad_url(url):
            continue
        if apply:
            client.delete_remote_link(key, str(link["id"]))
        bad.append((str(link["id"]), url))
    return key, scanned, bad


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge malformed .git remote links from Jira issues")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--throttle", type=float, default=None)
    parser.add_argument("--apply", action="store_true", help="delete the bad links; without it only the plan is printed")
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

    bad_by_issue: dict[str, list[tuple[str, str]]] = {}
    scanned_total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(purge_issue, key, base_url, email, token, throttle, args.apply) for key in keys]
        for future in as_completed(futures):
            key, scanned, bad = future.result()
            scanned_total += scanned
            if bad:
                bad_by_issue[key] = bad

    bad_total = sum(len(bad) for bad in bad_by_issue.values())
    verb = "deleted" if args.apply else "would delete"
    for key in sorted(bad_by_issue):
        for link_id, url in bad_by_issue[key]:
            print(f"{verb} {key} remote link {link_id}: {url}")
    print(f"Scanned {scanned_total} remote links across {len(keys)} issues; {verb} {bad_total} bad URLs")
    if not args.apply and bad_total:
        print("Dry run: nothing was changed. Re-run with --apply to delete these links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
