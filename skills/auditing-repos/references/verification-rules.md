# Verification Rules

Every rule here comes from an audit where a confident finding turned out to be wrong, or a fix turned out not to fix anything. They are cheap. Skipping them is what produces an audit a colleague cannot trust.

## The rule behind the rules

**A claim you did not execute is a hypothesis.** Report hypotheses as hypotheses. The cost of publishing a wrong finding is not the finding — it is that the reader now discounts the other twenty.

---

## 1. Read the invisible parts before claiming anything is missing

A repository that calls a **private or shared CI workflow** does more than its files reveal. Before writing "there is no coverage", "nothing scans dependencies", or "tests are not run":

```bash
gh api repos/OWNER/WORKFLOW-REPO/contents/.github/workflows/FILE.yml --jq '.content' | base64 -d
```

Your token may well read it even when the repo is private/internal.

Real case: two findings — "SonarCloud receives no coverage" and "no dependency scanning" — were both **false**. The shared workflow installed `pytest-cov`, appended the Sonar path, and ran Checkmarx and TruffleHog. Both had to be publicly corrected after filing.

If you genuinely cannot read it, say "not visible from this repository" rather than "does not exist".

## 2. Verify dependency ranges at BOTH ends

Green CI proves *one* resolution works. It says nothing about the range you declared.

```bash
uv pip compile requirements.in --resolution lowest-direct    # the floor
```

Then actually install and run the suite at that floor.

Real case: `fastapi>=0.115` with `httpx2>=2` — at the floor, `TestClient` raised on import. Nothing in CI resolved the floor, so it was invisible for as long as it existed.

**Symbols too.** "This constant exists" is a claim about a version, not about a library:

```
fastapi 0.115.0 (starlette 0.38.6) → HTTP_422_UNPROCESSABLE_CONTENT MISSING
fastapi 0.133.0 (starlette 1.6.0)  → 422
```

The same import passed CI and was broken at the floor of its own range.

## 3. Test every guard in both directions

A guard verified only in the passing direction is untested.

```bash
# coverage gate: does it FAIL when coverage drops?
# consistency check: does it FAIL on committed drift?
# pip-absence assertion: does it FAIL on an image that has pip?
```

Real case: a `--cov-fail-under` gate confirmed by adding an uncovered module (42% → exit 1), then removing it (100% → exit 0).

**Simulate the failure in the state the check actually sees.** A drift check that re-generates a file before diffing will erase a working-tree edit and report clean — the drift must be *committed* for a diff-against-HEAD to mean anything.

## 4. Distinguish "validates the artifact" from "validates the file"

`pip install --require-hashes` verifies each downloaded artifact matches the hash written beside it. It does **not** know whether the file is current.

```
requirements.txt: idna==3.7 + valid hashes for 3.7
uv.lock:          idna==3.18
pip install --require-hashes → exit 0, installs 3.7
```

Before claiming a flag protects against something, name the exact failure mode and test it. A wrong claim about what a security control covers is worse than no claim: it stops people looking for the gap.

## 5. Never claim a guarantee that nothing enforces

"Generated from X, so they cannot drift" describes an intention. Convention is not enforcement. Either add the check that makes it true, or describe it honestly as a convention.

Preferred: make the guarantee real rather than softening the sentence.

## 6. Auth failures masquerade as absence

An unauthenticated API returns *nothing exists*, not *you lack permission*.

```
GET /rest/api/3/myself         → 401 AUTHENTICATED_FAILED
GET /rest/api/3/issue/ABC-123  → "does not exist or you lack permission"
GET /rest/api/3/project/search → total: 0        ← the anonymous response
```

Always check identity first. Never conclude a ticket, project, or repo is missing while auth is failing.

## 7. Verify external references against the API, never from memory

Action SHAs, release tags, digests, package versions — look them up:

```bash
gh api repos/OWNER/REPO/tags --jq '.[0:5][] | "\(.name) \(.commit.sha)"'
gh api repos/OWNER/REPO/releases/latest --jq '.tag_name'
docker buildx imagetools inspect IMAGE:TAG        # multi-platform index digest
```

Real case: three action SHAs written from memory. One was correct by luck; one did not exist; one *existed but belonged to a different tag than its comment claimed*. `scripts/sweep.sh` checks both existence and tag correspondence.

Also verify the tool's own pins: `trivy-action@v0.36.0` defaulted to Trivy `v0.70.0`, which was never published.

## 8. Distinguish a flake from a permanent failure

Before calling CI "a flaky upstream":

1. Does the remote artifact actually exist? `gh api repos/O/R/releases/tags/vX` — if not, no rerun will ever fix it.
2. Try a **full** rerun, not just failed jobs: `gh run rerun <id>` beats `gh run rerun <id> --failed`. Four rounds of `--failed` failed where one full rerun passed.

## 9. Know which operations destroy work

| Operation | Consequence |
|---|---|
| Rename a branch that is the head of an open PR | **GitHub closes the PR** |
| `git reset --hard` | Discards uncommitted tracked changes (untracked survive) |
| `git add -A` with local agent tooling present | Sweeps `.serena/`, `.idea/`, local settings into the commit |
| Publishing an issue | Notifies people; deleting it does not un-notify |

## 10. Grep for what CI will reject

- **40-character identifiers** — TruffleHog's Lob detector matches any 40-char alphanumeric token and reports it as a *verified* secret. Real test names hit this.
- **Fake-looking credentials in tests** — a deliberately fake connection string did *not* trip it; length-40 identifiers did. Sweep for the pattern, do not reason about it.

`scripts/sweep.sh` covers these.

## 11. Verify your own fix, in the container, after fixing

Fixing one finding can break another. After each change, re-run the checks the original finding was based on — build, run, curl, permissions — not just the unit tests.

Real case: `pip uninstall … || true` — the `|| true` silently defeated the hardening it was written to perform. Verified afterwards by asserting on a stock image (exit 1) and the hardened one (exit 0).
