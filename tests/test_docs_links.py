"""Docs checks for the four documented items (stdlib only). Run from anywhere:

    python3 tests/test_docs_links.py
    python3 -m unittest discover -s tests -p 'test_docs*.py'

Every relative link, image and anchor in each item's README and docs/ must resolve, each index row must link its showcase
and install guide, the root README must link every item's docs, and the Jira variable names the docs use must be the ones
the scripts really read.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ["skills/auditing-repos", "skills/local-board-skill", "skills/install-unified-ci", "commands/query-from-cli"]
DOC_NAMES = ["instalacion.md", "instalacion-detallada.md", "showcase.md", "referencia.md"]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path: Path) -> set:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)  # '# comment' lines in code are not headings
    return {slug(m.group(2)) for m in re.finditer(r"^(#{1,6}) (.+)$", text, re.M)}


def pages(item: str) -> list:
    base = ROOT / item
    return [base / "README.md"] + [base / "docs" / name for name in DOC_NAMES]


class DocsTest(unittest.TestCase):
    def test_every_item_has_the_full_doc_set_and_images_under_300kb(self):
        for item in ITEMS:
            for page in pages(item):
                self.assertTrue(page.exists(), f"{page} is missing")
            images = list((ROOT / item / "docs" / "img").glob("*.png"))
            self.assertTrue(images, f"{item} has no images")
            for image in images:
                self.assertLess(image.stat().st_size, 300_000, f"{image} is over 300 KB")
                self.assertTrue((image.parent / "src" / f"{image.stem}.html").exists(), f"{image} has no HTML source")

    def test_every_relative_link_image_and_anchor_resolves(self):
        for item in ITEMS:
            for page in pages(item):
                for target in LINK.findall(page.read_text(encoding="utf-8")):
                    if re.match(r"[a-z]+:", target):  # https:, mailto:
                        continue
                    path, _, fragment = target.partition("#")
                    dest = (page.parent / path).resolve() if path else page
                    self.assertTrue(dest.exists(), f"{page.relative_to(ROOT)} links to {target}, which does not exist")
                    if fragment and dest.suffix == ".md":
                        self.assertIn(fragment, anchors(dest), f"{page.relative_to(ROOT)} links to {target}: no such heading")

    def test_the_index_rows_link_the_showcase_and_the_install_guide(self):
        for item in ITEMS:
            readme = (ROOT / item / "README.md").read_text(encoding="utf-8")
            block = readme.split("## Elegí por dónde empezar", 1)[1].split("\n## ", 1)[0]
            rows = [line for line in block.splitlines() if line.startswith("| **")]
            self.assertTrue(rows, f"{item} has no index rows")
            for row in rows:
                self.assertIn("docs/showcase.md#", row, f"{item}: {row[:40]}")
                self.assertIn("docs/instalacion.md#", row, f"{item}: {row[:40]}")

    def test_the_index_opens_with_a_capability_table_and_keeps_the_phase_block(self):
        for item in ITEMS:
            readme = (ROOT / item / "README.md").read_text(encoding="utf-8")
            self.assertIn("**Fase:", readme.split("\n## ", 1)[0])
            self.assertIn("| Le decís", readme.split("## Elegí", 1)[0])
            self.assertIn("../../README.md#ciclo-de-vida", readme)
            self.assertIn("../../../README.md#ciclo-de-vida", (ROOT / item / "docs" / "referencia.md").read_text(encoding="utf-8"))

    def test_the_root_readme_links_every_items_docs(self):
        root = (ROOT / "README.md").read_text(encoding="utf-8")
        for item in ITEMS:
            for name in ("instalacion.md", "showcase.md", "referencia.md"):
                self.assertIn(f"{item}/docs/{name}", root)
        self.assertIn("## Ciclo de vida", root)

    def test_the_cursor_guides_have_one_manual_step_called_out(self):
        for item in ITEMS:
            guide = (ROOT / item / "docs" / "instalacion.md").read_text(encoding="utf-8")
            self.assertIn("**no**", guide.split("| Paso |", 1)[0], f"{item}: say up front what cannot be a prompt")
            self.assertIn("## Si algo falla", guide)
            self.assertIn("## De dónde sale cada captura", guide)

    def test_auditing_repos_documents_exactly_the_jira_variables_its_scripts_read(self):
        scripts = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "skills/auditing-repos/scripts").glob("*.sh"))
        docs = "".join(p.read_text(encoding="utf-8") for p in pages("skills/auditing-repos"))
        for name in set(re.findall(r"\bIC_JIRA_[A-Z_]+\b", docs)):
            if name in ("IC_JIRA_USER_NAME", "IC_JIRA_EPIC_CHILD_MODE", "IC_JIRA_FIELD_EPIC_LINK"):
                continue  # documented as ignored on purpose
            self.assertIn(name, scripts, f"{name} is documented but no script reads it")

    def test_local_board_docs_use_the_generic_jira_names(self):
        docs = "".join(p.read_text(encoding="utf-8") for p in pages("skills/local-board-skill"))
        scripts = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "skills/local-board-skill/scripts").glob("*.py"))
        self.assertNotIn("IC_JIRA", docs)
        for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
            self.assertIn(name, docs)
            self.assertIn(name, scripts)

    def test_query_docs_give_an_alias_that_works_and_the_real_default_model(self):
        docs = "".join(p.read_text(encoding="utf-8") for p in pages("commands/query-from-cli"))
        self.assertNotIn("alias q=\"$PWD/commands", docs)  # literal $PWD in single quotes broke the alias
        self.assertIn('alias q=\\"$PWD/commands/query-from-cli/query.sh\\"', docs)
        self.assertNotIn("bash $PWD/commands", docs)  # query.sh is executable now: the alias calls it directly
        self.assertTrue(os.access(ROOT / "commands/query-from-cli/query.sh", os.X_OK))
        for stale in ("Defaults to claude", "100644"):
            self.assertNotIn(stale, docs)
        script = (ROOT / "commands/query-from-cli/query.sh").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_MODEL="copilot"', script)
        self.assertIn("copilot", (ROOT / "commands/query-from-cli/docs/instalacion.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
