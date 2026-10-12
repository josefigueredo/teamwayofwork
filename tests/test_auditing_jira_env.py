"""auditing-repos reads its Jira credentials as JIRA_*; IC_JIRA_* still works as an alias that is never advertised.

Every case runs the real scripts under a clean environment (env -i), so nothing depends on the credentials of whoever
runs the tests. Jira itself is replaced by a fake `curl` on PATH that records the arguments it receives.

Run: python3 -m unittest discover -s tests -p "test_auditing_jira_env.py" -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills/auditing-repos/scripts"
FAKE_CURL = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CURL_LOG"\nprintf 200\n'


class AuditingJiraEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        (tmp / "bin").mkdir()
        curl = tmp / "bin/curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)
        self.log = tmp / "curl.log"
        self.cwd = tmp / "empty"  # not a git repo: preflight must still reach the Jira section
        self.cwd.mkdir()

    def preflight(self, **env):
        clean = {"PATH": f"{self.tmp.name}/bin:/usr/bin:/bin", "HOME": self.tmp.name, "CURL_LOG": str(self.log)}
        clean.update(env)
        out = subprocess.run(["bash", str(SCRIPTS / "preflight.sh")], cwd=self.cwd, env=clean, text=True,
                             capture_output=True, stdin=subprocess.DEVNULL, check=False)
        return out.stdout + out.stderr

    def curl_calls(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_without_credentials_it_names_only_the_generic_variables(self):
        out = self.preflight()
        self.assertIn("skipped (missing: JIRA_BASE_URL JIRA_EMAIL JIRA_API_TOKEN)", out)
        self.assertNotIn("IC_JIRA", out)
        self.assertEqual(self.curl_calls(), "")

    def test_generic_variables_authenticate(self):
        out = self.preflight(JIRA_BASE_URL="https://generic.example", JIRA_EMAIL="g@x.com", JIRA_API_TOKEN="gtok",
                             JIRA_PROJECT_KEY="PLATE")
        self.assertRegex(out, r"jira auth\s+yes")
        self.assertIn("PLATE", out)
        self.assertIn("g@x.com:gtok", self.curl_calls())
        self.assertIn("https://generic.example/rest/api/3/myself", self.curl_calls())

    def test_the_ic_names_still_work_as_an_alias(self):
        out = self.preflight(IC_JIRA_BASE_URL="https://alias.example", IC_JIRA_USER_EMAIL="a@x.com",
                             IC_JIRA_API_TOKEN="atok", IC_JIRA_PROJECT_KEY="OLD")
        self.assertRegex(out, r"jira auth\s+yes")
        self.assertIn("OLD", out)
        self.assertIn("a@x.com:atok", self.curl_calls())

    def test_alias_wins_over_generic_as_in_jira_team_kit(self):
        self.preflight(IC_JIRA_BASE_URL="https://alias.example", IC_JIRA_USER_EMAIL="a@x.com", IC_JIRA_API_TOKEN="atok",
                       JIRA_BASE_URL="https://generic.example", JIRA_EMAIL="g@x.com", JIRA_API_TOKEN="gtok")
        self.assertIn("a@x.com:atok", self.curl_calls())
        self.assertIn("https://alias.example", self.curl_calls())

    def test_a_partial_set_reports_only_what_is_missing_with_generic_names(self):
        out = self.preflight(JIRA_BASE_URL="https://generic.example", IC_JIRA_API_TOKEN="atok")
        self.assertIn("skipped (missing: JIRA_EMAIL)", out)

    def test_check_attribution_uses_the_generic_variables(self):
        rg = shutil.which("rg")
        if rg is None:
            self.skipTest("check-attribution.sh needs rg")
        (Path(self.tmp.name) / "bin/rg").symlink_to(rg)
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                                        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x.com",
                                             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x.com"})
        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "base")
        git("commit", "-q", "--allow-empty", "-m", "feat: PLATE-1 algo")
        env = {"PATH": f"{self.tmp.name}/bin:/usr/bin:/bin", "HOME": self.tmp.name, "CURL_LOG": str(self.log),
               "JIRA_BASE_URL": "https://generic.example", "JIRA_EMAIL": "g@x.com", "JIRA_API_TOKEN": "gtok"}
        subprocess.run(["bash", str(SCRIPTS / "check-attribution.sh"), "HEAD~1"], cwd=repo, env=env, text=True,
                       capture_output=True, stdin=subprocess.DEVNULL, check=False)
        self.assertIn("g@x.com:gtok", self.curl_calls())
        self.assertIn("https://generic.example/rest/api/3/myself", self.curl_calls())

    def test_no_user_facing_text_of_the_skill_announces_the_ic_names(self):
        offenders = []
        for path in (ROOT / "skills/auditing-repos").rglob("*"):
            if path.is_file() and path.suffix in {".md", ".html", ".sh"} and path.name != "jira-env.sh":
                if re.search(r"\bIC_JIRA", path.read_text(encoding="utf-8")):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "only scripts/jira-env.sh may name the IC_JIRA_* alias")


if __name__ == "__main__":
    unittest.main()
