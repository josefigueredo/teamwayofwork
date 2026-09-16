#!/usr/bin/env python3
"""Refresh deterministic asset and specification nodes in a board graph."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from board_config import BoardConfig, load_board_config
from relations import load_document, save_document


def decode_scalar(value: str) -> str:
    """Decode JSON-escaped quoted string; fall back to strip-quotes."""
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, str) else str(parsed)
    except json.JSONDecodeError:
        return value[1:-1]


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if line and line[0] not in " \t" and ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = decode_scalar(value.strip())
    return data


def list_value(value: str) -> list[str]:
    if not value.startswith("[") or not value.endswith("]"):
        return []
    return [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]


def asset_nodes(config: BoardConfig) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    nodes: list[dict[str, Any]] = []
    spec_refs: dict[str, list[str]] = {}
    for path in sorted(config.board_dir.rglob(config.entity_glob)):
        if config.sync_dir in path.parents or config.board_dir / "_meta" in path.parents:
            continue
        data = frontmatter(path)
        asset_id = data.get("id")
        if not asset_id:
            continue
        nodes.append(
            {
                "id": f"asset:{asset_id}",
                "path": path.relative_to(config.board_dir).as_posix(),
                "type": data.get("type", ""),
                "summary": data.get("summary", ""),
                "jira_key": data.get("jira_key", ""),
            }
        )
        spec_refs[asset_id] = list_value(data.get("spec_refs", "[]"))
    return nodes, spec_refs


def specification_nodes(workspace: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    for path in sorted(workspace.rglob("spec.md")):
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        parent = path.parent
        relative = parent.relative_to(workspace).as_posix()
        match = re.match(r"specs/(\d+)-", relative)
        if match:
            node_id = f"spec:{match.group(1)}"
            aliases[match.group(1)] = node_id
        else:
            node_id = f"spec:{relative}"
        text = path.read_text(encoding="utf-8")
        title = next((line.removeprefix("# ").strip() for line in text.splitlines() if line.startswith("# ")), parent.name)
        status = next((line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("**Status**:")), "unknown")
        nodes.append({"id": node_id, "path": relative, "title": title, "status": status})
    return nodes, aliases


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh a configured board asset and spec catalog")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--relations", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the relationship graph; defaults to the board profile.",
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()

    config = load_board_config(args.board_dir)
    if args.relations and args.output:
        parser.error("--relations y --output son excluyentes")
    relations_path = args.output or args.relations or config.relations_file
    document = load_document(relations_path)
    assets, asset_spec_refs = asset_nodes(config)
    specs, aliases = specification_nodes(args.workspace.resolve())
    document["assets"] = assets
    document["specs"] = specs
    generated = []
    for asset_id, spec_ids in asset_spec_refs.items():
        for spec_id in spec_ids:
            source = aliases.get(spec_id)
            if not source:
                raise ValueError(f"spec_ref no resuelto para {asset_id}: {spec_id}")
            generated.append(
                    {
                        "from": source,
                        "to": f"asset:{asset_id}",
                        "type": "implements",
                        "evidence": "spec_refs en frontmatter del board",
                        "confidence": "high",
                        "decision": "derivado automáticamente del board",
                    }
                )
    non_generated = [
        relation
        for relation in document["relations"]
        if relation.get("decision") != "derivado automáticamente del board"
    ]
    seen: set[tuple[str, str, str]] = set()
    document["relations"] = []
    for relation in [*non_generated, *generated]:
        key = (relation["from"], relation["to"], relation["type"])
        if key not in seen:
            document["relations"].append(relation)
            seen.add(key)
    save_document(relations_path, document)
    print(f"Refreshed assets={len(assets)} specs={len(specs)} relations={len(document['relations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
