"""The SKILL.md is read by an agent from wherever the skill is installed, so every script it names must be reachable from there.

A path such as `skills/local-board-skill/scripts/sync.sh` only exists inside a clone of this repository; the installed skill
(`~/.agents/skills/local-board-skill`, by symlink or by `npx skills add`) has no `skills/` above it. auditing-repos names its
scripts by the installed folder, and so does this one.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
INSTALLED = "~/.agents/skills/local-board-skill"
TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8")
SCRIPT = re.compile(r"(\S*scripts/[A-Za-z_]+\.(?:py|sh))")


class SkillPathsTest(unittest.TestCase):
    def test_every_script_the_skill_runs_is_named_by_its_installed_path(self):
        named = SCRIPT.findall(TEXT)
        self.assertTrue(named, "the SKILL.md names no script: the pattern no longer matches how it writes them")
        for path in named:
            self.assertTrue(path.startswith(f"{INSTALLED}/scripts/"), f"{path} only resolves inside a clone of the repo")

    def test_each_script_it_names_exists_in_the_skill_folder(self):
        for path in SCRIPT.findall(TEXT):
            relative = path.removeprefix(f"{INSTALLED}/")
            self.assertTrue((SKILL / relative).is_file(), f"{path} is not in {SKILL.name}")

    def test_no_repo_relative_path_to_the_skill_is_left_anywhere(self):
        stripped = TEXT.replace(INSTALLED, "")
        self.assertNotIn("skills/local-board-skill", stripped)
        self.assertNotIn("local-board-skill/scripts", stripped)


if __name__ == "__main__":
    unittest.main()
