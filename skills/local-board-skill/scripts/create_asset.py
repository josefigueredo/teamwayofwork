#!/usr/bin/env python3
"""Create a structured epic, story, task or sub-task in a configured board."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from board_config import BoardConfig, load_board_config

TYPE_PREFIX = {"epic": "E", "story": "S", "task": "T", "sub-task": "ST"}
PARENT_TYPES = {"story": "epic", "task": "story", "sub-task": "task"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("slug vacío después de normalizar")
    return slug


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if line and line[0] not in " \t" and ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def entities(config: BoardConfig) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in config.board_dir.rglob(config.entity_glob):
        if config.sync_dir in path.parents or config.board_dir / "_meta" in path.parents:
            continue
        entity_id = parse_frontmatter(path).get("id")
        if entity_id:
            found[entity_id] = path
    return found


def next_id(config: BoardConfig, asset_type: str, known: dict[str, Path]) -> str:
    prefix = f"{config.entity_id_prefix}{TYPE_PREFIX[asset_type]}"
    numbers = [int(match.group(1)) for entity_id in known for match in [re.fullmatch(rf"{re.escape(prefix)}(\d+)", entity_id)] if match]
    return f"{prefix}{max(numbers, default=0) + 1:02d}"


def read_children(path: Path) -> list[str]:
    return [
        item.strip().strip('"').strip("'")
        for item in parse_frontmatter(path).get("children", "[]").strip("[]").split(",")
        if item.strip()
    ]


def add_child(path: Path, child_id: str) -> None:
    text = path.read_text(encoding="utf-8")
    children = read_children(path)
    if child_id in children:
        return
    children.append(child_id)
    replacement = "children: " + json.dumps(children, ensure_ascii=False)
    updated, count = re.subn(r"^children:.*$", replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{path} no contiene children en frontmatter")
    path.write_text(updated, encoding="utf-8")


def body(asset_type: str, summary: str) -> str:
    if asset_type in {"epic", "story"}:
        return f"# {summary}\n\n## Objetivo y contexto\n\nPendiente de completar con evidencia del board.\n\n## Alcance funcional y técnico\n\nPendiente de completar con responsabilidades, flujos y dependencias verificadas.\n\n## Restricciones y supuestos\n\nPendiente de completar; explicitar los puntos que requieran decisión.\n\n## Criterios de aceptación\n\n- Pendiente de completar con resultados verificables.\n\n## Validación y salida\n\nPendiente de completar con pruebas, documentación y criterios de salida.\n"
    if asset_type == "task":
        return f"# {summary}\n\n## Objetivo y alcance\n\nPendiente de completar con el cambio funcional y técnico respaldado por evidencia.\n\n## Responsabilidades, contratos y dependencias\n\nPendiente de completar; incluir interfaces, configuración, errores, compatibilidad, seguridad y observabilidad cuando apliquen.\n\n## Validación\n\nPendiente de completar con pruebas verificables y documentación esperada.\n\n## Supuestos y restricciones\n\nPendiente de completar; no inventar requisitos.\n"
    return f"# {summary}\n\n## Entregable y alcance\n\nPendiente de completar con la responsabilidad concreta.\n\n## Flujo, dependencias y restricciones\n\nPendiente de completar con evidencia disponible.\n\n## Criterios de aceptación y validación\n\n- Pendiente de completar con resultado verificable.\n\n## Documentación y salida\n\nPendiente de completar cuando corresponda.\n"


def write_asset(path: Path, args: argparse.Namespace, entity_id: str) -> None:
    lists = {
        "children": [],
        "blocks": [],
        "relates_to": [],
        "spec_refs": args.spec_ref,
        "plan_refs": args.plan_ref,
        "repos": args.repo,
        "releases": args.release,
        "commits": args.commit,
        "prs": args.pr,
        "tags": args.tag,
    }
    lines = [
        "---",
        f"id: {entity_id}",
        f"type: {args.type}",
        f"summary: {json.dumps(args.summary, ensure_ascii=False)}",
        f"status: {args.status}",
        f"assignee: {args.assignee}",
        f"assignee_account_id: {json.dumps(args.assignee_account_id)}",
        f"start: {args.start}",
    ]
    if args.end:
        lines.append(f"end: {args.end}")
    if args.parent:
        lines.append(f"parent: {args.parent}")
    lines.extend(
        [
            f"children: {json.dumps(lists['children'])}",
            "links:",
            f"  blocks: {json.dumps(lists['blocks'])}",
            f"  relates_to: {json.dumps(lists['relates_to'])}",
            f"spec_refs: {json.dumps(lists['spec_refs'])}",
            f"plan_refs: {json.dumps(lists['plan_refs'])}",
            f"repos: {json.dumps(lists['repos'])}",
            f"releases: {json.dumps(lists['releases'])}",
            "git_evidence:",
            f"  commits: {json.dumps(lists['commits'])}",
            f"  prs: {json.dumps(lists['prs'])}",
            f"  tags: {json.dumps(lists['tags'])}",
            'jira_key: ""',
            "jira_sync: pending",
            "---",
            "",
            body(args.type, f"{entity_id} - {args.summary}"),
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def destination(config: BoardConfig, asset_type: str, entity_id: str, slug: str, parent_path: Path | None) -> Path:
    if "/" in slug or "\\" in slug or any(part in {".", ".."} for part in Path(slug).parts) or Path(slug).is_absolute():
        raise ValueError("slug no puede contener separadores de ruta")
    if "/" in entity_id or "\\" in entity_id or entity_id in {".", ".."}:
        raise ValueError("id no puede contener separadores de ruta")
    if asset_type == "epic":
        directory = config.board_dir / f"{entity_id}-{slug}"
        return directory / f"{entity_id}.md"
    if not parent_path:
        raise ValueError(f"{asset_type} requiere parent")
    if asset_type == "sub-task":
        return parent_path.parent / f"{entity_id}-{slug}.md"
    directory = parent_path.parent / f"{entity_id}-{slug}"
    return directory / f"{entity_id}.md"


def validate_parent(args: argparse.Namespace, known: dict[str, Path], parser: argparse.ArgumentParser) -> Path | None:
    parent_path = known.get(args.parent) if args.parent else None
    expected_parent = PARENT_TYPES.get(args.type)
    if not expected_parent:
        if args.parent:
            parser.error("epic no admite parent")
        return None
    if not args.parent or not parent_path:
        parser.error(f"{args.type} requiere un parent existente de tipo {expected_parent}")
    if parse_frontmatter(parent_path).get("type") != expected_parent:
        parser.error(f"parent {args.parent} debe ser de tipo {expected_parent}")
    return parent_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a structured local-board asset")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--type", choices=TYPE_PREFIX, required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--slug", default=None)
    parser.add_argument("--id", default=None, help="Explicit ID; defaults to the next sequential ID.")
    parser.add_argument("--parent", default=None)
    parser.add_argument("--status", choices=["To Do", "In Progress", "Done"], default="To Do")
    parser.add_argument("--assignee", default="pending")
    parser.add_argument("--assignee-account-id", default="")
    parser.add_argument("--start", default=date.today().isoformat())
    parser.add_argument("--end", default=None)
    for name, destination_name in (("spec-ref", "spec_ref"), ("plan-ref", "plan_ref"), ("repo", "repo"), ("release", "release"), ("commit", "commit"), ("pr", "pr"), ("tag", "tag")):
        parser.add_argument(f"--{name}", dest=destination_name, action="append", default=[])
    args = parser.parse_args()
    config = load_board_config(args.board_dir)
    known = entities(config)
    entity_id = args.id or next_id(config, args.type, known)
    if entity_id in known:
        parser.error(f"ya existe el asset {entity_id}")
    parent_path = validate_parent(args, known, parser)
    target = destination(config, args.type, entity_id, args.slug or slugify(args.summary), parent_path)
    if target.exists() or (args.type != "sub-task" and target.parent.exists()):
        parser.error(f"el destino ya existe: {target.parent}")
    target.parent.mkdir(parents=True, exist_ok=True)
    parent_before = parent_path.read_text(encoding="utf-8") if parent_path else None
    try:
        write_asset(target, args, entity_id)
        if parent_path:
            add_child(parent_path, entity_id)
    except Exception:
        target.unlink(missing_ok=True)
        if parent_path and parent_before is not None:
            parent_path.write_text(parent_before, encoding="utf-8")
        try:
            target.parent.rmdir()
        except OSError:
            pass
        raise
    print(f"Created {entity_id}: {target.relative_to(config.board_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
