"""Every skill in this repo must conform to the Agent Skills format (https://agentskills.io/specification).

Run: python3 -m unittest discover -s tests -p "test_skills_spec.py" -v   (or: python3 tests/test_skills_spec.py)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skillspec import check_skill, discover  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

VALID = """---
name: demo-skill
description: >
  Use when a folded block
  spans several lines.
license: MIT
metadata:
  author: someone
compatibility: Needs git.
---

# Body
"""


def frontmatter(**overrides):
    """A minimal valid SKILL.md whose fields can be replaced; a None value drops the field."""
    fields = {"name": "demo-skill", "description": "Use when testing."}
    fields.update(overrides)
    lines = [f"{k}: {v}" for k, v in fields.items() if v is not None]
    return "---\n" + "\n".join(lines) + "\n---\n\n# Body\n"


class CheckSkillSelfTest(unittest.TestCase):
    """The reference must bite: each broken fixture fails for its own reason, the valid one passes."""

    def check(self, text, folder="demo-skill"):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / folder
            skill.mkdir()
            (skill / "SKILL.md").write_text(text, encoding="utf-8")
            return check_skill(skill)

    def assertFails(self, text, expected, folder="demo-skill"):
        errors = self.check(text, folder)
        self.assertTrue(any(expected in e for e in errors), f"expected '{expected}' in {errors}")

    def test_valid_with_folded_block_and_metadata(self):
        self.assertEqual(self.check(VALID), [])

    def test_field_outside_the_spec(self):
        self.assertFails(frontmatter(**{"user-invocable": "true"}), "user-invocable")

    def test_uppercase_name(self):
        self.assertFails(frontmatter(name="Demo-Skill"), "lowercase", folder="Demo-Skill")

    def test_consecutive_hyphens(self):
        self.assertFails(frontmatter(name="demo--skill"), "consecutive hyphens", folder="demo--skill")

    def test_hyphen_at_the_edge(self):
        self.assertFails(frontmatter(name="-demo"), "starts or ends with a hyphen", folder="-demo")

    def test_name_differs_from_folder(self):
        self.assertFails(frontmatter(name="other-name"), "does not match")

    def test_missing_description(self):
        self.assertFails(frontmatter(description=None), "missing required field: description")

    def test_description_too_long(self):
        self.assertFails(frontmatter(description="x" * 1025), "description is 1025 chars")

    def test_compatibility_too_long(self):
        self.assertFails(frontmatter(compatibility="x" * 501), "compatibility is 501 chars")

    def test_no_frontmatter(self):
        self.assertFails("# Just a body\n", "no YAML frontmatter")

    def test_name_too_long(self):
        name = "a" * 65
        self.assertFails(frontmatter(name=name), "max 64", folder=name)


class RepoSkillsConform(unittest.TestCase):
    def test_the_repo_has_skills_to_scan(self):
        self.assertTrue(discover(REPO), "discover() found no skill: the scan below would pass vacuously")

    def test_every_skill_follows_the_spec(self):
        failures = {}
        for skill in discover(REPO):
            # Every skill lives in skills/<name>/, so the folder name is the published name.
            errors = check_skill(skill)
            if errors:
                failures[str(skill.relative_to(REPO))] = errors
        self.assertEqual(failures, {}, "skills outside https://agentskills.io/specification")


if __name__ == "__main__":
    unittest.main()
