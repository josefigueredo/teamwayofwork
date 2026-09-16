#!/usr/bin/env python3
"""Regenerate a board index from entity frontmatter and its index profile."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from board_config import BoardConfig, load_board_config


@dataclass
class Entity:
    id: str
    type: str
    summary: str
    status: str
    start: str
    end: str
    parent: str | None
    jira_key: str
    path: Path
    rel: str


def decode_quoted_scalar(value: str) -> str:
    """Safely decode JSON-escaped quoted scalars; fall back to strip-quotes."""
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, str) else str(parsed)
    except json.JSONDecodeError:
        return value[1:-1]


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line or line[0] in " \t" or ":" not in line:
            continue
        k, v = line.split(":", 1)
        value = v.strip()
        data[k.strip()] = decode_quoted_scalar(value)
    return data


def load_entities(config: BoardConfig) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    for path in sorted(config.board_dir.rglob(config.entity_glob)):
        if config.sync_dir in path.parents or config.board_dir / "_meta" in path.parents:
            continue
        data = parse_frontmatter(path.read_text(encoding="utf-8"))
        eid = data.get("id")
        if not eid:
            continue
        rel = path.relative_to(config.board_dir).as_posix()
        out[eid] = Entity(
            id=eid,
            type=data.get("type", ""),
            summary=data.get("summary", ""),
            status=data.get("status", ""),
            start=data.get("start", ""),
            end=data.get("end", "") or "—",
            parent=data.get("parent") or None,
            jira_key=data.get("jira_key", ""),
            path=path,
            rel=rel,
        )
    return out


def short_summary(summary: str, eid: str) -> str:
    s = summary
    for p in (f"[{eid}] ", f"[{eid}]"):
        if s.startswith(p):
            s = s[len(p) :].lstrip()
    # keep index compact
    if len(s) > 70:
        s = s[:67] + "…"
    return s


def link(ent: Entity) -> str:
    label = ent.id
    return f"[{label}]({ent.rel})"


def index_frontmatter(config: BoardConfig) -> list[str]:
    text = config.index_file.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    return text[: end + 5].rstrip("\n").splitlines() if end >= 0 else []


def append_overview(lines: list[str], config: BoardConfig, epics: list[Entity], stories: list[Entity], tasks: list[Entity], subtasks: list[Entity]) -> None:
    lines.extend([
        "", f"# {config.name} (índice local)", "",
        f"Índice generado desde los frontmatter `{config.entity_glob}`. Sync: [`{config.sync_dir.name}/`]({config.sync_dir.name}/).", "",
        "> Periodo histórico: consultar `sync/git-inventory.json` para el baseline real.", ">",
        f"> Label Jira: `{config.jira_label}`. Proyecto: **{config.jira_project_key}**. Estado de sync: `{config.sync_dir.name}/state.json`.", "",
        "## Leyenda", "", "| Tipo | Prefijo | Cantidad |", "| --- | --- | --- |",
        f"| Epic | `{config.entity_id_prefix}E##` | {len(epics)} |",
        f"| Story | `{config.entity_id_prefix}S##` | {len(stories)} |",
        f"| Task | `{config.entity_id_prefix}T##` | {len(tasks)} |",
        f"| Sub-task | `{config.entity_id_prefix}ST##` | {len(subtasks)} |",
        f"| **Total** | | **{len(epics) + len(stories) + len(tasks) + len(subtasks)}** |", "",
        "- Estados: **Done** · **In Progress** · **To Do**", "",
    ])


def append_in_progress(lines: list[str], entities: dict[str, Entity]) -> None:
    in_progress = sorted((entity for entity in entities.values() if entity.status == "In Progress"), key=lambda entity: entity.id)
    lines.extend(["## En curso ahora", ""])
    if not in_progress:
        lines.extend(["_Ninguna entidad local en In Progress._", ""])
        return
    lines.extend(["| ID | Tipo | Jira | Summary |", "| --- | --- | --- | --- |"])
    lines.extend(f"| {link(entity)} | {entity.type} | {entity.jira_key or '—'} | {short_summary(entity.summary, entity.id)} |" for entity in in_progress)
    lines.append("")


def append_epic_sections(lines: list[str], epics: list[Entity], by_parent: dict[str, list[Entity]]) -> None:
    lines.extend(["## Épicas", "", "| ID | Épica | Estado | Jira | Start | End |", "| --- | --- | --- | --- | --- | --- |"])
    lines.extend(f"| {link(entity)} | {short_summary(entity.summary, entity.id)} | {entity.status} | {entity.jira_key or '—'} | {entity.start or '—'} | {entity.end} |" for entity in epics)
    lines.append("")
    for epic in epics:
        append_story_section(lines, epic, by_parent)


def append_story_section(lines: list[str], epic: Entity, by_parent: dict[str, list[Entity]]) -> None:
    stories = [entity for entity in by_parent.get(epic.id, []) if entity.type == "story"]
    lines.extend([f"## {epic.id} — {short_summary(epic.summary, epic.id)}", ""])
    if not stories:
        lines.extend(["_Sin stories._", ""])
        return
    lines.extend(["| Story | Estado | Jira | Start | End |", "| --- | --- | --- | --- | --- |"])
    lines.extend(f"| {link(story)} {short_summary(story.summary, story.id)} | {story.status} | {story.jira_key or '—'} | {story.start or '—'} | {story.end} |" for story in stories)
    lines.append("")
    for story in stories:
        append_task_section(lines, story, by_parent)


def append_task_section(lines: list[str], story: Entity, by_parent: dict[str, list[Entity]]) -> None:
    tasks = [entity for entity in by_parent.get(story.id, []) if entity.type == "task"]
    if not tasks:
        return
    lines.extend([f"### {story.id}", "", "| Task | Estado | Jira | Start | End |", "| --- | --- | --- | --- | --- |"])
    for task in tasks:
        lines.append(f"| {link(task)} {short_summary(task.summary, task.id)} | {task.status} | {task.jira_key or '—'} | {task.start or '—'} | {task.end} |")
        for subtask in (entity for entity in by_parent.get(task.id, []) if entity.type == "sub-task"):
            lines.append(f"| └ {link(subtask)} {short_summary(subtask.summary, subtask.id)} | {subtask.status} | {subtask.jira_key or '—'} | {subtask.start or '—'} | {subtask.end} |")
    lines.append("")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate a local board index")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--index-name", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the generated index; defaults to the configured primary index.",
    )
    return parser.parse_args()


def build_index(config: BoardConfig) -> list[str]:
    entities = load_entities(config)
    grouped = {kind: sorted((entity for entity in entities.values() if entity.type == kind), key=lambda entity: entity.id) for kind in ("epic", "story", "task", "sub-task")}
    by_parent: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities.values():
        if entity.parent:
            by_parent[entity.parent].append(entity)
    for children in by_parent.values():
        children.sort(key=lambda entity: entity.id)
    lines = index_frontmatter(config)
    append_overview(lines, config, grouped["epic"], grouped["story"], grouped["task"], grouped["sub-task"])
    append_in_progress(lines, entities)
    append_epic_sections(lines, grouped["epic"], by_parent)
    lines.extend(["---", "", f"_Índice regenerado automáticamente ({len(entities)} entidades)._", ""])
    return lines


def main() -> None:
    args = parse_args()
    config = load_board_config(args.board_dir, args.index_name)
    output_path = args.output or config.index_file
    if output_path.resolve() != config.index_file.resolve():
        raise ValueError("--output sólo admite el índice principal configurado")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = build_index(config)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output_path} ({len(load_entities(config))} entities)")


if __name__ == "__main__":
    main()
