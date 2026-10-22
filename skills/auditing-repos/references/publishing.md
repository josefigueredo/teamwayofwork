# Publishing: issues, PRs, branches, Jira

Only reached **after** the user approves the local report. Publish only findings marked `verified by execution` or `verified by docs`.

## Labels

```bash
for l in "security:b60205:Security or hardening concern" \
         "supply-chain:5319e7:Dependency, lock, or build provenance" \
         "resilience:0e8a16:Operational robustness in production" \
         "architecture:1d76db:Structural or design shape" \
         "testing:fbca04:Tests, coverage, or quality gates" \
         "ci:c2e0c6:Continuous integration and workflows"; do
  n="${l%%:*}"; r="${l#*:}"; gh label create "$n" --color "${r%%:*}" --description "${r#*:}" 2>/dev/null
done
```

## Issues — one per finding

Write each body to a file first (avoids shell-escaping mangling), then:

```bash
gh issue create --title "..." --body-file "$DIR/01.md" --label "security,ci"
```

Each body: what, **evidence as a command and its output**, why it matters, suggested fix.

**Issue numbers continue from PRs.** If the repo's last PR is #6, the first issue is #7 — so cross-references written as `#4` inside bodies will be wrong. Create issues first, capture the real numbers, then patch cross-references with `gh issue edit N --body-file`.

**"Anonymous"** means no LLM attribution — the issue is authored by the user's account with nothing anywhere in it identifying an agent. It does not mean hiding which human filed it. See `no-attribution.md`.

### Correcting a published issue

If a finding turns out to be wrong, do **not** silently edit it. Prepend a `> **Corrected.**` block explaining what was wrong and why, then rewrite the body around what remains true. The audit trail is the point.

## Pull requests — grouped by mergeable change

**One issue per finding; one PR per independently mergeable, independently revertible change.** That property — not the finding count — is the unit.

Group when findings share a file, or when one produces something another consumes (a config pointing at a file nothing generates is worse than no config).

Every PR body starts with:

```markdown
Closes #12. Closes #13. Closes #14.
```

and ends with a **Review notes** section naming shared files:

```markdown
## Review notes
Touches `pyproject.toml`, which #35 also restructures. Different regions, but
the lock regeneration will need a rerun for whichever merges second.
```

If a PR genuinely cannot merge first, say so at the top:

```markdown
> ⚠️ **Merge after #35.** At the current floor this import raises AttributeError.
```

## Branches

```bash
git checkout -b PLATE-384/harden-runtime-image
```

**Include the Jira key when creating the branch.** Retrofitting it is destructive:

> "If the renamed branch is the head branch of an open pull request, this pull request is closed." — GitHub docs

Base branches get retargeted on rename; **head branches close the PR**. For PRs that already exist, put the key in the **title** instead.

## Jira

Env vars, never hardcoded. Three are required; the fourth narrows the search:

```
JIRA_BASE_URL      required
JIRA_EMAIL         required
JIRA_API_TOKEN     required
JIRA_PROJECT_KEY   optional — restricts lookups to this project. Without it,
                   any ABC-123-shaped string in a commit gets looked up,
                   including other teams' keys and the occasional false match.
```

Other Jira settings may exist in the environment (a user name, an epic child
mode, an epic link field) and are deliberately unused: the last two configure
*creating* epic-linked tickets, and this skill only comments on tickets that
already exist.

Read a token from the clipboard (`pbpaste`) if the env var is stale. **Never write it to a file, never echo it** — print length and prefix only.

Jira links a PR to an issue when the key appears in the **branch name**, a **commit message**, or the **PR title**. Title is the non-destructive route for existing PRs:

```bash
gh pr edit N --title "$(gh pr view N --json title --jq '.title') (PLATE-384)"
```

Suffix, not prefix — it preserves the conventional-commit prefix, and Jira scans the whole title. **Key must be uppercase.**

### Posting a comment

Use **API v2 with wiki markup**, not v3. v3 requires Atlassian Document Format — a nested JSON tree you would have to build by hand.

```bash
python3 -c "import json,sys;json.dump({'body':open(sys.argv[1]).read()},sys.stdout)" body.wiki > p.json
curl -s -u "$JIRA_USER_EMAIL:$JIRA_API_TOKEN" \
  -X POST -H "Content-Type: application/json" --data @p.json \
  "$JIRA_BASE_URL/rest/api/2/issue/PLATE-384/comment"
```

Wiki markup: `h2.` headings, `{{code}}`, `||header||`/`|cell|` tables, `[text|url]` links, `*bold*`.

**Verify it rendered**, not just that it posted — a 201 with literal `h2.` on screen is a failure:

```bash
curl -s -u "$JIRA_USER_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/2/issue/KEY/comment/ID?expand=renderedBody" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['renderedBody'];print('h2 ok:','<h2' in r,'| leak:','h2.' in r)"
```

If the target uses Jira Cloud's **new editor**, paste Markdown instead — wiki markup renders literally there. API v2 still renders wiki markup regardless of editor.

**One comment per PR beats one long comment**, unless the cross-cutting framing matters — per-PR comments cannot carry an overview nobody will reconstruct from nine entries.

## Commits

Conventional commits. Body explains **why**, including what was verified.

**No LLM attribution, anywhere, no exceptions** — not in the author, a co-author trailer, the body, or any artifact this skill produces. See `no-attribution.md`. Describing *what was verified and how* is method, not attribution, and is encouraged.

## Before every push

```bash
~/.agents/skills/auditing-repos/scripts/sweep.sh
```

## Commenting on someone else's PR

Not covered here: that mode publishes one review comment and nothing in this file. See `pr-review.md`.

## Responding to automated review

Verify every comment before accepting or rejecting — both directions. Reply with what landed, what did not, and the evidence either way. When a comment is wrong on its reasoning but right in effect, say exactly that; it happens, and the distinction is the useful part.
