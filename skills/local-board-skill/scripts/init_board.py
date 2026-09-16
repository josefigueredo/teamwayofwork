#!/usr/bin/env python3
"""Create a portable board instance with its profile, sync data directory and local env template."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from relations import empty_document, save_document


METADATA_TEMPLATES = {
    "convenciones.md": "# Board Conventions\n\nDocument the entity hierarchy, frontmatter contract, statuses, and naming rules for this board.\n",
    "autores.md": "# Authors - Mapping\n\n| Key | Remote account ID | Git aliases |\n| --- | --- | --- |\n",
    "inventario-commits.md": "# Commit Inventory\n\nGenerated from `sync/git-inventory.json`. Run the skill inventory and render commands to refresh it.\n",
    "mapeo-capacidades.md": "# Capability Mapping\n\nDocument the product rationale used to group evidence into board assets.\n",
    "spec-ticket-traceability.md": "# Spec and Ticket Traceability\n\nDocument traceability decisions that need human context beyond the relationship graph.\n",
}

TRACKER_CONFIG_TEMPLATE = """{
    \"type_map\": {},
    \"status_map\": {},
    \"parent_strategy\": {},
    \"aliases\": {}
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a local board instance")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--name", required=True, help="Human-readable board name")
    parser.add_argument("--entity-glob", default="*.md")
    parser.add_argument("--entity-id-prefix", default="")
    parser.add_argument("--jira-project-key", required=True)
    parser.add_argument("--jira-label", required=True)
    parser.add_argument("--remote-link-namespace", default="local-board")
    args = parser.parse_args()
    board_dir = args.board_dir.resolve()
    index_file = board_dir / "Board.md"
    if index_file.exists():
        raise SystemExit(f"ERROR: ya existe el índice principal: {index_file}")
    sync_dir = board_dir / "sync"
    metadata_dir = board_dir / "_meta"
    sync_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        "---\n"
        f'board_name: "{args.name}"\n'
        f'entity_glob: "{args.entity_glob}"\n'
        f'entity_id_prefix: "{args.entity_id_prefix}"\n'
        'sync_dir: "sync"\n'
        'relations_file: "sync/relations.json"\n'
        f'jira_project_key: "{args.jira_project_key}"\n'
        f'jira_label: "{args.jira_label}"\n'
        f'remote_link_namespace: "{args.remote_link_namespace}"\n'
        "---\n\n"
        f"# {args.name}\n\n"
        "Board local inicializado. Definí el contrato de entidades antes de crear assets.\n",
        encoding="utf-8",
    )
    save_document(sync_dir / "relations.json", empty_document())
    (sync_dir / "state.json").write_text('{\n  "entities": {},\n  "last_run": null\n}\n', encoding="utf-8")
    (sync_dir / "jira-config.json").write_text(TRACKER_CONFIG_TEMPLATE, encoding="utf-8")
    (sync_dir / ".gitignore").write_text(".env\n__pycache__/\n*.pyc\n", encoding="utf-8")
    template = Path(__file__).with_name(".env.example")
    shutil.copyfile(template, sync_dir / ".env")
    for name, content in METADATA_TEMPLATES.items():
        (metadata_dir / name).write_text(content, encoding="utf-8")
    print(f"Initialized {board_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
