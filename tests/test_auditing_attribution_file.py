"""check-attribution.sh --file scans one draft (a review comment on someone else's PR) and nothing else.

On a colleague's branch the full sweep reads their commits, their diff and their PR bodies, which are not the user's
to judge or fix. --file must therefore never touch git, gh or Jira: each case runs outside any git repo with fake
`git`, `gh` and `curl` on PATH that record every call.

Run: python3 -m unittest discover -s tests -p "test_auditing_attribution_file.py" -v
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/auditing-repos/scripts/check-attribution.sh"
FAKE = '#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$CALL_LOG"\nexit 1\n'
# Assembled at runtime so this file does not itself read as an attribution.
DIRTY = "## Revisión\n\nTodo bien.\n\nGenerated with " + "Cla" + "ude Code\n"
CLEAN = "## Revisión con evidencia\n\nProbado sobre el merge con main. Copilot marcó lo mismo en su review.\n"


class AttributionFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        (tmp / "bin").mkdir()
        for tool in ("git", "gh", "curl"):
            fake = tmp / "bin" / tool
            fake.write_text(FAKE, encoding="utf-8")
            fake.chmod(0o755)
        self.log = tmp / "calls.log"

    def check(self, *args):
        tmp = Path(self.tmp.name)
        # rg is the only real tool the scan needs; keep its directory reachable after the fakes.
        rg = subprocess.run(["sh", "-c", "command -v rg"], text=True, capture_output=True, check=True).stdout.strip()
        env = {"PATH": f"{tmp}/bin:{Path(rg).parent}:/usr/bin:/bin", "HOME": str(tmp), "CALL_LOG": str(self.log),
               "JIRA_BASE_URL": "https://jira.invalid", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "x"}
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=tmp, env=env, text=True, capture_output=True,
                              stdin=subprocess.DEVNULL, check=False)

    def draft(self, body):
        path = Path(self.tmp.name) / "comment.md"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def calls(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_clean_draft_passes_without_touching_git_gh_or_jira(self):
        out = self.check("--file", self.draft(CLEAN))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("comment.md clean", out.stdout)
        self.assertEqual(self.calls(), "")

    def test_attribution_in_draft_fails_and_shows_the_line(self):
        out = self.check("--file", self.draft(DIRTY))
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("Generated with", out.stdout)
        self.assertEqual(self.calls(), "")

    def test_missing_file_is_a_usage_error_not_a_pass(self):
        out = self.check("--file", str(Path(self.tmp.name) / "nope.md"))
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertNotIn("clean", out.stdout)


if __name__ == "__main__":
    unittest.main()
