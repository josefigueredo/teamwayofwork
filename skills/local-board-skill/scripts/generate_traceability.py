#!/usr/bin/env python3
"""Generate the human-readable spec-to-ticket report from relations.json."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import os

from board_config import load_board_config
from relations import load_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a spec-to-ticket traceability report")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--relations", type=Path, default=None)
    parser.add_argument(
        "--output", type=Path, default=None
    )
    args = parser.parse_args()
    config = load_board_config(args.board_dir)
    relations_path = args.relations or config.relations_file
    output_path = args.output or config.board_dir / "_meta" / "spec-ticket-traceability.md"
    document = load_document(relations_path)
    assets = {node["id"]: node for node in document["assets"]}
    evidence_by_asset: dict[str, list[str]] = defaultdict(list)
    specs_by_asset: dict[str, list[str]] = defaultdict(list)
    for relation in document["relations"]:
        if relation["type"] == "implements" and relation["from"].startswith("spec:"):
            specs_by_asset[relation["to"]].append(relation["from"])
        if relation["type"] == "evidence_for" and relation["to"].startswith("asset:"):
            evidence_by_asset[relation["to"]].append(relation["from"])

    lines = [
        "# Trazabilidad de specs a tickets",
        "",
        f"Generado desde [`{relations_path.name}`]({os.path.relpath(relations_path, output_path.parent)}). No editar manualmente.",
        "",
        "| Spec | Títulos / estado | Board assets | Jira | Evidencia Git |",
        "| --- | --- | --- | --- | --- |",
    ]
    for spec in sorted(document["specs"], key=lambda item: item["id"]):
        spec_id = spec["id"]
        linked_assets = sorted(
            relation["to"]
            for relation in document["relations"]
            if relation["type"] == "implements" and relation["from"] == spec_id
        )
        asset_labels = [asset.removeprefix("asset:") for asset in linked_assets]
        jira_keys = [assets[asset].get("jira_key", "-") for asset in linked_assets if asset in assets]
        evidence = [item for asset in linked_assets for item in evidence_by_asset[asset]]
        title = str(spec.get("title", ""))
        status = str(spec.get("status", ""))
        lines.append(
            f"| `{spec_id.removeprefix('spec:')}` | {title} ({status}) | "
            f"{', '.join(asset_labels) or '-'} | {', '.join(jira_keys) or '-'} | "
            f"{len(evidence)} relación(es) |"
        )

    lines.extend(["", "## Cobertura", ""])
    lines.append(f"- Specs: {len(document['specs'])}")
    lines.append(f"- Assets: {len(document['assets'])}")
    lines.append(f"- Commits: {len(document['commits'])}")
    lines.append(f"- Relaciones: {len(document['relations'])}")
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
