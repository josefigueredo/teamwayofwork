#!/usr/bin/env python3
"""Load the generic board profile declared in its primary index Markdown file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoardConfig:
    board_dir: Path
    index_file: Path
    name: str
    entity_glob: str
    entity_id_prefix: str
    sync_dir: Path
    relations_file: Path
    jira_project_key: str
    jira_label: str
    remote_link_namespace: str


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"el índice principal {path} requiere frontmatter de configuración")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"frontmatter sin cierre en {path}")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_board_config(board_dir: Path, index_name: str | None = None) -> BoardConfig:
    board_dir = board_dir.resolve()
    index_file = board_dir / (index_name or "Board.md")
    if not index_file.is_file():
        raise ValueError(f"no se encontró índice principal Board.md bajo {board_dir}")
    values = _frontmatter(index_file)
    required = (
        "board_name",
        "entity_glob",
        "entity_id_prefix",
        "sync_dir",
        "relations_file",
        "jira_project_key",
        "jira_label",
        "remote_link_namespace",
    )
    missing = [
        key
        for key in required
        if key not in values or (key != "entity_id_prefix" and not values[key])
    ]
    if missing:
        raise ValueError(f"configuración incompleta en {index_file}: {', '.join(missing)}")
    return BoardConfig(
        board_dir=board_dir,
        index_file=index_file,
        name=values["board_name"],
        entity_glob=values["entity_glob"],
        entity_id_prefix=values["entity_id_prefix"],
        sync_dir=board_dir / values["sync_dir"],
        relations_file=board_dir / values["relations_file"],
        jira_project_key=values["jira_project_key"],
        jira_label=values["jira_label"],
        remote_link_namespace=values["remote_link_namespace"],
    )
