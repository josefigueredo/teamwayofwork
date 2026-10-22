# Reviewing someone else's PR

The same evidence bar as an audit, aimed at one pull request you did not write. The deliverable is **one comment on that PR**. Everything else in this skill that publishes — issues, PRs, branches, pushes — is off.

## Never

- Commit to, push to, rebase or force-push the author's branch.
- Open issues or PRs in their repo from this mode. If a finding deserves its own issue, say so in the comment and let the author or the user decide.
- Run `sweep.sh`, or `check-attribution.sh` without `--file`: they read the branch's commits and the repo's PR bodies, which are the author's. A hit there is not yours to report or fix.
- Approve or request changes. Post as `--comment` unless the user explicitly asks for a verdict.
- Post before the user has read the draft.

## 1. Fetch and pin

```bash
N=6
gh pr view $N --json number,title,author,baseRefName,headRefName,headRefOid,mergeStateStatus,files
BASE=$(gh pr view $N --json baseRefName --jq .baseRefName)
git fetch origin "$BASE"
git fetch origin "pull/$N/head"
HEAD_SHA=$(git rev-parse FETCH_HEAD); BASE_SHA=$(git rev-parse "origin/$BASE")
```

`pull/N/head` works for PRs from forks too, where the branch name alone does not resolve. Fetching into `FETCH_HEAD` instead of a local branch leaves nothing to delete afterwards; deleting a branch with `-D` is the kind of command a guardrail hook rightly blocks.

## 2. Build the merge result in a throwaway worktree

```bash
WT=$(mktemp -d)/pr-$N
git worktree add --detach "$WT" "$BASE_SHA"
git -C "$WT" merge --no-ff --no-edit "$HEAD_SHA"     # a conflict is a finding: report it, do not resolve it
```

On a conflict, list the files (`git -C "$WT" diff --name-only --diff-filter=U`), put them in the comment as a blocking finding, then `git -C "$WT" merge --abort`. Nothing can be built or run on a merge that does not exist; say so instead of testing the branch alone and calling it the merge.

**Why the merge and not the branch.** A branch behind its base still shows `mergeStateStatus: CLEAN`, because git can combine them. That says nothing about the *behaviour* of the combination. Real case: a branch that tightened nginx access was reviewed on the merge result; what main had added since (a CSP hash, an `error_page` on `/health`, eight `include`s) had to be proven to survive, and they did — that was half the comment's value.

Run `preflight.sh` inside `$WT`. Expect `no write access` on a colleague's repo; in this mode it only matters that you can comment.

## 3. Analyse the diff, verify what it can break

Read `gh pr diff $N` first, then the eight dimensions of SKILL.md applied to the diff and to what the merge can break around it. Every rule in `verification-rules.md` applies, especially:

- **Both directions.** A guard that blocks: show the blocked case *and* the legitimate case that must still pass. Then look for the legitimate case nobody listed (in the real case: a browser reload sends the page itself as `Referer`, and the allowlist did not include it — F5 returned 403).
- **Every route, not the one in the title.** A control on 3 of 12 locations protects the 3. Enumerate them and probe the ones without it.
- **Client-controlled inputs are not controls.** Headers like `Referer`, `Host`, `Sec-Fetch-*` are written by the client; test the evasions and say what the control is actually worth.
- **What the PR claims.** If the title says *secure* and the mechanism is a deterrent, that is a documentation finding.

Keep every command and its output; they go in the comment.

## 4. Draft the comment

Write it to a file **outside the repo** (the scratchpad), in the language the team uses on that PR. The shape that worked:

```markdown
## Revisión con evidencia

Probado sobre **el resultado del merge con `<base>`** (`<head-sha7>` sobre `<base-sha7>`), no sobre la rama sola. <What was built and run, and with what data.>

Primero lo que está bien: <what was verified to work, concretely — a reader trusts the findings more when the review shows it checked the good path too>.

Dicho eso, hay <n> cosas.

---

### 1 · Bloqueante: <the effect, in the user's terms>

<Evidence: the command and its output. A table when the comparison is the point.>

Efecto: <what a user experiences>.

Arreglo posible: <one option, and its trade-off if it relaxes something>.

---

### 2 · <Not blocking: scope or wording>

...

---

### Reproducción

    git fetch origin pull/<N>/head:pr<N> && git checkout pr<N> && git merge origin/<base>
    <build and run commands>

<Any non-obvious condition the reproduction depends on.>

---

<One closing line: which findings block the merge and which are decisions for the author.>
```

Rules for the body:

- **Severity in the heading.** `Bloqueante` / `Blocking` for what breaks the main flow; everything else is named as a decision of scope or wording. A review where everything is blocking gets nothing fixed.
- **Effects, not mechanisms, in headings.** "A reload inside the app returns 403", not "missing origin in `map $http_referer`".
- **No secrets, no real hostnames** that are not already in the PR. Replace with placeholders (`explorer.interno`) and say so.
- **No exploitation recipe beyond what proves the point.** One `curl` that shows the gap is evidence; a script that mass-downloads is not.
- **The author is a colleague.** No blame, no sarcasm, no "obviously".

## 5. Gate, post, read back

```bash
DRAFT=<scratchpad>/pr-$N-review.md
~/.agents/skills/auditing-repos/scripts/check-attribution.sh --file "$DRAFT"
```

Show the user the draft and the scan result. **Stop.** Post only after they approve, and post exactly the approved text:

```bash
gh pr review $N --comment --body-file "$DRAFT"
```

Then read it back and confirm it rendered (tables, code blocks) and carries nothing it should not:

```bash
gh api "repos/{owner}/{repo}/pulls/$N/reviews" --jq '.[-1] | .html_url, .body' | head -40
```

If something is wrong after posting, edit the review body with a visible correction (same rule as `publishing.md`: never a silent edit).

## 6. Clean up

```bash
git -C "$WT" merge --abort 2>/dev/null   # only if a conflicted merge is still in progress
git -C "$WT" status --porcelain        # build output left behind? remove it inside $WT first
git worktree remove "$WT"
```

No `--force`: if the worktree is not clean, find out what is in it instead of discarding it. No branch was created, so there is none to delete. The user's checkout was never touched; confirm with `git status` and `git worktree list`.
