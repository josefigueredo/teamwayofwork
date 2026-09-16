#!/usr/bin/env python3
"""Resolve every commit in an inventory into board evidence or an explicit exception."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from board_config import load_board_config
from relations import load_document, save_document


def exception_reason(subject: str) -> str | None:
    text = subject.lower()
    if "bump version" in text or "changelog" in text:
        return "reviewed release metadata; no independent product outcome"
    if "sonar" in text or text.startswith(("deps:", "deps(", "chore(deps)")) or ".devtools" in text:
        return "reviewed CI, dependency, security, or formatting maintenance"
    if text.startswith(("merge:", "merge ")):
        return "reviewed integration commit; no independent product outcome"
    if "bump image tags" in text or (text.startswith("chore(sdlc): bump") and "without" not in text):
        return "reviewed deployment metadata; no independent product outcome"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve inventory commits into graph evidence or exclusions")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--map", action="append", default=[], metavar="HASH=ASSET_ID")
    parser.add_argument("--auto-exceptions", action="store_true", help="Allow heuristic exclusions for clearly non-product commits.")
    return parser.parse_args()


def parse_assignments(values: list[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for item in values:
        key, value = item.split("=", 1)
        assignments[key] = value
    return assignments


def reconcile_commit(document: dict[str, Any], repository: dict[str, Any], commit: dict[str, Any], assignments: dict[str, str], assets: set[str], evidence: set[tuple[str, str]], exceptions: set[str], nodes: dict[str, dict[str, Any]], *, auto_exceptions: bool) -> str | None:
    node_id = f"commit:{repository['path']}:{commit['hash']}"
    nodes[node_id] = {
        **nodes.get(node_id, {}),
        "id": node_id,
        "repository": repository["path"],
        "hash": commit["hash"],
        "committed_at": commit["committed_at"],
        "author": commit["author"],
        "subject": commit["subject"],
    }
    matched_assets = [asset for prefix, asset in assignments.items() if commit["hash"].startswith(prefix)]
    if len(matched_assets) > 1:
        raise ValueError(f"ambiguous mapping for {repository['path']}@{commit['hash'][:12]}: {matched_assets}")
    asset_id = matched_assets[0] if matched_assets else None
    if asset_id:
        target = f"asset:{asset_id}"
        if target not in assets:
            raise ValueError(f"unknown asset: {asset_id}")
        pair = (node_id, target)
        if pair not in evidence:
            document["relations"].append({"from": node_id, "to": target, "type": "evidence_for", "evidence": "reviewed inventory commit", "confidence": "high", "decision": "explicit post-sync commit classification"})
            evidence.add(pair)
        if node_id in exceptions:
            document["exceptions"] = [item for item in document["exceptions"] if not (isinstance(item, dict) and item.get("commit") == node_id)]
            exceptions.discard(node_id)
        return None
    if any(existing_from == node_id for existing_from, _ in evidence) or node_id in exceptions:
        return None
    if not auto_exceptions:
        return f"{repository['path']}@{commit['hash'][:12]} {commit['subject']}"
    reason = exception_reason(commit["subject"])
    if not reason:
        return f"{repository['path']}@{commit['hash'][:12]} {commit['subject']}"
    document["exceptions"].append({"type": "excluded_with_reason", "commit": node_id, "reason": reason})
    exceptions.add(node_id)
    return None


def reconcile(document: dict[str, Any], inventory: dict[str, Any], assignments: dict[str, str], assets: set[str], *, auto_exceptions: bool) -> list[str]:
    existing_evidence = {
        (relation["from"], relation["to"])
        for relation in document["relations"]
        if relation.get("type") == "evidence_for"
    }
    exceptions = {item.get("commit") for item in document["exceptions"] if isinstance(item, dict)}
    nodes = {node["id"]: node for node in document["commits"]}
    unresolved: list[str] = []
    for repository in inventory.get("repositories", []):
        for commit in repository.get("commits", []):
            unresolved_commit = reconcile_commit(
                document,
                repository,
                commit,
                assignments,
                assets,
                existing_evidence,
                exceptions,
                nodes,
                auto_exceptions=auto_exceptions,
            )
            if unresolved_commit:
                unresolved.append(unresolved_commit)
    document["commits"] = sorted(nodes.values(), key=lambda node: node["id"])
    return unresolved


def main() -> int:
    args = parse_args()
    config = load_board_config(args.board_dir)
    assignments = parse_assignments(args.map)
    document = load_document(config.relations_file)
    assets = {asset["id"] for asset in document["assets"]}
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    unresolved = reconcile(document, inventory, assignments, assets, auto_exceptions=args.auto_exceptions)
    if unresolved:
        raise RuntimeError("commits require a mapping or explicit policy: " + "; ".join(unresolved))
    save_document(config.relations_file, document)
    print(f"Reconciled commits={len(document['commits'])} exceptions={len(document['exceptions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
