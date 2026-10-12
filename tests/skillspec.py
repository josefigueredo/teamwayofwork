"""Checks a skill folder against the Agent Skills format (https://agentskills.io/specification), stdlib only, Python 3.9+.

The rules are a port of skills-ref's validator (agentskills/agentskills @ 69ef37e, skills-ref/src/skills_ref/validator.py):
only the six fields the spec defines, `name` and `description` required, name <= 64 chars / lowercase / letters, digits and
single hyphens / no leading or trailing hyphen, description <= 1024, compatibility <= 500. It is a port, not the tool: the
reference library calls itself "for demonstration purposes only", needs Python 3.11 and a YAML library, so it is not run here.
If the spec changes, this file is what to update.

One deliberate difference: skills-ref compares `name` with the folder's name. A skill that sits at the root of its repo
(run-in-cursor) or in a folder installed under another name has the folder name of whoever cloned it, so the check takes the
name the installer publishes it under (`published_name`) and compares against that. Skills under `skills/<name>/` keep the
folder rule.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ALLOWED_FIELDS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
MAX_NAME, MAX_DESCRIPTION, MAX_COMPATIBILITY = 64, 1024, 500
_KEY = re.compile(r"^([A-Za-z][\w-]*):[ \t]*(.*)$")


def parse_frontmatter(text: str) -> "dict[str, str] | None":
    """Top-level keys of the YAML frontmatter with their scalar value (folded or literal blocks joined, quotes removed).
    A nested map such as `metadata:` yields an empty string: only its presence matters here."""
    match = re.match(r"---\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not match:
        return None
    fields: "dict[str, list[str]]" = {}
    head = ""
    for line in match.group(1).splitlines():
        key = _KEY.match(line)
        if key and not line[:1].isspace():
            head = key.group(1)
            fields[head] = [key.group(2).strip()]
        elif head and (line[:1].isspace() or not line.strip()):
            fields[head].append(line.strip())
    out = {}
    for name, parts in fields.items():
        first, rest = parts[0], [p for p in parts[1:] if p]
        if first in (">", "|", ">-", "|-", ">+", "|+"):
            value = " ".join(rest)
        else:
            value = " ".join([first] + rest).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name] = value
    return out


def check_skill(skill_dir: Path, published_name: "str | None" = None) -> "list[str]":
    """Errors for the skill in `skill_dir` (empty list = conforms). `published_name` is the name it is installed under;
    without it the folder name is used, as skills-ref does."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir}: no SKILL.md"]
    fields = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if fields is None:
        return [f"{skill_md}: no YAML frontmatter between --- lines"]
    errors = []
    extra = sorted(set(fields) - ALLOWED_FIELDS)
    if extra:
        errors.append(f"unexpected frontmatter fields: {', '.join(extra)} (the spec defines {sorted(ALLOWED_FIELDS)})")
    name = unicodedata.normalize("NFKC", fields.get("name", "").strip())
    if not name:
        errors.append("missing required field: name")
    else:
        if len(name) > MAX_NAME:
            errors.append(f"name '{name}' is {len(name)} chars, max {MAX_NAME}")
        if name != name.lower():
            errors.append(f"name '{name}' must be lowercase")
        if name.startswith("-") or name.endswith("-"):
            errors.append(f"name '{name}' starts or ends with a hyphen")
        if "--" in name:
            errors.append(f"name '{name}' has consecutive hyphens")
        if not all(c.isalnum() or c == "-" for c in name):
            errors.append(f"name '{name}' has characters other than letters, digits and hyphens")
        expected = published_name or skill_dir.name
        if unicodedata.normalize("NFKC", expected) != name:
            errors.append(f"name '{name}' does not match '{expected}'" + ("" if published_name else " (the folder name)"))
    description = fields.get("description", "").strip()
    if not description:
        errors.append("missing required field: description")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"description is {len(description)} chars, max {MAX_DESCRIPTION}")
    if "compatibility" in fields and len(fields["compatibility"]) > MAX_COMPATIBILITY:
        errors.append(f"compatibility is {len(fields['compatibility'])} chars, max {MAX_COMPATIBILITY}")
    return errors


def discover(root: Path) -> "list[Path]":
    """The skill folders of a repo: its root when it has a SKILL.md, and every `skills/<name>/` that has one."""
    found = [root] if (root / "SKILL.md").is_file() else []
    found += sorted(p.parent for p in (root / "skills").glob("*/SKILL.md"))
    return found
